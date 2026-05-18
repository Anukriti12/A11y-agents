"""
Elias Agent - Low Vision + Essential Tremor
Refactored to class-based architecture with BaseAgenticAgent
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from personas.base_agent import BaseAgenticAgent
from tools import Contrast_Checker_Agent
from tools import animation_detector_agent
from tools import autocomplete_validator_agent
from tools import heading_structure_agent
from tools import target_size_validator_agent
from tools import text_formatting_agent

load_dotenv()

ELIAS_SYSTEM_PROMPT = """
You are Elias, a retired teacher with low vision and essential tremor.

You use screen magnification (200-300% zoom) to read text. You have difficulty with:
- Low contrast text (you need AAA contrast 7:1)
- Tiny fonts that disappear when you zoom
- Small click targets (tremor makes precise clicking hard)
- Motion and animations (trigger nausea and disorientation)
- Fixed layouts that don't reflow when zoomed

Output ONLY valid JSON (no preamble):
{
  "label": "passed" | "failed" | "inapplicable",
  "severity": "critical" | "serious" | "moderate" | "minor" | "N/A",
  "issues": [
    {
      "wcag": "X.X.X",
      "evidence": "What the tool found",
      "persona_impact": "Why this affects YOU as Elias with low vision and tremor",
      "recommendation": "How to fix it"
    }
  ],
  "overall_assessment": "Brief summary"
}

DECISION CRITERIA:
- FAILED = Barriers for magnification users or users with tremor
- PASSED = Content works well when zoomed, targets are large enough
- Severity:
  - CRITICAL: Prevents access (severe contrast failure, content clips when zoomed)
  - SERIOUS: Major barrier (AAA contrast failure, tiny targets, autoplay animations)
  - MODERATE: Inconvenient (poor heading structure)

TOOL USAGE:
- Always call check_aaa_color_contrast (Elias needs enhanced 7:1 contrast)
- If interactive elements → Call validate_target_size (tremor needs large targets)
- If animations/video → Call detect_animations_and_autoplay_media
- If text present → Call check_wcag_text_spacing_and_reflow (zoom issues)
- If headings → Call analyze_heading_structure

INTERPRETING RESULTS:
- check_aaa_color_contrast: If violations found → FAILED serious
- validate_target_size: If targets < 44x44px → FAILED serious
- detect_animations: If autoplay or flashing → FAILED serious (triggers nausea)
- check_wcag_text_spacing: If content clips when zoomed → FAILED critical
"""

class EliasAgent(BaseAgenticAgent):
    def __init__(self, api_key):
        super().__init__(api_key, persona_name="Elias")
        
        self.contrast_agent = Contrast_Checker_Agent.ContrastAAA_HTML_Agent()
        self.animation_agent = animation_detector_agent.AnimationDetectorAgent()
        self.autocomplete_agent = autocomplete_validator_agent.AutocompleteValidatorAgent()
        self.heading_agent = heading_structure_agent.HeadingStructureAgent()
        self.target_size_agent = target_size_validator_agent.TargetSizeValidatorAgent()
        self.text_formatting_agent_inst = text_formatting_agent.TextFormattingAgent()
        
        self.tool_dispatcher = {
            "check_aaa_color_contrast": self.contrast_agent.execute,
            "detect_animations_and_autoplay_media": self.animation_agent.execute,
            "validate_autocomplete_and_autofill": self.autocomplete_agent.execute,
            "analyze_heading_structure": self.heading_agent.execute,
            "validate_target_size": self.target_size_agent.execute,
            "check_wcag_text_spacing_and_reflow": self.text_formatting_agent_inst.execute
        }
    
    def get_system_prompt(self):
        return ELIAS_SYSTEM_PROMPT
    
    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_aaa_color_contrast",
                    "description": """
[WHAT] Runs axe-core color contrast checks at WCAG AAA level (7:1 for normal text, 4.5:1 for large).

[WHEN] Use this when:
- Page has text content with colored backgrounds
- Evaluating readability for low vision users
- Checking if text is visible when magnified

[WHO] CRITICAL for Elias (low vision - needs enhanced contrast to read)
- Elias: With low vision, pale text disappears - needs 7:1 contrast to see clearly
- Also helps: Older users, users in bright sunlight

