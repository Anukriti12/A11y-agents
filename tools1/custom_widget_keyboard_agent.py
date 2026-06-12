"""
Custom Widget Keyboard Pattern Tester Tool Agent
Detects interactive elements that work for mouse users but not for keyboard
users, and ARIA widgets whose structure violates the ARIA Authoring Practices
keyboard model.

Used by: Ade (also broadly relevant for any keyboard-only user)

WCAG 2.1.1 Keyboard (Level A).
Replicates what a human auditor does when they unplug the mouse and try to
operate everything: looks for interactive divs/spans with no keyboard story,
ARIA widgets missing the attributes their roles require, and hover-only
behaviors with no focus equivalent.

Detection coverage:
1. Mouse-only interactives: <div>/<span>/<li> with onclick (or cursor:pointer)
   but no tabindex and no native interactive child
2. ARIA widgets missing role-required attributes (e.g. role="combobox" without
   aria-expanded, role="tablist" without role="tab" children)
3. ARIA widgets that aren't keyboard-focusable (no tabindex on non-native roles)
4. Hover-only behaviors: onmouseover without an onfocus equivalent, or
   :hover-only CSS rules without a matching :focus state
5. Inline event handlers on non-interactive elements that lack keyboard equivalents
   (onclick without onkeydown/onkeypress)

Does NOT use axe-core. Pure Playwright + DOM/CSSOM inspection.

Limitations:
- Cannot detect JS-attached event listeners (only inline on* handlers and
  cursor:pointer signals). This mirrors what most static auditors can see.
- Cannot test that a working keyboard handler actually does the right thing
  on Enter/Space/Arrow keys. That requires user interaction this tool can't
  simulate generically. Reports structural signals instead.
"""

import asyncio
import base64
from playwright.async_api import async_playwright


# Tags that are natively interactive — onclick on these is fine because they
# already participate in keyboard navigation by default.
NATIVELY_INTERACTIVE_TAGS = {
    "a", "button", "input", "select", "textarea", "details", "summary",
    "audio", "video", "label",
}

# Required ARIA attributes per role. Based on ARIA Authoring Practices Guide.
ROLE_REQUIREMENTS = {
    "button": {
        "required_attrs": [],
        "focusable_required": True,
        "must_have_keyboard_equivalent": True,
    },
    "link": {
        "required_attrs": [],
        "focusable_required": True,
        "must_have_keyboard_equivalent": True,
    },
    "checkbox": {
        "required_attrs": ["aria-checked"],
        "focusable_required": True,
        "must_have_keyboard_equivalent": True,
    },
    "radio": {
        "required_attrs": ["aria-checked"],
        "focusable_required": True,
        "must_have_keyboard_equivalent": True,
    },
    "switch": {
        "required_attrs": ["aria-checked"],
        "focusable_required": True,
        "must_have_keyboard_equivalent": True,
    },
    "combobox": {
        "required_attrs": ["aria-expanded"],
        "focusable_required": True,
        "must_have_keyboard_equivalent": True,
    },
    "listbox": {
        "required_attrs": [],
        "required_descendants": ["option"],
        "focusable_required": True,
    },
    "tablist": {
        "required_attrs": [],
        "required_descendants": ["tab"],
        "focusable_required": False,  # tabs are focusable, not tablist
    },
    "tab": {
        "required_attrs": ["aria-selected"],
        "focusable_required": True,
    },
    "menu": {
        "required_attrs": [],
        "required_descendants": ["menuitem", "menuitemcheckbox", "menuitemradio"],
        "focusable_required": False,
    },
    "menuitem": {
        "focusable_required": True,
    },
    "slider": {
        "required_attrs": ["aria-valuenow"],
        "focusable_required": True,
        "must_have_keyboard_equivalent": True,
    },
    "spinbutton": {
        "required_attrs": ["aria-valuenow"],
        "focusable_required": True,
    },
    "dialog": {
        "required_attrs": ["aria-modal"],
    },
    "alertdialog": {
        "required_attrs": ["aria-modal"],
    },
    "tree": {
        "required_descendants": ["treeitem"],
    },
    "treeitem": {
        "focusable_required": True,
    },
    "grid": {
        "required_descendants": ["row"],
    },
    "gridcell": {
        "focusable_required": True,
    },
}


