"""
NVDA Agent — Tool Agent
Evaluates four WCAG criteria using NVDA screen-reader announcement capture,
playwright DOM inspection, and Chrome DevTools Protocol accessibility tree.

Covers: WCAG 1.1.1, 1.4.5, 2.4.1, 4.1.2.
Used by: Lakshmi.

This version removes axe-core entirely. The original four axe rule runs are
replaced with direct DOM / CDP / OCR checks, so this tool's output can be
compared cleanly against an axe-only baseline without contamination.

Requirements:
  - Windows
  - NVDA running with the Speech Viewer window open
  - Tesseract OCR installed (path configurable below)
"""

import json
import time
import io
from pathlib import Path

import pytesseract
from PIL import Image
from playwright.sync_api import sync_playwright
from pywinauto.application import Application

OUTPUT_DIR = Path("a11y_results")
OUTPUT_DIR.mkdir(exist_ok=True)

# Set Tesseract path to match your install location
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

URL = "https://www.w3.org/WAI/content-assets/wcag-act-rules/testcases/97a4e1/a4cc71b0434f71f4ea0069c409f73e0207dfb403.html"


# =====================================================
# NVDA SPEECH CAPTURE
# =====================================================

def capture_nvda_speech():
    try:
        app = Application(backend="uia").connect(title="Speech Viewer")
        window = app.window(title="Speech Viewer")
        text = window.child_window(control_type="Edit").window_text()
        return text
    except Exception:
        return None


# =====================================================
# WCAG 1.1.1 — NON-TEXT CONTENT
# =====================================================

def run_local_alt_audit(page):
    """
    Direct DOM audit covering:
      - <img> with missing or empty alt
      - <img> inside a link with missing alt
      - <input type="image"> without alt
      - <object> without accessible name

    Replaces the original axe-core image-alt / input-image-alt / object-alt rules.
    """
    results = page.evaluate("""
        () => {
            const flags = {
                alt_missing: [],
                alt_null: [],
                alt_link: [],
                alt_input: [],
                alt_object: [],
            };

            document.querySelectorAll("img").forEach(img => {
                const alt = img.getAttribute("alt");
                const src = img.src || img.getAttribute("data-src") || "";
                const inLink = !!img.closest("a");
                const info = { src, outerHTML: img.outerHTML.slice(0, 150) };

                if (alt === null) {
                    if (inLink) flags.alt_link.push(info);
                    else flags.alt_missing.push(info);
                } else if (alt.trim() === "") {
                    flags.alt_null.push(info);
                }
            });

            document.querySelectorAll("input[type='image']").forEach(el => {
                const alt = el.getAttribute("alt");
                if (!alt || alt.trim() === "") {
                    flags.alt_input.push({ outerHTML: el.outerHTML.slice(0, 150) });
                }
            });

            document.querySelectorAll("object").forEach(el => {
                const label = el.getAttribute("aria-label") ||
                              el.getAttribute("title") ||
                              el.innerText.trim();
                if (!label) {
                    flags.alt_object.push({ outerHTML: el.outerHTML.slice(0, 150) });
                }
            });

            return flags;
        }
    """)

    return {k: {"count": len(v), "items": v} for k, v in results.items()}


def capture_nvda_image_announcements(page):
    """
    Focuses each image element and captures NVDA's announcement.
    'Meaningful' means NVDA said more than just 'graphic'.
    """
    results = []
    elements = page.query_selector_all("img, input[type='image'], object")

    for i, el in enumerate(elements):
        el.scroll_into_view_if_needed()
        el.focus()
        time.sleep(0.5)

        nvda_output = capture_nvda_speech()

        tag = el.evaluate("el => el.tagName")
        alt = el.get_attribute("alt")
        aria_label = el.get_attribute("aria-label")
        aria_labelledby = el.get_attribute("aria-labelledby")
        role = el.get_attribute("role")
        src = el.get_attribute("src") or el.get_attribute("data")

        if nvda_output:
            announcement_lower = nvda_output.lower()
            is_meaningful = not (
                "graphic" in announcement_lower and
                len(announcement_lower.strip()) <= len("graphic")
            )
        else:
            is_meaningful = None

        results.append({
            "index": i,
            "tag": tag,
            "src": src,
            "alt_attr": alt,
            "aria_label": aria_label,
            "aria_labelledby": aria_labelledby,
            "role": role,
            "nvda_announcement": nvda_output,
            "nvda_meaningful": is_meaningful,
        })

    return results


