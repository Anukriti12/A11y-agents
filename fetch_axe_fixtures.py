#!/usr/bin/env python3
"""
fetch_axe_fixtures.py
======================

Backfills partial corpus buckets using axe-core's integration fixtures.

ACT's coverage of certain SCs is sparse, so this script supplements with
axe-core's per-rule fixture files. Axe stores one HTML file per rule with
elements tagged #pass1, #fail1, #inapplicable1, etc. We extract elements
by ID from the fixture and synthesize separate per-bucket pages so they
slot into the same corpus tree that build_corpus.py produces.

Rules currently fetched (verified against rule-descriptions.md):
  bypass                       -> WCAG 2.4.1 (Lakshmi)
  blink                        -> WCAG 2.2.2 (Elias, Ian, Stefan)
  marquee                      -> WCAG 2.2.2 (Elias, Ian, Stefan)
  form-field-multiple-labels   -> WCAG 3.3.2 (Sophie)

This is not exhaustive axe coverage. It only includes rules that map to
WCAG criteria Anukriti's personas evaluate and that produce useful
per-bucket synthesis from axe's per-element fixture format.

Run AFTER build_corpus.py:
    python build_corpus.py
    python fetch_axe_fixtures.py

This script ADDS files to the existing corpus tree. It does not delete
or replace ACT-sourced cases.
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path


# --------------------------------------------------------------------------- #
#  Configuration                                                               #
# --------------------------------------------------------------------------- #

# raw.githubusercontent.com base for axe-core fixtures on develop branch
AXE_RAW_BASE = "https://raw.githubusercontent.com/dequelabs/axe-core/develop"

# Rules to fetch. Each entry: axe rule name -> WCAG criterion this rule
# directly tests according to its tags array in lib/rules/<rule>.json.
# Personas listed are the ones whose matrix includes that criterion.
AXE_RULES = [
    {
        "rule": "bypass",
        "wcag_criterion": "2.4.1",
        "personas": ["lakshmi"],
        # bypass is page-level so we use the full fixture, not per-element
        "synthesis": "page-level",
    },
    {
        "rule": "blink",
        "wcag_criterion": "2.2.2",
        "personas": ["elias", "ian", "stefan"],
        "synthesis": "element-level",
    },
    {
        "rule": "marquee",
        "wcag_criterion": "2.2.2",
        "personas": ["elias", "ian", "stefan"],
        "synthesis": "element-level",
    },
    {
        "rule": "form-field-multiple-labels",
        "wcag_criterion": "3.3.2",
        "personas": ["sophie"],
        "synthesis": "element-level",
    },
]

# Per-bucket cap matches build_corpus.py
CASES_PER_BUCKET = 2

DOWNLOAD_DELAY_SEC = 0.2
REQUEST_TIMEOUT_SEC = 30


# --------------------------------------------------------------------------- #
#  Network                                                                     #
# --------------------------------------------------------------------------- #

def _ssl_context():
    return ssl._create_unverified_context()


def fetch_text(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "A11yAgents-AxeFetcher/1.0"}
    )
    with urllib.request.urlopen(
        req, context=_ssl_context(), timeout=REQUEST_TIMEOUT_SEC
    ) as r:
        return r.read().decode("utf-8", errors="replace")


def axe_fixture_urls(rule):
    """Return (html_url, json_url) for an axe rule's integration fixture."""
    base = f"{AXE_RAW_BASE}/test/integration/rules/{rule}/{rule}"
    return base + ".html", base + ".json"


# --------------------------------------------------------------------------- #
#  Per-element extraction from axe fixtures                                    #
# --------------------------------------------------------------------------- #