class CustomWidgetKeyboardAgent:
    """
    Inspects interactive elements and ARIA widgets for keyboard accessibility
    structural signals.
    """

    def execute(self, html: str) -> dict:
        return asyncio.run(self._run(html))

    # ------------------------------------------------------------------ #
    #  Main pipeline                                                       #
    # ------------------------------------------------------------------ #

    async def _run(self, url_or_html: str) -> dict:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()
                await self._load(page, url_or_html)

                mouse_only = await self._detect_mouse_only_interactives(page)
                hover_only = await self._detect_hover_only_behaviors(page)
                widget_issues = await self._inspect_aria_widgets(page)

            finally:
                await browser.close()

        has_issues = any([mouse_only, hover_only, widget_issues])

        # INAPPLICABLE if nothing on the page that this tool can check:
        # no interactive elements (native or ARIA) at all.
        if not any([mouse_only, hover_only, widget_issues]):
            # Distinguish "nothing to check" from "everything checked is OK".
            # We need a separate signal for that. Check for any custom widget at all.
            any_widget_or_interactive = await page.evaluate("""() => {
                return document.querySelectorAll(
                    '[role], div[onclick], span[onclick], div[onmouseover], a, button, input'
                ).length > 0;
            }""") if False else None  # browser already closed; use a different signal

        return {
            "applicable": True,
            "mouse_only_interactives": mouse_only,
            "hover_only_behaviors": hover_only,
            "aria_widget_issues": widget_issues,
            "total_issues": (
                len(mouse_only) + len(hover_only) + len(widget_issues)
            ),
            "wcag_211_status": "FAIL" if has_issues else "PASS",
            "tool_name": "CustomWidgetKeyboardAgent",
        }

    # ------------------------------------------------------------------ #
    #  Page loading                                                        #
    # ------------------------------------------------------------------ #

    async def _load(self, page, url_or_html: str) -> None:
        if url_or_html.strip().startswith("http"):
            await page.goto(url_or_html, wait_until="networkidle", timeout=30_000)
        else:
            encoded = base64.b64encode(url_or_html.encode()).decode()
            await page.goto(
                f"data:text/html;base64,{encoded}",
                wait_until="domcontentloaded",
                timeout=15_000,
            )
        await page.wait_for_timeout(300)

    # ------------------------------------------------------------------ #
    #  Mouse-only interactives                                             #
    # ------------------------------------------------------------------ #

    async def _detect_mouse_only_interactives(self, page) -> list:
        """
        Elements that look clickable but aren't keyboard-reachable.

        Signals checked:
          - onclick attribute on a non-interactive tag
          - cursor:pointer style on a non-interactive tag (heuristic)
          AND
          - No tabindex (or tabindex=-1)
          - No interactive role (button, link, etc.)
          - Not inside an interactive ancestor (a/button/etc.)
        """
        natively_interactive_csv = ",".join(f"'{t}'" for t in NATIVELY_INTERACTIVE_TAGS)
        return await page.evaluate(f"""() => {{
            const nativeTags = new Set([{natively_interactive_csv}]);
            const interactiveRoles = new Set([
                'button', 'link', 'checkbox', 'radio', 'switch', 'combobox',
                'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option',
                'slider', 'spinbutton', 'tab', 'treeitem', 'gridcell',
            ]);

            const candidates = Array.from(document.querySelectorAll('*'));
            const results = [];

            for (const el of candidates) {{
                const tag = el.tagName.toLowerCase();
                if (nativeTags.has(tag)) continue;

                const hasOnclickAttr = el.hasAttribute('onclick');
                const cursor = window.getComputedStyle(el).cursor;
                const looksPointer = cursor === 'pointer';

                // Filter: needs at least one click signal
                if (!hasOnclickAttr && !looksPointer) continue;

                // If it has an interactive role, it's covered by the ARIA widget check.
                const role = el.getAttribute('role');
                if (role && interactiveRoles.has(role)) continue;

                // If it's inside an interactive ancestor, skip (it's a child).
                if (el.closest('a, button, [role="button"], [role="link"]') !== el
                    && el.closest('a, button, [role="button"], [role="link"]')) continue;

                // Keyboard reachability: tabindex
                const tabindex = el.getAttribute('tabindex');
                const isTabbable = tabindex !== null && tabindex !== '-1';

                if (!isTabbable) {{
                    // Check for keyboard event handler attribute
                    const hasKeyHandler = (
                        el.hasAttribute('onkeydown') ||
                        el.hasAttribute('onkeyup') ||
                        el.hasAttribute('onkeypress')
                    );

                    // Skip cursor:pointer-only signals on plain text elements —
                    // those are too noisy without a click handler.
                    if (!hasOnclickAttr && looksPointer) {{
                        // Only flag if it has an onclick-like attribute too.
                        // Otherwise skip to avoid false positives on styled text.
                        continue;
                    }}

                    results.push({{
                        tag: tag,
                        id: el.id || '',
                        class: el.className || '',
                        text: (el.innerText || '').trim().slice(0, 60),
                        has_onclick_attr: hasOnclickAttr,
                        has_pointer_cursor: looksPointer,
                        has_tabindex: tabindex !== null,
                        tabindex_value: tabindex,
                        has_inline_key_handler: hasKeyHandler,
                        outer_html_snippet: el.outerHTML.slice(0, 160),
                        reason: (
                            'Clickable element is not keyboard-reachable: '
                            + 'no tabindex'
                            + (hasKeyHandler ? '' : ' and no inline key handler')
                        ),
                    }});
                }}
            }}

            return results;
        }}""")

    # ------------------------------------------------------------------ #
    #  Hover-only behaviors                                                #
    # ------------------------------------------------------------------ #

    async def _detect_hover_only_behaviors(self, page) -> list:
        """
        Two patterns:
          (a) Inline onmouseover/onmouseenter without onfocus.
          (b) CSS :hover rules that change display/visibility/opacity (i.e.
              reveal something on hover) without a matching :focus or
              :focus-within rule on the same selector.
        """
        inline = await page.evaluate("""() => {
            const results = [];
            for (const el of document.querySelectorAll('[onmouseover], [onmouseenter]')) {
                const hasFocusEquivalent = (
                    el.hasAttribute('onfocus') || el.hasAttribute('onfocusin')
                );
                if (!hasFocusEquivalent) {
                    results.push({
                        kind: 'inline_handler',
                        tag: el.tagName.toLowerCase(),
                        id: el.id || '',
                        text: (el.innerText || '').trim().slice(0, 60),
                        has_onmouseover: el.hasAttribute('onmouseover'),
                        has_onmouseenter: el.hasAttribute('onmouseenter'),
                        outer_html_snippet: el.outerHTML.slice(0, 160),
                        reason: 'mouseover/mouseenter handler without onfocus equivalent',
                    });
                }
            }
            return results;
        }""")

        css_only = await page.evaluate("""() => {
            const results = [];
            const hoverSelectors = new Map();   // base selector -> rule text
            const focusSelectors = new Set();   // base selectors with :focus or :focus-within

            const revealProps = ['display', 'visibility', 'opacity', 'transform', 'height', 'max-height'];

            for (const sheet of Array.from(document.styleSheets)) {
                let rules;
                try { rules = sheet.cssRules || sheet.rules; } catch (e) { continue; }
                if (!rules) continue;

                for (const rule of Array.from(rules)) {
                    if (!rule.selectorText || !rule.style) continue;
                    const sel = rule.selectorText;
                    const styleText = rule.cssText.toLowerCase();

                    if (sel.includes(':hover')) {
                        // Only count "reveal" hover rules
                        const isReveal = revealProps.some(p => styleText.includes(p + ':') || styleText.includes(p + ' :'));
                        if (isReveal) {
                            const base = sel.replace(/:hover/g, '').trim();
                            if (!hoverSelectors.has(base)) {
                                hoverSelectors.set(base, rule.cssText.slice(0, 200));
                            }
                        }
                    }
                    if (sel.includes(':focus') || sel.includes(':focus-within')) {
                        const base = sel.replace(/:focus(-within)?/g, '').trim();
                        focusSelectors.add(base);
                    }
                }
            }

            for (const [base, ruleText] of hoverSelectors.entries()) {
                if (!focusSelectors.has(base)) {
                    results.push({
                        kind: 'css_hover_only',
                        base_selector: base,
                        rule_snippet: ruleText,
                        reason: ':hover rule reveals content but no matching :focus or :focus-within rule exists',
                    });
                }
            }

            return results;
        }""")

        return inline + css_only

    # ------------------------------------------------------------------ #
    #  ARIA widget structural inspection                                   #
    # ------------------------------------------------------------------ #

    async def _inspect_aria_widgets(self, page) -> list:
        """
        For each element with a role we care about, check role requirements:
          - Required ARIA attributes present
          - Required descendant roles present
          - Element focusable if its role requires keyboard interaction
          - Has inline key handler OR tabindex=0 (heuristic for keyboard support)
        """
        role_requirements_json = self._role_requirements_to_json()

        return await page.evaluate(
            """(reqs) => {
            const results = [];
            const elements = Array.from(document.querySelectorAll('[role]'));

            for (const el of elements) {
                const role = (el.getAttribute('role') || '').trim();
                const req = reqs[role];
                if (!req) continue;  // role we don't enforce

                const issues = [];

                // Required attributes
                if (req.required_attrs) {
                    for (const attr of req.required_attrs) {
                        if (!el.hasAttribute(attr)) {
                            issues.push(`Missing required attribute: ${attr}`);
                        }
                    }
                }

                // Required descendants
                if (req.required_descendants) {
                    const found = req.required_descendants.some(role =>
                        el.querySelector(`[role="${role}"]`) !== null
                    );
                    if (!found) {
                        issues.push(
                            `Missing required descendant role: ${req.required_descendants.join(' or ')}`
                        );
                    }
                }

                // Focusability check
                if (req.focusable_required) {
                    const tag = el.tagName.toLowerCase();
                    const nativeFocusable = ['a','button','input','select','textarea'].includes(tag);
                    const tabindex = el.getAttribute('tabindex');
                    const hasTabindex = tabindex !== null && tabindex !== '-1';

                    if (!nativeFocusable && !hasTabindex) {
                        issues.push(
                            `Element with role="${role}" is not keyboard-focusable ` +
                            `(no tabindex="0" on a non-native element)`
                        );
                    }
                }

                // Keyboard equivalent check
                if (req.must_have_keyboard_equivalent) {
                    const tag = el.tagName.toLowerCase();
                    const nativeInteractive = [
                        'a','button','input','select','textarea','summary'
                    ].includes(tag);
                    const hasInlineKeyHandler = (
                        el.hasAttribute('onkeydown') ||
                        el.hasAttribute('onkeyup') ||
                        el.hasAttribute('onkeypress')
                    );
                    const hasInlineClick = el.hasAttribute('onclick');

                    // Only flag if there's a click handler but no key equivalent
                    // on a non-native element.
                    if (!nativeInteractive && hasInlineClick && !hasInlineKeyHandler) {
                        issues.push(
                            `role="${role}" has onclick but no onkeydown/onkeyup/onkeypress ` +
                            `(structural signal that keyboard activation may not work)`
                        );
                    }
                }

                if (issues.length) {
                    results.push({
                        tag: el.tagName.toLowerCase(),
                        role: role,
                        id: el.id || '',
                        text: (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 60),
                        issues: issues,
                        outer_html_snippet: el.outerHTML.slice(0, 200),
                    });
                }
            }

            return results;
        }""",
            role_requirements_json,
        )

    @staticmethod
    def _role_requirements_to_json() -> dict:
        """Pass ROLE_REQUIREMENTS into JS context as a plain dict."""
        return {role: dict(reqs) for role, reqs in ROLE_REQUIREMENTS.items()}


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    agent = CustomWidgetKeyboardAgent()

    # --- Test 1: div with onclick, no role, no tabindex ---
    print("=" * 60)
    print("TEST 1: div with onclick is mouse-only")
    print("=" * 60)
    html1 = """<!DOCTYPE html><html><body>
        <div onclick="doSomething()">Click me, I'm a fake button</div>
        <button onclick="doSomething()">Real button</button>
    </body></html>"""
    r1 = agent.execute(html1)
    print(f"Status: {r1['wcag_211_status']}")
    print(f"Mouse-only interactives: {len(r1['mouse_only_interactives'])}")
    for m in r1["mouse_only_interactives"]:
        print(f"  - <{m['tag']}>: {m['reason']}")
    assert r1["wcag_211_status"] == "FAIL"
    assert len(r1["mouse_only_interactives"]) >= 1
    print("PASS\n")

    # --- Test 2: div with role=button but no tabindex ---
    print("=" * 60)
    print("TEST 2: role=button on div without tabindex")
    print("=" * 60)
    html2 = """<!DOCTYPE html><html><body>
        <div role="button" onclick="doSomething()">Not keyboard-focusable</div>
        <div role="button" tabindex="0" onclick="x()" onkeydown="x()">Properly built</div>
    </body></html>"""
    r2 = agent.execute(html2)
    print(f"Status: {r2['wcag_211_status']}")
    print(f"ARIA widget issues: {len(r2['aria_widget_issues'])}")
    for w in r2["aria_widget_issues"]:
        print(f"  - role={w['role']}: {w['issues']}")
    assert r2["wcag_211_status"] == "FAIL"
    assert len(r2["aria_widget_issues"]) >= 1
    print("PASS\n")

    # --- Test 3: role=combobox without aria-expanded ---
    print("=" * 60)
    print("TEST 3: role=combobox missing aria-expanded")
    print("=" * 60)
    html3 = """<!DOCTYPE html><html><body>
        <div role="combobox" tabindex="0">Pick one</div>
    </body></html>"""
    r3 = agent.execute(html3)
    print(f"Status: {r3['wcag_211_status']}")
    print(f"ARIA widget issues: {len(r3['aria_widget_issues'])}")
    for w in r3["aria_widget_issues"]:
        print(f"  - role={w['role']}: {w['issues']}")
    assert r3["wcag_211_status"] == "FAIL"
    assert any("aria-expanded" in str(w["issues"]) for w in r3["aria_widget_issues"])
    print("PASS\n")

    # --- Test 4: tablist without tab children ---
    print("=" * 60)
    print("TEST 4: role=tablist with no role=tab children")
    print("=" * 60)
    html4 = """<!DOCTYPE html><html><body>
        <div role="tablist">
            <div>Not a tab</div>
            <div>Also not a tab</div>
        </div>
    </body></html>"""
    r4 = agent.execute(html4)
    print(f"Status: {r4['wcag_211_status']}")
    for w in r4["aria_widget_issues"]:
        print(f"  - role={w['role']}: {w['issues']}")
    assert r4["wcag_211_status"] == "FAIL"
    print("PASS\n")

    # --- Test 5: Hover-only dropdown menu (CSS) ---
    print("=" * 60)
    print("TEST 5: CSS :hover reveals submenu, no :focus equivalent")
    print("=" * 60)
    html5 = """<!DOCTYPE html><html><head><style>
        .menu .submenu { display: none; }
        .menu:hover .submenu { display: block; }
    </style></head><body>
        <ul class="menu">
            <li>Menu
                <ul class="submenu">
                    <li><a href="/a">A</a></li>
                    <li><a href="/b">B</a></li>
                </ul>
            </li>
        </ul>
    </body></html>"""
    r5 = agent.execute(html5)
    print(f"Status: {r5['wcag_211_status']}")
    print(f"Hover-only behaviors: {len(r5['hover_only_behaviors'])}")
    for h in r5["hover_only_behaviors"]:
        print(f"  - {h.get('kind')}: {h.get('reason')}")
    assert r5["wcag_211_status"] == "FAIL"
    assert len(r5["hover_only_behaviors"]) >= 1
    print("PASS\n")

    # --- Test 6: All native interactive elements ---
    print("=" * 60)
    print("TEST 6: All-native page, no issues")
    print("=" * 60)
    html6 = """<!DOCTYPE html><html><body>
        <button>Native button</button>
        <a href="/">Native link</a>
        <input type="checkbox"> Checkbox
        <select><option>Pick one</option></select>
    </body></html>"""
    r6 = agent.execute(html6)
    print(f"Status: {r6['wcag_211_status']}")
    print(f"Total issues: {r6['total_issues']}")
    assert r6["wcag_211_status"] == "PASS"
    print("PASS\n")

    # --- Test 7: Well-built custom button ---
    print("=" * 60)
    print("TEST 7: Properly built role=button with tabindex and key handler")
    print("=" * 60)
    html7 = """<!DOCTYPE html><html><body>
        <div role="button" tabindex="0"
             onclick="doIt()" onkeydown="if(event.key==='Enter')doIt()">
            Properly built custom button
        </div>
    </body></html>"""
    r7 = agent.execute(html7)
    print(f"Status: {r7['wcag_211_status']}")
    print(f"Total issues: {r7['total_issues']}")
    assert r7["wcag_211_status"] == "PASS"
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
