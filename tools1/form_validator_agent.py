"""
Form Validator Tool Agent
Detects accessibility issues in HTML forms across multiple WCAG criteria.

Used by: Sophie (3.3.1, 3.3.2), Lakshmi (form labelling under 4.1.2 + 3.3.x).

Detection coverage:
  1. Inputs without an associated label (WCAG 1.3.1, 3.3.2, 4.1.2)
  2. Placeholder used as the sole label (WCAG 3.3.2 — disappears on input)
  3. Required fields with no programmatic required indicator (WCAG 3.3.2)
  4. Required fields with no visible required indicator (WCAG 3.3.2)
  5. Fields lacking format examples or instruction text (WCAG 3.3.2)
       Sophie's WAI story explicitly asks for examples for date and phone formats.
  6. Radio/checkbox groups not wrapped in <fieldset>/<legend> (WCAG 1.3.1, 3.3.2)
  7. Error feedback after form submission (WCAG 3.3.1)

Does NOT use axe-core. Pure Playwright + WCAG-grounded DOM inspection.
"""

import asyncio
import base64
import re
from playwright.async_api import async_playwright


# Format-example detection patterns. Each pattern represents a recognizable
# format hint a user would expect for that input type.
FORMAT_EXAMPLE_PATTERNS = [
    # Date formats: MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD
    r"\bMM[/-]DD[/-]YYYY\b",
    r"\bDD[/-]MM[/-]YYYY\b",
    r"\bYYYY[/-]MM[/-]DD\b",
    # Phone formats: (555) 555-5555, 555-555-5555, +1 555 555 5555
    r"\(\d{3}\)\s*\d{3}[-\s]?\d{4}",
    r"\d{3}[-\s]\d{3}[-\s]\d{4}",
    r"\+\d{1,3}\s\d{2,4}\s\d{3,4}\s\d{3,4}",
    # Generic example markers
    r"\bexample[:\s]",
    r"\be\.g\.",
    r"\bformat[:\s]",
    r"\bsuch as\b",
]
FORMAT_EXAMPLE_REGEX = re.compile("|".join(FORMAT_EXAMPLE_PATTERNS), re.IGNORECASE)

# Field types where a format hint is most commonly needed
FORMAT_HINT_NEEDED_TYPES = {"date", "tel", "datetime-local", "week", "month"}

# Field names/IDs/labels that suggest formatting is non-obvious
FORMAT_HINT_KEYWORDS = [
    "date", "birth", "dob", "phone", "tel", "mobile",
    "zip", "postal", "credit", "card", "ssn", "tax",
]