def evaluate_wcag_1_1_1(local_alt_results, nvda_results):
    """
    PASS: All meaningful images have descriptive alt. Decorative have alt="".
          NVDA announces meaningful content for every image.
    FAIL: Meaningful image missing/empty alt. NVDA announces 'graphic' only.
    N/A:  Page contains no images.
    """
    total_images = len(nvda_results)

    has_any_local_issue = any(
        v.get("count", 0) > 0
        for k, v in local_alt_results.items()
        if k != "alt_null"
    )

    if total_images == 0 and not has_any_local_issue:
        return "N/A", "Page contains no non-text content elements."

    failures = []

    for flag_key, flag_data in local_alt_results.items():
        if flag_data.get("count", 0) > 0 and flag_key != "alt_null":
            failures.append({
                "source": "local-alt-audit",
                "rule": flag_key,
                "count": flag_data["count"],
                "items": flag_data["items"],
                "reason": f"{flag_data['count']} element(s) flagged for {flag_key}",
            })

    for item in nvda_results:
        if item["nvda_meaningful"] is False:
            failures.append({
                "source": "NVDA",
                "element_index": item["index"],
                "tag": item["tag"],
                "src": item["src"],
                "nvda_announcement": item["nvda_announcement"],
                "reason": "NVDA announced 'graphic' with no meaningful description.",
            })

    return ("FAIL", failures) if failures else (
        "PASS", "All non-text content has appropriate text alternatives."
    )


# =====================================================
# WCAG 1.4.5 — IMAGES OF TEXT
# =====================================================

def run_redundant_alt_audit(page):
    """
    Direct DOM check that replicates axe-core's `image-redundant-alt` rule.
    An image is "redundant" when its alt text appears verbatim in the
    immediately adjacent text (parent's textContent or sibling text node).
    This flags decorative images with redundant alt, which often indicates
    text-baked-into-image content where the alt was a copy-paste.
    """
    return page.evaluate("""
        () => {
            const results = [];

            document.querySelectorAll("img").forEach(img => {
                const alt = img.getAttribute("alt");
                if (!alt || alt.trim() === "") return;

                const altNorm = alt.trim().toLowerCase();
                if (altNorm.length < 3) return;

                // Build context text: parent element minus the image itself.
                const parent = img.parentElement;
                if (!parent) return;

                const parentText = (parent.textContent || "").trim().toLowerCase();
                if (!parentText) return;

                // Strip alt from parentText to check actual surrounding text.
                const surrounding = parentText.replace(altNorm, "").trim();

                // Redundant if surrounding text still contains the alt as substring.
                if (surrounding.includes(altNorm)) {
                    results.push({
                        alt: alt,
                        src: img.src,
                        outerHTML: img.outerHTML.slice(0, 150),
                        surrounding_text: parent.textContent.slice(0, 200),
                    });
                }
            });

            return results;
        }
    """)


def run_ocr_image_text_detector(page):
    """
    For every <img> on the page:
      1. Screenshot the element
      2. Run Tesseract OCR
      3. Compare OCR result to the img's alt attribute

    FAIL when an image visibly contains text but alt is missing or doesn't
    match. PASS when no text in image OR alt matches OCR.
    """
    results = []
    elements = page.query_selector_all("img")

    for i, el in enumerate(elements):
        alt = el.get_attribute("alt")
        src = el.get_attribute("src") or ""
        html_snippet = el.evaluate("el => el.outerHTML")[:150]

        try:
            screenshot_bytes = el.screenshot()
        except Exception as e:
            results.append({
                "index": i, "src": src, "alt_attr": alt,
                "ocr_text": None, "has_text_in_image": None,
                "alt_matches_ocr": None, "html_snippet": html_snippet,
                "error": str(e),
            })
            continue

        try:
            image = Image.open(io.BytesIO(screenshot_bytes))
            ocr_raw = pytesseract.image_to_string(image).strip()
            ocr_text = " ".join(ocr_raw.split())
        except Exception as e:
            results.append({
                "index": i, "src": src, "alt_attr": alt,
                "ocr_text": None, "has_text_in_image": None,
                "alt_matches_ocr": None, "html_snippet": html_snippet,
                "error": str(e),
            })
            continue

        alt_matches_ocr = None
        has_text_in_image = bool(ocr_text and len(ocr_text) > 2)

        if has_text_in_image:
            if alt is None or alt.strip() == "":
                alt_matches_ocr = False
            else:
                alt_norm = " ".join(alt.strip().split()).lower()
                ocr_norm = ocr_text.lower()
                alt_matches_ocr = (ocr_norm in alt_norm or alt_norm in ocr_norm)

        results.append({
            "index": i, "src": src, "alt_attr": alt,
            "ocr_text": ocr_text,
            "has_text_in_image": has_text_in_image,
            "alt_matches_ocr": alt_matches_ocr,
            "html_snippet": html_snippet,
        })

    return results


