"""
Readability Analyzer Tool Agent
Calculates readability scores for text content in HTML
Used by: Ian
"""

from bs4 import BeautifulSoup # Handles text analysis and HTML parsing
import textstat
import re
import enchant # Handles dictionary checks for identifying potential abbreviations

class ReadabilityAnalyzerAgent:
    """Calculates various readability metrics for given HTML content."""
    def __init__(self):
        self.d = enchant.Dict("en_US")
    
    def execute(self, html: str) -> dict:
        """
        Analyzes the readability of the text within the given HTML.
        
        Args:
            html: HTML string to analyze.
            
        Returns:
            A dictionary containing various readability scores.
        """
        
        text = self._extract_text(html)
        
        if not text or text.isspace():
            return self._get_default_scores()
        
        abbr_audit = self._analyze_wcag_abbreviations(html)
        potential_unmarked = self._identify_in_text_abbreviations(text)

        marked_terms = [item['text'] for item in abbr_audit['details']]
        true_missing_tags = [word for word in potential_unmarked if word not in marked_terms]

        return {
            "flesch_reading_ease": textstat.flesch_reading_ease(text),
            "flesch_kincaid_grade": textstat.flesch_kincaid_grade(text),
            "gunning_fog": textstat.gunning_fog(text),
            "smog_index": textstat.smog_index(text),
            "automated_readability_index": textstat.automated_readability_index(text),
            "coleman_liau_index": textstat.coleman_liau_index(text),
            "linsear_write_formula": textstat.linsear_write_formula(text),
            "dale_chall_readability_score": textstat.dale_chall_readability_score(text),
            "reading_time_seconds": self._estimate_reading_time(text),
            "word_count": textstat.lexicon_count(text),
            "sentence_count": textstat.sentence_count(text),
            "average_sentence_length": self._average_sentence_length(text),
            "Abbreviation Audit": {
                "total_marked_tags": abbr_audit['total_found'],
                "properly_expanded": abbr_audit['properly_expanded'],
                "missing_titles_list": [f['text'] for f in abbr_audit['details'] if not f['has_expansion']],
                "potential_unmarked_in_text": true_missing_tags
            },
            "tool_name": "ReadabilityAnalyzerAgent",
            
        }

    def _extract_text(self, html: str) -> str:
        """Extracts visible text from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        
        # Get text and clean up whitespace
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return '\n'.join(chunk for chunk in chunks if chunk)

    def _estimate_reading_time(self, text: str, wpm: int = 200) -> float:
        """Estimates reading time in seconds."""
        word_count = textstat.lexicon_count(text)
        return (word_count / wpm) * 60

    def _average_sentence_length(self, text: str) -> float:
        """Calculates average sentence length."""
        words = textstat.lexicon_count(text)
        sentences = textstat.sentence_count(text)
        return words / sentences if sentences > 0 else 0

    def _get_default_scores(self) -> dict:
        """Returns a dictionary with default scores for when there is no text."""
        return {
            "flesch_reading_ease": 0,
            "flesch_kincaid_grade": 0,
            "gunning_fog": 0,
            "smog_index": 0,
            "automated_readability_index": 0,
            "coleman_liau_index": 0,
            "linsear_write_formula": 0,
            "dale_chall_readability_score": 0,
            "reading_time_seconds": 0,
            "word_count": 0,
            "sentence_count": 0,
            "average_sentence_length": 0,
            "tool_name": "ReadabilityAnalyzerAgent"
        }
    
    def _analyze_wcag_abbreviations(self, html: str) -> dict:
        """Checks for WCAG 3.1.4 compliance regarding abbreviations."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # WCAG 3.1.4 looks for <abbr> and legacy <acronym> tags
        abbr_elements = soup.find_all(['abbr', 'acronym'])
        
        findings = []
        total_found = len(abbr_elements)
        properly_expanded = 0

        for el in abbr_elements:
            expansion = el.get('title')
            is_valid = bool(expansion and expansion.strip())
            
            if is_valid:
                properly_expanded += 1
                
            findings.append({
                "tag": el.name,
                "text": el.get_text(strip=True),
                "has_expansion": is_valid,
                "expansion_text": expansion if is_valid else None,
                "outer_html": str(el)
            })

        # Basic compliance score (0.0 to 1.0)
        score = (properly_expanded / total_found) if total_found > 0 else 1.0

        return {
            "total_found": len(abbr_elements),
            "properly_expanded": properly_expanded,
            "details": findings,
            "score": score
        }
    
    def _identify_in_text_abbreviations(self, text: str) -> list:
        """
        Uses a dictionary check to filter out capitalized words from 
        potential abbreviations in the text content itself (items not marked by <abbr> tags).
        Specifically uses MySpell open source online spell checker
        """
        d = self.d
        
        candidates = set(re.findall(r'\b[A-Z]{2,7}\b', text))
        
        true_abbreviations = []
        
        # Check both the uppercase and lowercase versions to see if the word exists in the english dictionary
        for word in candidates:
            is_standard_word = d.check(word.lower()) or d.check(word.capitalize())
            
            # Words that are all caps and not in the dictionary are likely abbreviations
            if not is_standard_word:
                true_abbreviations.append(word)
        return true_abbreviations