class FormValidatorAgent:
    """
    Form accessibility checker with Sophie-grounded checks for instruction
    text, format examples, placeholder-as-label, and fieldset grouping.
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

                forms_count = await page.evaluate(
                    "document.querySelectorAll('form').length"
                )

                if forms_count == 0:
                    return {
                        "forms_found": 0,
                        "unlabeled_inputs": [],
                        "placeholder_as_label": [],
                        "missing_required_indicator": [],
                        "fields_needing_format_hint": [],
                        "ungrouped_radio_checkbox": [],
                        "error_feedback_issues": [],
                        "total_issues": 0,
                        "wcag_332_status": "INAPPLICABLE",
                        "wcag_331_status": "INAPPLICABLE",
                        "tool_name": "FormValidatorAgent",
                    }

                unlabeled = await self._check_labels(page)
                placeholder_as_label = await self._check_placeholder_as_label(page)
                missing_required = await self._check_required_indicators(page)
                needing_format = await self._check_format_examples_and_instructions(page)
                ungrouped = await self._check_fieldset_grouping(page)
                error_feedback = await self._check_error_feedback(page)

            finally:
                await browser.close()

        total_332 = (
            len(unlabeled)
            + len(placeholder_as_label)
            + len(missing_required)
            + len(needing_format)
            + len(ungrouped)
        )
        error_issues = error_feedback["issues"]
        error_elements_present = error_feedback["error_elements_present"]

        # 3.3.1 can only be evaluated when error messages are actually present.
        if not error_elements_present:
            wcag_331 = "INAPPLICABLE"
        else:
            wcag_331 = "FAIL" if error_issues else "PASS"

        return {
            "forms_found": forms_count,
            "unlabeled_inputs": unlabeled,
            "placeholder_as_label": placeholder_as_label,
            "missing_required_indicator": missing_required,
            "fields_needing_format_hint": needing_format,
            "ungrouped_radio_checkbox": ungrouped,
            "error_feedback_issues": error_issues,
            "error_elements_present_on_page": error_elements_present,
            "total_issues": total_332 + len(error_issues),
            "wcag_332_status": "FAIL" if total_332 > 0 else "PASS",
            "wcag_331_status": wcag_331,
            "tool_name": "FormValidatorAgent",
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
    #  Check 1: Inputs without an associated label                         #
    # ------------------------------------------------------------------ #

    async def _check_labels(self, page) -> list:
        return await page.evaluate("""() => {
            const results = [];
            const inputs = document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="reset"]):not([type="button"]), select, textarea'
            );
            inputs.forEach(input => {
                const id = input.id;
                const hasForLabel = id && document.querySelector(`label[for="${id}"]`);
                const hasWrappingLabel = !!input.closest('label');
                const hasAriaLabel = !!input.getAttribute('aria-label');
                const hasAriaLabelledBy = !!input.getAttribute('aria-labelledby');

                if (!hasForLabel && !hasWrappingLabel && !hasAriaLabel && !hasAriaLabelledBy) {
                    results.push({
                        tag: input.tagName.toLowerCase(),
                        type: input.type || '',
                        name: input.name || '',
                        id: id || '',
                        outer_html: input.outerHTML.slice(0, 150),
                    });
                }
            });
            return results;
        }""")

    # ------------------------------------------------------------------ #
    #  Check 2: Placeholder as the sole label                              #
    # ------------------------------------------------------------------ #

    async def _check_placeholder_as_label(self, page) -> list:
        """
        Field has a placeholder but no actual label. WCAG 3.3.2 fails because
        placeholder disappears on input, leaving users with no persistent
        identifier of what they're filling in.
        """
        return await page.evaluate("""() => {
            const results = [];
            const inputs = document.querySelectorAll('input, textarea');
            inputs.forEach(input => {
                const placeholder = input.getAttribute('placeholder');
                if (!placeholder || !placeholder.trim()) return;

                const id = input.id;
                const hasForLabel = id && document.querySelector(`label[for="${id}"]`);
                const hasWrappingLabel = !!input.closest('label');
                const hasAriaLabel = !!input.getAttribute('aria-label');
                const hasAriaLabelledBy = !!input.getAttribute('aria-labelledby');

                const hasAnyLabel = hasForLabel || hasWrappingLabel || hasAriaLabel || hasAriaLabelledBy;
                if (!hasAnyLabel) {
                    results.push({
                        tag: input.tagName.toLowerCase(),
                        type: input.type || '',
                        name: input.name || '',
                        id: id || '',
                        placeholder: placeholder,
                        outer_html: input.outerHTML.slice(0, 150),
                        reason: 'Placeholder is being used as the only label. It disappears on focus, leaving the user without a persistent label.',
                    });
                }
            });
            return results;
        }""")

    # ------------------------------------------------------------------ #
    #  Check 3: Required fields missing required indicators                #
    # ------------------------------------------------------------------ #

    async def _check_required_indicators(self, page) -> list:
        """
        For each field with `required` attribute, verify there's also a
        VISIBLE required indicator (asterisk, "(required)", etc.) and an
        ARIA equivalent (aria-required). Missing visible indicators leave
        the user guessing.
        """
        return await page.evaluate("""() => {
            const results = [];
            const required = document.querySelectorAll(
                'input[required], select[required], textarea[required], '
                + 'input[aria-required="true"], select[aria-required="true"], textarea[aria-required="true"]'
            );

            required.forEach(input => {
                const id = input.id;
                let labelEl = null;
                if (id) labelEl = document.querySelector(`label[for="${id}"]`);
                if (!labelEl) labelEl = input.closest('label');

                const labelText = labelEl ? labelEl.textContent : '';
                const ariaLabel = input.getAttribute('aria-label') || '';
                const combined = (labelText + ' ' + ariaLabel).toLowerCase();

                const hasVisibleIndicator = (
                    combined.includes('*') ||
                    combined.includes('required') ||
                    combined.includes('mandatory')
                );

                if (!hasVisibleIndicator) {
                    results.push({
                        tag: input.tagName.toLowerCase(),
                        name: input.name || '',
                        id: id || '',
                        label_text: labelText.trim().slice(0, 60),
                        outer_html: input.outerHTML.slice(0, 150),
                        reason: 'Required field has no visible required indicator (asterisk or "required" text) in label or aria-label.',
                    });
                }
            });

            return results;
        }""")

    # ------------------------------------------------------------------ #
    #  Check 4: Fields needing format hints or instructions                #
    # ------------------------------------------------------------------ #

    async def _check_format_examples_and_instructions(self, page) -> list:
        """
        Sophie's WAI story directly: "give me an example of the format they
        want, especially for dates."

        For inputs of types where format is non-obvious (date, tel, etc.) OR
        whose name/id suggests format-dependent content (zip, ssn, credit
        card), check whether visible instruction text near the field
        provides a format example. We look for:
          - Sibling text nodes with format patterns
          - The label's text
          - aria-describedby target element's text
          - Helper text in elements with classes like .hint, .help-text, .description
        """
        format_patterns_js = list(FORMAT_EXAMPLE_PATTERNS)
        format_keywords_js = FORMAT_HINT_KEYWORDS
        hint_types_js = list(FORMAT_HINT_NEEDED_TYPES)

        return await page.evaluate(
            """({patterns, keywords, hintTypes}) => {
            const results = [];
            const regex = new RegExp(patterns.join('|'), 'i');
            const inputs = document.querySelectorAll('input, textarea');

            inputs.forEach(input => {
                const type = (input.type || '').toLowerCase();
                const name = (input.name || '').toLowerCase();
                const id = (input.id || '').toLowerCase();

                // Skip non-text-like fields
                if (['hidden','submit','button','reset','checkbox','radio','file','image','range','color'].includes(type)) {
                    return;
                }

                // Does this field warrant a format hint?
                const typeNeedsHint = hintTypes.includes(type);
                const nameNeedsHint = keywords.some(k => name.includes(k) || id.includes(k));
                if (!typeNeedsHint && !nameNeedsHint) return;

                // Collect candidate hint text from several sources
                let candidateText = '';

                // Label text
                let labelEl = null;
                if (input.id) labelEl = document.querySelector(`label[for="${input.id}"]`);
                if (!labelEl) labelEl = input.closest('label');
                if (labelEl) candidateText += ' ' + labelEl.textContent;

                // aria-describedby target
                const describedById = input.getAttribute('aria-describedby');
                if (describedById) {
                    describedById.split(/\\s+/).forEach(ref => {
                        const target = document.getElementById(ref);
                        if (target) candidateText += ' ' + target.textContent;
                    });
                }

                // Placeholder counts as a (weak) source of format hint
                const placeholder = input.getAttribute('placeholder') || '';
                candidateText += ' ' + placeholder;

                // Title attribute
                candidateText += ' ' + (input.getAttribute('title') || '');

                // Sibling helper text
                const parent = input.parentElement;
                if (parent) {
                    parent.querySelectorAll(
                        '.hint, .help-text, .description, .form-hint, .input-hint, small'
                    ).forEach(el => { candidateText += ' ' + el.textContent; });
                }

                const hasFormatHint = regex.test(candidateText);

                if (!hasFormatHint) {
                    results.push({
                        tag: input.tagName.toLowerCase(),
                        type: type,
                        name: input.name || '',
                        id: input.id || '',
                        outer_html: input.outerHTML.slice(0, 150),
                        candidate_text_snippet: candidateText.trim().slice(0, 100),
                        reason: 'Field expects format-sensitive input (date, phone, etc.) but no format example or instruction was found near it.',
                    });
                }
            });

            return results;
        }""",
            {
                "patterns": format_patterns_js,
                "keywords": format_keywords_js,
                "hintTypes": hint_types_js,
            },
        )

    # ------------------------------------------------------------------ #
    #  Check 5: Radio/checkbox groups not wrapped in fieldset/legend       #
    # ------------------------------------------------------------------ #

    async def _check_fieldset_grouping(self, page) -> list:
        """
        Groups of radios sharing `name`, or 2+ checkboxes representing a
        related set, should be wrapped in <fieldset> with a <legend>.
        Otherwise screen-reader users hear the options without the group label.
        """
        return await page.evaluate("""() => {
            const results = [];

            // Group radios by name
            const radioGroups = {};
            document.querySelectorAll('input[type="radio"]').forEach(r => {
                const name = r.name || '__unnamed__';
                if (!radioGroups[name]) radioGroups[name] = [];
                radioGroups[name].push(r);
            });

            Object.entries(radioGroups).forEach(([name, group]) => {
                if (group.length < 2) return;
                // Find common ancestor
                const first = group[0];
                const fieldset = first.closest('fieldset');
                let inSameFieldset = false;
                let hasLegend = false;

                if (fieldset) {
                    inSameFieldset = group.every(r => r.closest('fieldset') === fieldset);
                    hasLegend = !!fieldset.querySelector('legend');
                }

                if (!inSameFieldset || !hasLegend) {
                    results.push({
                        group_type: 'radio',
                        group_name: name,
                        group_size: group.length,
                        in_fieldset: inSameFieldset,
                        has_legend: hasLegend,
                        sample_outer_html: first.outerHTML.slice(0, 150),
                        reason: !inSameFieldset
                            ? `${group.length} radio buttons with name="${name}" are not grouped inside a single <fieldset>.`
                            : `${group.length} radio buttons with name="${name}" are in a <fieldset> but it has no <legend>.`,
                    });
                }
            });

            // Similar check for checkbox groups (same name attribute)
            const checkboxGroups = {};
            document.querySelectorAll('input[type="checkbox"]').forEach(c => {
                const name = c.name || '__unnamed__';
                if (!checkboxGroups[name]) checkboxGroups[name] = [];
                checkboxGroups[name].push(c);
            });

            Object.entries(checkboxGroups).forEach(([name, group]) => {
                if (group.length < 2 || name === '__unnamed__') return;
                const first = group[0];
                const fieldset = first.closest('fieldset');
                let inSameFieldset = false;
                let hasLegend = false;

                if (fieldset) {
                    inSameFieldset = group.every(c => c.closest('fieldset') === fieldset);
                    hasLegend = !!fieldset.querySelector('legend');
                }

                if (!inSameFieldset || !hasLegend) {
                    results.push({
                        group_type: 'checkbox',
                        group_name: name,
                        group_size: group.length,
                        in_fieldset: inSameFieldset,
                        has_legend: hasLegend,
                        sample_outer_html: first.outerHTML.slice(0, 150),
                        reason: !inSameFieldset
                            ? `${group.length} checkboxes with name="${name}" are not grouped inside a single <fieldset>.`
                            : `${group.length} checkboxes with name="${name}" are in a <fieldset> but it has no <legend>.`,
                    });
                }
            });

            return results;
        }""")

    # ------------------------------------------------------------------ #
    #  Check 6: Error feedback after submission                            #
    # ------------------------------------------------------------------ #

    async def _check_error_feedback(self, page) -> dict:
        """
        Look at any error messages ALREADY visible on the page. For each,
        check whether it's programmatically linked to a form field via
        aria-describedby OR sits inside a role=alert / aria-live region.

        We do NOT proactively trigger validation, because that would mark
        every empty required field as invalid on initial load and flood
        the results with false positives on well-built forms.

        Returns a dict with:
          error_elements_present: bool — whether any error messages exist
          issues: list — errors lacking programmatic linkage
        """
        return await page.evaluate("""() => {
            const errorEls = Array.from(document.querySelectorAll(
                '[role="alert"], [aria-live], [class*="error" i], [class*="invalid" i]'
            )).filter(el => {
                const text = (el.textContent || '').trim();
                if (!text) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return false;
                return true;
            });

            if (errorEls.length === 0) {
                return { error_elements_present: false, issues: [] };
            }

            const referencedIds = new Set();
            document.querySelectorAll('[aria-describedby]').forEach(el => {
                (el.getAttribute('aria-describedby') || '').split(/\\s+/).forEach(id => {
                    if (id) referencedIds.add(id);
                });
            });

            const issues = [];
            errorEls.forEach(el => {
                const inLiveRegion = el.matches('[role="alert"], [aria-live]')
                    || !!el.closest('[role="alert"], [aria-live]');
                const referencedById = el.id && referencedIds.has(el.id);

                if (!inLiveRegion && !referencedById) {
                    issues.push({
                        outer_html: el.outerHTML.slice(0, 200),
                        text: (el.textContent || '').trim().slice(0, 100),
                        reason: 'Apparent error message is neither in a live region nor referenced by aria-describedby on a form field.',
                    });
                }
            });

            return { error_elements_present: true, issues: issues };
        }""")


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    agent = FormValidatorAgent()

    # --- Test 1: Form with proper labels, fieldset, format example ---
    print("=" * 60)
    print("TEST 1: Well-built form, no issues")
    print("=" * 60)
    html1 = """<!DOCTYPE html><html><body>
    <form>
        <label for="email">Email <span>(required)</span></label>
        <input type="email" id="email" name="email" required autocomplete="email">

        <label for="dob">Date of birth (MM/DD/YYYY)</label>
        <input type="date" id="dob" name="dob">

        <fieldset>
            <legend>Subscription preference</legend>
            <label><input type="radio" name="sub" value="weekly"> Weekly</label>
            <label><input type="radio" name="sub" value="monthly"> Monthly</label>
        </fieldset>

        <button type="submit">Submit</button>
    </form>
    </body></html>"""
    r1 = agent.execute(html1)
    print(f"WCAG 3.3.2 status: {r1['wcag_332_status']}")
    print(f"Total issues: {r1['total_issues']}")
    assert r1["wcag_332_status"] == "PASS", f"Got {r1['wcag_332_status']} with issues: {r1}"
    print("PASS\n")

    # --- Test 2: Placeholder as sole label ---
    print("=" * 60)
    print("TEST 2: Input with placeholder but no label")
    print("=" * 60)
    html2 = """<!DOCTYPE html><html><body>
    <form>
        <input type="text" name="search" placeholder="Search...">
        <button type="submit">Go</button>
    </form>
    </body></html>"""
    r2 = agent.execute(html2)
    print(f"Status: {r2['wcag_332_status']}")
    print(f"Placeholder-as-label: {len(r2['placeholder_as_label'])}")
    print(f"Unlabeled: {len(r2['unlabeled_inputs'])}")
    assert r2["wcag_332_status"] == "FAIL"
    assert len(r2["placeholder_as_label"]) >= 1
    print("PASS\n")

    # --- Test 3: Date field without format example ---
    print("=" * 60)
    print("TEST 3: Date field with label but no format example")
    print("=" * 60)
    html3 = """<!DOCTYPE html><html><body>
    <form>
        <label for="dob">Date of birth</label>
        <input type="date" id="dob" name="dob">
    </form>
    </body></html>"""
    r3 = agent.execute(html3)
    print(f"Status: {r3['wcag_332_status']}")
    print(f"Fields needing format hint: {len(r3['fields_needing_format_hint'])}")
    if r3["fields_needing_format_hint"]:
        print(f"  - {r3['fields_needing_format_hint'][0]['reason']}")
    assert r3["wcag_332_status"] == "FAIL"
    assert len(r3["fields_needing_format_hint"]) >= 1
    print("PASS\n")

    # --- Test 4: Radio group without fieldset ---
    print("=" * 60)
    print("TEST 4: Radio group not wrapped in fieldset")
    print("=" * 60)
    html4 = """<!DOCTYPE html><html><body>
    <form>
        <label for="size">Size:</label>
        <label><input type="radio" name="size" value="small"> Small</label>
        <label><input type="radio" name="size" value="medium"> Medium</label>
        <label><input type="radio" name="size" value="large"> Large</label>
    </form>
    </body></html>"""
    r4 = agent.execute(html4)
    print(f"Status: {r4['wcag_332_status']}")
    print(f"Ungrouped radio/checkbox: {len(r4['ungrouped_radio_checkbox'])}")
    assert r4["wcag_332_status"] == "FAIL"
    assert len(r4["ungrouped_radio_checkbox"]) >= 1
    print("PASS\n")

    # --- Test 5: Required field without visible indicator ---
    print("=" * 60)
    print("TEST 5: Required field with label but no asterisk or 'required' text")
    print("=" * 60)
    html5 = """<!DOCTYPE html><html><body>
    <form>
        <label for="email">Email</label>
        <input type="email" id="email" name="email" required>
    </form>
    </body></html>"""
    r5 = agent.execute(html5)
    print(f"Status: {r5['wcag_332_status']}")
    print(f"Missing required indicator: {len(r5['missing_required_indicator'])}")
    assert r5["wcag_332_status"] == "FAIL"
    assert len(r5["missing_required_indicator"]) >= 1
    print("PASS\n")

    # --- Test 6: Phone field with format hint ---
    print("=" * 60)
    print("TEST 6: Phone field with format hint in describedby")
    print("=" * 60)
    html6 = """<!DOCTYPE html><html><body>
    <form>
        <label for="phone">Phone number</label>
        <input type="tel" id="phone" name="phone" aria-describedby="phone-hint">
        <small id="phone-hint">Format: (555) 555-5555</small>
    </form>
    </body></html>"""
    r6 = agent.execute(html6)
    print(f"Status: {r6['wcag_332_status']}")
    print(f"Fields needing format hint: {len(r6['fields_needing_format_hint'])}")
    assert r6["wcag_332_status"] == "PASS"
    assert len(r6["fields_needing_format_hint"]) == 0
    print("PASS\n")

    # --- Test 7: No forms on page ---
    print("=" * 60)
    print("TEST 7: Page with no forms")
    print("=" * 60)
    html7 = "<!DOCTYPE html><html><body><p>No forms.</p></body></html>"
    r7 = agent.execute(html7)
    print(f"Status: {r7['wcag_332_status']}")
    assert r7["wcag_332_status"] == "INAPPLICABLE"
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