[RETURNS]
- contrast_violations: Elements failing AAA standard
- contrast_ratios: Actual measured ratios
- If violations found → FAILED serious (Elias can't read the text)

[DON'T USE]
- Page is image-only with no text
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "detect_animations_and_autoplay_media",
                    "description": """
[WHAT] Detects CSS animations, autoplay video/audio, flashing content (WCAG 2.3.3, 1.4.2, 2.2.2).

[WHEN] Use when:
- Page has <video>, <audio>, or animated CSS
- Checking for motion that could trigger nausea
- Evaluating if user can control animations

[WHO] CRITICAL for Elias (motion triggers severe nausea and disorientation)
- Elias: Autoplay videos while he's trying to read magnified text cause nausea
- Flashing animations worsen with magnification
- Also helps: Users with vestibular disorders, Ian (autism - unexpected motion)

[RETURNS]
- animation_count: Number of animated elements
- autoplay_found: Boolean - autoplay video/audio?
- controls_available: Can user pause/stop?
- If autoplay OR flashing → FAILED serious

[DON'T USE]
- Static page with no motion
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_autocomplete_and_autofill",
                    "description": """
[WHAT] Validates autocomplete attributes on form fields (WCAG 1.3.5).

[WHEN] Use when:
- HTML has <form> with input fields
- Checking if forms reduce typing burden

[WHO] Important for Elias (tremor makes typing difficult and error-prone)
- Elias: Autocomplete reduces typing - tremor makes accurate typing exhausting
- Also helps: Sophie (reduces memory burden), Ade (faster than voice typing)

[RETURNS]
- missing_autocomplete: Fields that should have autocomplete
- If missing_autocomplete found → FAILED moderate

[DON'T USE]
- No forms present
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_heading_structure",
                    "description": """
[WHAT] Analyzes heading hierarchy and structure (WCAG 1.3.1, 2.4.6).

[WHEN] Use when page has headings.

[WHO] Helps Elias navigate when using screen magnification
- Clear headings help Elias understand page structure when he can only see small portions

[RETURNS]
- skipped_levels, generic_headings
- If issues found → FAILED moderate

[DON'T USE]
- No headings present
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_target_size",
                    "description": """
[WHAT] Checks for interactive elements smaller than 44x44 pixels (WCAG 2.5.5).

[WHEN] Use when:
- Page has buttons, links, or other clickable elements
- Checking if targets are large enough for tremor

[WHO] CRITICAL for Elias (essential tremor makes precise clicking impossible)
- Elias: Tremor means he often misses small targets - needs 44x44px minimum
- Also helps: Ade (adaptive devices), mobile users

[RETURNS]
- undersized_targets: Elements < 44x44px → FAILED serious
- target_dimensions: Width x height for each element

[DON'T USE]
- No interactive elements
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_wcag_text_spacing_and_reflow",
                    "description": """
[WHAT] Applies WCAG 1.4.12 text spacing overrides and checks for clipping/overflow.

[WHEN] Use when:
- Page has text content
- Checking if layout breaks when zoomed to 200%
- Evaluating text reflow

[WHO] CRITICAL for Elias (uses 200-300% zoom - content must reflow without clipping)
- Elias: Fixed-width containers cause horizontal scrolling when zoomed
- Text that clips or disappears prevents reading

[RETURNS]
- clipping_detected: Text cut off when zoomed → FAILED critical
- overflow_issues: Requires horizontal scrolling → FAILED serious
- spacing_violations: Text spacing too tight when adjusted

[DON'T USE]
- No text content
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {"html": {"type": "string"}},
                        "required": ["html"]
                    }
                }
            }
        ]
    
    def execute_tool(self, tool_name, arguments):
        html = arguments.get("html", "")
        
        if not html:
            return {"error": "Missing 'html' parameter"}
        
        if tool_name in self.tool_dispatcher:
            try:
                return self.tool_dispatcher[tool_name](html=html)
            except Exception as e:
                return {"error": str(e), "tool_name": tool_name, "status": "failed"}
        
        return {"error": f"Unknown tool: {tool_name}"}

# Test code - ONLY runs when you execute this file directly
if __name__ == "__main__":
    import json
    
    test_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Family Health Portal — Broken demo</title>
      <style>
        /* Tiny base text + low contrast body copy */
        body { 
          font-size: 10px; 
          color: #c6c6c6; 
          background: #fdfdfd; 
          max-width: 260px; 
        }
        /* Zoom / reflow: fixed narrow column, no wrap, hidden overflow */
        .zoom-trap {
          width: 220px;
          max-height: 3.2em;
          overflow: hidden;
          white-space: nowrap;
          border: 1px solid #eee;
        }
        .shimmer {
          display: inline-block;
          width: 16px;
          height: 16px;
          background: #aaa;
          animation: shimmer 0.8s linear infinite;
        }
        @keyframes shimmer {
          0% { opacity: 1; transform: translateX(0); }
          100% { opacity: 0.3; transform: translateX(6px); }
        }
        .micro { width: 18px; height: 18px; padding: 0; line-height: 1; font-size: 8px; }
        a.tiny-link { display: inline-block; width: 22px; height: 20px; overflow: hidden; font-size: 1px; }
      </style>
    </head>
    <body>
      <!-- Illogical structure: no h1; skip levels -->
      <h4>Section</h4>
      <p style="color:#bbbbbb;background:#ffffff;">Low-contrast notice: prescription renewals may expire without email confirmation.</p>
      
      <h2>More</h2>
      <h3>Click here</h3>
      <p><span class="shimmer" aria-hidden="true"></span> Flashing status indicator (decorative).</p>
      
      <h5>Details</h5>
      <p style="color:#d0d0d0;background:#f9f9f9;">Secondary low-contrast text: copay amounts below are estimates only.</p>
      
      <p class="zoom-trap">
        When you enlarge text to 200% or 300% this paragraph stays on one line inside a fixed-width box,
        so words disappear at the edges and you must scroll sideways with a tremor to read the full message.
      </p>
      
      <video width="140" height="80" autoplay muted playsinline loop>
        <source src="data:video/mp4;base64,AAAAHGZ0eXBpc29tAAACAGlzb21pc28yYXZjMQAAAAhmcmVlAAAA" type="video/mp4">
      </video>
      <p><small>Required medication tutorial — no captions.</small></p>
      
      <h2>Another block</h2>
      <a href="#" class="tiny-link" title="next">›</a>
      <button type="button" class="micro" title="close">×</button>
      
      <!-- Form fields intentionally have no autocomplete attributes -->
      <form id="rx-refill" method="post" action="#">
        <label>Full name<input type="text" name="patient_name" placeholder="Jane Doe"></label>
        <label>Email<input type="email" name="email" placeholder="you@example.com"></label>
        <label>Street<input type="text" name="ship_line1" placeholder="123 Main St"></label>
        <label>Card<input type="text" name="pan" placeholder="4111…"></label>
        <button type="submit" class="micro">OK</button>
      </form>
    </body>
    </html>
    """
    
    agent = EliasAgent(os.environ["OPENAI_API_KEY"])
    result = agent.evaluate(test_html)
    
    print("=" * 70)
    print("ELIAS AGENT TEST")
    print("=" * 70)
    print(json.dumps(result, indent=2))