# Test
if __name__ == "__main__":
    agent = ReadabilityAnalyzerAgent()

    # Test 1: Simple text
    print("=" * 50)
    print("TEST 1: Simple Text")
    print("=" * 50)
    html_simple = """
    <html><body>
    <p>This is a simple sentence. It is easy to read. See the cat run.</p>
    </body></html>
    """
    result = agent.execute(html_simple)
    print("Result:", result)
    assert result['word_count'] == 14, f"Expected 14 words, got {result['word_count']}"
    assert result['sentence_count'] == 3, f"Expected 3 sentences, got {result['sentence_count']}"
    assert result['flesch_kincaid_grade'] < 5, "Expected grade level below 5 for simple text"
    print("✓ PASS")
    print()

    # Test 2: Complex text
    print("=" * 50)
    print("TEST 2: Complex Text")
    print("=" * 50)
    html_complex = """
    <html><body>
    <p>The Flesch-Kincaid grade level is a readability test designed to indicate
    how difficult a passage in English is to understand. It is the result of the
    Flesch Reading Ease test, which was developed in 1948 by Rudolf Flesch.</p>
    </body></html>
    """
    result = agent.execute(html_complex)
    print("Result:", result)
    assert result['word_count'] == 38
    assert result['flesch_kincaid_grade'] > 8, "Expected grade level above 8 for complex text"
    print("✓ PASS")
    print()

    # Test 3: No text
    print("=" * 50)
    print("TEST 3: No Text")
    print("=" * 50)
    html_no_text = "<html><body><img src='cat.jpg'></body></html>"
    result = agent.execute(html_no_text)
    print("Result:", result)
    assert result['word_count'] == 0, "Expected 0 words"
    assert result['sentence_count'] == 0, "Expected 0 sentences"
    assert result['flesch_kincaid_grade'] == 0, "Expected 0 grade level"
    print("✓ PASS")
    print()


    # Test 4: Abbreviation Properly Expanded Test 
    print("=" * 50)
    print("TEST 4: Abbreviation Test")
    print("=" * 50)
    html_abbr = """
    <html><body>
        <h1>Applying for Benefits</h1>
        <p>
        The <abbr title="Social Security Administration">SSA</abbr> processes all benefit 
        applications within 90 days.
        </p>
        <p>
        You may qualify for 
        <abbr title="Supplemental Nutrition Assistance Program">SNAP</abbr> if your 
        household income is below 130% of the federal poverty level.
        </p>
        <p>
        To apply online, you will need your 
        <abbr title="Social Security Number">SSN</abbr> and a valid 
        <abbr title="Identification">ID</abbr>.
        </p>
    </body></html>
    """
    result = agent.execute(html_abbr)
    print("Result:", result)
    assert result['Abbreviation Audit']['total_marked_tags'] == 4, "Expected 4 marked abbreviations"
    assert result['Abbreviation Audit']['properly_expanded'] == 4, "Expected all abbreviations to be properly expanded"
    assert len(result['Abbreviation Audit']['missing_titles_list']) == 0, "Expected no missing titles"
    print("✓ PASS")
    print()


    # Test 6: Abbreviation Expansion Missing Test
    print("=" * 50)
    print("TEST 5: Abbreviation Test")
    print("=" * 50)
    html_abbr = """
    <html><body>
    <body>
    <main>
        <h1>How to File Your Taxes</h1>
        <p>Download the W-2 form from your employer's HR portal by January 31.</p>
        <p>If you have income from freelance work, you will also need a 1099 form.
        File your return with the IRS by April 15 to avoid penalties.</p>
        <p>Consider using EITC if you qualify — this can significantly reduce your AGI
        and lower the amount you owe to the IRS.</p>
        <p>For complex returns, consult a CPA. VITA offers free tax prep for qualifying filers.</p>
    </main>
    </body>
    </html>""" 
    result = agent.execute(html_abbr)
    print("Result:", result)
    assert result['Abbreviation Audit']['total_marked_tags'] == 0, "Expected 0 marked abbreviations"
    assert result['Abbreviation Audit']['properly_expanded'] == 0, "Expected no abbreviations to be properly expanded"
    assert len(result['Abbreviation Audit']['potential_unmarked_in_text']) >= 4, "Expected at least 4 potential unmarked abbreviations"
    print("✓ PASS")
    print()  

    print("=" * 50)
    print("TEST 5: Abbreviation Test")
    print("=" * 50)
    html_abbr = """
    <html><body>
    <body>
    <main>
        <h1>Referral Letter</h1>
        <p>Patient presents with elevated <abbr>BMI</abbr> and borderline 
        <abbr>HbA1c</abbr> levels. Recommend referral to 
        <abbr>ENT</abbr> for evaluation of 
        <abbr>OSA</abbr> given reported symptoms.</p>
        <p>Please copy the <abbr>GP</abbr> and the 
       <abbr>MDT</abbr> coordinator on all correspondence.</p>
    </main>
    </body>
    </html>""" 
    result = agent.execute(html_abbr)
    print("Result:", result)
    assert result['Abbreviation Audit']['total_marked_tags'] == 6, "Expected 6 marked abbreviations"
    assert result['Abbreviation Audit']['properly_expanded'] == 0, "Expected no abbreviations to be properly expanded"
    assert len(result['Abbreviation Audit']['potential_unmarked_in_text']) == 0, "Expected at least 0 potential unmarked abbreviations"
    print("✓ PASS")
    print()     


    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)