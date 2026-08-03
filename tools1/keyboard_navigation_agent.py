"""
keyboard_navigation_agent.py — v2 (patched)

Changes from v1 (marked with [PATCH]):
  [PATCH-1] Adds Enter/Space activation test: after each Tab, presses Enter
            and captures whether page state changed. This is what an auditor
            does to verify 2.1.1 Keyboard operability.
  [PATCH-2] Detects "dead focus stops" — elements that receive focus but
            do not respond to keyboard activation.
  [PATCH-3] Adds Escape-key test on any dialog/modal found on the page.
  [PATCH-4] Adds explicit applicability signal: pages with no interactive
            elements return INAPPLICABLE.
  [PATCH-5] Adds wcag_211_status verdict logic.

Drop-in replacement. Class name KeyboardNavigationAgent, same interface.

Used by: Ade (2.1.1 Keyboard), Lakshmi (2.1.1 Keyboard).
"""

from playwright.sync_api import sync_playwright
import base64
import html as html_lib


class KeyboardNavigationAgent:
    """Analyzes HTML for keyboard navigation accessibility issues."""

    def execute(self, html: str) -> dict:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                page = context.new_page()
                self._load(page, html)

                # [PATCH-4] Applicability check
                interactive_count = page.evaluate("""() => {
                    return document.querySelectorAll(
                        'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"]), [role=button], [role=link]'
                    ).length;
                }""")

                if interactive_count == 0:
                    return {
                        "applicability": {
                            "applies": False,
                            "reason": "Page contains no interactive elements. WCAG 2.1.1 does not apply.",
                        },
                        "wcag_211_status": "INAPPLICABLE",
                        "interactive_elements_found": 0,
                        "tool_name": "KeyboardNavigationAgent",
                    }

                # Enumerate focusable elements (existing behavior)
                focusable = self._enumerate_focusable(page)

                # [PATCH-1,2] Walk the tab sequence with activation testing
                tab_walk = self._walk_tab_sequence_with_activation(page)

                # [PATCH-3] Check for modals and escape behavior
                modal_test = self._test_modal_escape(page)

                # Detect mouse-only interactives (pattern from v1)
                mouse_only = self._detect_mouse_only(page)

            finally:
                browser.close()

        # ==============================================================
        # [PATCH-5] Verdict for WCAG 2.1.1
        # ==============================================================
        dead_stops = [t for t in tab_walk if t.get("responds_to_activation") is False]
        keyboard_traps = [t for t in tab_walk if t.get("is_trap")]

        issues = []
        if mouse_only:
            issues.append({
                "type": "mouse_only_interactives",
                "count": len(mouse_only),
                "examples": mouse_only[:3],
            })
        if dead_stops:
            issues.append({
                "type": "dead_focus_stops",
                "count": len(dead_stops),
                "description": "Elements receive focus but do not respond to Enter/Space",
                "examples": dead_stops[:3],
            })
        if keyboard_traps:
            issues.append({
                "type": "keyboard_traps",
                "count": len(keyboard_traps),
                "examples": keyboard_traps[:2],
            })
        if modal_test.get("modal_present") and not modal_test.get("escape_closes"):
            issues.append({
                "type": "modal_no_escape",
                "description": "Modal dialog does not close on Escape key",
            })

        wcag_211_status = "PASS" if not issues else "FAIL"

        return {
            "applicability": {
                "applies": True,
                "elements_present": {"interactive": interactive_count},
            },
            "focusable_elements_found": len(focusable),
            "tab_sequence_walked": len(tab_walk),
            "activation_test_results": tab_walk,
            "dead_focus_stops": dead_stops,
            "keyboard_traps": keyboard_traps,
            "mouse_only_interactives": mouse_only,
            "modal_test": modal_test,
            "issues": issues,
            "wcag_211_status": wcag_211_status,
            "tool_name": "KeyboardNavigationAgent",
        }

    # ------------------------------------------------------------------ #
    #  Loading                                                             #
    # ------------------------------------------------------------------ #

    def _load(self, page, html_or_url: str):
        if html_or_url.strip().startswith("http"):
            page.goto(html_or_url, wait_until="networkidle", timeout=30_000)
        else:
            encoded = base64.b64encode(html_or_url.encode()).decode()
            page.goto(f"data:text/html;base64,{encoded}", wait_until="domcontentloaded")

    # ------------------------------------------------------------------ #
    #  Existing: enumerate focusable                                       #
    # ------------------------------------------------------------------ #

    def _enumerate_focusable(self, page) -> list:
        return page.evaluate("""() => {
            const results = [];
            document.querySelectorAll(
                'a[href], button, input:not([type=hidden]), select, textarea, [tabindex]:not([tabindex="-1"])'
            ).forEach(el => {
                if (el.disabled) return;
                const style = getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return;
                results.push({
                    tag: el.tagName,
                    type: el.type || '',
                    id: el.id || '',
                    tabindex: el.getAttribute('tabindex'),
                    text: (el.textContent || el.value || '').trim().slice(0, 50),
                });
            });
            return results;
        }""")

    # ------------------------------------------------------------------ #
    #  [PATCH-1,2] Walk tab sequence with activation testing               #
    # ------------------------------------------------------------------ #

    def _walk_tab_sequence_with_activation(self, page, max_stops: int = 30) -> list:
        """
        Tab through the page, and for each stop:
          - Record which element received focus
          - Press Enter and observe whether page state changed
          - Flag "dead" focus stops (focused but non-responsive)
        """
        # Focus body first
        page.evaluate("() => document.body.focus()")

        results = []
        seen_signatures = set()
        stops = 0

        while stops < max_stops:
            page.keyboard.press("Tab")

            current = page.evaluate("""() => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                const rect = el.getBoundingClientRect();
                return {
                    tag: el.tagName,
                    type: el.type || '',
                    id: el.id || '',
                    role: el.getAttribute('role') || '',
                    text: (el.textContent || el.value || '').trim().slice(0, 40),
                    href: el.getAttribute('href') || '',
                    visible: rect.width > 0 && rect.height > 0,
                    top: rect.top,
                    left: rect.left,
                };
            }""")

            if not current:
                # Tab did not move focus anywhere: end of sequence
                break

            # Signature to detect keyboard traps (same element focused twice in a row)
            signature = f"{current['tag']}#{current['id']}:{current['text']}"
            if signature in seen_signatures and len(results) > 0 and results[-1].get("signature") == signature:
                current["is_trap"] = True
                results.append({**current, "signature": signature})
                break
            seen_signatures.add(signature)

            # Capture state before pressing Enter
            state_before = page.evaluate("""() => ({
                url: location.href,
                dom_length: document.body.innerHTML.length,
                active_id: document.activeElement.id || document.activeElement.tagName,
            })""")

            # Press Enter (also try Space for buttons/checkboxes)
            key_to_press = "Space" if current.get("type") in ("checkbox", "radio", "button") else "Enter"
            try:
                page.keyboard.press(key_to_press)
                page.wait_for_timeout(150)
            except Exception:
                pass

            state_after = page.evaluate("""() => ({
                url: location.href,
                dom_length: document.body.innerHTML.length,
            })""")

            state_changed = (
                state_before["url"] != state_after["url"]
                or state_before["dom_length"] != state_after["dom_length"]
            )

            # Interactive-looking elements should respond; non-interactive shouldn't
            is_interactive_looking = (
                current["tag"] in ("A", "BUTTON", "INPUT", "SELECT", "TEXTAREA")
                or current.get("role") in ("button", "link", "checkbox", "radio")
            )
            responds = state_changed
            is_dead = is_interactive_looking and not responds and current["tag"] != "INPUT"

            results.append({
                "signature": signature,
                **current,
                "activation_key": key_to_press,
                "state_changed_on_activation": state_changed,
                "responds_to_activation": responds,
                "is_dead_focus_stop": is_dead,
            })
            stops += 1

            # If Enter navigated away, we can't continue on this page
            if state_before["url"] != state_after["url"]:
                break

        return results

    # ------------------------------------------------------------------ #
    #  [PATCH-3] Modal escape test                                         #
    # ------------------------------------------------------------------ #

    def _test_modal_escape(self, page) -> dict:
        modal_selector = "[role=dialog], [aria-modal=true], .modal.open, dialog[open]"
        modal_present = page.evaluate(
            f"() => !!document.querySelector('{modal_selector}')"
        )
        if not modal_present:
            return {"modal_present": False}

        # Focus into the modal
        page.evaluate(f"""() => {{
            const m = document.querySelector('{modal_selector}');
            if (m) m.focus();
        }}""")

        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        still_present = page.evaluate(f"""() => {{
            const m = document.querySelector('{modal_selector}');
            if (!m) return false;
            const style = getComputedStyle(m);
            return style.display !== 'none' && style.visibility !== 'hidden';
        }}""")

        return {
            "modal_present": True,
            "escape_closes": not still_present,
        }

    # ------------------------------------------------------------------ #
    #  Mouse-only interactive detection                                    #
    # ------------------------------------------------------------------ #

    def _detect_mouse_only(self, page) -> list:
        return page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('div, span, li, td').forEach(el => {
                const hasClick = !!el.onclick || el.hasAttribute('onclick');
                const hasKey = !!el.onkeydown || !!el.onkeyup || !!el.onkeypress;
                const tabindex = el.getAttribute('tabindex');
                const role = el.getAttribute('role');
                const isInteractiveRole = ['button', 'link', 'checkbox', 'radio', 'menuitem'].includes(role);
                if (hasClick && !hasKey && (tabindex === null || tabindex === '-1') && !isInteractiveRole) {
                    results.push({
                        tag: el.tagName,
                        text: el.textContent.trim().slice(0, 40),
                        classes: el.className || '',
                    });
                }
            });
            return results;
        }""")
