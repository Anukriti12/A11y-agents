# Test Scenario Template and Examples

## Template Structure

Each test scenario should follow this structure:
```json
{
  "scenario_id": "[persona]_[number]",
  "scenario_type": "shared" or "persona-specific",
  "title": "Brief descriptive title",
  "category": "Category of issue (e.g., Images, Forms, Navigation)",
  "source": "Where this came from (W3C, real site, created)",
  
  "html": "HTML code with the accessibility issue",
  
  "wcag_violation": {
    "criterion": "X.X.X",
    "name": "Criterion name",
    "level": "A, AA, or AAA"
  },
  
  "manual_testing": {
    "persona": "Name",
    "date": "YYYY-MM-DD",
    "tool": "Tool name and version",
    "method": "What you did step-by-step",
    "observed": "What you saw/heard",
    "issue_found": true/false,
    "severity": "critical/serious/moderate/minor",
    "notes": "Any additional observations"
  },
  
  "expected_results": {
    "persona_name": {
      "result": "PASS/FAIL/PARTIAL",
      "reasoning": "Why this persona would/wouldn't catch this",
      "severity": "critical/serious/moderate or N/A"
    }
  },
  
  "baseline_comparison": {
    "axe_core": "What axe-core reports",
    "our_value_add": "What our agent adds beyond baseline"
  }
}
```

## Example 1: Shared Scenario (All Personas Test)

**File: shared/scenario_001_product_image.json**
```json
{
  "scenario_id": "shared_001",
  "scenario_type": "shared",
  "title": "Product image with uninformative alt text",
  "category": "Images and media",
  "source": "Common e-commerce pattern",
  
  "html": "<div class='product'>\n  <img src='handbag.jpg' alt='image'>\n  <h2>Leather Handbag</h2>\n  <p>$99.00 - Premium red leather with gold clasp</p>\n  <button>Add to Cart</button>\n</div>",
  
  "wcag_violation": {
    "criterion": "1.1.1",
    "name": "Non-text Content",
    "level": "A"
  },
  
  "manual_testing": {
    "persona": "Lakshmi",
    "date": "2024-02-05",
    "tool": "NVDA 2024.1",
    "method": "Opened page in Chrome, started NVDA, pressed G to navigate to graphic",
    "observed": "NVDA announced: 'image'",
    "issue_found": true,
    "severity": "critical",
    "notes": "Alt text is present but provides no information about the product. Screen reader user has no idea what the product looks like."
  },
  
  "expected_results": {
    "lakshmi": {
      "result": "FAIL",
      "reasoning": "Screen reader announces 'image' which provides no product description. Cannot make informed purchase decision.",
      "severity": "critical"
    },
    "elias": {
      "result": "PASS",
      "reasoning": "Can see the image with magnification. Alt text quality doesn't affect low vision users who can perceive the image visually.",
      "severity": "N/A"
    },
    "ade": {
      "result": "PASS",
      "reasoning": "Image doesn't affect keyboard navigation. Can skip past it with Tab key.",
      "severity": "N/A"
    },
    "stefan": {
      "result": "PASS",
      "reasoning": "Static image doesn't cause distraction or cognitive overload.",
      "severity": "N/A"
    },
    "sophie": {
      "result": "PASS",
      "reasoning": "Can see image. Text description below image provides product information.",
      "severity": "N/A"
    },
    "ian": {
      "result": "PASS",
      "reasoning": "Image is predictable and doesn't cause sensory overload. Has clear context.",
      "severity": "N/A"
    }
  },
  
  "baseline_comparison": {
    "axe_core": "PASS - Alt attribute exists",
    "our_value_add": "We detect that alt text is uninformative ('image' provides no context). This is a quality issue that passes technical checks but fails usability."
  }
}
```

**Corresponding HTML file: shared/scenario_001_product_image.html**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Product Page - Scenario 001</title>
</head>
<body>
    <div class='product'>
        <img src='handbag.jpg' alt='image'>
        <h2>Leather Handbag</h2>
        <p>$99.00 - Premium red leather with gold clasp</p>
        <button>Add to Cart</button>
    </div>
