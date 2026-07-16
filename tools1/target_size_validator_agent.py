"""
Target Size Validator Tool Agent
Measures interactive elements and verifies they meet WCAG target-size
requirements, applying the spec's exceptions for inline text, user-agent
controls, and (at AA) spacing.

Used by: Ade (level AAA, 2.5.5, 44x44px), also relevant for Elias.

Two thresholds supported via the `level` parameter:

  Level AAA  (WCAG 2.5.5 Target Size — Enhanced)
    44x44 CSS px minimum.
    Exceptions:
      - Inline: target is in a sentence or block of text
      - User agent: size is determined by the user agent (native checkbox,
        radio, select with no author-overridden dimensions)
      - Essential: can't be detected generically, skipped

  Level AA   (WCAG 2.5.8 Target Size — Minimum, WCAG 2.2)
    24x24 CSS px minimum.
    Same exceptions as 2.5.5 PLUS a spacing exception: an undersized
    target passes if a 24-diameter circle centered on it does not
    intersect any other target's bounding box.

Replicates what a human auditor with a measuring tool does: measure each
interactive element, ignore the cases the spec excludes, flag the rest.

Does NOT use axe-core. Pure Playwright DOM inspection.
"""

import asyncio
import base64
from playwright.async_api import async_playwright


THRESHOLDS = {
    "AAA": {"min_px": 44, "sc": "2.5.5", "has_spacing_exception": False},
    "AA":  {"min_px": 24, "sc": "2.5.8", "has_spacing_exception": True},
}

# Maximum elements reported in detail
MAX_REPORTED = 200