def evaluate_wcag_1_4_5(redundant_alt_results, ocr_results):
    """
    PASS: No essential text rendered as image, OR alt matches OCR-detected text.
    FAIL: Image contains text with no/non-matching alt, OR alt is redundant
          with surrounding text (often indicates text-baked-into-image).
    N/A:  Page contains no images.
    """
    if not ocr_results and not redundant_alt_results:
        return "N/A", "Page contains no images."

    failures = []

    for item in redundant_alt_results:
        failures.append({
            "source": "redundant-alt-audit",
            "rule": "image-redundant-alt",
            "element": item["outerHTML"],
            "alt": item["alt"],
            "surrounding_text": item["surrounding_text"],
            "reason": "Image alt text duplicates adjacent text content.",
        })

    for item in ocr_results:
        if item.get("error"):
            continue
        if item["has_text_in_image"] and item["alt_matches_ocr"] is False:
            failures.append({
                "source": "OCR",
                "index": item["index"],
                "src": item["src"],
                "ocr_text": item["ocr_text"],
                "alt_attr": item["alt_attr"],
                "html_snippet": item["html_snippet"],
                "reason": (
                    "Image contains text but alt is missing."
                    if not item["alt_attr"]
                    else f"Image text '{item['ocr_text']}' does not match alt '{item['alt_attr']}'."
                ),
            })

    return ("FAIL", failures) if failures else (
        "PASS", "No images of text detected, or all image text matches alt attribute."
    )


# =====================================================
# WCAG 2.4.1 — BYPASS BLOCKS
# =====================================================

def run_landmark_and_skiplink_audit(page):
    """
    Direct DOM/keyboard audit covering everything axe's skip-link and bypass
    rules check, plus the functional Tab-position test which axe does NOT do.

    Checks:
      1. ARIA landmarks present (<main>, <nav>, <header>, <footer>)
      2. Skip-link candidates discovered
      3. Tab order: is the skip link the FIRST focusable item?
      4. Skip-link target exists on the page
    """
    results = {}

    landmarks = page.evaluate("""
        () => ({
            main:   document.querySelectorAll('main, [role="main"]').length,
            nav:    document.querySelectorAll('nav, [role="navigation"]').length,
            header: document.querySelectorAll('header, [role="banner"]').length,
            footer: document.querySelectorAll('footer, [role="contentinfo"]').length,
        })
    """)
    results["landmarks"] = landmarks

    skip_links = page.evaluate("""
        () => {
            const candidates = Array.from(document.querySelectorAll('a[href]'));
            return candidates
                .filter(a => {
                    const text = a.textContent.toLowerCase().trim();
                    const href = a.getAttribute('href') || '';
                    return (
                        text.includes('skip') ||
                        text.includes('bypass') ||
                        text.includes('jump') ||
                        text.includes('main content') ||
                        href.startsWith('#')
                    );
                })
                .map(a => ({
                    text: a.textContent.trim(),
                    href: a.getAttribute('href'),
                    outerHTML: a.outerHTML.slice(0, 200),
                    targetExists: a.getAttribute('href').startsWith('#')
                        ? !!document.querySelector(a.getAttribute('href'))
                        : true,
                }));
        }
    """)
    results["skip_links_found"] = skip_links
    results["has_skip_link"] = len(skip_links) > 0

    tab_sequence = []
    visited = set()
    skip_link_tab_position = None

    for step in range(10):
        page.keyboard.press("Tab")
        time.sleep(0.3)

        active = page.evaluate("""
            () => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                return {
                    tag: el.tagName,
                    href: el.getAttribute('href'),
                    text: el.innerText ? el.innerText.trim().slice(0, 80) : '',
                    outerHTML: el.outerHTML.slice(0, 150),
                    tabIndex: el.tabIndex,
                };
            }
        """)

        if not active:
            break

        identifier = f"{active['tag']}-{active.get('href', '')}-{active['text']}"
        if identifier in visited:
            break
        visited.add(identifier)

        tab_sequence.append({"step": step, **active})

        if skip_link_tab_position is None:
            text_lower = active.get("text", "").lower()
            href = active.get("href", "") or ""
            if (
                "skip" in text_lower or
                "bypass" in text_lower or
                "jump" in text_lower or
                "main content" in text_lower or
                href.startswith("#")
            ):
                skip_link_tab_position = step

    results["tab_sequence_first_10"] = tab_sequence
    results["skip_link_tab_position"] = skip_link_tab_position
    results["skip_link_is_first"] = skip_link_tab_position == 0

    return results


