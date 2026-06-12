"""
Autocomplete Validator Tool Agent
Validates autocomplete attributes on form fields per WCAG 1.3.5
Identify Input Purpose (Level AA).

Used by: Elias (also referenced by Sophie's profile in some configurations).

This version removes the previous `_test_autofill_functionality` method,
which used `send_keys()` and called that "autofill testing." That was
misleading — it tested whether a field accepts typed input, not whether
the browser's autofill machinery can populate it.

WCAG 1.3.5 only requires that the input purpose be programmatically
determinable through the `autocomplete` attribute, which the static
analysis here covers correctly. Selenium dependency is no longer needed.

Detection coverage:
  1. Form fields collecting personal data that lack autocomplete attributes
  2. Fields with autocomplete values that aren't valid WCAG 1.3.5 tokens
  3. Fields with autocomplete="off" on personal-data fields (a regression
     of 1.3.5 even when the rest of the form is fine)
"""

from bs4 import BeautifulSoup


class AutocompleteValidatorAgent:
    """
    Static analysis of autocomplete attributes on form fields.
    No browser required.
    """

    # Valid autocomplete tokens enumerated by WCAG 1.3.5
    VALID_AUTOCOMPLETE_TOKENS = {
        # Contact info
        "name", "honorific-prefix", "given-name", "additional-name",
        "family-name", "honorific-suffix", "nickname",

        # Email/phone
        "email", "tel", "tel-country-code", "tel-national",
        "tel-area-code", "tel-local", "tel-extension",

        # Address
        "street-address", "address-line1", "address-line2", "address-line3",
        "address-level1", "address-level2", "address-level3", "address-level4",
        "country", "country-name", "postal-code",

        # Payment
        "cc-name", "cc-given-name", "cc-additional-name", "cc-family-name",
        "cc-number", "cc-exp", "cc-exp-month", "cc-exp-year", "cc-csc", "cc-type",

        # Other
        "username", "new-password", "current-password",
        "one-time-code", "organization", "organization-title",
        "bday", "bday-day", "bday-month", "bday-year",
        "sex", "url", "photo", "language", "impp",
    }

    # Keywords in field name/id/placeholder/label that suggest personal data
    PERSONAL_DATA_KEYWORDS = [
        "name", "email", "phone", "tel", "address", "street", "city",
        "state", "zip", "postal", "country", "card", "credit", "password",
        "username", "birthday", "birth", "organization", "company",
    ]

    def execute(self, html: str) -> dict:
        results = self._analyze_autocomplete_attributes(html)

        # WCAG 1.3.5 verdict
        if results["fields_analyzed"] == 0:
            wcag_status = "INAPPLICABLE"
        elif (
            results["fields_missing_autocomplete"]
            or results["fields_with_invalid_autocomplete"]
            or results["fields_with_autocomplete_off"]
        ):
            wcag_status = "FAIL"
        else:
            wcag_status = "PASS"

        return {
            **results,
            "wcag_135_status": wcag_status,
            "tool_name": "AutocompleteValidatorAgent",
        }

    def _analyze_autocomplete_attributes(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        # Inputs that should plausibly have autocomplete
        relevant_inputs = soup.find_all(
            "input",
            type=lambda t: t in ["text", "email", "tel", "url", "password", "search", None],
        )

        fields_missing = []
        fields_invalid = []
        fields_off = []
        fields_valid = 0

        for input_field in relevant_inputs:
            field_info = self._extract_field_info(input_field)
            autocomplete = input_field.get("autocomplete", "").strip().lower()

            if not autocomplete:
                if self._should_have_autocomplete(input_field):
                    fields_missing.append(field_info)
            elif autocomplete == "off":
                if self._should_have_autocomplete(input_field):
                    fields_off.append(field_info)
            else:
                if self._validate_autocomplete_value(autocomplete):
                    fields_valid += 1
                else:
                    field_info["invalid_autocomplete_value"] = autocomplete
                    fields_invalid.append(field_info)

        return {
            "fields_analyzed": len(relevant_inputs),
            "fields_with_autocomplete": fields_valid,
            "fields_missing_autocomplete": fields_missing,
            "fields_with_invalid_autocomplete": fields_invalid,
            "fields_with_autocomplete_off": fields_off,
        }

    def _extract_field_info(self, input_field) -> dict:
        return {
            "id": input_field.get("id", ""),
            "name": input_field.get("name", ""),
            "type": input_field.get("type", "text"),
            "placeholder": input_field.get("placeholder", ""),
            "label": self._find_label_text(input_field),
        }

    def _find_label_text(self, input_field) -> str:
        # label[for=id]
        field_id = input_field.get("id")
        if field_id:
            parent = input_field.find_parent()
            if parent:
                label = parent.find("label", attrs={"for": field_id})
                if label:
                    return label.get_text(strip=True)

        # Wrapping label
        label = input_field.find_parent("label")
        if label:
            return label.get_text(strip=True)

        return ""

    def _should_have_autocomplete(self, input_field) -> bool:
        name = input_field.get("name", "").lower()
        id_attr = input_field.get("id", "").lower()
        placeholder = input_field.get("placeholder", "").lower()
        label = self._find_label_text(input_field).lower()
        combined = f"{name} {id_attr} {placeholder} {label}"
        return any(kw in combined for kw in self.PERSONAL_DATA_KEYWORDS)

    def _validate_autocomplete_value(self, autocomplete_value: str) -> bool:
        """
        Format: "section-* shipping|billing token token"
        Examples: "email", "shipping name", "billing cc-number"
        """
        tokens = autocomplete_value.split()
        if tokens and tokens[0].startswith("section-"):
            tokens = tokens[1:]
        if tokens and tokens[0] in ("shipping", "billing"):
            tokens = tokens[1:]
        if not tokens:
            return False
        return tokens[0] in self.VALID_AUTOCOMPLETE_TOKENS


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    agent = AutocompleteValidatorAgent()

    # --- Test 1: Fields missing autocomplete ---
    print("=" * 60)
    print("TEST 1: Personal-data fields missing autocomplete")
    print("=" * 60)
    html1 = """<form>
        <label for="email">Email</label>
        <input type="email" id="email" name="email">
        <label for="phone">Phone</label>
        <input type="tel" id="phone" name="phone">
    </form>"""
    r1 = agent.execute(html1)
    print(f"Status: {r1['wcag_135_status']}")
    print(f"Missing: {len(r1['fields_missing_autocomplete'])}")
    assert r1["wcag_135_status"] == "FAIL"
    assert len(r1["fields_missing_autocomplete"]) == 2
    print("PASS\n")

    # --- Test 2: Valid autocomplete ---
    print("=" * 60)
    print("TEST 2: All personal-data fields have valid autocomplete")
    print("=" * 60)
    html2 = """<form>
        <label for="email">Email</label>
        <input type="email" id="email" name="email" autocomplete="email">
        <label for="phone">Phone</label>
        <input type="tel" id="phone" name="phone" autocomplete="tel">
        <label for="name">Full Name</label>
        <input type="text" id="name" name="name" autocomplete="name">
    </form>"""
    r2 = agent.execute(html2)
    print(f"Status: {r2['wcag_135_status']}")
    print(f"Valid: {r2['fields_with_autocomplete']}")
    assert r2["wcag_135_status"] == "PASS"
    assert r2["fields_with_autocomplete"] == 3
    print("PASS\n")

    # --- Test 3: Invalid autocomplete values ---
    print("=" * 60)
    print("TEST 3: Autocomplete values not in WCAG 1.3.5 list")
    print("=" * 60)
    html3 = """<form>
        <input type="email" id="email" autocomplete="invalid-token">
        <input type="text" id="name" autocomplete="fullname">
    </form>"""
    r3 = agent.execute(html3)
    print(f"Status: {r3['wcag_135_status']}")
    print(f"Invalid: {len(r3['fields_with_invalid_autocomplete'])}")
    assert r3["wcag_135_status"] == "FAIL"
    assert len(r3["fields_with_invalid_autocomplete"]) == 2
    print("PASS\n")

    # --- Test 4: autocomplete="off" on personal data ---
    print("=" * 60)
    print("TEST 4: autocomplete='off' on personal-data fields")
    print("=" * 60)
    html4 = """<form>
        <input type="email" id="email" name="email" autocomplete="off">
        <input type="password" id="password" name="password" autocomplete="off">
    </form>"""
    r4 = agent.execute(html4)
    print(f"Status: {r4['wcag_135_status']}")
    print(f"Off: {len(r4['fields_with_autocomplete_off'])}")
    assert r4["wcag_135_status"] == "FAIL"
    assert len(r4["fields_with_autocomplete_off"]) == 2
    print("PASS\n")

    # --- Test 5: No form fields ---
    print("=" * 60)
    print("TEST 5: Page with no relevant form fields")
    print("=" * 60)
    html5 = "<div><p>No forms here.</p></div>"
    r5 = agent.execute(html5)
    print(f"Status: {r5['wcag_135_status']}")
    assert r5["wcag_135_status"] == "INAPPLICABLE"
    print("PASS\n")

    # --- Test 6: Section and shipping/billing prefixes ---
    print("=" * 60)
    print("TEST 6: Compound autocomplete values (section-, shipping/billing)")
    print("=" * 60)
    html6 = """<form>
        <input type="text" name="ship-name" autocomplete="shipping name">
        <input type="text" name="bill-name" autocomplete="billing name">
        <input type="text" name="alt-email" autocomplete="section-alt email">
    </form>"""
    r6 = agent.execute(html6)
    print(f"Status: {r6['wcag_135_status']}")
    print(f"Valid: {r6['fields_with_autocomplete']}")
    assert r6["wcag_135_status"] == "PASS"
    assert r6["fields_with_autocomplete"] == 3
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