class TargetSizeValidatorAgent:
    """
    Measures all interactive elements and classifies each as PASS, FAIL, or
    one of the EXEMPT categories.
    """

    def __init__(self, level: str = "AAA"):
        if level not in THRESHOLDS:
            raise ValueError(f"level must be 'AA' or 'AAA', got '{level}'")
        self.level = level

    def execute(self, html: str) -> dict:
        return asyncio.run(self._run(html))

    # ------------------------------------------------------------------ #
    #  Main pipeline                                                       #
    # ------------------------------------------------------------------ #

    async def _run(self, url_or_html: str) -> dict:
        threshold = THRESHOLDS[self.level]
        min_px = threshold["min_px"]
        sc = threshold["sc"]
        has_spacing = threshold["has_spacing_exception"]

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()
                await self._load(page, url_or_html)

                # Collect every interactive element with its measurements
                targets = await self._collect_targets(page, min_px)
            finally:
                await browser.close()

        # Apply spacing exception (AA only) after collection,
        # since we need pairwise comparisons across all targets.
        if has_spacing:
            self._apply_spacing_exception(targets, radius_px=min_px)

        passing = [t for t in targets if t["status"] == "PASS"]
        violations = [t for t in targets if t["status"] == "FAIL"]
        exempt_inline = [t for t in targets if t["status"] == "EXEMPT_INLINE"]
        exempt_ua = [t for t in targets if t["status"] == "EXEMPT_UA_CONTROL"]
        exempt_spacing = [t for t in targets if t["status"] == "EXEMPT_SPACING"]

        if not targets:
            wcag_status = "INAPPLICABLE"
        elif violations:
            wcag_status = "FAIL"
        else:
            wcag_status = "PASS"

        sc_label = f"wcag_{sc.replace('.', '')}_status"

        return {
            "level": self.level,
            "wcag_sc": sc,
            "threshold_px": min_px,
            "spacing_exception_applied": has_spacing,
            "targets_analyzed": len(targets),
            "passing_count": len(passing),
            "violation_count": len(violations),
            "exempt_inline_count": len(exempt_inline),
            "exempt_ua_control_count": len(exempt_ua),
            "exempt_spacing_count": len(exempt_spacing),
            "violations": violations[:MAX_REPORTED],
            "exempt_inline_samples": exempt_inline[:20],
            "exempt_ua_samples": exempt_ua[:20],
            "exempt_spacing_samples": exempt_spacing[:20],
            sc_label: wcag_status,
            # Backward-compat keys for existing study harness
            "small_targets": violations,
            "small_targets_count": len(violations),
            "issue_found": len(violations) > 0,
            "tool_name": "TargetSizeValidatorAgent",
        }

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
    #  Target collection + initial classification                          #
    # ------------------------------------------------------------------ #

    async def _collect_targets(self, page, min_px: int) -> list:
        """
        Find every interactive element. For each, measure its bounding rect
        and classify as PASS, FAIL, EXEMPT_INLINE, or EXEMPT_UA_CONTROL.
        Spacing exception is applied later (since it needs pairwise info).
        """
        return await page.evaluate(
            """({minPx}) => {
            const selector = [
                'a[href]',
                'button',
                'input:not([type="hidden"])',
                'select',
                'textarea',
                'summary',
                '[role="button"]',
                '[role="link"]',
                '[role="checkbox"]',
                '[role="radio"]',
                '[role="menuitem"]',
                '[role="switch"]',
                '[role="tab"]',
                '[tabindex]:not([tabindex="-1"])',
            ].join(', ');

            const results = [];
            const elements = Array.from(document.querySelectorAll(selector));

            // Helper: is this element a native user-agent-sized control?
            function isUserAgentControl(el) {
                const tag = el.tagName.toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();

                // Native checkbox, radio: browser sizes them small by convention
                if (tag === 'input' && (type === 'checkbox' || type === 'radio')) {
                    // Author has overridden size only if there's explicit dimension styling
                    const inlineStyle = el.getAttribute('style') || '';
                    if (/width|height/i.test(inlineStyle)) return false;
                    return true;
                }

                // Native single-select dropdown (not multi-select which has its own sizing)
                if (tag === 'select' && !el.multiple) {
                    const inlineStyle = el.getAttribute('style') || '';
                    if (/width|height/i.test(inlineStyle)) return false;
                    return true;
                }

                return false;
            }

            // Helper: is this an inline target inside running text?
            function isInlineInRunningText(el) {
                // Only <a> and inline buttons typically claim this exception
                const tag = el.tagName.toLowerCase();
                if (tag !== 'a' && el.getAttribute('role') !== 'link') return false;

                // Element must have display:inline (not inline-block, not block)
                const display = window.getComputedStyle(el).display;
                if (display !== 'inline') return false;

                // Parent must be a typical text container with text content beyond
                // just this anchor
                const parent = el.parentElement;
                if (!parent) return false;

                const textContainers = ['p', 'li', 'td', 'th', 'span', 'div', 'blockquote', 'dd', 'dt'];
                if (!textContainers.includes(parent.tagName.toLowerCase())) return false;

                // Parent text content minus this element's text must be non-trivial
                const ownText = (el.innerText || '').trim();
                const parentText = (parent.innerText || '').trim();
                const siblingText = parentText.replace(ownText, '').trim();
                return siblingText.length >= 5;
            }

            elements.forEach((el, idx) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                // Skip hidden / zero-size elements: they aren't operable targets
                if (rect.width === 0 || rect.height === 0) return;
                if (style.display === 'none' || style.visibility === 'hidden') return;
                if (parseFloat(style.opacity) === 0) return;
                if (el.hasAttribute('disabled')) return;
                if (el.getAttribute('aria-disabled') === 'true') return;

                const width = Math.round(rect.width);
                const height = Math.round(rect.height);
                const meetsThreshold = width >= minPx && height >= minPx;

                const entry = {
                    dom_index: idx,
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type') || '',
                    role: el.getAttribute('role') || '',
                    id: el.id || '',
                    class: el.className || '',
                    text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 50),
                    width_px: width,
                    height_px: height,
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    center_x: Math.round(rect.left + rect.width / 2),
                    center_y: Math.round(rect.top + rect.height / 2),
                    threshold_px: minPx,
                };

                if (meetsThreshold) {
                    entry.status = 'PASS';
                } else if (isUserAgentControl(el)) {
                    entry.status = 'EXEMPT_UA_CONTROL';
                    entry.exemption_reason = `Native ${entry.tag}${entry.type ? '[type=' + entry.type + ']' : ''} with no author-specified dimensions`;
                } else if (isInlineInRunningText(el)) {
                    entry.status = 'EXEMPT_INLINE';
                    entry.exemption_reason = 'Inline target inside a sentence or block of running text';
                } else {
                    entry.status = 'FAIL';
                    entry.shortfall = `Target is ${width}x${height}px, below ${minPx}x${minPx}px minimum`;
                }

                results.push(entry);
            });

            return results;
        }""",
            {"minPx": min_px},
        )

    # ------------------------------------------------------------------ #
    #  Spacing exception (AA / 2.5.8 only)                                 #
    # ------------------------------------------------------------------ #

    def _apply_spacing_exception(self, targets: list, radius_px: int) -> None:
        """
        Per WCAG 2.5.8: an undersized target passes if a circle of diameter
        equal to the threshold (24px), centered on the target's bounding box,
        does not intersect any other target's bounding box or its own
        equivalent circle.

        Simplified pairwise check: for each FAIL target, examine every other
        target. If the closest edge-to-center distance is >= radius_px, the
        spacing exception applies.
        """
        radius = radius_px / 2.0  # circle radius

        for t in targets:
            if t["status"] != "FAIL":
                continue

            cx, cy = t["center_x"], t["center_y"]
            spacing_ok = True
            nearest_neighbor = None
            nearest_dist = None

            for other in targets:
                if other is t:
                    continue
                # Distance from t's center to other's bounding box
                left = other["x"]
                top = other["y"]
                right = other["x"] + other["width_px"]
                bottom = other["y"] + other["height_px"]

                # Closest point on other's rect to t's center
                nearest_x = max(left, min(cx, right))
                nearest_y = max(top, min(cy, bottom))
                dx = cx - nearest_x
                dy = cy - nearest_y
                dist = (dx * dx + dy * dy) ** 0.5

                if nearest_dist is None or dist < nearest_dist:
                    nearest_dist = dist
                    nearest_neighbor = other

                if dist < radius:
                    spacing_ok = False
                    break

            if spacing_ok:
                t["status"] = "EXEMPT_SPACING"
                t["exemption_reason"] = (
                    f"Undersized target has clear {radius_px}px-diameter "
                    f"spacing from neighbors (nearest at {nearest_dist:.0f}px)"
                    if nearest_dist is not None
                    else f"Undersized target has clear {radius_px}px-diameter spacing (no neighbors)"
                )


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":

    # --- Test 1: 50x50 button passes AAA ---
    print("=" * 60)
    print("TEST 1: 50x50 button meets 44x44 AAA threshold")
    print("=" * 60)
    html1 = """<!DOCTYPE html><html><body>
        <button style="width:50px;height:50px">OK</button>
    </body></html>"""
    r1 = TargetSizeValidatorAgent(level="AAA").execute(html1)
    print(f"Status: {r1['wcag_255_status']}, passing: {r1['passing_count']}, violations: {r1['violation_count']}")
    assert r1["wcag_255_status"] == "PASS"
    print("PASS\n")

    # --- Test 2: 20x20 button fails AAA, no exception ---
    print("=" * 60)
    print("TEST 2: 20x20 standalone button fails AAA")
    print("=" * 60)
    html2 = """<!DOCTYPE html><html><body>
        <button style="width:20px;height:20px;padding:0">X</button>
    </body></html>"""
    r2 = TargetSizeValidatorAgent(level="AAA").execute(html2)
    print(f"Status: {r2['wcag_255_status']}, violations: {r2['violation_count']}")
    assert r2["wcag_255_status"] == "FAIL"
    print("PASS\n")

    # --- Test 3: Inline link in paragraph is exempt at AAA ---
    print("=" * 60)
    print("TEST 3: Inline link inside running text is exempt")
    print("=" * 60)
    html3 = """<!DOCTYPE html><html><body>
        <p>Read <a href="/docs">the documentation</a> for more details about how this works.</p>
    </body></html>"""
    r3 = TargetSizeValidatorAgent(level="AAA").execute(html3)
    print(f"Status: {r3['wcag_255_status']}")
    print(f"Exempt inline: {r3['exempt_inline_count']}")
    print(f"Violations: {r3['violation_count']}")
    assert r3["wcag_255_status"] == "PASS"
    assert r3["exempt_inline_count"] >= 1
    print("PASS\n")

    # --- Test 4: Native checkbox is UA-exempt ---
    print("=" * 60)
    print("TEST 4: Native checkbox/radio are user-agent-control exempt")
    print("=" * 60)
    html4 = """<!DOCTYPE html><html><body>
        <label><input type="checkbox" name="agree"> I agree</label>
        <label><input type="radio" name="opt"> Option A</label>
    </body></html>"""
    r4 = TargetSizeValidatorAgent(level="AAA").execute(html4)
    print(f"Status: {r4['wcag_255_status']}")
    print(f"Exempt UA controls: {r4['exempt_ua_control_count']}")
    print(f"Violations: {r4['violation_count']}")
    assert r4["wcag_255_status"] == "PASS"
    assert r4["exempt_ua_control_count"] >= 2
    print("PASS\n")

    # --- Test 5: AA spacing exception applies for isolated small target ---
    print("=" * 60)
    print("TEST 5: 18x18 button alone in viewport passes AA via spacing exception")
    print("=" * 60)
    html5 = """<!DOCTYPE html><html><body>
        <div style="margin:200px">
            <button style="width:18px;height:18px;padding:0">X</button>
        </div>
    </body></html>"""
    r5 = TargetSizeValidatorAgent(level="AA").execute(html5)
    print(f"Status: {r5['wcag_258_status']}")
    print(f"Exempt spacing: {r5['exempt_spacing_count']}")
    print(f"Violations: {r5['violation_count']}")
    assert r5["wcag_258_status"] == "PASS"
    assert r5["exempt_spacing_count"] >= 1
    print("PASS\n")

    # --- Test 6: AA spacing exception denied when targets adjacent ---
    print("=" * 60)
    print("TEST 6: Two 14x14 buttons adjacent fail AA (spacing doesn't apply)")
    print("=" * 60)
    html6 = """<!DOCTYPE html><html><body style="margin:0;padding:0">
        <button style="width:14px;height:14px;padding:0;margin:0;border:0">A</button><button style="width:14px;height:14px;padding:0;margin:0;border:0">B</button>
    </body></html>"""
    r6 = TargetSizeValidatorAgent(level="AA").execute(html6)
    print(f"Status: {r6['wcag_258_status']}, violations: {r6['violation_count']}")
    if r6["violations"]:
        v = r6["violations"][0]
        print(f"  - {v['text']}: {v.get('shortfall', '')}")
    assert r6["wcag_258_status"] == "FAIL"
    assert r6["violation_count"] >= 2
    print("PASS\n")

    # --- Test 7: Same Test 5 page fails at AAA (spacing exception doesn't apply at AAA) ---
    print("=" * 60)
    print("TEST 7: Same isolated 18x18 button fails AAA (no spacing exception)")
    print("=" * 60)
    r7 = TargetSizeValidatorAgent(level="AAA").execute(html5)
    print(f"Status: {r7['wcag_255_status']}, violations: {r7['violation_count']}")
    assert r7["wcag_255_status"] == "FAIL"
    print("PASS\n")

    # --- Test 8: Page with no interactive elements ---
    print("=" * 60)
    print("TEST 8: Page with no interactive targets is INAPPLICABLE")
    print("=" * 60)
    html8 = """<!DOCTYPE html><html><body>
        <h1>Just text</h1>
        <p>No interactive controls here.</p>
    </body></html>"""
    r8 = TargetSizeValidatorAgent(level="AAA").execute(html8)
    print(f"Status: {r8['wcag_255_status']}")
    assert r8["wcag_255_status"] == "INAPPLICABLE"
    print("PASS\n")

    # --- Test 9: Mixed page with some passing, some failing, some exempt ---
    print("=" * 60)
    print("TEST 9: Mixed page with all four outcomes")
    print("=" * 60)
    html9 = """<!DOCTYPE html><html><body>
        <button style="width:50px;height:50px">Big button (PASS)</button>
        <button style="width:20px;height:20px;padding:0;margin:50px">Small (FAIL)</button>
        <p>Inline <a href="/x">link here</a> in some surrounding text content for context.</p>
        <label><input type="checkbox"> Checkbox (UA exempt)</label>
    </body></html>"""
    r9 = TargetSizeValidatorAgent(level="AAA").execute(html9)
    print(f"Status: {r9['wcag_255_status']}")
    print(f"Targets: {r9['targets_analyzed']}, passing: {r9['passing_count']}, "
          f"violations: {r9['violation_count']}, "
          f"inline exempt: {r9['exempt_inline_count']}, UA exempt: {r9['exempt_ua_control_count']}")
    assert r9["wcag_255_status"] == "FAIL"  # has at least one true violation
    assert r9["passing_count"] >= 1
    assert r9["violation_count"] >= 1
    assert r9["exempt_inline_count"] >= 1
    assert r9["exempt_ua_control_count"] >= 1
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
