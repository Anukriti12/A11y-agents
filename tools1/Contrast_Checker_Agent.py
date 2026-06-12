"""
Contrast Checker Tool Agent
Evaluates WCAG color contrast for every text-bearing element on the page,
implementing the WCAG contrast formula directly (no axe-core dependency).

Used by: Elias (default AA, WCAG 1.4.3), can be configured to AAA (WCAG 1.4.6).

Replicates what a human auditor with a contrast picker does: walk the visible
text, identify foreground and background colors, compute the contrast ratio,
and compare against the threshold appropriate to the text size and weight.

Threshold table:
  Level AA (1.4.3):   4.5:1 for normal text, 3:1 for large text
  Level AAA (1.4.6):  7:1   for normal text, 4.5:1 for large text

Large text: 18pt+ regular (>=24px) OR 14pt+ bold (>=18.66px with font-weight>=700)

Detection coverage:
  1. Every visible element whose own text node is non-empty
  2. Foreground from getComputedStyle('color')
  3. Background by walking up ancestors until an opaque color is found,
     defaulting to white if none is found before <html>
  4. Ambiguous flag: element has a background-image, gradient, or partially
     transparent ancestor stack the tool cannot resolve confidently
  5. Disabled controls exempted (input[disabled], [aria-disabled="true"])

Does NOT use axe-core. Pure Playwright + WCAG contrast math in JS.
"""

import asyncio
import base64
from playwright.async_api import async_playwright


# WCAG thresholds
THRESHOLDS = {
    "AA":  {"normal": 4.5, "large": 3.0},
    "AAA": {"normal": 7.0, "large": 4.5},
}

# Maximum elements to report in detail (keeps output manageable on huge pages)
MAX_VIOLATIONS_REPORTED = 200


