"""
readability_analyzer_agent.py — v2 (patched)

Changes from v1 (marked with [PATCH]):
  [PATCH-1] Detects "first-use expansion" pattern for WCAG 3.1.4 (e.g.,
            "United Nations (UN)" or "UN (United Nations)"). Currently only
            <abbr> elements were checked, missing this common technique.
  [PATCH-2] Detects glossary/definitions links elsewhere on the page. Any of
            the three WCAG 3.1.4 mechanisms is sufficient per the spec.
  [PATCH-3] Filters common-vocabulary acronyms from candidates (USB, HTML,
            API, etc.) to reduce false positives.
  [PATCH-4] Adds supplemental content check for WCAG 3.1.5 (glossary, TL;DR,
            simple-language link, illustrations, video/audio).
  [PATCH-5] Adds explicit applicability signal: text-free pages return
            INAPPLICABLE with the reason, so the LLM correctly predicts
            "inapplicable" instead of misreading zero scores as "passed."
  [PATCH-6] Adds explicit wcag_314_status and wcag_315_status verdicts so
            the LLM has clear signals to reason from.

Drop-in replacement. Keeps class name ReadabilityAnalyzerAgent and public
interface (execute(html) -> dict).

Used by: Ian (3.1.4, 3.1.5), Sophie (3.1.4), Stefan (3.1.4).
"""

from bs4 import BeautifulSoup
import textstat
import re
import enchant


# Acronyms so widely known they do not require expansion per WCAG intent.
# Reduces false positives on Ian's 3.1.4 tool calls.
COMMON_VOCABULARY_ACRONYMS = {
    "USA", "UK", "EU", "USB", "PDF", "HTML", "CSS", "JS", "API",
    "URL", "URI", "AM", "PM", "AI", "IT", "TV", "OK", "DVD", "CD",
    "GPS", "FAQ", "CEO", "CTO", "CFO", "HR", "IP", "OS", "PC",
    "SMS", "MMS", "3D", "2D", "HD", "UHD", "GB", "MB", "KB", "TB",
    "AC", "DC", "UV", "SUV", "ATM", "PIN", "DIY", "DNA",
}

# Patterns that indicate supplemental / simpler content is available for 3.1.5
SUPPLEMENTAL_LINK_PATTERNS = re.compile(
    r"plain[\s\-]?language|easy[\s\-]?read|simple[\s\-]?version|"
    r"summary|tldr|tl;?dr|in[\s\-]?brief|overview|abstract",
    re.IGNORECASE,
)

GLOSSARY_LINK_PATTERNS = re.compile(
    r"glossary|definitions?|acronyms?|abbreviations?|terminology",
    re.IGNORECASE,
)