def capture_nvda_landmark_navigation(page):
    """
    Uses F6 (NVDA landmark navigation key) to verify <main> is reachable
    via landmark shortcut.
    """
    results = []

    for i in range(5):
        page.keyboard.press("F6")
        time.sleep(0.5)
        nvda_output = capture_nvda_speech()

        results.append({
            "press": i,
            "key": "F6",
            "nvda_announcement": nvda_output,
        })

        if nvda_output and "main" in nvda_output.lower():
            break

    main_reached = any(
        r["nvda_announcement"] and "main" in r["nvda_announcement"].lower()
        for r in results
    )

    return {
        "landmark_navigation_log": results,
        "main_landmark_reached": main_reached,
    }


def evaluate_wcag_2_4_1(landmark_audit, nvda_landmark):
    """
    PASS: Skip link is first focusable, landmarks present, NVDA reaches <main>.
    FAIL: No skip link, missing landmarks, or NVDA cannot reach <main>.
    N/A:  Page has no repeated navigation blocks.
    """
    landmarks = landmark_audit.get("landmarks", {})
    has_nav = landmarks.get("nav", 0) > 0
    has_main = landmarks.get("main", 0) > 0

    if not has_nav:
        return "N/A", "Page has no repeated navigation blocks — bypass not required."

    failures = []

    if not landmark_audit.get("has_skip_link"):
        failures.append({
            "source": "landmark-audit",
            "reason": "No skip link or bypass mechanism found on the page.",
        })
    else:
        if not landmark_audit.get("skip_link_is_first"):
            pos = landmark_audit.get("skip_link_tab_position")
            failures.append({
                "source": "landmark-audit",
                "reason": f"Skip link found but is not the first focusable item (Tab position: {pos}).",
            })

        for sl in landmark_audit.get("skip_links_found", []):
            if not sl.get("targetExists"):
                failures.append({
                    "source": "landmark-audit",
                    "reason": f"Skip link '{sl['text']}' points to '{sl['href']}' but target does not exist on the page.",
                })

    if not has_main:
        failures.append({
            "source": "landmark-audit",
            "reason": "Page is missing a <main> landmark — NVDA cannot navigate directly to main content.",
        })

    if not nvda_landmark.get("main_landmark_reached"):
        failures.append({
            "source": "NVDA",
            "reason": "NVDA could not reach the <main> landmark via F6 landmark navigation.",
            "nvda_log": nvda_landmark.get("landmark_navigation_log"),
        })

    return ("FAIL", failures) if failures else (
        "PASS",
        "Skip link is first focusable item, landmarks are present, and NVDA can navigate to <main>.",
    )


# =====================================================
# WCAG 4.1.2 — NAME, ROLE, VALUE
# =====================================================

