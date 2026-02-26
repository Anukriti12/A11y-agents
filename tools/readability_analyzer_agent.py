"""
Readability Analyzer Tool Agent
Calculates readability scores for text content in HTML
Used by: Ian
"""

from bs4 import BeautifulSoup # Handles text analysis and HTML parsing
import textstat
import re

class ReadabilityAnalyzerAgent:
    """Calculates various readability metrics for given HTML content."""
    
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
            "tool_name": "ReadabilityAnalyzerAgent"
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

    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
