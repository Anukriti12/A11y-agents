"""
Heading Structure Agent
Analyzes heading hierarchy, logical structure, and content quality
Used by: Stefan, Lakshmi, Sophie, Elias
WCAG: 1.3.1 (Info and Relationships), 2.4.6 (Headings and Labels)
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re

class HeadingStructureAgent:
    """
    Validates heading structure for navigation and comprehension.
    
    Goes beyond axe-core by checking:
    - Content quality (descriptive vs generic)
    - Text density between headings
    - Logical hierarchy (no skipped levels)
    - First heading appropriateness
    """
    
    def execute(self, html):
        """
        Analyze heading structure and quality.
        
        Args:
            html: HTML string to analyze
        
        Returns:
            {
                "headings": [...],
                "total_count": int,
                "hierarchy_valid": bool,
                "hierarchy_issues": [...],
                "generic_headings": [...],
                "words_between_headings": [...],
                "max_words_between_headings": int,
                "missing_h1": bool,
                "multiple_h1": bool,
                "skipped_levels": [...],
                "tool_name": "HeadingStructureAgent"
            }
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract all headings with positions
        headings = self._extract_headings(soup)
        
        # Check hierarchy validity
        hierarchy_issues = self._validate_hierarchy(headings)
        
        # Identify generic/uninformative headings
        generic_headings = self._find_generic_headings(headings)
        
        # Calculate text density between headings
        words_between = self._calculate_words_between_headings(soup, headings)
        
        # Check for H1 issues
        h1_issues = self._check_h1_usage(headings)
        
        # Find skipped levels
        skipped_levels = self._find_skipped_levels(headings)
        
        return {
            "headings": headings,
            "total_count": len(headings),
            "hierarchy_valid": len(hierarchy_issues) == 0,
            "hierarchy_issues": hierarchy_issues,
            "generic_headings": generic_headings,
            "words_between_headings": words_between,
            "max_words_between_headings": max(words_between) if words_between else 0,
            "missing_h1": h1_issues["missing_h1"],
            "multiple_h1": h1_issues["multiple_h1"],
            "h1_count": h1_issues["h1_count"],
            "skipped_levels": skipped_levels,
            "tool_name": "HeadingStructureAgent"
        }
    
    def _extract_headings(self, soup):
        """
        Extract all headings with their level, text, and position.
        
        Returns:
            [
                {
                    "level": 1,
                    "tag": "h1",
                    "text": "Main Title",
                    "id": "main-title",
                    "position": 0,
                    "word_count": 2
                },
                ...
            ]
        """
        
        headings = []
        
        # Find all heading elements
        for position, heading_elem in enumerate(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])):
            level = int(heading_elem.name[1])  # Extract level from h1, h2, etc.
            text = heading_elem.get_text(strip=True)
            word_count = len(text.split())
            
            headings.append({
                "level": level,
                "tag": heading_elem.name,
                "text": text,
                "id": heading_elem.get('id', ''),
                "class": heading_elem.get('class', []),
                "position": position,
                "word_count": word_count
            })
        
        return headings
    
    def _validate_hierarchy(self, headings):
        """
        Check for logical heading hierarchy.
        
        Issues to detect:
        - Skipped levels (h1 → h3, skipping h2)
        - Improper nesting
        """
        
        issues = []
        
        if not headings:
            issues.append({
                "type": "no_headings",
                "message": "Page has no headings for structure",
                "severity": "serious"
            })
            return issues
        
        # Check for skipped levels
        for i in range(len(headings) - 1):
            current_level = headings[i]["level"]
            next_level = headings[i + 1]["level"]
            
            # If next level is more than 1 greater than current
            if next_level > current_level + 1:
                issues.append({
                    "type": "skipped_level",
                    "message": f"Heading hierarchy skips from H{current_level} to H{next_level}",
                    "from_heading": headings[i]["text"],
                    "to_heading": headings[i + 1]["text"],
                    "position": i + 1,
                    "severity": "moderate"
                })
        
        return issues
    
    def _find_generic_headings(self, headings):
        """
        Identify headings with generic/uninformative text.
        
        Generic patterns:
        - "Section", "Content", "Information"
        - Single words without context
        - Numbers only
        - "Click here", "Read more"
        """
        
        generic_patterns = [
            'section', 'content', 'information', 'details', 'description',
            'untitled', 'heading', 'title', 'text', 'item', 'entry',
            'click here', 'read more', 'more info', 'learn more'
        ]
        
        generic_headings = []
        
        for heading in headings:
            text = heading["text"].lower().strip()
            
            # Check if matches generic patterns
            if text in generic_patterns:
                generic_headings.append({
                    **heading,
                    "issue": "generic_text",
                    "severity": "moderate"
                })
            
            # Check if only numbers
            elif re.match(r'^\d+$', text):
                generic_headings.append({
                    **heading,
                    "issue": "numbers_only",
                    "severity": "serious"
                })
            
            # Check if too short (1-2 characters)
            elif len(text) <= 2:
                generic_headings.append({
                    **heading,
                    "issue": "too_short",
                    "severity": "serious"
                })
            
            # Check if single word without descriptive value
            elif heading["word_count"] == 1 and len(text) < 8:
                # Allow common descriptive single words
                allowed_single_words = ['home', 'about', 'contact', 'blog', 'news', 'products', 'services']
                if text not in allowed_single_words:
                    generic_headings.append({
                        **heading,
                        "issue": "single_word_vague",
                        "severity": "minor"
                    })
        
        return generic_headings
    
    def _calculate_words_between_headings(self, soup, headings):
        """
        Calculate word count between headings to identify "walls of text".
        
        Important for:
        - Stefan: Loses place in dense text without heading anchors
        - Sophie: Overwhelmed by long paragraphs
        - Lakshmi: Needs headings for efficient navigation
        
        Returns:
            [150, 320, 89, ...]  # Word counts between each heading
        """
        
        if not headings:
            # Count all body text if no headings
            body = soup.find('body')
            if body:
                text = body.get_text()
                return [len(text.split())]
            return [0]
        
        words_between = []
        
        # Get all heading elements in order
        all_headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        for i in range(len(all_headings)):
            # Count words between this heading and the next
            current_heading = all_headings[i]
            next_heading = all_headings[i + 1] if i + 1 < len(all_headings) else None
            
            # Get all text between headings
            text_content = []
            for sibling in current_heading.next_siblings:
                if sibling == next_heading:
                    break
                if hasattr(sibling, 'get_text'):
                    text_content.append(sibling.get_text())
                elif isinstance(sibling, str):
                    text_content.append(sibling)
            
            combined_text = ' '.join(text_content)
            word_count = len(combined_text.split())
            words_between.append(word_count)
        
        return words_between
    
    def _check_h1_usage(self, headings):
        """
        Check for proper H1 usage.
        
        Rules:
        - Should have exactly one H1
        - H1 should be first heading (usually)
        """
        
        h1_headings = [h for h in headings if h["level"] == 1]
        h1_count = len(h1_headings)
        
        missing_h1 = h1_count == 0
        multiple_h1 = h1_count > 1
        
        return {
            "h1_count": h1_count,
            "missing_h1": missing_h1,
            "multiple_h1": multiple_h1,
            "h1_headings": h1_headings
        }
    
    def _find_skipped_levels(self, headings):
        """
        Find all instances of skipped heading levels.
        
        Returns:
            [
                {"from": 1, "to": 3, "position": 2},
                ...
            ]
        """
        
        skipped = []
        
        for i in range(len(headings) - 1):
            current_level = headings[i]["level"]
            next_level = headings[i + 1]["level"]
            
            if next_level > current_level + 1:
                skipped.append({
                    "from": current_level,
                    "to": next_level,
                    "skipped": next_level - current_level - 1,
                    "position": i + 1,
                    "from_text": headings[i]["text"],
                    "to_text": headings[i + 1]["text"]
                })
        
        return skipped


