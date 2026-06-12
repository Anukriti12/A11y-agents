"""
Focus Order Validator Tool Agent
Walks the page's tab sequence and validates that focus moves in a meaningful,
operable order that preserves visual relationships.

Used by: Ade (also relevant for Lakshmi)

WCAG 2.4.3 Focus Order (Level A).
Replicates what a human auditor does: tab through the page from the start,
record what gets focus and where it sits visually, and flag cases where the
order would confuse a keyboard or screen-reader user.

Detection coverage:
1. tabindex > 0 anti-pattern (forces an unnatural order)
2. Tab order that diverges from DOM order
3. Visual order violations (focus jumps backward on the same row,
   or jumps upward without a clear new-column transition)
4. Focusable elements in the DOM that Tab never reaches
5. Modal dialogs missing essential focus-management attributes

Does NOT use axe-core. Pure Playwright + computed-style inspection.
"""

import asyncio
import base64
from playwright.async_api import async_playwright


# Tolerance for treating two elements as being on the same visual row.
ROW_TOLERANCE_PX = 20

# Tolerance for ignoring tiny leftward shifts (sub-pixel rounding, padding).
SAME_ROW_LEFTWARD_THRESHOLD_PX = 5

# Hard cap on tab steps to prevent infinite loops on broken pages.
MAX_TAB_STEPS = 200