class ReadabilityAnalyzerAgent:
    """Text readability + WCAG 3.1.4 abbreviations + 3.1.5 reading level."""

    def execute(self, html: str) -> dict:
        text = self._extract_text(html)
        soup = BeautifulSoup(html, "html.parser")

        # [PATCH-5] Explicit applicability
        word_count = textstat.lexicon_count(text) if text and not text.isspace() else 0

        if word_count < 50:
            return {
                "applicability": {
                    "applies": False,
                    "reason": (
                        f"Text content is minimal ({word_count} words). "
                        "Reading level and abbreviation checks are not "
                        "meaningful on such short text."
                    ),
                },
                "wcag_314_status": "INAPPLICABLE",
                "wcag_315_status": "INAPPLICABLE",
                "word_count": word_count,
                "tool_name": "ReadabilityAnalyzerAgent",
            }

        # ==============================================================
        # Compute readability scores (unchanged from v1)
        # ==============================================================
        readability = {
            "flesch_reading_ease": textstat.flesch_reading_ease(text),
            "flesch_kincaid_grade": textstat.flesch_kincaid_grade(text),
            "gunning_fog": textstat.gunning_fog(text),
            "smog_index": textstat.smog_index(text),
            "automated_readability_index": textstat.automated_readability_index(text),
            "coleman_liau_index": textstat.coleman_liau_index(text),
            "linsear_write_formula": textstat.linsear_write_formula(text),
            "dale_chall_readability_score": textstat.dale_chall_readability_score(text),
            "reading_time_seconds": self._estimate_reading_time(text),
            "word_count": word_count,
            "sentence_count": textstat.sentence_count(text),
            "average_sentence_length": self._average_sentence_length(text),
        }

        # ==============================================================
        # [PATCH-1,2,3] WCAG 3.1.4 Abbreviations — three-mechanism check
        # ==============================================================
        abbr_result = self._check_abbreviations_three_mechanisms(soup, text)

        # ==============================================================
        # [PATCH-4] WCAG 3.1.5 Reading Level — supplemental content
        # ==============================================================
        supplemental = self._check_supplemental_content(soup)
        wcag_315 = self._verdict_315(readability, supplemental)

        return {
            "applicability": {"applies": True, "elements_present": {"text_words": word_count}},
            **readability,
            "wcag_314": abbr_result,
            "wcag_314_status": abbr_result["verdict"],
            "wcag_315": {
                "readability_suggests_above_secondary": (
                    readability["flesch_kincaid_grade"] >= 9
                ),
                "supplemental_content": supplemental,
            },
            "wcag_315_status": wcag_315,
            "tool_name": "ReadabilityAnalyzerAgent",
        }

    # ------------------------------------------------------------------ #
    #  [PATCH-1,2,3] Three-mechanism abbreviation check                    #
    # ------------------------------------------------------------------ #

    def _check_abbreviations_three_mechanisms(self, soup, text):
        """
        WCAG 3.1.4 is satisfied by ANY of:
          1. <abbr title="expansion">
          2. First-use expansion pattern
          3. Glossary/definitions link elsewhere on page
        """
        # Extract candidate abbreviations
        raw_candidates = set(re.findall(r"\b[A-Z]{2,6}\b", text))
        candidates = raw_candidates - COMMON_VOCABULARY_ACRONYMS

        # Filter out proper nouns using dictionary check
        try:
            en_dict = enchant.Dict("en_US")
            candidates = {c for c in candidates if not en_dict.check(c.capitalize())}
        except Exception:
            pass  # If enchant unavailable, keep all candidates

        # Check global glossary presence (one signal covers all abbreviations)
        glossary_link_present = self._detect_glossary_link(soup)

        # Per-abbreviation analysis
        per_abbr = {}
        for abbr in candidates:
            mechanisms = {
                "abbr_element_present": self._check_abbr_element(soup, abbr),
                "first_use_expansion": self._check_first_use_expansion(text, abbr),
                "glossary_link_present": glossary_link_present,
            }
            per_abbr[abbr] = {
                "has_any_mechanism": any(mechanisms.values()),
                "mechanisms": mechanisms,
            }

        # Verdict
        if not candidates:
            verdict = "PASS"
            evidence = "No abbreviations detected in content."
        else:
            failing = [a for a, r in per_abbr.items() if not r["has_any_mechanism"]]
            if not failing:
                verdict = "PASS"
                evidence = (
                    f"All {len(candidates)} detected abbreviations have at least "
                    f"one WCAG 3.1.4 mechanism (abbr element, first-use expansion, "
                    f"or glossary link)."
                )
            else:
                verdict = "FAIL"
                evidence = (
                    f"{len(failing)} abbreviations lack any expansion mechanism: "
                    f"{sorted(failing)[:5]}"
                )

        return {
            "verdict": verdict,
            "evidence": evidence,
            "candidates_detected": sorted(candidates),
            "glossary_link_present_on_page": glossary_link_present,
            "per_abbreviation": per_abbr,
        }

    def _check_abbr_element(self, soup, abbr):
        for el in soup.find_all("abbr"):
            if el.get_text(strip=True) == abbr and el.get("title"):
                return True
        return False

    def _check_first_use_expansion(self, text, abbr):
        """
        Detect patterns like:
          "United Nations (UN)"
          "UN (United Nations)"
          "United Nations, or UN, ..."
        """
        # Pattern 1: "Expansion (ABBR)"
        pat1 = rf"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){{1,5}})\s*\(\s*{re.escape(abbr)}\s*\)"
        if re.search(pat1, text):
            return True
        # Pattern 2: "ABBR (Expansion)"
        pat2 = rf"\b{re.escape(abbr)}\s*\(\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){{1,5}})\s*\)"
        if re.search(pat2, text):
            return True
        # Pattern 3: "Expansion, or ABBR,"
        pat3 = rf"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){{1,5}}),?\s+or\s+{re.escape(abbr)}[\s,]"
        if re.search(pat3, text):
            return True
        return False

    def _detect_glossary_link(self, soup):
        """Check for glossary/definitions links anywhere on the page."""
        # Link text
        for a in soup.find_all("a"):
            if GLOSSARY_LINK_PATTERNS.search(a.get_text(strip=True) or ""):
                return True
            href = a.get("href", "")
            if GLOSSARY_LINK_PATTERNS.search(href):
                return True
        return False

    # ------------------------------------------------------------------ #
    #  [PATCH-4] Supplemental content check for 3.1.5                      #
    # ------------------------------------------------------------------ #

    def _check_supplemental_content(self, soup):
        """Detect content that provides simpler alternatives for hard text."""
        results = {
            "glossary_link": self._detect_glossary_link(soup),
            "summary_section": False,
            "simple_language_link": False,
            "illustrations_with_caption": 0,
            "audio_or_video_present": False,
            "descriptive_alt_images": 0,
        }

        # Summary section
        for el in soup.find_all(True):
            classes = " ".join(el.get("class", []))
            id_str = el.get("id", "")
            if SUPPLEMENTAL_LINK_PATTERNS.search(classes + " " + id_str):
                results["summary_section"] = True
                break
        # aria-label / role=doc-abstract
        if soup.find(attrs={"role": "doc-abstract"}):
            results["summary_section"] = True

        # Simple-language link
        for a in soup.find_all("a"):
            if SUPPLEMENTAL_LINK_PATTERNS.search(a.get_text(strip=True) or ""):
                results["simple_language_link"] = True
                break

        # Illustrations
        results["illustrations_with_caption"] = len(soup.find_all("figcaption"))

        # Audio/video
        results["audio_or_video_present"] = bool(
            soup.find_all(["audio", "video"])
        )

        # Images with descriptive alt (>= 20 chars)
        for img in soup.find_all("img"):
            alt = img.get("alt", "")
            if alt and len(alt) >= 20:
                results["descriptive_alt_images"] += 1

        results["has_any_supplemental"] = any([
            results["glossary_link"],
            results["summary_section"],
            results["simple_language_link"],
            results["illustrations_with_caption"] > 0,
            results["audio_or_video_present"],
            results["descriptive_alt_images"] > 0,
        ])
        return results

    def _verdict_315(self, readability, supplemental):
        """
        WCAG 3.1.5 verdict rules:
          - Reading grade < 9 (below secondary): PASS (criterion doesn't trigger)
          - Grade >= 9 AND supplemental present: PASS
          - Grade >= 9 AND no supplemental: FAIL
        """
        fkg = readability.get("flesch_kincaid_grade", 0)
        if fkg < 9:
            return "PASS"
        if supplemental.get("has_any_supplemental"):
            return "PASS"
        return "FAIL"

    # ------------------------------------------------------------------ #
    #  Existing v1 helpers (kept)                                          #
    # ------------------------------------------------------------------ #

    def _extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return "\n".join(chunk for chunk in chunks if chunk)

    def _estimate_reading_time(self, text: str, wpm: int = 200) -> float:
        words = len(text.split())
        return round((words / wpm) * 60, 1)

    def _average_sentence_length(self, text: str) -> float:
        sents = textstat.sentence_count(text)
        words = textstat.lexicon_count(text)
        if sents == 0:
            return 0
        return round(words / sents, 1)