def extract_element_by_id(html, target_id):
    """
    Pull a single top-level element with id=target_id out of an axe fixture.
    Axe fixtures are flat lists of small elements with explicit IDs. Returns
    the raw element source as a string, or None if not found.

    We use a regex rather than a real HTML parser because axe fixtures are
    intentionally simple snippets and a parser would normalize whitespace
    and attribute quoting in ways we want to preserve as evidence.
    """
    pattern = re.compile(
        r"(<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bid\s*=\s*[\"']" +
        re.escape(target_id) +
        r"[\"'][^>]*>)",
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return None

    full_tag = m.group(1)
    tag_name = m.group(2)
    start = m.start()

    # Void elements have no closing tag
    void = {"input", "img", "br", "hr", "meta", "link", "area", "base",
            "col", "embed", "source", "track", "wbr"}
    if tag_name.lower() in void or full_tag.rstrip().endswith("/>"):
        return full_tag

    # Find matching close tag with depth counting
    open_re = re.compile(rf"<{tag_name}\b[^>]*>", re.IGNORECASE)
    close_re = re.compile(rf"</{tag_name}\s*>", re.IGNORECASE)
    depth = 1
    pos = m.end()
    while depth > 0 and pos < len(html):
        next_open = open_re.search(html, pos)
        next_close = close_re.search(html, pos)
        if not next_close:
            break
        if next_open and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            pos = next_close.end()
    if depth != 0:
        return None
    return html[start:pos]


def ids_for_bucket(axe_json, bucket_key):
    """
    axe JSON has shape:
        { "passes": [["#pass1"], ...],
          "violations": [["#fail1"], ...],
          "incomplete": [["#incomplete1"], ...] }
    Each inner list is a CSS-selector chain; we use only the first segment
    and strip leading '#'. Returns a list of element IDs.
    """
    raw = axe_json.get(bucket_key, []) or []
    ids = []
    for chain in raw:
        if not chain:
            continue
        sel = chain[0]
        if isinstance(sel, str) and sel.startswith("#"):
            ids.append(sel[1:])
    return ids


def find_inapplicable_ids(html, used_ids):
    """
    Axe JSON doesn't list 'inapplicable' explicitly. By convention, axe
    fixtures include elements with IDs like inapplicable1/na1/skip1 that
    fall outside any rule bucket. Find IDs in the HTML that aren't in
    `used_ids` and look like inapplicable markers.
    """
    all_ids = set(re.findall(
        r"\bid\s*=\s*[\"']([A-Za-z_][\w-]*)[\"']", html
    ))
    inap_pattern = re.compile(
        r"^(inapplicable|na|n_a|skip|notapplicable)\d*$",
        re.IGNORECASE,
    )
    candidates = [i for i in all_ids if i not in used_ids and inap_pattern.match(i)]
    candidates.sort()
    return candidates


def wrap_as_page(snippets, title, criterion):
    """Wrap a list of element snippets in a minimal HTML5 page."""
    body = "\n\n".join(snippets) if snippets else "<p>(no relevant elements)</p>"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{title}</title>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>Test page for WCAG {criterion}</h1>\n"
        f"  {body}\n"
        "</body>\n"
        "</html>\n"
    )


# --------------------------------------------------------------------------- #
#  Synthesis modes                                                             #
# --------------------------------------------------------------------------- #

def synthesize_element_level(rule_meta, html, axe_json):
    """
    Build per-bucket pages by extracting elements from the fixture.
    Returns {bucket -> [{"id": case_id, "html": str, "source_element_ids": [...]}]}
    """
    rule = rule_meta["rule"]
    criterion = rule_meta["wcag_criterion"]

    pass_ids = ids_for_bucket(axe_json, "passes")
    fail_ids = ids_for_bucket(axe_json, "violations")
    used = set(pass_ids) | set(fail_ids) | set(
        ids_for_bucket(axe_json, "incomplete")
    )
    inap_ids = find_inapplicable_ids(html, used)

    out = {"passed": [], "failed": [], "inapplicable": []}

    for bucket_name, ids in [
        ("passed", pass_ids),
        ("failed", fail_ids),
        ("inapplicable", inap_ids),
    ]:
        for i in range(min(CASES_PER_BUCKET, len(ids))):
            element_id = ids[i]
            snippet = extract_element_by_id(html, element_id)
            if not snippet:
                continue
            case_id = f"axe-{rule}-{bucket_name}-{i+1:02d}"
            page = wrap_as_page(
                [snippet],
                title=f"axe-core {rule} {bucket_name} example",
                criterion=criterion,
            )
            out[bucket_name].append({
                "id": case_id,
                "html": page,
                "source_element_ids": [element_id],
            })

    return out