class FocusOrderValidatorAgent:
    """
    Walks the tab sequence with Playwright keyboard, captures position of
    each focused element, and compares the sequence against DOM order and
    visual reading order.
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

                focusables = await self._catalog_focusables(page)

                if not focusables:
                    return self._inapplicable_result("No focusable elements on page")

                tab_sequence = await self._walk_tab_sequence(page, len(focusables))

                positive_tabindex = [
                    {
                        "tag": f["tag"],
                        "id": f["id"],
                        "text": f["text"],
                        "explicit_tabindex": f["explicit_tabindex"],
                    }
                    for f in focusables
                    if f.get("explicit_tabindex") is not None
                    and str(f["explicit_tabindex"]).isdigit()
                    and int(f["explicit_tabindex"]) > 0
                ]

                dom_mismatches = self._compare_to_dom_order(tab_sequence, focusables)
                visual_mismatches = self._compare_to_visual_order(tab_sequence)
                unreachable = self._find_unreachable(tab_sequence, focusables)
                modal_issues = await self._check_modals(page)

            finally:
                await browser.close()

        has_issues = any([
            positive_tabindex,
            dom_mismatches,
            visual_mismatches,
            unreachable,
            modal_issues,
        ])

        return {
            "applicable": True,
            "applicability_reason": f"{len(focusables)} focusable element(s) found",
            "focusables_in_dom": len(focusables),
            "tab_sequence_length": len(tab_sequence),
            "tab_sequence": tab_sequence,
            "positive_tabindex_elements": positive_tabindex,
            "dom_order_mismatches": dom_mismatches,
            "visual_order_mismatches": visual_mismatches,
            "unreachable_elements": unreachable,
            "modal_issues": modal_issues,
            "wcag_243_status": "FAIL" if has_issues else "PASS",
            "tool_name": "FocusOrderValidatorAgent",
        }

    def _inapplicable_result(self, reason: str) -> dict:
        return {
            "applicable": False,
            "applicability_reason": reason,
            "focusables_in_dom": 0,
            "tab_sequence_length": 0,
            "tab_sequence": [],
            "positive_tabindex_elements": [],
            "dom_order_mismatches": [],
            "visual_order_mismatches": [],
            "unreachable_elements": [],
            "modal_issues": [],
            "wcag_243_status": "INAPPLICABLE",
            "tool_name": "FocusOrderValidatorAgent",
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
        await page.wait_for_timeout(400)

    # ------------------------------------------------------------------ #
    #  Catalog all focusable elements                                      #
    # ------------------------------------------------------------------ #

    async def _catalog_focusables(self, page) -> list:
        return await page.evaluate("""() => {
            const selector = [
                'a[href]',
                'button:not([disabled])',
                'input:not([disabled]):not([type="hidden"])',
                'textarea:not([disabled])',
                'select:not([disabled])',
                '[tabindex]:not([tabindex="-1"])',
                '[contenteditable="true"]',
                'details summary',
                'audio[controls]',
                'video[controls]',
            ].join(', ');

            const elements = Array.from(document.querySelectorAll(selector));
            return elements
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && parseFloat(style.opacity) > 0;
                })
                .map((el, idx) => {
                    const rect = el.getBoundingClientRect();
                    const text = (
                        el.innerText ||
                        el.value ||
                        el.getAttribute('aria-label') ||
                        el.getAttribute('alt') ||
                        ''
                    ).trim().slice(0, 60);
                    return {
                        dom_index: idx,
                        tag: el.tagName.toLowerCase(),
                        id: el.id || '',
                        text: text,
                        tabindex: el.tabIndex,
                        explicit_tabindex: el.getAttribute('tabindex'),
                        x: Math.round(rect.left + window.scrollX),
                        y: Math.round(rect.top + window.scrollY),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                    };
                });
        }""")

    # ------------------------------------------------------------------ #
    #  Walk tab sequence                                                   #
    # ------------------------------------------------------------------ #

    async def _walk_tab_sequence(self, page, expected_count: int) -> list:
        """
        Press Tab repeatedly, capture each focused element with its position.
        Stop when focus cycles back or when we exceed a safety cap.
        """
        await page.evaluate(
            "if (document.activeElement && document.activeElement !== document.body) "
            "document.activeElement.blur();"
        )
        await page.evaluate("window.scrollTo(0, 0);")
        await page.wait_for_timeout(80)

        tab_sequence = []
        seen_signatures = set()
        max_steps = min(expected_count * 2 + 5, MAX_TAB_STEPS)

        for step in range(max_steps):
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(30)

            active = await page.evaluate("""() => {
                const el = document.activeElement;
                if (!el || el === document.body || el === document.documentElement) return null;
                const rect = el.getBoundingClientRect();
                const text = (
                    el.innerText ||
                    el.value ||
                    el.getAttribute('aria-label') ||
                    el.getAttribute('alt') ||
                    ''
                ).trim().slice(0, 60);
                return {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    text: text,
                    tabindex: el.tabIndex,
                    explicit_tabindex: el.getAttribute('tabindex'),
                    x: Math.round(rect.left + window.scrollX),
                    y: Math.round(rect.top + window.scrollY),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                };
            }""")

            if not active:
                break

            sig = self._element_signature(active)
            if sig in seen_signatures:
                # Focus cycled back to an already-visited element.
                break
            seen_signatures.add(sig)

            tab_sequence.append({**active, "tab_position": step})

        return tab_sequence

    @staticmethod
    def _element_signature(el: dict) -> str:
        """Stable identifier for matching tab-sequence entries to DOM entries."""
        return f"{el['tag']}|{el.get('id', '')}|{el.get('text', '')}|{el['x']},{el['y']}"

    # ------------------------------------------------------------------ #
    #  DOM order comparison                                                #
    # ------------------------------------------------------------------ #

    def _compare_to_dom_order(self, tab_sequence: list, focusables: list) -> list:
        """
        For each step in the tab sequence, look up its DOM index.
        Flag when the tab order regresses to an earlier DOM position.
        This is the structural signature of positive tabindex usage.
        """
        dom_lookup = {self._element_signature(f): f["dom_index"] for f in focusables}
        mismatches = []
        last_dom_idx = -1

        for tab_idx, item in enumerate(tab_sequence):
            dom_idx = dom_lookup.get(self._element_signature(item))
            if dom_idx is None:
                continue

            if dom_idx < last_dom_idx:
                mismatches.append({
                    "tab_position": tab_idx,
                    "dom_index": dom_idx,
                    "previous_max_dom_index": last_dom_idx,
                    "element_tag": item["tag"],
                    "element_text": item["text"][:40],
                    "message": (
                        f"Tab step {tab_idx} reached DOM index {dom_idx} "
                        f"after already passing DOM index {last_dom_idx}"
                    ),
                })

            last_dom_idx = max(last_dom_idx, dom_idx)

        return mismatches

    # ------------------------------------------------------------------ #
    #  Visual order comparison                                             #
    # ------------------------------------------------------------------ #

    def _compare_to_visual_order(self, tab_sequence: list) -> list:
        """
        Visual reading order (LTR languages): top-to-bottom, left-to-right.
        Be conservative to avoid flagging legitimate multi-column layouts.

        Flag two patterns:
          (a) Same-row leftward jump: y values within ROW_TOLERANCE_PX
              and x decreased by more than SAME_ROW_LEFTWARD_THRESHOLD_PX.
          (b) Upward jump that is NOT compensated by a clear column shift
              right: y decreased by more than ROW_TOLERANCE_PX AND
              x did not increase substantially.
        """
        mismatches = []

        for i in range(1, len(tab_sequence)):
            prev = tab_sequence[i - 1]
            curr = tab_sequence[i]

            dy = curr["y"] - prev["y"]
            dx = curr["x"] - prev["x"]
            same_row = abs(dy) < ROW_TOLERANCE_PX

            if same_row and dx < -SAME_ROW_LEFTWARD_THRESHOLD_PX:
                mismatches.append({
                    "type": "same_row_leftward",
                    "tab_position": i,
                    "previous_position": i - 1,
                    "previous_text": prev["text"][:40],
                    "current_text": curr["text"][:40],
                    "previous_xy": [prev["x"], prev["y"]],
                    "current_xy": [curr["x"], curr["y"]],
                    "message": (
                        f"Focus moved leftward on the same row from "
                        f"({prev['x']},{prev['y']}) to ({curr['x']},{curr['y']})"
                    ),
                })
            elif dy < -ROW_TOLERANCE_PX and dx < prev["width"]:
                # Upward jump that isn't a "new column to the right" pattern.
                mismatches.append({
                    "type": "upward_jump",
                    "tab_position": i,
                    "previous_position": i - 1,
                    "previous_text": prev["text"][:40],
                    "current_text": curr["text"][:40],
                    "previous_xy": [prev["x"], prev["y"]],
                    "current_xy": [curr["x"], curr["y"]],
                    "message": (
                        f"Focus jumped upward from y={prev['y']} to y={curr['y']} "
                        f"without a clear new-column transition"
                    ),
                })

        return mismatches

    # ------------------------------------------------------------------ #
    #  Unreachable focusables                                              #
    # ------------------------------------------------------------------ #

    def _find_unreachable(self, tab_sequence: list, focusables: list) -> list:
        reached = {self._element_signature(item) for item in tab_sequence}
        unreachable = []
        for f in focusables:
            if self._element_signature(f) not in reached:
                unreachable.append({
                    "dom_index": f["dom_index"],
                    "tag": f["tag"],
                    "id": f["id"],
                    "text": f["text"][:40],
                    "explicit_tabindex": f["explicit_tabindex"],
                })
        return unreachable

    # ------------------------------------------------------------------ #
    #  Modal focus management                                              #
    # ------------------------------------------------------------------ #

    async def _check_modals(self, page) -> list:
        """
        For any open dialog on the page, check that essential focus-management
        signals are present. This is a structural check; a full focus-trap
        test would need user interaction beyond this tool's scope.
        """
        issues = []
        modals = await page.query_selector_all('dialog, [role="dialog"], [role="alertdialog"]')

        for modal in modals:
            is_open = await modal.evaluate("""el => {
                if (el.tagName === 'DIALOG') return el.open;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0 && rect.height > 0;
            }""")

            if not is_open:
                continue

            aria_modal = await modal.get_attribute("aria-modal")
            has_label = await modal.evaluate("""el => {
                return !!(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby'));
            }""")

            missing = []
            if aria_modal != "true":
                missing.append('aria-modal="true"')
            if not has_label:
                missing.append("accessible name (aria-label or aria-labelledby)")

            if missing:
                modal_id = await modal.get_attribute("id") or ""
                role = await modal.get_attribute("role") or "dialog"
                issues.append({
                    "modal_id": modal_id,
                    "role": role,
                    "missing_attributes": missing,
                })

        return issues


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    agent = FocusOrderValidatorAgent()

    # --- Test 1: Natural order, no issues ---
    print("=" * 60)
    print("TEST 1: Natural tab order matches DOM and visual order")
    print("=" * 60)
    html1 = """<!DOCTYPE html><html><body>
        <a href="/home">Home</a>
        <a href="/about">About</a>
        <button>Sign up</button>
        <input type="text" placeholder="Search">
    </body></html>"""
    r1 = agent.execute(html1)
    print(f"Status: {r1['wcag_243_status']}")
    print(f"Tab sequence length: {r1['tab_sequence_length']}")
    print(f"Positive tabindex: {len(r1['positive_tabindex_elements'])}")
    print(f"DOM mismatches: {len(r1['dom_order_mismatches'])}")
    print(f"Visual mismatches: {len(r1['visual_order_mismatches'])}")
    assert r1["wcag_243_status"] == "PASS", f"Expected PASS, got {r1['wcag_243_status']}"
    print("PASS\n")

    # --- Test 2: Positive tabindex anti-pattern ---
    print("=" * 60)
    print("TEST 2: Positive tabindex values force unnatural order")
    print("=" * 60)
    html2 = """<!DOCTYPE html><html><body>
        <button tabindex="3">Third in tab order</button>
        <button tabindex="1">First in tab order</button>
        <button tabindex="2">Second in tab order</button>
    </body></html>"""
    r2 = agent.execute(html2)
    print(f"Status: {r2['wcag_243_status']}")
    print(f"Positive tabindex elements: {len(r2['positive_tabindex_elements'])}")
    for el in r2["positive_tabindex_elements"]:
        print(f"  - {el['tag']} tabindex={el['explicit_tabindex']}: '{el['text']}'")
    assert r2["wcag_243_status"] == "FAIL"
    assert len(r2["positive_tabindex_elements"]) == 3
    print("PASS\n")

    # --- Test 3: Visually shuffled via CSS order (flex) ---
    print("=" * 60)
    print("TEST 3: CSS flex order shuffles visual position vs DOM order")
    print("=" * 60)
    html3 = """<!DOCTYPE html><html><head><style>
        .container { display: flex; }
        .first { order: 3; }
        .second { order: 1; }
        .third { order: 2; }
    </style></head><body>
        <div class="container">
            <button class="first">Looks third, in DOM first</button>
            <button class="second">Looks first, in DOM second</button>
            <button class="third">Looks second, in DOM third</button>
        </div>
    </body></html>"""
    r3 = agent.execute(html3)
    print(f"Status: {r3['wcag_243_status']}")
    print(f"Visual mismatches: {len(r3['visual_order_mismatches'])}")
    for m in r3["visual_order_mismatches"]:
        print(f"  - {m['type']}: {m['message']}")
    assert r3["wcag_243_status"] == "FAIL"
    assert len(r3["visual_order_mismatches"]) >= 1
    print("PASS\n")

    # --- Test 4: Empty page, no focusables ---
    print("=" * 60)
    print("TEST 4: Page with no interactive elements")
    print("=" * 60)
    html4 = """<!DOCTYPE html><html><body>
        <h1>Static page</h1>
        <p>No focusable elements here.</p>
    </body></html>"""
    r4 = agent.execute(html4)
    print(f"Status: {r4['wcag_243_status']}")
    assert r4["wcag_243_status"] == "INAPPLICABLE"
    print("PASS\n")

    # --- Test 5: Modal missing aria-modal and label ---
    print("=" * 60)
    print("TEST 5: Open dialog missing aria-modal and accessible name")
    print("=" * 60)
    html5 = """<!DOCTYPE html><html><body>
        <button>Open background button</button>
        <div role="dialog" style="display:block;position:fixed;top:50px;left:50px;width:200px;height:200px;background:white;border:1px solid black">
            <p>Dialog with no aria-modal or label</p>
            <button>Close</button>
        </div>
    </body></html>"""
    r5 = agent.execute(html5)
    print(f"Status: {r5['wcag_243_status']}")
    print(f"Modal issues: {len(r5['modal_issues'])}")
    for issue in r5["modal_issues"]:
        print(f"  - role={issue['role']}: missing {issue['missing_attributes']}")
    assert r5["wcag_243_status"] == "FAIL"
    assert len(r5["modal_issues"]) >= 1
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