# Valid ARIA roles from WAI-ARIA 1.2 (abstract roles excluded)
VALID_ARIA_ROLES = {
    "alert", "alertdialog", "application", "article", "banner", "blockquote",
    "button", "caption", "cell", "checkbox", "code", "columnheader", "combobox",
    "complementary", "contentinfo", "definition", "deletion", "dialog",
    "directory", "document", "emphasis", "feed", "figure", "form", "generic",
    "grid", "gridcell", "group", "heading", "img", "insertion", "link", "list",
    "listbox", "listitem", "log", "main", "marquee", "math", "menu", "menubar",
    "menuitem", "menuitemcheckbox", "menuitemradio", "meter", "navigation",
    "none", "note", "option", "paragraph", "presentation", "progressbar",
    "radio", "radiogroup", "region", "row", "rowgroup", "rowheader", "scrollbar",
    "search", "searchbox", "separator", "slider", "spinbutton", "status",
    "strong", "subscript", "superscript", "switch", "tab", "table", "tablist",
    "tabpanel", "term", "textbox", "time", "timer", "toolbar", "tooltip",
    "tree", "treegrid", "treeitem",
}

# Required ARIA attributes per role (from WAI-ARIA 1.2)
REQUIRED_ARIA_ATTRS = {
    "checkbox":   ["aria-checked"],
    "combobox":   ["aria-expanded"],
    "menuitemcheckbox": ["aria-checked"],
    "menuitemradio":    ["aria-checked"],
    "option":     ["aria-selected"],
    "radio":      ["aria-checked"],
    "scrollbar":  ["aria-controls", "aria-valuenow"],
    "slider":     ["aria-valuenow"],
    "spinbutton": ["aria-valuenow"],
    "switch":     ["aria-checked"],
}


def run_aria_role_validation(page):
    """
    Direct DOM check that replicates axe-core's `aria-roles` and
    `aria-required-attr` rules.

    Flags:
      - Invalid role values (typos, deprecated roles, abstract roles)
      - Missing required ARIA attributes per role

    Replaces axe in the 4.1.2 evaluation.
    """
    valid_roles = list(VALID_ARIA_ROLES)
    required_attrs = REQUIRED_ARIA_ATTRS

    return page.evaluate(
        """({validRoles, requiredAttrs}) => {
            const validSet = new Set(validRoles);
            const violations = [];

            document.querySelectorAll('[role]').forEach(el => {
                const role = (el.getAttribute('role') || '').trim();
                if (!role) return;

                // Handle space-separated role fallback chains: use first valid one
                const roles = role.split(/\\s+/);
                const matchedRole = roles.find(r => validSet.has(r));

                if (!matchedRole) {
                    violations.push({
                        rule: 'aria-roles',
                        role: role,
                        tag: el.tagName.toLowerCase(),
                        outerHTML: el.outerHTML.slice(0, 200),
                        reason: `Invalid ARIA role: '${role}' is not a valid WAI-ARIA role.`,
                    });
                    return;
                }

                const required = requiredAttrs[matchedRole] || [];
                const missing = required.filter(attr => !el.hasAttribute(attr));
                if (missing.length > 0) {
                    violations.push({
                        rule: 'aria-required-attr',
                        role: matchedRole,
                        tag: el.tagName.toLowerCase(),
                        outerHTML: el.outerHTML.slice(0, 200),
                        missing_attrs: missing,
                        reason: `role='${matchedRole}' requires: ${missing.join(', ')}`,
                    });
                }
            });

            return violations;
        }""",
        {"validRoles": valid_roles, "requiredAttrs": required_attrs},
    )


def run_aria_tree_inspection(page):
    """
    Extracts full accessibility tree via CDP, filtered to interactive elements.
    Checks each for an accessible name. This replicates axe's `button-name`
    rule and goes further by covering all interactive ARIA roles.
    """
    client = page.context.new_cdp_session(page)
    full_tree = client.send("Accessibility.getFullAXTree")

    interactive_roles = {
        "button", "link", "textbox", "checkbox", "radio",
        "combobox", "listbox", "menuitem", "switch", "tab",
        "slider", "spinbutton", "searchbox",
    }

    interactive_elements = []
    for node in full_tree.get("nodes", []):
        role = node.get("role", {}).get("value", "")
        if role not in interactive_roles:
            continue

        name = node.get("name", {}).get("value", "")
        properties = {p["name"]: p["value"] for p in node.get("properties", [])}

        state_attrs = {
            k: v for k, v in properties.items()
            if k in ("checked", "expanded", "selected", "pressed", "disabled")
        }

        interactive_elements.append({
            "role": role,
            "name": name,
            "has_accessible_name": bool(name.strip()),
            "state": state_attrs,
            "node_id": node.get("nodeId"),
            "backend_node_id": node.get("backendDOMNodeId"),
        })

    return {
        "full_tree": full_tree,
        "interactive_elements": interactive_elements,
    }