# Tests
if __name__ == "__main__":
    agent = HeadingStructureAgent()
    
    # Test 1: Good structure
    print("=" * 60)
    print("TEST 1: Good heading structure")
    print("=" * 60)
    
    test_html_1 = """
    <html>
    <body>
        <h1>Main Page Title</h1>
        <p>Introductory paragraph with about 50 words of text that provides context
           for the page content and helps users understand what they will find here.</p>
        
        <h2>First Section</h2>
        <p>Some content for the first section. This is a reasonable amount of text
           between headings - not too much, not too little.</p>
        
        <h3>Subsection A</h3>
        <p>Content for subsection A.</p>
        
        <h3>Subsection B</h3>
        <p>Content for subsection B.</p>
        
        <h2>Second Section</h2>
        <p>Content for second section.</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_1)
    print(f"Total headings: {result['total_count']}")
    print(f"Hierarchy valid: {result['hierarchy_valid']}")
    print(f"Missing H1: {result['missing_h1']}")
    print(f"Multiple H1: {result['multiple_h1']}")
    print(f"Generic headings: {len(result['generic_headings'])}")
    print(f"Max words between headings: {result['max_words_between_headings']}")
    assert result['hierarchy_valid'] == True
    assert result['missing_h1'] == False
    print("✓ PASS\n")
    
    # Test 2: Skipped levels
    print("=" * 60)
    print("TEST 2: Skipped heading levels (h1 → h3)")
    print("=" * 60)
    
    test_html_2 = """
    <html>
    <body>
        <h1>Main Title</h1>
        <h3>Skipped H2, went straight to H3</h3>
        <p>This is bad for hierarchy.</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_2)
    print(f"Hierarchy valid: {result['hierarchy_valid']}")
    print(f"Skipped levels: {result['skipped_levels']}")
    print(f"Issues: {result['hierarchy_issues']}")
    assert result['hierarchy_valid'] == False
    assert len(result['skipped_levels']) == 1
    print("✓ PASS\n")
    
    # Test 3: Generic headings
    print("=" * 60)
    print("TEST 3: Generic/uninformative headings")
    print("=" * 60)
    
    test_html_3 = """
    <html>
    <body>
        <h1>Welcome</h1>
        <h2>Section</h2>
        <p>Generic heading above.</p>
        
        <h2>Content</h2>
        <p>Another generic heading.</p>
        
        <h2>1</h2>
        <p>Just a number.</p>
        
        <h2>Product Details and Features</h2>
        <p>This one is descriptive!</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_3)
    print(f"Generic headings found: {len(result['generic_headings'])}")
    for generic in result['generic_headings']:
        print(f"  - '{generic['text']}' (issue: {generic['issue']})")
    assert len(result['generic_headings']) >= 3  # Section, Content, 1
    print("✓ PASS\n")
    
    # Test 4: Wall of text (no headings for 500+ words)
    print("=" * 60)
    print("TEST 4: Wall of text - too many words between headings")
    print("=" * 60)
    
    long_text = " ".join(["word"] * 600)  # 600 words
    
    test_html_4 = f"""
    <html>
    <body>
        <h1>Title</h1>
        <p>{long_text}</p>
        <h2>Finally Another Heading</h2>
        <p>Some more text.</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_4)
    print(f"Max words between headings: {result['max_words_between_headings']}")
    print(f"Words between each heading: {result['words_between_headings']}")
    assert result['max_words_between_headings'] > 500
    print("✓ PASS (detected wall of text)\n")
    
    # Test 5: Missing H1
    print("=" * 60)
    print("TEST 5: Missing H1")
    print("=" * 60)
    
    test_html_5 = """
    <html>
    <body>
        <h2>Started with H2</h2>
        <p>No H1 on page.</p>
        
        <h3>Subsection</h3>
        <p>Still no H1.</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_5)
    print(f"Missing H1: {result['missing_h1']}")
    print(f"H1 count: {result['h1_count']}")
    assert result['missing_h1'] == True
    print("✓ PASS\n")
    
    # Test 6: Multiple H1s
    print("=" * 60)
    print("TEST 6: Multiple H1s (problematic)")
    print("=" * 60)
    
    test_html_6 = """
    <html>
    <body>
        <h1>First H1</h1>
        <p>Some content.</p>
        
        <h1>Second H1</h1>
        <p>This is confusing.</p>
        
        <h1>Third H1</h1>
        <p>Way too many top-level headings.</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_6)
    print(f"Multiple H1: {result['multiple_h1']}")
    print(f"H1 count: {result['h1_count']}")
    assert result['multiple_h1'] == True
    assert result['h1_count'] == 3
    print("✓ PASS\n")
    
    # Test 7: No headings at all
    print("=" * 60)
    print("TEST 7: No headings (serious issue)")
    print("=" * 60)
    
    test_html_7 = """
    <html>
    <body>
        <p>This page has no headings at all.</p>
        <p>Just paragraphs of text.</p>
        <p>Very difficult to navigate or understand structure.</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_7)
    print(f"Total headings: {result['total_count']}")
    print(f"Hierarchy issues: {result['hierarchy_issues']}")
    assert result['total_count'] == 0
    assert len(result['hierarchy_issues']) > 0
    print("✓ PASS\n")
    
    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)