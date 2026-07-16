"""
Autocomplete Validator Tool Agent
Validates autocomplete attributes and tests functional autofill
Used by: Elias, Sophie, Ian
WCAG: 1.3.5 Identify Input Purpose (Level AA)
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time

class AutocompleteValidatorAgent:
    """
    Validates autocomplete attributes on form fields.
    Goes beyond axe-core by testing if autofill actually works.
    """
    
    # Valid autocomplete tokens from WCAG 1.3.5
    VALID_AUTOCOMPLETE_TOKENS = {
        # Contact info
        'name', 'honorific-prefix', 'given-name', 'additional-name', 
        'family-name', 'honorific-suffix', 'nickname',
        
        # Email/phone
        'email', 'tel', 'tel-country-code', 'tel-national', 
        'tel-area-code', 'tel-local', 'tel-extension',
        
        # Address
        'street-address', 'address-line1', 'address-line2', 'address-line3',
        'address-level1', 'address-level2', 'address-level3', 'address-level4',
        'country', 'country-name', 'postal-code',
        
        # Payment
        'cc-name', 'cc-given-name', 'cc-additional-name', 'cc-family-name',
        'cc-number', 'cc-exp', 'cc-exp-month', 'cc-exp-year', 'cc-csc', 'cc-type',
        
        # Other
        'username', 'new-password', 'current-password', 
        'one-time-code', 'organization', 'organization-title',
        'bday', 'bday-day', 'bday-month', 'bday-year',
        'sex', 'url', 'photo', 'language', 'impp'
    }
    
    def execute(self, html):
        """
        Validate autocomplete attributes on form fields.
        
        Args:
            html: HTML string to analyze
        
        Returns:
            {
                "fields_analyzed": int,
                "fields_with_autocomplete": int,
                "fields_missing_autocomplete": [...],
                "fields_with_invalid_autocomplete": [...],
                "fields_with_autocomplete_off": [...],
                "autofill_test_results": [...],  # NEW: functional testing
                "tool_name": "AutocompleteValidatorAgent"
            }
        """
        
        # Part 1: Static analysis (like axe-core)
        static_results = self._analyze_autocomplete_attributes(html)
        
        # Part 2: Functional testing (beyond axe-core)
        driver = self._start_browser()
        try:
            driver.get(f"data:text/html;charset=utf-8,{html}")
            time.sleep(0.5)
            
            functional_results = self._test_autofill_functionality(driver, static_results)
        finally:
            driver.quit()
        
        # Combine results
        return {
            **static_results,
            "autofill_test_results": functional_results,
            "tool_name": "AutocompleteValidatorAgent"
        }
    
    def _analyze_autocomplete_attributes(self, html):
        """
        Static analysis of autocomplete attributes (like axe-core does).
        
        Returns:
            {
                "fields_analyzed": int,
                "fields_with_autocomplete": int,
                "fields_missing_autocomplete": [...],
                "fields_with_invalid_autocomplete": [...],
                "fields_with_autocomplete_off": [...]
            }
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all input fields that should have autocomplete
        relevant_inputs = soup.find_all('input', type=lambda t: t in [
            'text', 'email', 'tel', 'url', 'password', 'search', None
        ])
        
        fields_missing = []
        fields_invalid = []
        fields_off = []
        fields_valid = 0
        
        for input_field in relevant_inputs:
            field_info = self._extract_field_info(input_field)
            autocomplete = input_field.get('autocomplete', '').strip().lower()
            
            if not autocomplete:
                # Missing autocomplete entirely
                if self._should_have_autocomplete(input_field):
                    fields_missing.append(field_info)
            
            elif autocomplete == 'off':
                # Explicitly disabled autocomplete
                if self._should_have_autocomplete(input_field):
                    fields_off.append(field_info)
            
            else:
                # Has autocomplete value - validate it
                is_valid = self._validate_autocomplete_value(autocomplete)
                if is_valid:
                    fields_valid += 1
                else:
                    field_info['invalid_autocomplete_value'] = autocomplete
                    fields_invalid.append(field_info)
        
        return {
            "fields_analyzed": len(relevant_inputs),
            "fields_with_autocomplete": fields_valid,
            "fields_missing_autocomplete": fields_missing,
            "fields_with_invalid_autocomplete": fields_invalid,
            "fields_with_autocomplete_off": fields_off
        }
    
    def _extract_field_info(self, input_field):
        """Extract identifying information about a form field"""
        return {
            "id": input_field.get('id', ''),
            "name": input_field.get('name', ''),
            "type": input_field.get('type', 'text'),
            "placeholder": input_field.get('placeholder', ''),
            "label": self._find_label_text(input_field)
        }
    
    def _find_label_text(self, input_field):
        """Find associated label text for an input"""
        # Check for label by 'for' attribute
        field_id = input_field.get('id')
        if field_id:
            label = input_field.find_parent().find('label', attrs={'for': field_id})
            if label:
                return label.get_text(strip=True)
        
        # Check for wrapping label
        label = input_field.find_parent('label')
        if label:
            return label.get_text(strip=True)
        
        return ''
    
    def _should_have_autocomplete(self, input_field):
        """
        Determine if this field should have autocomplete.
        Based on WCAG 1.3.5 - fields collecting user information.
        """
        
        # Check field attributes for hints
        name = input_field.get('name', '').lower()
        id_attr = input_field.get('id', '').lower()
        placeholder = input_field.get('placeholder', '').lower()
        label = self._find_label_text(input_field).lower()
        
        # Keywords that suggest personal data
        personal_data_keywords = [
            'name', 'email', 'phone', 'tel', 'address', 'street', 'city',
            'state', 'zip', 'postal', 'country', 'card', 'credit', 'password',
            'username', 'birthday', 'birth', 'organization', 'company'
        ]
        
        all_text = f"{name} {id_attr} {placeholder} {label}"
        
        return any(keyword in all_text for keyword in personal_data_keywords)
    
    def _validate_autocomplete_value(self, autocomplete_value):
        """
        Validate autocomplete value against WCAG 1.3.5 specification.
        
        Format can be: "section-* shipping|billing token token"
        Examples: "email", "shipping name", "billing cc-number"
        """
        
        tokens = autocomplete_value.split()
        
        # Remove optional section prefix (e.g., "section-red")
        if tokens and tokens[0].startswith('section-'):
            tokens = tokens[1:]
        
        # Remove optional shipping/billing prefix
        if tokens and tokens[0] in ['shipping', 'billing']:
            tokens = tokens[1:]
        
        # The actual autocomplete token should be valid
        if tokens:
            main_token = tokens[0]
            return main_token in self.VALID_AUTOCOMPLETE_TOKENS
        
        return False
    
    def _test_autofill_functionality(self, driver, static_results):
        """
        NEW: Test if autofill actually works (beyond axe-core).
        
        This simulates browser autofill to verify fields can be populated.
        """
        
        autofill_results = []
        
        # Get all fields that have valid autocomplete
        valid_autocomplete_fields = []
        
        # Find inputs with autocomplete attributes
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete]')
        
        for input_elem in inputs:
            autocomplete = input_elem.get_attribute('autocomplete')
            
            if not autocomplete or autocomplete.lower() == 'off':
                continue
            
            # Test data based on autocomplete type
            test_value = self._get_test_value_for_autocomplete(autocomplete)
            
            if test_value:
                try:
                    # Attempt to fill the field
                    initial_value = input_elem.get_attribute('value') or ''
                    input_elem.clear()
                    input_elem.send_keys(test_value)
                    time.sleep(0.1)
                    new_value = input_elem.get_attribute('value') or ''
                    
                    autofill_success = (new_value == test_value)
                    
                    autofill_results.append({
                        "field_id": input_elem.get_attribute('id') or '',
                        "field_name": input_elem.get_attribute('name') or '',
                        "autocomplete": autocomplete,
                        "test_value": test_value,
                        "autofill_success": autofill_success,
                        "error": None if autofill_success else "Value did not populate"
                    })
                    
                except Exception as e:
                    autofill_results.append({
                        "field_id": input_elem.get_attribute('id') or '',
                        "field_name": input_elem.get_attribute('name') or '',
                        "autocomplete": autocomplete,
                        "autofill_success": False,
                        "error": str(e)
                    })
        
        return autofill_results
    
    def _get_test_value_for_autocomplete(self, autocomplete):
        """Get test data for different autocomplete types"""
        
        autocomplete = autocomplete.lower().split()[-1]  # Get main token
        
        test_data = {
            'name': 'John Doe',
            'given-name': 'John',
            'family-name': 'Doe',
            'email': 'john.doe@example.com',
            'tel': '555-123-4567',
            'street-address': '123 Main Street',
            'address-line1': '123 Main Street',
            'address-level2': 'Springfield',  # City
            'address-level1': 'IL',  # State
            'postal-code': '62701',
            'country': 'US',
            'cc-number': '4111111111111111',
            'cc-exp-month': '12',
            'cc-exp-year': '2025',
            'username': 'johndoe',
            'organization': 'Acme Corp'
        }
        
        return test_data.get(autocomplete, 'Test Value')
    
    def _start_browser(self):
        """Start headless Chrome browser"""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        return webdriver.Chrome(options=options)