def capture_nvda_interactive_announcements(page):
    """
    Tabs through interactive elements capturing NVDA name, role, and state
    change announcements. Unchanged from the original.
    """
    results = []

    selector = (
        "button, input, select, textarea, a[href], "
        "[role='button'], [role='checkbox'], [role='radio'], "
        "[role='combobox'], [role='listbox'], [role='menuitem'], "
        "[role='switch'], [role='tab'], [role='slider']"
    )

    elements = page.query_selector_all(selector)

    for i, el in enumerate(elements):
        el.scroll_into_view_if_needed()
        el.focus()
        time.sleep(0.5)

        nvda_before = capture_nvda_speech()

        tag = el.evaluate("el => el.tagName")
        role = el.get_attribute("role") or tag.lower()
        aria_label = el.get_attribute("aria-label")
        aria_labelledby = el.get_attribute("aria-labelledby")
        aria_checked = el.get_attribute("aria-checked")
        aria_expanded = el.get_attribute("aria-expanded")
        aria_selected = el.get_attribute("aria-selected")
        try:
            inner_text = el.inner_text().strip()
        except Exception:
            inner_text = el.get_attribute("textContent") or ""
        inner_text = " ".join(inner_text.split())
        html_snippet = el.evaluate("el => el.outerHTML")[:150]

        nvda_after_interaction = None
        if aria_checked is not None or tag.lower() in ("input",):
            input_type = el.get_attribute("type") or ""
            if input_type in ("checkbox", "radio") or aria_checked is not None:
                el.click()
                time.sleep(0.5)
                nvda_after_interaction = capture_nvda_speech()
                el.click()
                time.sleep(0.3)

        has_name_announced = False
        has_role_announced = False
        has_state_announced = False

        if nvda_before:
            speech_lower = nvda_before.lower()
            name_candidates = [
                aria_label or "",
                inner_text,
                el.get_attribute("value") or "",
                el.get_attribute("title") or "",
                el.get_attribute("aria-labelledby") or "",
            ]
            has_name_announced = any(
                " ".join(n.lower().split()) in " ".join(speech_lower.split())
                for n in name_candidates if n.strip()
            )
            role_keywords = {
                "button": "button", "checkbox": "checkbox",
                "link": "link", "textbox": ["edit", "textbox"],
                "combobox": "combo", "radio": "radio button",
            }
            role_key = role_keywords.get(role, role)
            if isinstance(role_key, list):
                has_role_announced = any(r in speech_lower for r in role_key)
            else:
                has_role_announced = role_key in speech_lower

        if nvda_after_interaction:
            state_words = ["checked", "unchecked", "expanded", "collapsed", "selected"]
            has_state_announced = any(
                w in nvda_after_interaction.lower() for w in state_words
            )

        results.append({
            "index": i,
            "tag": tag,
            "role": role,
            "aria_label": aria_label,
            "aria_labelledby": aria_labelledby,
            "inner_text": inner_text,
            "html_snippet": html_snippet,
            "aria_checked": aria_checked,
            "aria_expanded": aria_expanded,
            "aria_selected": aria_selected,
            "nvda_on_focus": nvda_before,
            "nvda_after_interaction": nvda_after_interaction,
            "has_name_announced": has_name_announced,
            "has_role_announced": has_role_announced,
            "has_state_announced": has_state_announced if nvda_after_interaction else None,
        })

    return results


