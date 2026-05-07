"""
Consistency Validator Tool Agent
Analyzes multiple pages to detect inconsistencies in layout and navigation.
Used by: Ian, Ade
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

class ConsistencyValidatorAgent:
    """
    Checks for structural and navigational consistency across a set of pages from the same website.
    Aims to address issues faced by users like Ian, who benefit from predictable layouts.
    """

    def execute(self, html_pages: list) -> dict:
        """
        Analyzes a list of HTML pages for inconsistencies.

        Args:
            html_pages: A list of HTML content strings.

        Returns:
            A dictionary containing the analysis results.
        """
        if not html_pages or len(html_pages) < 2:
            return {
                "summary": "At least two pages are required for a consistency check.",
                "pages_analyzed": len(html_pages) if html_pages else 0,
                "issues_found": 0,
                "inconsistencies": [],
                "tool_name": "ConsistencyValidatorAgent"
            }

        driver = self._start_browser()
        try:
            fingerprints = []
            for html in html_pages:
                driver.get(f"data:text/html;charset=utf-8,{html}")
                time.sleep(0.5)
                fingerprints.append(self._get_page_fingerprint(driver))

            inconsistencies = self._compare_fingerprints(fingerprints)
            
            summary = f"Analyzed {len(html_pages)} pages. Found {len(inconsistencies)} potential inconsistencies."

            return {
                "summary": summary,
                "pages_analyzed": len(html_pages),
                "issues_found": len(inconsistencies),
                "inconsistencies": inconsistencies,
                "tool_name": "ConsistencyValidatorAgent"
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

    def _get_page_fingerprint(self, driver) -> dict:
        """Extracts a structural 'fingerprint' from the current page."""
        
        # 1. Get Landmark Order
        get_landmarks_script = """
            const landmark_elements = document.querySelectorAll('header, nav, main, footer, aside');
            const landmarks = [];
            landmark_elements.forEach(el => landmarks.push(el.tagName.toLowerCase()));
            return landmarks;
        """
        landmarks = driver.execute_script(get_landmarks_script)
        
        # 2. Get Navigation Links
        get_nav_links_script = """
            const nav = document.querySelector('nav');
            if (!nav) return [];
            const links = [];
            nav.querySelectorAll('a').forEach(a => {
                links.push({
                    text: a.textContent.trim(),
                    href: a.getAttribute('href') || ''
                });
            });
            return links;
        """
        nav_links = driver.execute_script(get_nav_links_script)

        return {
            "landmarks": landmarks,
            "nav_links": nav_links,
        }

    def _compare_fingerprints(self, fingerprints: list) -> list:
        """Compares page fingerprints against the first page as a baseline."""
        baseline = fingerprints[0]
        issues = []

        for i, current in enumerate(fingerprints[1:]):
            page_index = i + 1

            # Compare landmark order
            if baseline["landmarks"] != current["landmarks"]:
                issues.append({
                    "type": "LANDMARK_ORDER",
                    "page_index": page_index,
                    "baseline": baseline["landmarks"],
                    "found": current["landmarks"],
                    "message": f"Page {page_index} has a different order of landmark elements."
                })

            # Compare navigation links (simple comparison of the list of dicts)
            if baseline["nav_links"] != current["nav_links"]:
                baseline_links = {f"{link['text']}|{link['href']}" for link in baseline["nav_links"]}
                current_links = {f"{link['text']}|{link['href']}" for link in current["nav_links"]}
                
                missing = baseline_links - current_links
                added = current_links - baseline_links

                message = f"Page {page_index} has different navigation links."
                if missing:
                    message += f" Missing: {list(missing)}."
                if added:
                    message += f" Added: {list(added)}."
                
                issues.append({
                    "type": "NAVIGATION_LINKS",
                    "page_index": page_index,
                    "message": message
                })
        
        return issues


# Test cases
if __name__ == "__main__":
    agent = ConsistencyValidatorAgent()

    base_nav = "<nav><a href='/'>Home</a><a href='/about'>About</a></nav>"
    header = "<header><h1>My Site</h1></header>"
    main = "<main><p>Content</p></main>"
    footer = "<footer><p>&copy; 2026</p></footer>"

    # Page set 1: Consistent pages
    page1_ok = f"<body>{header}{base_nav}{main}{footer}</body>"
    page2_ok = f"<body>{header}{base_nav}{main}{footer}</body>"
    
    print("=" * 50)
    print("TEST 1: Consistent Pages")
    result_ok = agent.execute([page1_ok, page2_ok])
    print(result_ok)
    assert result_ok['issues_found'] == 0, "Test 1 Failed: Should find no issues."
    print("✓ PASS")
    print()

    # Page set 2: Inconsistent landmarks
    page1_landmarks = f"<body>{header}{base_nav}{main}{footer}</body>"
    page2_landmarks = f"<body>{header}{main}{base_nav}{footer}</body>" # Swapped main and nav
    
    print("=" * 50)
    print("TEST 2: Inconsistent Landmarks")
    result_landmarks = agent.execute([page1_landmarks, page2_landmarks])
    print(result_landmarks)
    assert result_landmarks['issues_found'] > 0, "Test 2 Failed: Should find landmark issue."
    assert result_landmarks['inconsistencies'][0]['type'] == 'LANDMARK_ORDER', "Test 2 Failed: Should be landmark issue type."
    print("✓ PASS")
    print()

    # Page set 3: Inconsistent navigation
    page1_nav = f"<body>{header}{base_nav}{main}{footer}</body>"
    page2_nav_bad = f"<body>{header}<nav><a href='/'>Home</a><a href='/contact'>Contact</a></nav>{main}{footer}</body>"

    print("=" * 50)
    print("TEST 3: Inconsistent Navigation")
    result_nav = agent.execute([page1_nav, page2_nav_bad])
    print(result_nav)
    assert result_nav['issues_found'] > 0, "Test 3 Failed: Should find navigation issue."
    assert result_nav['inconsistencies'][0]['type'] == 'NAVIGATION_LINKS', "Test 3 Failed: Should be navigation issue type."
    print("✓ PASS")
    print()
    
    # Page set 4: One page only
    print("=" * 50)
    print("TEST 4: Only one page provided")
    result_one = agent.execute([page1_ok])
    print(result_one)
    assert result_one['pages_analyzed'] == 1, "Test 4 Failed: Should show 1 page analyzed."
    assert "required" in result_one['summary'], "Test 4 Failed: Summary should mention requirement."
    print("✓ PASS")
    print()
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
