[
  {
    "snippet_id": "test_001",
    "primary_persona": "ade",
    "html": "<!DOCTYPE html><html><head><meta http-equiv='refresh' content='30'></head><body><form><input type='text' name='email' placeholder='Email'><button style='width: 20px; height: 20px;'>×</button></form><div onclick='alert(\"hi\")'>Click me</div></body></html>",
    "ground_truth": {
      "ade": {
        "label": "failed",
        "severity": "critical",
        "issues": ["timing", "missing labels", "tiny target", "non-keyboard div"]
      }
    }
  },
  {
    "snippet_id": "test_002",
    "primary_persona": "stefan",
    "html": "<!DOCTYPE html><html><body><video autoplay loop>Ad</video><p>The implementation of contemporary methodological frameworks necessitates organizational paradigm shifts.</p></body></html>",
    "ground_truth": {
      "stefan": {
        "label": "failed",
        "severity": "critical",
        "issues": ["autoplay video", "complex text"]
      }
    }
  },
  {
    "snippet_id": "test_003",
    "primary_persona": "lakshmi",
    "html": "<!DOCTYPE html><html><body><img src='chart.png'><h4>Section</h4><h2>Content</h2><button></button></body></html>",
    "ground_truth": {
      "lakshmi": {
        "label": "failed",
        "severity": "serious",
        "issues": ["missing alt", "heading skip", "empty button"]
      }
    }
  }
]