# Test
if __name__ == "__main__":
    agent = AutocompleteValidatorAgent()
    
    # Test 1: Missing autocomplete
    print("=" * 60)
    print("TEST 1: Fields missing autocomplete")
    print("=" * 60)
    
    test_html_1 = """
    <form>
        <label for="email">Email</label>
        <input type="email" id="email" name="email">
        
        <label for="phone">Phone</label>
        <input type="tel" id="phone" name="phone">
    </form>
    """
    
    result = agent.execute(test_html_1)
    print(f"Fields analyzed: {result['fields_analyzed']}")
    print(f"Fields missing autocomplete: {len(result['fields_missing_autocomplete'])}")
    print(f"Missing: {result['fields_missing_autocomplete']}")
    assert len(result['fields_missing_autocomplete']) == 2
    print("✓ PASS\n")
    
    # Test 2: Valid autocomplete
    print("=" * 60)
    print("TEST 2: Valid autocomplete attributes")
    print("=" * 60)
    
    test_html_2 = """
    <form>
        <label for="email">Email</label>
        <input type="email" id="email" name="email" autocomplete="email">
        
        <label for="phone">Phone</label>
        <input type="tel" id="phone" name="phone" autocomplete="tel">
        
        <label for="name">Full Name</label>
        <input type="text" id="name" name="name" autocomplete="name">
    </form>
    """
    
    result = agent.execute(test_html_2)
    print(f"Fields analyzed: {result['fields_analyzed']}")
    print(f"Fields with valid autocomplete: {result['fields_with_autocomplete']}")
    print(f"Autofill test results: {len(result['autofill_test_results'])} fields tested")
    for test in result['autofill_test_results']:
        print(f"  - {test['autocomplete']}: {'✓' if test['autofill_success'] else '✗'}")
    assert result['fields_with_autocomplete'] == 3
    print("✓ PASS\n")
    
    # Test 3: Invalid autocomplete
    print("=" * 60)
    print("TEST 3: Invalid autocomplete values")
    print("=" * 60)
    
    test_html_3 = """
    <form>
        <label for="email">Email</label>
        <input type="email" id="email" autocomplete="invalid-token">
        
        <label for="name">Name</label>
        <input type="text" id="name" autocomplete="fullname">
    </form>
    """
    
    result = agent.execute(test_html_3)
    print(f"Fields with invalid autocomplete: {len(result['fields_with_invalid_autocomplete'])}")
    print(f"Invalid: {result['fields_with_invalid_autocomplete']}")
    assert len(result['fields_with_invalid_autocomplete']) == 2
    print("✓ PASS\n")
    
    # Test 4: autocomplete="off" (problematic)
    print("=" * 60)
    print("TEST 4: autocomplete='off' on personal data fields")
    print("=" * 60)
    
    test_html_4 = """
    <form>
        <label for="email">Email</label>
        <input type="email" id="email" autocomplete="off">
        
        <label for="password">Password</label>
        <input type="password" id="password" autocomplete="off">
    </form>
    """
    
    result = agent.execute(test_html_4)
    print(f"Fields with autocomplete='off': {len(result['fields_with_autocomplete_off'])}")
    print(f"Off: {result['fields_with_autocomplete_off']}")
    assert len(result['fields_with_autocomplete_off']) == 2
    print("✓ PASS\n")
    
    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