class ContrastCheckerAgent:
    """
    Walks text-bearing elements and evaluates WCAG color contrast.
    Default threshold is AA (1.4.3). Pass level="AAA" for 1.4.6.
    """

    def __init__(self, level: str = "AA"):
        if level not in THRESHOLDS:
            raise ValueError(f"level must be 'AA' or 'AAA', got '{level}'")
        self.level = level

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

                analyzed = await self._evaluate_contrast(
                    page,
                    threshold_normal=THRESHOLDS[self.level]["normal"],
                    threshold_large=THRESHOLDS[self.level]["large"],
                )
            finally:
                await browser.close()

        violations = [e for e in analyzed if e["status"] == "FAIL"]
        ambiguous = [e for e in analyzed if e["status"] == "AMBIGUOUS"]
        passing = [e for e in analyzed if e["status"] == "PASS"]
        exempt = [e for e in analyzed if e["status"] == "EXEMPT"]

        if not analyzed:
            wcag_status = "INAPPLICABLE"
        elif violations:
            wcag_status = "FAIL"
        else:
            wcag_status = "PASS"

        sc_label = "wcag_143_status" if self.level == "AA" else "wcag_146_status"

        return {
            "level": self.level,
            "threshold_normal": THRESHOLDS[self.level]["normal"],
            "threshold_large": THRESHOLDS[self.level]["large"],
            "text_elements_analyzed": len(analyzed),
            "passing_count": len(passing),
            "violation_count": len(violations),
            "ambiguous_count": len(ambiguous),
            "exempt_count": len(exempt),
            "violations": violations[:MAX_VIOLATIONS_REPORTED],
            "ambiguous": ambiguous[:MAX_VIOLATIONS_REPORTED],
            sc_label: wcag_status,
            "tool_name": "ContrastCheckerAgent",
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
    #  Contrast evaluation (all DOM work + math done in JS)                #
    # ------------------------------------------------------------------ #

    async def _evaluate_contrast(self, page, threshold_normal: float, threshold_large: float) -> list:
        return await page.evaluate(
            """({ thresholdNormal, thresholdLarge }) => {

            // --------------------------------------------------------- //
            //  Color parsing                                             //
            // --------------------------------------------------------- //

            function parseRGBA(str) {
                if (!str) return null;
                const s = str.trim().toLowerCase();
                if (s === 'transparent' || s === 'rgba(0, 0, 0, 0)') {
                    return { r: 0, g: 0, b: 0, a: 0 };
                }
                // Match rgb()/rgba() with comma or space separators
                const m = s.match(/rgba?\\s*\\(\\s*([0-9.]+)[\\s,]+([0-9.]+)[\\s,]+([0-9.]+)(?:[\\s,]+([0-9.]+))?\\s*\\)/);
                if (m) {
                    return {
                        r: parseFloat(m[1]),
                        g: parseFloat(m[2]),
                        b: parseFloat(m[3]),
                        a: m[4] !== undefined ? parseFloat(m[4]) : 1.0,
                    };
                }
                return null;
            }

            // --------------------------------------------------------- //
            //  WCAG relative luminance + contrast ratio                  //
            // --------------------------------------------------------- //

            function linearize(c) {
                c = c / 255;
                return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
            }

            function relativeLuminance(rgb) {
                return 0.2126 * linearize(rgb.r)
                     + 0.7152 * linearize(rgb.g)
                     + 0.0722 * linearize(rgb.b);
            }

            function contrastRatio(rgb1, rgb2) {
                const L1 = relativeLuminance(rgb1);
                const L2 = relativeLuminance(rgb2);
                const lighter = Math.max(L1, L2);
                const darker  = Math.min(L1, L2);
                return (lighter + 0.05) / (darker + 0.05);
            }

            // --------------------------------------------------------- //
            //  Alpha blending (compose foreground over background)      //
            // --------------------------------------------------------- //

            function blend(fg, bg) {
                // Source-over alpha composition. fg and bg both {r,g,b,a}.
                // Returns opaque blended color.
                const a = fg.a + bg.a * (1 - fg.a);
                if (a === 0) return { r: 0, g: 0, b: 0, a: 0 };
                return {
                    r: (fg.r * fg.a + bg.r * bg.a * (1 - fg.a)) / a,
                    g: (fg.g * fg.a + bg.g * bg.a * (1 - fg.a)) / a,
                    b: (fg.b * fg.a + bg.b * bg.a * (1 - fg.a)) / a,
                    a: a,
                };
            }

            // --------------------------------------------------------- //
            //  Background resolution                                     //
            // --------------------------------------------------------- //

            function resolveBackground(el) {
                // Walk up ancestors, accumulating colors. Stop at first fully
                // opaque ancestor. If we hit document root, default to white.
                // Returns { color: {r,g,b,a:1}, ambiguous: bool, reason: str }.
                let current = el;
                let stack = [];
                let ambiguous = false;
                let ambiguityReason = '';

                while (current && current !== document.documentElement.parentElement) {
                    const cs = window.getComputedStyle(current);

                    // Background image / gradient breaks confident resolution
                    const bgImage = cs.backgroundImage;
                    if (bgImage && bgImage !== 'none') {
                        ambiguous = true;
                        ambiguityReason = 'ancestor has background-image or gradient';
                    }

                    const bg = parseRGBA(cs.backgroundColor);
                    if (bg && bg.a > 0) {
                        stack.push(bg);
                        if (bg.a >= 1.0) {
                            // Fully opaque ancestor: stop walking
                            break;
                        }
                    }
                    current = current.parentElement;
                }

                // Compose stack from bottom up. Bottom is white by default.
                let resolved = { r: 255, g: 255, b: 255, a: 1.0 };
                for (let i = stack.length - 1; i >= 0; i--) {
                    resolved = blend(stack[i], resolved);
                }
                resolved.a = 1.0;  // After composition, treat as opaque

                return { color: resolved, ambiguous, reason: ambiguityReason };
            }

            // --------------------------------------------------------- //
            //  Large-text classification                                 //
            // --------------------------------------------------------- //

            function isLargeText(fontSize, fontWeight) {
                // fontSize as parsed pixels; fontWeight as numeric (normal=400, bold=700)
                if (fontSize >= 24) return true;
                if (fontSize >= 18.66 && fontWeight >= 700) return true;
                return false;
            }

            // --------------------------------------------------------- //
            //  Direct-text detection                                     //
            // --------------------------------------------------------- //

            function hasDirectText(el) {
                // True if the element has a non-empty text node as a direct child
                // (i.e., text that gets el's color, not text from a styled descendant).
                for (const node of el.childNodes) {
                    if (node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0) {
                        return true;
                    }
                }
                return false;
            }

            // --------------------------------------------------------- //
            //  Exemption check                                           //
            // --------------------------------------------------------- //

            function isExempt(el) {
                if (el.hasAttribute('disabled')) return 'disabled attribute';
                if (el.getAttribute('aria-disabled') === 'true') return 'aria-disabled=true';
                // Inactive elements inside a disabled fieldset
                const fs = el.closest('fieldset[disabled]');
                if (fs) return 'inside disabled fieldset';
                return null;
            }

            // --------------------------------------------------------- //
            //  Walk the DOM                                              //
            // --------------------------------------------------------- //

            const results = [];
            const all = document.body ? document.body.querySelectorAll('*') : [];

            for (const el of all) {
                if (!hasDirectText(el)) continue;

                // Skip script/style/noscript content
                const tag = el.tagName.toLowerCase();
                if (['script', 'style', 'noscript', 'template'].includes(tag)) continue;

                // Skip if not visible
                const cs = window.getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                if (parseFloat(cs.opacity) === 0) continue;

                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                // Parse foreground
                const fgRaw = parseRGBA(cs.color);
                if (!fgRaw || fgRaw.a === 0) continue;

                // Parse font characteristics
                const fontSize = parseFloat(cs.fontSize) || 16;
                const fontWeight = parseInt(cs.fontWeight, 10) || 400;
                const large = isLargeText(fontSize, fontWeight);

                // Exemption
                const exemptReason = isExempt(el);
                if (exemptReason) {
                    results.push({
                        status: 'EXEMPT',
                        tag: tag,
                        id: el.id || '',
                        text: (el.textContent || '').trim().slice(0, 60),
                        exempt_reason: exemptReason,
                    });
                    continue;
                }

                // Resolve background
                const bgResult = resolveBackground(el);

                // If foreground has alpha < 1, blend it over the background
                let fg = fgRaw;
                if (fgRaw.a < 1.0) {
                    fg = blend(fgRaw, bgResult.color);
                }

                const ratio = contrastRatio(fg, bgResult.color);
                const threshold = large ? thresholdLarge : thresholdNormal;

                const entry = {
                    tag: tag,
                    id: el.id || '',
                    class: el.className || '',
                    text: (el.textContent || '').trim().slice(0, 60),
                    font_size_px: fontSize,
                    font_weight: fontWeight,
                    is_large_text: large,
                    foreground: `rgb(${Math.round(fg.r)}, ${Math.round(fg.g)}, ${Math.round(fg.b)})`,
                    background: `rgb(${Math.round(bgResult.color.r)}, ${Math.round(bgResult.color.g)}, ${Math.round(bgResult.color.b)})`,
                    contrast_ratio: Math.round(ratio * 100) / 100,
                    threshold_required: threshold,
                };

                if (bgResult.ambiguous) {
                    entry.status = 'AMBIGUOUS';
                    entry.ambiguity_reason = bgResult.reason;
                } else if (ratio >= threshold) {
                    entry.status = 'PASS';
                } else {
                    entry.status = 'FAIL';
                }

                results.push(entry);
            }

            return results;
        }""",
            {"thresholdNormal": threshold_normal, "thresholdLarge": threshold_large},
        )


# --------------------------------------------------------------------------- #
#  Backward-compatibility alias for existing imports                           #
# --------------------------------------------------------------------------- #

ContrastAAA_HTML_Agent = ContrastCheckerAgent  # legacy name


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":

    # --- Test 1: Perfect black on white = PASS at AA and AAA ---
    print("=" * 60)
    print("TEST 1: Black text on white background")
    print("=" * 60)
    html1 = """<!DOCTYPE html><html><body style="background:#fff">
        <p style="color:#000;font-size:16px">Normal text, ratio 21:1</p>
    </body></html>"""
    r1 = ContrastCheckerAgent(level="AA").execute(html1)
    print(f"Status: {r1['wcag_143_status']}")
    print(f"Elements: {r1['text_elements_analyzed']}, "
          f"passing: {r1['passing_count']}, violations: {r1['violation_count']}")
    if r1["violations"] or r1["ambiguous"]:
        print("Unexpected issues:", r1["violations"], r1["ambiguous"])
    assert r1["wcag_143_status"] == "PASS"
    print("PASS\n")

    # --- Test 2: Gray on white, normal text, fails AA ---
    print("=" * 60)
    print("TEST 2: #999 on white normal text (~2.85:1) fails AA")
    print("=" * 60)
    html2 = """<!DOCTYPE html><html><body style="background:#fff">
        <p style="color:#999;font-size:14px">Low-contrast normal text</p>
    </body></html>"""
    r2 = ContrastCheckerAgent(level="AA").execute(html2)
    print(f"Status: {r2['wcag_143_status']}")
    if r2["violations"]:
        v = r2["violations"][0]
        print(f"Ratio: {v['contrast_ratio']} (needs {v['threshold_required']})")
    assert r2["wcag_143_status"] == "FAIL"
    print("PASS\n")

    # --- Test 3: Gray on white, LARGE text, passes AA ---
    print("=" * 60)
    print("TEST 3: #888 on white large text (~3.5:1) passes AA at 3:1")
    print("=" * 60)
    html3 = """<!DOCTYPE html><html><body style="background:#fff">
        <h1 style="color:#888;font-size:24px;font-weight:normal">Large heading</h1>
    </body></html>"""
    r3 = ContrastCheckerAgent(level="AA").execute(html3)
    print(f"Status: {r3['wcag_143_status']}")
    print(f"Passing: {r3['passing_count']}, Violations: {r3['violation_count']}")
    assert r3["wcag_143_status"] == "PASS"
    print("PASS\n")

    # --- Test 4: Same gray, LARGE text, AAA threshold = FAIL ---
    print("=" * 60)
    print("TEST 4: #888 on white large text under AAA (needs 4.5:1) fails")
    print("=" * 60)
    r4 = ContrastCheckerAgent(level="AAA").execute(html3)
    print(f"Status: {r4['wcag_146_status']}")
    if r4["violations"]:
        v = r4["violations"][0]
        print(f"Ratio: {v['contrast_ratio']} (needs {v['threshold_required']})")
    assert r4["wcag_146_status"] == "FAIL"
    print("PASS\n")

    # --- Test 5: Gradient background = AMBIGUOUS ---
    print("=" * 60)
    print("TEST 5: Gradient background is flagged as ambiguous")
    print("=" * 60)
    html5 = """<!DOCTYPE html><html><body
        style="background:linear-gradient(to right, #fff, #000)">
        <p style="color:#888;font-size:14px">Unknown contrast over gradient</p>
    </body></html>"""
    r5 = ContrastCheckerAgent(level="AA").execute(html5)
    print(f"Status: {r5['wcag_143_status']}")
    print(f"Ambiguous count: {r5['ambiguous_count']}")
    if r5["ambiguous"]:
        print(f"Reason: {r5['ambiguous'][0]['ambiguity_reason']}")
    assert r5["ambiguous_count"] >= 1
    # No violations means the page passes — ambiguity is a warning, not a fail.
    assert r5["wcag_143_status"] == "PASS"
    print("PASS\n")

    # --- Test 6: Disabled control is exempt ---
    print("=" * 60)
    print("TEST 6: Disabled input is exempt")
    print("=" * 60)
    html6 = """<!DOCTYPE html><html><body style="background:#fff">
        <button disabled style="color:#999;background:#eee;font-size:14px">
            Disabled button
        </button>
        <button style="color:#000;background:#fff;font-size:14px">
            Active button
        </button>
    </body></html>"""
    r6 = ContrastCheckerAgent(level="AA").execute(html6)
    print(f"Status: {r6['wcag_143_status']}")
    print(f"Exempt count: {r6['exempt_count']}")
    print(f"Violations: {r6['violation_count']}")
    assert r6["exempt_count"] >= 1
    assert r6["wcag_143_status"] == "PASS"
    print("PASS\n")

    # --- Test 7: Inherited background via nested elements ---
    print("=" * 60)
    print("TEST 7: Nested element inherits opaque ancestor background")
    print("=" * 60)
    html7 = """<!DOCTYPE html><html><body style="background:#000">
        <div>
            <span style="color:#fff;font-size:14px">White text on inherited black</span>
        </div>
    </body></html>"""
    r7 = ContrastCheckerAgent(level="AA").execute(html7)
    print(f"Status: {r7['wcag_143_status']}")
    print(f"Passing: {r7['passing_count']}, Violations: {r7['violation_count']}")
    assert r7["wcag_143_status"] == "PASS"
    assert r7["violation_count"] == 0
    print("PASS\n")

    # --- Test 8: No text on page = INAPPLICABLE ---
    print("=" * 60)
    print("TEST 8: Page with no visible text")
    print("=" * 60)
    html8 = """<!DOCTYPE html><html><body>
        <img src="x" alt="">
    </body></html>"""
    r8 = ContrastCheckerAgent(level="AA").execute(html8)
    print(f"Status: {r8['wcag_143_status']}")
    assert r8["wcag_143_status"] == "INAPPLICABLE"
    print("PASS\n")

    # --- Test 9: Semi-transparent foreground over a known background ---
    print("=" * 60)
    print("TEST 9: rgba(0,0,0,0.5) text on white blends to gray, fails AA")
    print("=" * 60)
    html9 = """<!DOCTYPE html><html><body style="background:#fff">
        <p style="color:rgba(0,0,0,0.3);font-size:14px">Semi-transparent text</p>
    </body></html>"""
    r9 = ContrastCheckerAgent(level="AA").execute(html9)
    print(f"Status: {r9['wcag_143_status']}")
    if r9["violations"]:
        v = r9["violations"][0]
        print(f"Blended foreground: {v['foreground']}, ratio: {v['contrast_ratio']}")
    assert r9["wcag_143_status"] == "FAIL"
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