def evaluate_wcag_4_1_2(role_validation, aria_tree, nvda_results):
    """
    PASS: Every interactive element has accessible name, valid role,
          required ARIA attrs, and NVDA announces name/role/state.
    FAIL: Invalid role, missing required attr, no accessible name,
          or NVDA fails to announce.
    N/A:  Page has no interactive elements.
    """
    aria_interactive = aria_tree.get("interactive_elements", [])
    total_nvda = len(nvda_results)

    if total_nvda == 0 and not role_validation and not aria_interactive:
        return "N/A", "Page is purely static with no interactive elements."

    failures = []

    for v in role_validation:
        failures.append({
            "source": "aria-role-validation",
            "rule": v["rule"],
            "role": v.get("role"),
            "element": v["outerHTML"],
            "reason": v["reason"],
        })

    for el in aria_interactive:
        if not el["has_accessible_name"]:
            failures.append({
                "source": "aria-tree",
                "role": el["role"],
                "node_id": el["node_id"],
                "reason": f"Interactive element with role '{el['role']}' has no accessible name.",
            })

    for item in nvda_results:
        if not item["has_name_announced"]:
            failures.append({
                "source": "NVDA",
                "element_index": item["index"],
                "tag": item["tag"],
                "role": item["role"],
                "html_snippet": item["html_snippet"],
                "nvda_announcement": item["nvda_on_focus"],
                "reason": "NVDA did not announce an accessible name for this control.",
            })
        if not item["has_role_announced"]:
            failures.append({
                "source": "NVDA",
                "element_index": item["index"],
                "tag": item["tag"],
                "role": item["role"],
                "html_snippet": item["html_snippet"],
                "nvda_announcement": item["nvda_on_focus"],
                "reason": f"NVDA did not announce the role '{item['role']}' for this control.",
            })
        if item["has_state_announced"] is False:
            failures.append({
                "source": "NVDA",
                "element_index": item["index"],
                "tag": item["tag"],
                "role": item["role"],
                "html_snippet": item["html_snippet"],
                "nvda_announcement": item["nvda_after_interaction"],
                "reason": "NVDA did not announce state change after interaction.",
            })

    return ("FAIL", failures) if failures else (
        "PASS", "All interactive elements have accessible name, role, and state."
    )


# =====================================================
# MAIN EXECUTION
# =====================================================

