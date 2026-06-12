"""
Text Formatting Analysis Tool Agent
Analyzes the structure and formatting of text content in HTML
Used by: Sophie
"""

from bs4 import BeautifulSoup # Handles text analysis and HTML parsing
from playwright.sync_api import sync_playwright
import tempfile
import os

class TextFormattingAgent:
    """Analyzes the structure and formatting of text content in HTML after injecting some CSS overriding."""
    
    def apply_wcag_text_spacing(self, html_content: str) -> str:
        """
        The CSS injection function. Applies WCAG 1.4.12 Text Spacing requirements:
        - Line height: 1.5x the font size
        - Letter spacing: 0.12em
        - Word spacing: 0.16em
        - Paragraph spacing: 2em
        """
        parser = BeautifulSoup(html_content, "html.parser")

        WCAG_SPACING = {
            "line-height": "1.5",
            "letter-spacing": "0.12em",
            "word-spacing": "0.16em",
        }

        PARAGRAPH_SPACING = {
            "margin-bottom": "2em",
            "margin-top": "2em",
        }

        def apply_styles(tag, styles: dict):
            """Helper to merge new styles into a tag's existing inline style."""
            existing = tag.get("style", "")
            existing_styles = {}

            for declaration in existing.split(";"):
                declaration = declaration.strip()
                if ":" in declaration:
                    prop, _, val = declaration.partition(":")
                    existing_styles[prop.strip()] = val.strip()

            merged = {**existing_styles, **styles}
            tag["style"] = "; ".join(f"{k}: {v}" for k, v in merged.items())

        text_tags = ["p", "li", "td", "th", "div", "span", "h1", "h2",
                    "h3", "h4", "h5", "h6", "blockquote", "label", "a"]

        for tag in parser.find_all(text_tags):
            apply_styles(tag, WCAG_SPACING)

        for p_tag in parser.find_all("p"):
            apply_styles(p_tag, PARAGRAPH_SPACING)

        return str(parser)

    def _write_temp(self, html: str) -> str:
        """Write an HTML string to a temp file and return its path."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
        f.write(html)
        f.close()
        return f.name

    def _has_text_content(self, html_content: str) -> bool:
        """Check if the HTML has text-bearing tags that WCAG 1.4.12 applies to.
        Excludes div/span — too generic, match empty containers."""
        parser = BeautifulSoup(html_content, "html.parser")
        text_tags = ["p", "li", "td", "th", "h1", "h2",
                    "h3", "h4", "h5", "h6", "blockquote", "label", "a"]
        for tag in parser.find_all(text_tags):
            if tag.get_text(strip=True):
                return True
        return False

    def check_overflow(self, html_path: str) -> list[dict]:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{os.path.abspath(html_path)}")

            overflow_issues = page.evaluate("""
                () => {
                    const issues = [];
                    const tags = ['p','li','td','th','div','span','h1','h2','h3','h4','h5','h6'];

                    for (const tag of tags) {
                        for (const el of document.querySelectorAll(tag)) {
                            const isOverflowing =
                                el.scrollHeight > el.clientHeight + 2 ||
                                el.scrollWidth  > el.clientWidth  + 2;

                            if (isOverflowing) {
                                issues.push({
                                    tag:       el.tagName,
                                    id:        el.id || null,
                                    class:     el.className || null,
                                    text:      el.innerText.slice(0, 80),
                                    scrollH:   el.scrollHeight,
                                    clientH:   el.clientHeight,
                                    scrollW:   el.scrollWidth,
                                    clientW:   el.clientWidth,
                                });
                            }
                        }
                    }
                    return issues;
                }
            """)

            browser.close()
            return overflow_issues
        
    def extract_text(self, html_path: str) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{os.path.abspath(html_path)}")
            text = page.evaluate("() => document.body.innerText")
            browser.close()
            return text

    def check_content_integrity(self, before_path: str, after_path: str) -> dict:
        """Checks if any text content was changed or lost during the formatting process."""
        before_text = " ".join(self.extract_text(before_path).split())
        after_text  = " ".join(self.extract_text(after_path).split())

        result = {
            "status": "pass",
            "details": None
        }

        if before_text != after_text:
            for i, (a, b) in enumerate(zip(before_text, after_text)):
                if a != b:
                    details = {
                        "type": "char_mismatch",
                        "index": i,
                        "before_snippet": before_text[max(0, i-30):i+30],
                        "after_snippet": after_text[max(0, i-30):i+30]
                    }
                    result["status"] = "fail"
                    result["details"] = details
                    print(f"Text mismatch at char {i}:")
                    print(f"   Before: ...{details['before_snippet']}...")
                    print(f"   After:  ...{details['after_snippet']}...")
                    return result

            details = {"type": "length_mismatch", "before_len": len(before_text), "after_len": len(after_text)}
            result["status"] = "fail"
            result["details"] = details
            print(f"Length mismatch: {len(before_text)} → {len(after_text)} chars")
            return result

        print("Content integrity: PASS")
        return result

    def process_file(self, input_path: str, output_path: str):
        """For running the agent against HTML files on disk."""
        print("Processing file for WCAG 1.4.12 text spacing...\n")
        with open(input_path, "r", encoding="utf-8") as f:
            html = f.read()

        updated_html = self.apply_wcag_text_spacing(html)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(updated_html)

        print(f"WCAG 1.4.12 spacing applied: {input_path} → {output_path}\n")

    #----- Execution Interface -----#
    def execute(self, html: str) -> dict:
        html_content = html
        """
        Main execution method. Takes an HTML string directly.
        Returns a report with:
          - wcag_status: 'pass' | 'fail' | 'inapplicable'
          - spacing_applied: bool
          - overflow: {status, issues}
          - content_integrity: {status, details}
        """
        # If no relevant text content, WCAG 1.4.12 does not apply
        if not self._has_text_content(html_content):
            print("WCAG 1.4.12: INAPPLICABLE — no text content found\n")
            return {
                "wcag_status": "inapplicable",
                "spacing_applied": False,
                "overflow": {"status": "inapplicable", "issues": []},
                "content_integrity": {"status": "inapplicable", "details": None},
            }

        before_path = self._write_temp(html_content)
        after_html  = self.apply_wcag_text_spacing(html_content)
        after_path  = self._write_temp(after_html)

        print("Processing for WCAG 1.4.12 text spacing...\n")

        spacing_applied = html_content != after_html
        print(f"Spacing applied: {'yes' if spacing_applied else 'no (no matching tags found)'}")

        issues = self.check_overflow(after_path)
        overflow_status = "fail" if issues else "pass"
        if issues:
            print(f"Overflow detected in {len(issues)} element(s):")
            for issue in issues:
                print(f"   <{issue['tag']}> id={issue['id']} | \"{issue['text']}...\"")
                print(f"      scrollH={issue['scrollH']} clientH={issue['clientH']}")
        else:
            print("Overflow check: PASS")

        content_result = self.check_content_integrity(before_path, after_path)

        os.unlink(before_path)
        os.unlink(after_path)

        wcag_status = "fail" if overflow_status == "fail" or content_result["status"] == "fail" else "pass"

        report = {
            "wcag_status": wcag_status,
            "spacing_applied": spacing_applied,
            "overflow": {"status": overflow_status, "issues": issues},
            "content_integrity": content_result,
        }

        return report


# TESTS

def run_tests():
    agent = TextFormattingAgent()
    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"PASS | {name}")
            passed += 1
        else:
            print(f"FAIL | {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    # CSS injection check
    print("\n── CSS Injection ──")

    r = agent.apply_wcag_text_spacing("<p>Hi, this is a test for CSS injection.</p>")
    check("line-height injected",     "line-height: 1.5"       in r)
    check("letter-spacing injected",  "letter-spacing: 0.12em" in r)
    check("word-spacing injected",    "word-spacing: 0.16em"   in r)
    check("margin-bottom injected",   "margin-bottom: 2em"     in r)
    check("margin-top injected",      "margin-top: 2em"        in r)

    r = agent.apply_wcag_text_spacing('<p style="color: red;">Hi, this is a test for CSS injection.</p>')
    check("existing styles preserved", "color: red" in r or "color:red" in r)

    r = agent.apply_wcag_text_spacing("<h1>Title</h1>")
    check("headings get spacing",     "line-height: 1.5" in r)


    # WCAG 1.4.12 HTML Test Cases
    

    # Test 1: FAIL 
    print("\n── Test 1: Stefan/Elias | FAIL | Fixed height clips text ──")
    report = agent.execute("""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="utf-8"><title>Event Card</title>
    <style>
      .event-card { height: 80px; overflow: hidden; border: 1px solid #ccc; padding: 8px; width: 300px; }
      .event-title { line-height: 1.2; font-size: 16px; }
    </style></head>
    <body>
      <div class="event-card">
        <p class="event-title">Annual Accessibility Conference — Improving Digital Inclusion for
        Everyone, Everywhere in 2025</p>
        <p class="event-date">March 15, 2025 · San Francisco</p>
      </div>
    </body>
    </html>
    """)
    check("event card — fixed height clips text (expect: fail)",
          report["wcag_status"] == "fail",
          f"got wcag_status='{report['wcag_status']}'")

    # Test 2: Inapplicable
    print("\n── Test 2: Stefan/Elias | INAPPLICABLE | Video only, no text ──")
    report = agent.execute("""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="utf-8"><title>Tutorial Video</title></head>
    <body>
      <main>
        <video controls width="640" height="360">
          <source src="tutorial.mp4" type="video/mp4">
          <track kind="captions" src="captions.vtt" srclang="en" label="English">
        </video>
      </main>
    </body>
    </html>
    """)
    check("video only — no text content (expect: inapplicable)",
          report["wcag_status"] == "inapplicable",
          f"got wcag_status='{report['wcag_status']}'")

    # Test 3: PASS 
    print("\n── Test 3: Stefan/Elias | PASS | Form with min-height ──")
    report = agent.execute("""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="utf-8"><title>Login</title>
    <style>
      .form-group { margin-bottom: 1.5em; }
      label { display: block; margin-bottom: 0.5em; font-weight: bold; }
      input { width: 100%; padding: 8px; min-height: 44px; box-sizing: border-box; border: 1px solid #666; }
    </style></head>
    <body>
      <h1>Sign In</h1>
      <form>
        <div class="form-group">
          <label for="email">Email address</label>
          <input id="email" type="email" autocomplete="email">
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input id="password" type="password" autocomplete="current-password">
        </div>
        <button type="submit">Sign in</button>
      </form>
    </body>
    </html>
    """)
    check("login form — min-height expands, labels visible (expect: pass)",
          report["wcag_status"] == "pass",
          f"got wcag_status='{report['wcag_status']}'")

    # Test 4: FAIL 
    print("\n── Test 4: Stefan/Elias | FAIL | Nav fixed height clips links ──")
    report = agent.execute("""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="utf-8"><title>Product Nav</title>
    <style>
      .nav-item { display: inline-block; width: 120px; height: 40px; line-height: 40px;
                  letter-spacing: 0; overflow: hidden; text-align: center; }
    </style></head>
    <body>
      <nav aria-label="Categories">
        <span class="nav-item"><a href="/electronics">Electronics</a></span>
        <span class="nav-item"><a href="/clothing">Clothing</a></span>
        <span class="nav-item"><a href="/home">Home &amp; Garden</a></span>
      </nav>
    </body>
    </html>
    """)
    check("product nav — fixed height clips links (expect: fail)",
          report["wcag_status"] == "fail",
          f"got wcag_status='{report['wcag_status']}'")

    # Summary 
    total = passed + failed
    print(f"\n── Results: {passed}/{total} passed ──")
    if failed:
        print(f"   {failed} test(s) failed — review output above")


# ================================================================
if __name__ == "__main__":
    run_tests()
