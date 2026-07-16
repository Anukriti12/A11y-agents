"""
Form Validator Tool Agent
Detects common accessibility issues in HTML forms.
Used by: Ade
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
# from urllib.parse import quote

class FormValidationAgent:
    """
    Analyzes HTML forms for accessibility issues.
    Checks for:
    1.  Properly associated labels for all form controls.
    2.  Clear identification of required fields.
    3.  Programmatic linking of error messages to form fields.
    4.  Presence of 'autocomplete' attributes on relevant fields.
    """

    def execute(self, html: str) -> dict:
        """
        Analyzes the given HTML for form accessibility issues.
        """
        driver = self._start_browser()
        try:
            driver.get(f"data:text/html;charset=utf-8,{(html)}")
            time.sleep(1)

            forms = driver.find_elements(By.TAG_NAME, 'form')
            if not forms:
                return {
                    "summary": "No forms found on the page.",
                    "forms_found": 0,
                    "issues_found": 0,
                    "tool_name": "FormValidationAgent",
                    "details": []
                }

            all_results = []
            total_issues = 0
            for i, form in enumerate(forms):
                form_id = form.get_attribute('id') or f"form_{i}"
                
                unlabeled = self._check_labels(driver, form_id)
                missing_required = self._check_required_indicators(driver, form_id)
                missing_autocomplete = self._check_autocomplete(driver, form_id)
                error_handling = self._check_error_feedback(driver, form, form_id)

                form_issues_count = len(unlabeled) + len(missing_required) + len(missing_autocomplete) + len(error_handling['unlinked_errors'])

                total_issues += form_issues_count

                all_results.append({
                    "form_id": form_id,
                    "unlabeled_inputs": unlabeled,
                    "missing_required_indicators": missing_required,
                    "missing_autocomplete_suggestions": missing_autocomplete,
                    "error_handling_issues": error_handling,
                    "total_form_issues": form_issues_count
                })

            summary = f"Found {len(forms)} form(s) with a total of {total_issues} potential accessibility issues."

            return {
                "summary": summary,
                "forms_found": len(forms),
                "issues_found": total_issues,
                "details": all_results,
                "tool_name": "FormValidationAgent"
            }

        finally:
            driver.quit()

    def _start_browser(self):
        """Starts a headless Chrome browser."""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        return webdriver.Chrome(options=options)

    def _check_labels(self, driver, form_id):
        script = """
        const form = document.getElementById(arguments[0]) || document.querySelector('form');
        const inputs = form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="reset"]):not([type="button"]), select, textarea');
        const unlabeled = [];
        inputs.forEach(input => {
            const hasAriaLabel = input.getAttribute('aria-label');
            const hasAriaLabelledBy = input.getAttribute('aria-labelledby');
            const id = input.id;
            const hasForLabel = id ? form.querySelector(`label[for="${id}"]`) : null;
            
            if (!hasAriaLabel && !hasAriaLabelledBy && !hasForLabel) {
                unlabeled.push({
                    tag: input.tagName.toLowerCase(),
                    type: input.type,
                    name: input.name || '',
                    id: input.id || ''
                });
            }
        });
        return unlabeled;
        """
        return driver.execute_script(script, form_id)

    def _check_required_indicators(self, driver, form_id):
        script = """
        const form = document.getElementById(arguments[0]) || document.querySelector('form');
        const inputs = form.querySelectorAll('input, select, textarea');
        const missing = [];
        inputs.forEach(input => {
            // Check if it's a field that would typically be required
            if (input.hasAttribute('required') && !input.hasAttribute('aria-required')) {
                 // Not a failure, but good practice to have both
            }
            // For this check, we'll assume fields with a name that implies required are our target
            if (/(name|email|password)/i.test(input.name) && !input.hasAttribute('required') && input.getAttribute('aria-required') !== 'true') {
                 missing.push({
                    tag: input.tagName.toLowerCase(),
                    name: input.name,
                    id: input.id,
                    suggestion: "Consider adding 'required' or 'aria-required=\\"true\\"' if this field is mandatory."
                });
            }
        });
        return missing;
        """
        return driver.execute_script(script, form_id)

    def _check_autocomplete(self, driver, form_id):
        script = """
        const form = document.getElementById(arguments[0]) || document.querySelector('form');
        const inputs = form.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input[type="url"]');
        const missing = [];
        const autocompleteMap = {
            'email': 'email', 'e-mail': 'email',
            'name': 'name', 'fullname': 'name', 'fname': 'given-name', 'lname': 'family-name',
            'phone': 'tel', 'telephone': 'tel',
            'address': 'street-address', 'city': 'address-level2', 'zip': 'postal-code', 'postcode': 'postal-code'
        };
        inputs.forEach(input => {
            if (!input.hasAttribute('autocomplete')) {
                const name = (input.name || input.id || '').toLowerCase();
                for (const key in autocompleteMap) {
                    if (name.includes(key)) {
                        missing.push({
                            tag: input.tagName.toLowerCase(),
                            name: input.name,
                            id: input.id,
                            suggestion: `Consider adding autocomplete="${autocompleteMap[key]}"`
                        });
                        break;
                    }
                }
            }
        });
        return missing;
        """
        return driver.execute_script(script, form_id)

    def _check_error_feedback(self, driver, form, form_id):
        try:
            # Try to submit the form to trigger validation
            submit_button = form.find_element(By.CSS_SELECTOR, 'input[type="submit"], button[type="submit"], button:not([type])')
            submit_button.click()
            time.sleep(0.5) # Wait for errors to appear
        except Exception:
            # No submit button or form can't be submitted
            return {"unlinked_errors": [], "summary": "Could not find a submit button to test error feedback."}

        script = """
        const form = document.getElementById(arguments[0]) || document.querySelector('form');
        const inputs = form.querySelectorAll('input, select, textarea');
        const unlinkedErrors = [];
        const errorMessages = new Set();
        
        // Find all potential error messages
        form.querySelectorAll('[role="alert"], [class*="error"], [class*="validation-message"]').forEach(el => {
            if (el.textContent.trim()) {
                errorMessages.add(el.textContent.trim());
            }
        });

        inputs.forEach(input => {
            const describedBy = input.getAttribute('aria-describedby');
            // If an input is described by an element, we assume that element contains a relevant message (error or otherwise)
            // and should not be considered an "unlinked" error.
            if (describedBy) {
                const descEl = document.getElementById(describedBy);
                if (descEl && descEl.textContent.trim()) {
                    errorMessages.delete(descEl.textContent.trim());
                }
            }
        });
        
        // Whatever is left in errorMessages is likely unlinked
        errorMessages.forEach(msg => unlinkedErrors.push({ message: msg }));

        return { unlinked_errors: unlinkedErrors, summary: "Found " + unlinkedErrors.length + " potential unlinked error messages after submission." };
        """
        return driver.execute_script(script, form_id)


# Test cases
if __name__ == "__main__":
    agent = FormValidationAgent()

    # Test 1: Bad form with many issues
    html_bad = """
    <form id="login_form">
        Email <input type="text" name="email">
        Password <input type="password" id="pwd">
        <div class="error-message">Password is required.</div>
        <button type="submit">Log In</button>
    </form>
    """
    print("="*50)
    print("TEST 1: Bad Form")
    result_bad = agent.execute(html_bad)
    print(result_bad)
    assert result_bad['issues_found'] > 0, "Test 1 Failed: Should find issues"
    print("✓ PASS")
    print()

    # Test 2: Good form, fully accessible
    html_good = """
    <form id="register_form">
        <label for="name_id">Full Name</label>
        <input type="text" id="name_id" name="name" autocomplete="name" required aria-required="true">
        
        <label for="email_id">Email</label>
        <input type="email" id="email_id" name="email" autocomplete="email" required aria-required="true" aria-describedby="email_error">
        <div id="email_error" role="alert" style="visibility: hidden;">Please enter a valid email.</div>

        <button type="submit">Register</button>
    </form>
    """
    print("="*50)
    print("TEST 2: Good Form")
    result_good = agent.execute(html_good)
    print(result_good)
    assert result_good['issues_found'] == 0, "Test 2 Failed: Should find no issues"
    print("✓ PASS")
    print()

    # Test 3: No form on the page
    html_none = "<body><p>Hello world</p></body>"
    print("="*50)
    print("TEST 3: No Form")
    result_none = agent.execute(html_none)
    print(result_none)
    assert result_none['forms_found'] == 0, "Test 3 Failed: Should find no forms"
    print("✓ PASS")
    print()
    
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