def run_full_analysis(url):
    print(f"Starting full accessibility analysis for: {url}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print(f"Navigating to {url}...")
        page.goto(url, wait_until="networkidle", timeout=60000)
        print("Page loaded.\n")

        # WCAG 1.1.1
        print("[ WCAG 1.1.1 ] Running local alt audit...")
        local_alt_results = run_local_alt_audit(page)

        print("[ WCAG 1.1.1 ] Capturing NVDA image announcements...")
        nvda_results_111 = capture_nvda_image_announcements(page)

        # WCAG 1.4.5
        print("[ WCAG 1.4.5 ] Running redundant-alt audit...")
        redundant_alt_results = run_redundant_alt_audit(page)

        print("[ WCAG 1.4.5 ] Running Tesseract OCR image text detector...")
        ocr_results = run_ocr_image_text_detector(page)

        # WCAG 2.4.1
        print("[ WCAG 2.4.1 ] Running landmark and skip-link audit...")
        landmark_audit = run_landmark_and_skiplink_audit(page)

        print("[ WCAG 2.4.1 ] Capturing NVDA landmark navigation...")
        nvda_landmark = capture_nvda_landmark_navigation(page)

        # WCAG 4.1.2
        print("[ WCAG 4.1.2 ] Running ARIA role validation...")
        role_validation = run_aria_role_validation(page)

        print("[ WCAG 4.1.2 ] Extracting ARIA tree via CDP...")
        aria_tree = run_aria_tree_inspection(page)

        print("[ WCAG 4.1.2 ] Capturing NVDA interactive announcements...")
        nvda_results_412 = capture_nvda_interactive_announcements(page)

        browser.close()

    # Evaluate verdicts
    print("\nEvaluating verdicts...")
    verdict_111, details_111 = evaluate_wcag_1_1_1(local_alt_results, nvda_results_111)
    verdict_145, details_145 = evaluate_wcag_1_4_5(redundant_alt_results, ocr_results)
    verdict_241, details_241 = evaluate_wcag_2_4_1(landmark_audit, nvda_landmark)
    verdict_412, details_412 = evaluate_wcag_4_1_2(role_validation, aria_tree, nvda_results_412)

    alt_null_items = local_alt_results.get("alt_null", {}).get("items", [])

    output = {
        "url": url,
        "wcag_1_1_1": {
            "wcag": "1.1.1 Non-text Content",
            "verdict": verdict_111,
            "details": details_111,
            "decorative_images_to_review": alt_null_items,
            "raw": {
                "local_alt_results": local_alt_results,
                "nvda_results": nvda_results_111,
            },
        },
        "wcag_1_4_5": {
            "wcag": "1.4.5 Images of Text",
            "verdict": verdict_145,
            "details": details_145,
            "raw": {
                "redundant_alt_results": redundant_alt_results,
                "ocr_results": ocr_results,
            },
        },
        "wcag_2_4_1": {
            "wcag": "2.4.1 Bypass Blocks",
            "verdict": verdict_241,
            "details": details_241,
            "raw": {
                "landmark_audit": landmark_audit,
                "nvda_landmark": nvda_landmark,
            },
        },
        "wcag_4_1_2": {
            "wcag": "4.1.2 Name, Role, Value",
            "verdict": verdict_412,
            "details": details_412,
            "raw": {
                "role_validation": role_validation,
                "aria_tree_interactive": aria_tree["interactive_elements"],
                "nvda_results": nvda_results_412,
            },
        },
    }

    # Save outputs
    with open(OUTPUT_DIR / "wcag_1_1_1_local_alt.json", "w", encoding="utf-8") as f:
        json.dump(local_alt_results, f, indent=2)
    with open(OUTPUT_DIR / "wcag_1_1_1_nvda_results.json", "w", encoding="utf-8") as f:
        json.dump(nvda_results_111, f, indent=2)
    with open(OUTPUT_DIR / "wcag_1_4_5_redundant_alt.json", "w", encoding="utf-8") as f:
        json.dump(redundant_alt_results, f, indent=2)
    with open(OUTPUT_DIR / "wcag_1_4_5_ocr_results.json", "w", encoding="utf-8") as f:
        json.dump(ocr_results, f, indent=2)
    with open(OUTPUT_DIR / "wcag_2_4_1_landmark_audit.json", "w", encoding="utf-8") as f:
        json.dump(landmark_audit, f, indent=2)
    with open(OUTPUT_DIR / "wcag_2_4_1_nvda_landmark.json", "w", encoding="utf-8") as f:
        json.dump(nvda_landmark, f, indent=2)
    with open(OUTPUT_DIR / "wcag_4_1_2_role_validation.json", "w", encoding="utf-8") as f:
        json.dump(role_validation, f, indent=2)
    with open(OUTPUT_DIR / "wcag_4_1_2_aria_tree.json", "w", encoding="utf-8") as f:
        json.dump(aria_tree, f, indent=2)
    with open(OUTPUT_DIR / "wcag_4_1_2_nvda_results.json", "w", encoding="utf-8") as f:
        json.dump(nvda_results_412, f, indent=2)
    with open(OUTPUT_DIR / "full_verdict.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    # Print summary
    print(f"\n{'='*40}")
    print(f"WCAG 1.1.1 Verdict: {verdict_111}")
    print(f"{'='*40}")
    if verdict_111 == "FAIL":
        print(f"Failures found: {len(details_111)}")
        for f in details_111:
            print(f"  [{f['source']}] {f.get('rule', '')} — {f.get('reason', '')}")
    else:
        print(details_111)
    if alt_null_items:
        print(f"\nDecorative images to manually review: {len(alt_null_items)}")

    print(f"\n{'='*40}")
    print(f"WCAG 1.4.5 Verdict: {verdict_145}")
    print(f"{'='*40}")
    if verdict_145 == "FAIL":
        print(f"Failures found: {len(details_145)}")
        for f in details_145:
            print(f"  [{f['source']}] {f.get('rule', f.get('ocr_text', ''))} — {f.get('reason', '')}")
    else:
        print(details_145)

    print(f"\n{'='*40}")
    print(f"WCAG 2.4.1 Verdict: {verdict_241}")
    print(f"{'='*40}")
    if verdict_241 == "FAIL":
        print(f"Failures found: {len(details_241)}")
        for f in details_241:
            print(f"  [{f['source']}] — {f.get('reason', '')}")
    else:
        print(details_241)

    print(f"\n{'='*40}")
    print(f"WCAG 4.1.2 Verdict: {verdict_412}")
    print(f"{'='*40}")
    if verdict_412 == "FAIL":
        print(f"Failures found: {len(details_412)}")
        for f in details_412:
            print(f"  [{f['source']}] {f.get('role', f.get('rule', ''))} — {f.get('reason', '')}")
    else:
        print(details_412)

    print(f"\nAll results saved to: {OUTPUT_DIR}")
    return output


if __name__ == "__main__":
    run_full_analysis(URL)
