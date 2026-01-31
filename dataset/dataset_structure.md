# Ground Truth Dataset Structure

## Overview

Our ground truth dataset consists of HTML test scenarios with known accessibility issues, manually tested with assistive technology, and documented with expected results for each persona.

## Directory Structure
```
accessibility-agents-dataset/
│
├── scenarios/
│   ├── shared/
│   │   ├── scenario_001_product_image.html
│   │   ├── scenario_001_product_image.json
│   │   ├── scenario_002_news_article.html
│   │   ├── scenario_002_news_article.json
│   │   └── ... (12 shared scenarios total)
│   │
│   ├── lakshmi/
│   │   ├── scenario_l01_ambiguous_links.html
│   │   ├── scenario_l01_ambiguous_links.json
│   │   └── ... (3 Lakshmi scenarios total)
│   │
│   ├── elias/
│   ├── ade/
│   ├── stefan/
│   ├── sophie/
│   └── ian/
│
├── manual-testing-logs/
│   ├── lakshmi/
│   │   ├── nvda_logs/
│   │   │   ├── scenario_001_nvda_output.txt
│   │   │   └── ...
│   │   ├── test_notes/
│   │   │   ├── scenario_001_notes.md
│   │   │   └── ...
│   │   └── summary.md
│   │
│   ├── elias/
│   │   ├── screenshots/
│   │   │   ├── scenario_001_100percent.png
│   │   │   ├── scenario_001_200percent.png
│   │   │   └── ...
│   │   ├── measurements/
│   │   │   ├── scenario_001_metrics.json
│   │   │   └── ...
│   │   └── summary.md
│   │
│   ├── ade/
│   │   ├── keyboard_traces/
│   │   ├── focus_screenshots/
│   │   └── summary.md
│   │
│   ├── stefan/
│   ├── sophie/
│   └── ian/
│
├── agent-results/
│   ├── lakshmi/
│   │   ├── scenario_001_result.json
│   │   └── ...
│   ├── elias/
│   ├── ade/
│   ├── stefan/
│   ├── sophie/
│   └── ian/
│
├── baseline-results/
│   ├── axe-core/
│   │   ├── scenario_001_axe.json
│   │   └── ...
│   └── comparison_summary.json
│
└── README.md
```

## File Formats

### Scenario JSON Format

See test scenario template for complete format. Key sections:
```json
{
  "scenario_id": "unique_id",
  "html": "HTML code",
  "wcag_violation": {...},
  "manual_testing": {...},
  "expected_results": {...},
  "baseline_comparison": {...}
}
```

### Manual Testing Log Format

#### For Elias (Screenshots + Measurements):

**File: manual-testing-logs/elias/measurements/scenario_001_metrics.json**
```json
{
  "scenario_id": "scenario_001",
  "date": "2024-02-05",
  "tool": "Chrome DevTools + Selenium",
  
  "zoom_test": {
    "100_percent": {
      "viewport_width": 1280,
      "document_width": 1280,
      "horizontal_scroll": false,
      "screenshot": "scenario_001_100percent.png"
    },
    "200_percent": {
      "viewport_width": 1280,
      "document_width": 1450,
      "horizontal_scroll": true,
      "screenshot": "scenario_001_200percent.png"
    }
  },
  
  "target_sizes": [
    {
      "element": "button.add-to-cart",
      "width": 120,
      "height": 40,
      "meets_minimum": true,
      "note": "Adequate size"
    }
  ],
  
  "issues_identified": [
    {
      "wcag": "1.4.10",
      "type": "horizontal_scroll_at_zoom",
      "severity": "critical",
      "evidence": "Page width 1450px at 200% zoom exceeds viewport 1280px"
    }
  ]
}
```

#### For Ade (Keyboard Navigation):

**File: manual-testing-logs/ade/keyboard_traces/scenario_001_trace.json**
```json
{
  "scenario_id": "scenario_001",
  "date": "2024-02-05",
  "tool": "Keyboard only (no mouse)",
  
  "tab_sequence": [
    {
      "index": 1,
      "element": "img",
      "text": "",
      "focusable": false,
      "note": "Skipped - not interactive"
    },
    {
      "index": 2,
      "element": "button",
      "text": "Add to Cart",
      "focusable": true,
      "focus_visible": true,
      "position": {"x": 100, "y": 250}
    }
  ],
  
  "issues_identified": [],
  
  "task_completion": {
    "task": "Add product to cart",
    "completed": true,
    "steps": 2,
    "time_seconds": 5,
    "obstacles": []
  }
}
```