def synthesize_page_level(rule_meta, html, axe_json):
    """
    For page-level rules like 'bypass'. The fixture's full HTML IS the
    failing example (axe runs the rule against the whole page). We use
    the full fixture as one 'failed' case and synthesize matching pass
    and inapplicable cases from boilerplate.
    """
    rule = rule_meta["rule"]
    criterion = rule_meta["wcag_criterion"]
    out = {"passed": [], "failed": [], "inapplicable": []}

    # Failed: the fixture as-is (axe's bypass.html has no skip-link mechanism)
    out["failed"].append({
        "id": f"axe-{rule}-failed-01",
        "html": html if "<html" in html.lower() else wrap_as_page(
            [html], title=f"axe-core {rule} failed example", criterion=criterion
        ),
        "source_element_ids": ["<full-page>"],
    })

    # Passed: same structure with a skip-link added (bypass-specific)
    if rule == "bypass":
        passed_html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            "  <title>Page with skip link</title>\n"
            "</head>\n"
            "<body>\n"
            '  <a href="#main" class="skip-link">Skip to main content</a>\n'
            "  <header>\n"
            "    <nav>\n"
            '      <a href="/">Home</a> | <a href="/products">Products</a>\n'
            "    </nav>\n"
            "  </header>\n"
            '  <main id="main">\n'
            "    <h1>Main content heading</h1>\n"
            "    <p>Main body text starts here.</p>\n"
            "  </main>\n"
            "</body>\n"
            "</html>\n"
        )
        out["passed"].append({
            "id": f"axe-{rule}-passed-01",
            "html": passed_html,
            "source_element_ids": ["<synthesized>"],
        })

        # Second pass: landmark-only bypass mechanism
        passed_html_2 = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            "  <title>Page with landmarks</title>\n"
            "</head>\n"
            "<body>\n"
            "  <header><nav>Navigation</nav></header>\n"
            "  <main>\n"
            "    <h1>Article title</h1>\n"
            "    <p>Article content.</p>\n"
            "  </main>\n"
            "  <footer>Site footer</footer>\n"
            "</body>\n"
            "</html>\n"
        )
        out["passed"].append({
            "id": f"axe-{rule}-passed-02",
            "html": passed_html_2,
            "source_element_ids": ["<synthesized>"],
        })

        # Inapplicable: page with no repeated blocks
        inap_html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            "  <title>Single-section page</title>\n"
            "</head>\n"
            "<body>\n"
            "  <h1>Error 404</h1>\n"
            "  <p>The page you requested was not found.</p>\n"
            "</body>\n"
            "</html>\n"
        )
        out["inapplicable"].append({
            "id": f"axe-{rule}-inapplicable-01",
            "html": inap_html,
            "source_element_ids": ["<synthesized>"],
        })

    return out


# --------------------------------------------------------------------------- #
#  Layout                                                                      #
# --------------------------------------------------------------------------- #

def write_case(case, persona, criterion, bucket, rule, source_url, output_root):
    """Write one synthesized case + metadata json into the corpus tree."""
    target_dir = output_root / persona / criterion / bucket
    target_dir.mkdir(parents=True, exist_ok=True)

    html_path = target_dir / f"{case['id']}.html"
    json_path = target_dir / f"{case['id']}.json"

    html_path.write_text(case["html"], encoding="utf-8")

    metadata = {
        "testcaseId": case["id"],
        "testcaseTitle": f"axe-core {rule} {bucket} example",
        "expected": bucket,
        "source": "axe-core integration fixtures",
        "axe_rule": rule,
        "axe_fixture_url": source_url,
        "source_element_ids": case["source_element_ids"],
        "wcag_criterion_in_corpus": criterion,
        "persona_folder": persona,
    }
    json_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return html_path


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Backfill corpus from axe-core fixtures."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("corpus"),
        help="Corpus root directory (default: ./corpus, same as build_corpus.py)",
    )
    args = parser.parse_args()

    output_root = args.output.resolve()
    if not output_root.exists():
        print(
            f"FATAL: corpus root {output_root} does not exist. "
            "Run build_corpus.py first.",
            file=sys.stderr,
        )
        return 2

    print(f"Backfilling axe-core fixtures into {output_root}/ ...\n")

    total_written = 0
    per_rule_report = []

    for rule_meta in AXE_RULES:
        rule = rule_meta["rule"]
        html_url, json_url = axe_fixture_urls(rule)
        print(f"--- {rule} (WCAG {rule_meta['wcag_criterion']}) ---")
        print(f"  fetching {html_url}")

        try:
            html = fetch_text(html_url)
            time.sleep(DOWNLOAD_DELAY_SEC)
            axe_json = json.loads(fetch_text(json_url))
            time.sleep(DOWNLOAD_DELAY_SEC)
        except Exception as e:
            print(f"  SKIP {rule}: {e}")
            per_rule_report.append((rule, 0, str(e)))
            continue

        if rule_meta["synthesis"] == "element-level":
            buckets = synthesize_element_level(rule_meta, html, axe_json)
        else:
            buckets = synthesize_page_level(rule_meta, html, axe_json)

        rule_written = 0
        for bucket_name, cases in buckets.items():
            for case in cases:
                for persona in rule_meta["personas"]:
                    write_case(
                        case, persona,
                        rule_meta["wcag_criterion"], bucket_name,
                        rule, html_url, output_root,
                    )
                    rule_written += 1

        counts = " | ".join(
            f"{k}={len(v)}" for k, v in buckets.items()
        )
        print(f"  buckets: {counts}")
        print(f"  files written (incl. cross-persona copies): {rule_written}")
        total_written += rule_written
        per_rule_report.append((rule, rule_written, "ok"))

    print()
    print("=" * 60)
    print(f"Total files written: {total_written}")
    print("=" * 60)
    for rule, n, status in per_rule_report:
        print(f"  {rule}: {n} files, status={status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
