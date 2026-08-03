"""
form_validator_agent.py — v2 (patched)

Changes from v1 (marked with [PATCH]):
  [PATCH-1] Adds _test_error_behavior(): submits the form with empty required
            fields and captures resulting HTML5 validation errors, aria-live
            announcements, and visible error elements. This is what an
            auditor actually does for WCAG 3.3.1.
  [PATCH-2] Adds explicit applicability signal so the LLM can distinguish
            "no form present" (INAPPLICABLE) from "form present but no errors
            in initial state" (needs submission test).
  [PATCH-3] Revises verdict logic for 3.3.1 to use the submission test
            result rather than requiring pre-existing error elements.

Drop-in replacement: keeps class name FormValidatorAgent and same public
interface (execute(html) -> dict). Persona agents do not need changes.

Used by: Sophie (3.3.1, 3.3.2), Lakshmi (form labelling under 4.1.2 + 3.3.x).
"""

import asyncio
import base64
import re
from playwright.async_api import async_playwright


# ============================================================================
# Existing FORMAT_EXAMPLE regex patterns (unchanged from v1)
# ============================================================================

FORMAT_EXAMPLE_PATTERNS = [
    r"\bMM[/-]DD[/-]YYYY\b",
    r"\bDD[/-]MM[/-]YYYY\b",
    r"\bYYYY[/-]MM[/-]DD\b",
    r"\(\d{3}\)\s*\d{3}[-\s]?\d{4}",
    r"\d{3}[-\s]\d{3}[-\s]\d{4}",
    r"\+\d{1,3}\s\d{2,4}\s\d{3,4}\s\d{3,4}",
    r"\bexample[:\s]",
    r"\be\.g\.",
    r"\bformat[:\s]",
    r"\bsuch as\b",
]
FORMAT_EXAMPLE_REGEX = re.compile("|".join(FORMAT_EXAMPLE_PATTERNS), re.IGNORECASE)

FORMAT_HINT_NEEDED_TYPES = {"date", "tel", "datetime-local", "week", "month"}
FORMAT_HINT_KEYWORDS = [
    "date", "birth", "dob", "phone", "tel", "mobile",
    "zip", "postal", "credit", "card", "ssn",
]