</body>
</html>
```

## Example 2: Persona-Specific Scenario (Lakshmi)

**File: lakshmi/scenario_l01_ambiguous_links.json**
```json
{
  "scenario_id": "lakshmi_001",
  "scenario_type": "persona-specific",
  "title": "Multiple ambiguous 'click here' links",
  "category": "Links and navigation",
  "source": "W3C Failure F84",
  
  "html": "<article>\n  <h2>Accessibility Resources</h2>\n  <p>We have published a new accessibility guide. <a href='/guide.pdf'>Click here</a> to download.</p>\n  <p>For training materials, <a href='/training.html'>click here</a>.</p>\n  <p>Contact our accessibility team by <a href='/contact.html'>clicking here</a>.</p>\n</article>",
  
  "wcag_violation": {
    "criterion": "2.4.4",
    "name": "Link Purpose (In Context)",
    "level": "A"
  },
  
  "manual_testing": {
    "persona": "Lakshmi",
    "date": "2024-02-05",
    "tool": "NVDA 2024.1",
    "method": "Navigated page, then pressed Insert+F7 to open NVDA links list",
    "observed": "Links list showed: 'click here', 'click here', 'clicking here' - no context about destinations",
    "issue_found": true,
    "severity": "serious",
    "notes": "Screen reader users often navigate by links list to find specific content. With all links saying 'click here', they have to read surrounding text for each link to understand where it goes. Very inefficient."
  },
  
  "expected_results": {
    "lakshmi": {
      "result": "FAIL",
      "reasoning": "NVDA links list shows 'click here' three times. Must read context for each link to understand destination. Links are not self-descriptive.",
      "severity": "serious"
    },
    "elias": {
      "result": "PASS",
      "reasoning": "Can see surrounding context visually. Link text clarity less critical when context is visible.",
      "severity": "N/A"
    },
    "ade": {
      "result": "PARTIAL",
      "reasoning": "Links are keyboard accessible, but tabbing through them doesn't provide enough context about destination.",
      "severity": "moderate"
    },
    "stefan": {
      "result": "PASS",
      "reasoning": "No cognitive overload from link text.",
      "severity": "N/A"
    },
    "sophie": {
      "result": "PASS",
      "reasoning": "Can read surrounding text for context.",
      "severity": "N/A"
    },
    "ian": {
      "result": "PASS",
      "reasoning": "Links are predictable in context. No sensory issues.",
      "severity": "N/A"
    }
  },
  
  "baseline_comparison": {
    "axe_core": "PASS - Links are keyboard accessible and have href attributes",
    "our_value_add": "We detect that link text is ambiguous when read out of context (as screen reader users do via links list). Quality issue missed by automated tools."
  }
}
```

## Example 3: Persona-Specific Scenario (Stefan)

**File: stefan/scenario_s01_multiple_animations.json**
```json
{
  "scenario_id": "stefan_001",
  "scenario_type": "persona-specific",
  "title": "Multiple simultaneous animations and autoplay",
  "category": "Cognitive load and distractions",
  "source": "Based on typical news site patterns",
  
  "html": "<!DOCTYPE html>\n<html>\n<head>\n<style>\n@keyframes rotate { from {transform: rotate(0deg);} to {transform: rotate(360deg);} }\n@keyframes flash { 0% {opacity: 1;} 50% {opacity: 0;} 100% {opacity: 1;} }\n.ad { animation: rotate 3s infinite; }\n.banner { animation: flash 2s infinite; }\n</style>\n</head>\n<body>\n<video autoplay loop src='news.mp4'></video>\n<div class='ad'>Sale! Click Now!</div>\n<div class='banner'>Breaking News!</div>\n<article>\n<h1>Today's Headlines</h1>\n<p>Main article content here...</p>\n</article>\n</body>\n</html>",
  
  "wcag_violation": {
    "criterion": "2.2.2",
    "name": "Pause, Stop, Hide",
    "level": "A"
  },
  
  "manual_testing": {
    "persona": "Stefan",
    "date": "2024-02-05",
    "tool": "Chrome DevTools + manual observation",
    "method": "Opened page, counted moving elements, attempted to read article content",
    "observed": "Auto-playing video + 2 CSS animations running simultaneously. Eyes drawn to motion. Could not focus on article text. No pause controls visible.",
    "issue_found": true,
    "severity": "critical",
    "notes": "With ADHD, multiple moving elements make it impossible to focus on static content. Attention constantly pulled to animations. After 30 seconds, gave up trying to read article."
  },
  
  "expected_results": {
    "stefan": {
      "result": "FAIL",
      "reasoning": "Three simultaneous moving elements (video + 2 animations) create severe cognitive overload. Cannot focus on article content. No pause mechanism.",
      "severity": "critical"
    },
    "sophie": {
      "result": "FAIL",
      "reasoning": "Multiple moving elements are confusing and distracting. Hard to know where to look.",
      "severity": "serious"
    },
    "elias": {
      "result": "PARTIAL",
      "reasoning": "Moving elements harder to track when magnified, but main issue is cognitive rather than visual.",
      "severity": "moderate"
    },
    "lakshmi": {
      "result": "PASS",
      "reasoning": "Screen reader doesn't convey animations. Autoplay video might announce but doesn't create visual distraction.",
      "severity": "N/A"
    },
    "ian": {
      "result": "FAIL",
      "reasoning": "Unexpected motion is overwhelming and anxiety-inducing. Violates predictability.",
      "severity": "critical"
    },
    "ade": {
      "result": "PASS",
      "reasoning": "Animations don't affect keyboard navigation functionality.",
      "severity": "N/A"
    }
  },
  
  "baseline_comparison": {
    "axe_core": "PARTIAL - Can detect autoplay attribute but cannot assess whether animation count is overwhelming",
    "our_value_add": "We detect that MULTIPLE animations create cognitive overload, not just presence/absence of autoplay. Assesses cumulative distraction level."
  }
}
```

## Example 4: Persona-Specific Scenario (Ade)

**File: ade/scenario_a01_keyboard_trap.json**
```json
{
  "scenario_id": "ade_001",
  "scenario_type": "persona-specific",
  "title": "Modal dialog with keyboard trap",
  "category": "Keyboard navigation",
  "source": "Common modal implementation error",
  
  "html": "<!DOCTYPE html>\n<html>\n<body>\n<button onclick=\"openModal()\">Open Modal</button>\n<div id=\"modal\" style=\"display:none\">\n  <h2>Subscribe to Newsletter</h2>\n  <input type=\"email\" placeholder=\"Enter email\">\n  <button onclick=\"subscribe()\">Subscribe</button>\n  <button onclick=\"closeModal()\">Close</button>\n</div>\n<script>\nfunction openModal() { document.getElementById('modal').style.display='block'; }\nfunction closeModal() { document.getElementById('modal').style.display='none'; }\n</script>\n</body>\n</html>",
  
  "wcag_violation": {
    "criterion": "2.1.2",
    "name": "No Keyboard Trap",
    "level": "A"
  },
  
  "manual_testing": {
    "persona": "Ade",
    "date": "2024-02-05",
    "tool": "Keyboard only (no mouse)",
    "method": "Tabbed to 'Open Modal' button, pressed Enter to open, attempted to tab through modal and close it using only keyboard",
    "observed": "Modal opened. Tabbed through email field and buttons. After last button, Tab moved focus OUTSIDE modal to background page elements. Modal still visible but focus escaped. Cannot close modal with keyboard - Close button requires mouse click. Pressed Escape - nothing happened. Stuck with modal blocking view.",
    "issue_found": true,
    "severity": "critical",
    "notes": "Focus is not trapped within modal as it should be. Also, no keyboard method to close modal (Escape doesn't work, Close button doesn't respond to Enter). Keyboard users are stuck."
  },
  
  "expected_results": {
    "ade": {
      "result": "FAIL",
      "reasoning": "Focus escapes modal. Cannot close modal with keyboard alone. This is a critical keyboard trap - user stuck with modal blocking content.",
      "severity": "critical"
    },
    "lakshmi": {
      "result": "FAIL",
      "reasoning": "Screen reader users also use keyboard navigation. Same trap affects blind users.",
      "severity": "critical"
    },
    "elias": {
      "result": "PARTIAL",
      "reasoning": "If using keyboard due to tremor, experiences same trap. Otherwise can use mouse to close.",
      "severity": "serious"
    },
    "stefan": {
      "result": "PASS",
      "reasoning": "Can use mouse to close modal. No cognitive barrier.",
      "severity": "N/A"
    },
    "sophie": {
      "result": "PASS",
      "reasoning": "Can use mouse to close. Modal content is simple.",
      "severity": "N/A"
    },
    "ian": {
      "result": "PARTIAL",
      "reasoning": "Modal appearing unexpectedly might cause anxiety, but can close with mouse.",
      "severity": "moderate"
    }
  },
  
  "baseline_comparison": {
    "axe_core": "PARTIAL - May detect modal lacks proper focus management but cannot test actual keyboard trap behavior",
    "our_value_add": "We actually test keyboard navigation flow through Selenium automation. Detect that focus escapes modal and close button doesn't work with keyboard. Functional testing vs static analysis."
  }
}
```