class FormValidatorAgent:
    """Form accessibility checker with submit-and-capture behavior for 3.3.1."""

    def execute(self, html: str) -> dict:
        return asyncio.run(self._run(html))

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

                # [PATCH-2] Explicit applicability
                if forms_count == 0:
                    return {
                        "applicability": {
                            "applies": False,
                            "reason": "No <form> elements present on the page.",
                        },
                        "forms_found": 0,
                        "wcag_331_status": "INAPPLICABLE",
                        "wcag_332_status": "INAPPLICABLE",
                        "tool_name": "FormValidatorAgent",
                    }

                # Static structure checks (unchanged from v1)
                unlabeled = await self._check_labels(page)
                placeholder_as_label = await self._check_placeholder_as_label(page)
                missing_required = await self._check_required_indicators(page)
                needing_format = await self._check_format_examples_and_instructions(page)
                ungrouped = await self._check_fieldset_grouping(page)

                # [PATCH-1] Test what happens when the form is submitted
                submission_test = await self._test_error_behavior(page)

                # Also keep the pre-existing error-state inspection for cases
                # where the corpus HTML ships pre-rendered error messages
                pre_existing_errors = await self._check_error_feedback(page)

            finally:
                await browser.close()

        # ==============================================================
        # Verdict for 3.3.2 Labels or Instructions (unchanged logic)
        # ==============================================================
        total_332 = (
            len(unlabeled)
            + len(placeholder_as_label)
            + len(missing_required)
            + len(needing_format)
            + len(ungrouped)
        )
        wcag_332 = "FAIL" if total_332 > 0 else "PASS"

        # ==============================================================
        # [PATCH-3] Verdict for 3.3.1 Error Identification
        # ==============================================================
        # Use submission test as primary evidence. Fall back to pre-existing
        # error elements only if submission test was inconclusive.
        wcag_331, wcag_331_evidence = self._verdict_331(
            submission_test, pre_existing_errors
        )

        return {
            "applicability": {
                "applies": True,
                "elements_present": {
                    "forms": forms_count,
                    "inputs": await page.evaluate(
                        "document.querySelectorAll('form input, form textarea, form select').length"
                    ) if False else "n/a",  # kept simple
                },
            },
            "forms_found": forms_count,
            "unlabeled_inputs": unlabeled,
            "placeholder_as_label": placeholder_as_label,
            "missing_required_indicator": missing_required,
            "fields_needing_format_hint": needing_format,
            "ungrouped_radio_checkbox": ungrouped,
            "submission_test": submission_test,
            "pre_existing_error_elements": pre_existing_errors,
            "wcag_331_status": wcag_331,
            "wcag_331_evidence": wcag_331_evidence,
            "wcag_332_status": wcag_332,
            "wcag_332_issues_count": total_332,
            "tool_name": "FormValidatorAgent",
        }

    # ------------------------------------------------------------------ #
    #  [PATCH-1] New: submit form and capture error behavior              #
    # ------------------------------------------------------------------ #

    async def _test_error_behavior(self, page) -> dict:
        """
        Attempt to submit the first form with empty required fields.
        Capture what error messages appear via three channels:
          - HTML5 constraint validation (native browser)
          - aria-live regions and role=alert (accessible announcements)
          - visible .error / [aria-invalid] elements

        Returns a dict the LLM can use to judge 3.3.1 compliance.
        """
        form_present = await page.evaluate("() => !!document.querySelector('form')")
        if not form_present:
            return {
                "testable": False,
                "reason": "no form to test",
            }

        submit_btn = await page.evaluate("""() => {
            const form = document.querySelector('form');
            if (!form) return null;
            const btn = form.querySelector('button[type=submit], input[type=submit], button:not([type])');
            if (!btn) return null;
            return {tag: btn.tagName, text: (btn.textContent || btn.value || '').trim()};
        }""")

        if not submit_btn:
            return {
                "testable": False,
                "reason": "no submit button found in form",
            }

        # Snapshot the DOM before submit
        dom_length_before = await page.evaluate("() => document.body.innerHTML.length")
        url_before = page.url

        # Click submit
        try:
            await page.evaluate("""() => {
                const btn = document.querySelector(
                    'form button[type=submit], form input[type=submit], form button:not([type])'
                );
                if (btn) btn.click();
            }""")
            # Give the page time to respond
            await page.wait_for_timeout(500)
        except Exception as e:
            return {
                "testable": False,
                "reason": f"submit action failed: {str(e)[:100]}",
            }

        # Capture what happened
        url_after = page.url
        dom_length_after = await page.evaluate("() => document.body.innerHTML.length")

        # Channel 1: HTML5 constraint validation
        html5_errors = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('input, select, textarea').forEach(el => {
                if (!el.checkValidity || el.checkValidity()) return;
                const id = el.id || el.name || '';
                let labelText = '';
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) labelText = lbl.textContent.trim();
                }
                results.push({
                    field_id: id,
                    field_label: labelText,
                    validation_message: el.validationMessage || '',
                    validity: {
                        valueMissing: el.validity.valueMissing,
                        typeMismatch: el.validity.typeMismatch,
                        patternMismatch: el.validity.patternMismatch,
                    },
                    identifies_field: !!id || !!labelText,
                });
            });
            return results;
        }""")

        # Channel 2: aria-live / role=alert regions
        aria_alerts = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('[role=alert], [aria-live]').forEach(el => {
                const text = el.textContent.trim();
                if (!text) return;
                const live = el.getAttribute('aria-live') || el.getAttribute('role');
                // Does the text reference a specific field?
                const identifiesField = /this field|the (\\w+) field|required|invalid|missing|enter your|please provide/i.test(text);
                results.push({
                    text: text.slice(0, 200),
                    live_type: live,
                    identifies_field: identifiesField,
                });
            });
            return results;
        }""")

        # Channel 3: Visible error elements
        visible_errors = await page.evaluate("""() => {
            const selectors = ['.error', '.invalid', '.field-error', '[aria-invalid=true]',
                               '.help-block.error', '.form-error', '.errorlist'];
            const found = new Set();
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    if (el.offsetHeight > 0 && el.textContent.trim()) {
                        found.add(el);
                    }
                });
            });
            return Array.from(found).map(el => ({
                text: el.textContent.trim().slice(0, 200),
                tag: el.tagName,
                identifies_field: !!el.getAttribute('data-field') ||
                                   /field|required|invalid/i.test(el.textContent),
            }));
        }""")

        # Determine if error identification is adequate
        any_error_appeared = (
            len(html5_errors) > 0
            or len(aria_alerts) > 0
            or len(visible_errors) > 0
        )
        errors_identify_fields = (
            any(e["identifies_field"] for e in html5_errors)
            or any(a["identifies_field"] for a in aria_alerts)
            or any(v["identifies_field"] for v in visible_errors)
        )
        dom_changed = dom_length_after != dom_length_before
        url_changed = url_after != url_before

        return {
            "testable": True,
            "submit_button": submit_btn,
            "dom_changed_on_submit": dom_changed,
            "url_changed_on_submit": url_changed,
            "html5_validation_errors": html5_errors,
            "aria_alerts_after_submit": aria_alerts,
            "visible_error_elements": visible_errors,
            "any_error_appeared": any_error_appeared,
            "errors_identify_fields": errors_identify_fields,
            "form_appears_to_have_no_client_validation": (
                url_changed and not any_error_appeared
            ),
        }

    def _verdict_331(self, submission_test, pre_existing_errors):
        """Combine submission test and pre-existing errors into a 3.3.1 verdict."""

        if not submission_test.get("testable"):
            # Fall back to pre-existing error inspection
            if pre_existing_errors.get("error_elements_present"):
                if pre_existing_errors.get("issues"):
                    return "FAIL", "Pre-existing error elements have identification issues."
                return "PASS", "Pre-existing error elements properly identify fields."
            return "INAPPLICABLE", (
                "Cannot test error identification: "
                + submission_test.get("reason", "no submit button")
            )

        # Submission test was run
        if submission_test.get("form_appears_to_have_no_client_validation"):
            # Form submitted to server without any client-side validation.
            # This is a common pattern (server-side validation returns errors).
            # We cannot determine from a single page load whether the server
            # would identify errors. Fall back to pre-existing state.
            if pre_existing_errors.get("error_elements_present"):
                return (
                    "PASS" if not pre_existing_errors.get("issues") else "FAIL",
                    "Server-side flow; verdict based on pre-existing error state.",
                )
            return "INAPPLICABLE", (
                "Form uses server-side validation without pre-rendered errors. "
                "Cannot test error identification from static HTML."
            )

        if not submission_test.get("any_error_appeared"):
            # Form has required fields (or should error) but nothing happened
            # on empty submit. This is a genuine 3.3.1 failure.
            html5 = submission_test.get("html5_validation_errors", [])
            if html5:
                # Browser knows there are errors but nothing was surfaced to user
                return "FAIL", (
                    "Empty submit triggered HTML5 validation errors that were "
                    "not surfaced via aria-live or visible messages."
                )
            return "INAPPLICABLE", (
                "Form has no required fields or validation. "
                "Error identification cannot be evaluated."
            )

        # Errors did appear on submit
        if not submission_test.get("errors_identify_fields"):
            return "FAIL", (
                "Errors appeared on submit but do not identify specific fields."
            )

        return "PASS", "Errors appeared on submit and identify specific fields."

    # ------------------------------------------------------------------ #
    #  Existing v1 methods (kept as-is)                                    #
    # ------------------------------------------------------------------ #

    async def _load(self, page, url_or_html: str) -> None:
        if url_or_html.strip().startswith("http"):
            await page.goto(url_or_html, wait_until="networkidle", timeout=30_000)
        else:
            encoded = base64.b64encode(url_or_html.encode()).decode()
            await page.goto(
                f"data:text/html;base64,{encoded}", wait_until="domcontentloaded"
            )

    async def _check_labels(self, page) -> list:
        return await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('form input, form textarea, form select').forEach(el => {
                if (['hidden', 'submit', 'button', 'reset', 'image'].includes(el.type)) return;
                const hasLabelFor = el.id && !!document.querySelector(`label[for="${el.id}"]`);
                const hasWrappedLabel = !!el.closest('label');
                const hasAriaLabel = !!el.getAttribute('aria-label');
                const hasAriaLabelledBy = !!el.getAttribute('aria-labelledby');
                if (!hasLabelFor && !hasWrappedLabel && !hasAriaLabel && !hasAriaLabelledBy) {
                    results.push({
                        selector: el.tagName.toLowerCase() + (el.id ? '#'+el.id : ''),
                        type: el.type || 'text',
                        name: el.name || '',
                    });
                }
            });
            return results;
        }""")

    async def _check_placeholder_as_label(self, page) -> list:
        return await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('form input[placeholder], form textarea[placeholder]').forEach(el => {
                if (['hidden', 'submit', 'button'].includes(el.type)) return;
                const hasLabelFor = el.id && !!document.querySelector(`label[for="${el.id}"]`);
                const hasWrappedLabel = !!el.closest('label');
                const hasAriaLabel = !!el.getAttribute('aria-label');
                if (!hasLabelFor && !hasWrappedLabel && !hasAriaLabel) {
                    results.push({
                        selector: el.tagName.toLowerCase() + (el.id ? '#'+el.id : ''),
                        placeholder: el.placeholder,
                    });
                }
            });
            return results;
        }""")

    async def _check_required_indicators(self, page) -> list:
        return await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('form input[required], form textarea[required], form select[required]').forEach(el => {
                const ariaRequired = el.getAttribute('aria-required');
                const hasAria = ariaRequired === 'true';
                // Look for visible marker in associated label
                let labelText = '';
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) labelText = lbl.textContent;
                }
                const hasVisibleMarker = /\\*|required/i.test(labelText);
                if (!hasAria && !hasVisibleMarker) {
                    results.push({
                        selector: el.tagName.toLowerCase() + (el.id ? '#'+el.id : ''),
                        label: labelText.trim().slice(0, 50),
                    });
                }
            });
            return results;
        }""")

    async def _check_format_examples_and_instructions(self, page) -> list:
        """Check whether format hints are given for fields that need them."""
        fields = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('form input, form textarea').forEach(el => {
                if (['hidden', 'submit', 'button', 'reset'].includes(el.type)) return;
                let labelText = '';
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) labelText = lbl.textContent.trim();
                }
                const nearbyText = (el.closest('.form-group, .field, div, p') || {}).textContent || '';
                results.push({
                    selector: el.tagName.toLowerCase() + (el.id ? '#'+el.id : ''),
                    type: el.type || 'text',
                    name: (el.name || '').toLowerCase(),
                    id: (el.id || '').toLowerCase(),
                    label: labelText,
                    nearby_text: nearbyText,
                    aria_describedby: el.getAttribute('aria-describedby') || '',
                });
            });
            return results;
        }""")

        needing = []
        for f in fields:
            keyword_match = any(
                kw in f["name"] + f["id"] + f["label"].lower()
                for kw in FORMAT_HINT_KEYWORDS
            )
            type_needs = f["type"] in FORMAT_HINT_NEEDED_TYPES
            if not (keyword_match or type_needs):
                continue
            combined = f["label"] + " " + f["nearby_text"]
            if FORMAT_EXAMPLE_REGEX.search(combined):
                continue
            if f["aria_describedby"]:
                continue
            needing.append({
                "selector": f["selector"],
                "type": f["type"],
                "reason": "field type or name suggests format hint needed",
            })
        return needing

    async def _check_fieldset_grouping(self, page) -> list:
        return await page.evaluate("""() => {
            const results = [];
            const groups = {};
            document.querySelectorAll('form input[type=radio], form input[type=checkbox]').forEach(el => {
                const name = el.name;
                if (!name) return;
                if (!groups[name]) groups[name] = [];
                groups[name].push(el);
            });
            for (const [name, els] of Object.entries(groups)) {
                if (els.length < 2) continue;
                const hasFieldset = els.every(el => !!el.closest('fieldset'));
                if (!hasFieldset) {
                    results.push({group_name: name, count: els.length});
                }
            }
            return results;
        }""")

    async def _check_error_feedback(self, page) -> dict:
        """Check for pre-existing error elements (form already displaying errors)."""
        error_els = await page.evaluate("""() => {
            const selectors = ['.error', '.invalid', '[aria-invalid=true]',
                              '.field-error', '.form-error', '[role=alert]'];
            const found = [];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    if (el.offsetHeight > 0 && el.textContent.trim()) {
                        found.push({
                            text: el.textContent.trim().slice(0, 200),
                            associated_field: el.getAttribute('data-field') ||
                                             el.getAttribute('for') ||
                                             (el.getAttribute('id') || '').replace(/-error$/, ''),
                        });
                    }
                });
            });
            return found;
        }""")

        issues = []
        for e in error_els:
            if not e["associated_field"] and not re.search(
                r"\bthis field|the .{1,20} field|required|missing\b",
                e["text"], re.IGNORECASE
            ):
                issues.append({
                    "text": e["text"],
                    "issue": "error element does not identify field",
                })

        return {
            "error_elements_present": len(error_els) > 0,
            "count": len(error_els),
            "issues": issues,
        }
