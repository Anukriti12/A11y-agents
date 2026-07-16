#!/usr/bin/env python3
"""
build_corpus.py
================

Builds the A11yAgents study corpus from the W3C ACT test cases.

Input:
    https://www.w3.org/WAI/content-assets/wcag-act-rules/testcases.json
    (1190 test cases as of June 2026)

Output structure:
    corpus/
    ├── ade/
    │   ├── 2.1.1/
    │   │   ├── passed/
    │   │   │   ├── <testcaseId>.html
    │   │   │   ├── <testcaseId>.json    (metadata)
    │   │   │   └── ...
    │   │   ├── failed/
    │   │   └── inapplicable/
    │   ├── 2.2.1/
    │   ...
    ├── elias/
    ├── ian/
    ├── lakshmi/
    ├── sophie/
    └── stefan/

For each persona × criterion: 2 passed, 2 failed, 2 inapplicable cases
(or fewer if the ACT set doesn't have that many).

Selection is DETERMINISTIC: test cases are sorted by testcaseId and the
first N of each expected type are taken. Re-running this script produces
the same corpus.

Shared criteria (e.g. 2.2.2 belongs to Elias, Ian, Stefan) get the same
test cases copied into each persona's folder, so each persona has a
self-contained corpus.

Usage:
    python build_corpus.py [--output corpus] [--no-download]

    --output: corpus root directory (default: ./corpus)
    --no-download: build folder structure and metadata only, skip
                   downloading HTML files (useful for inspecting selection)
"""

import argparse
import json
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path


# --------------------------------------------------------------------------- #
#  Configuration                                                               #
# --------------------------------------------------------------------------- #

TESTCASES_URL = "https://www.w3.org/WAI/content-assets/wcag-act-rules/testcases.json"

# Final locked persona × WCAG matrix from the A11yAgents study.
PERSONA_MATRIX = {
    "ade":     ["2.1.1", "2.2.1", "2.4.3", "2.4.7", "2.5.5"],
    "elias":   ["1.3.5", "1.4.3", "1.4.12", "2.2.2", "2.4.8"],
    "ian":     ["1.3.1", "2.2.2", "2.4.6", "3.1.4", "3.1.5"],
    "lakshmi": ["1.1.1", "1.3.1", "2.1.1", "2.4.1", "4.1.2"],
    "sophie":  ["2.2.1", "2.4.8", "3.1.4", "3.3.1", "3.3.2"],
    "stefan":  ["1.4.12", "2.2.2", "2.4.5", "2.4.6", "3.1.4"],
}

# Number of test cases to select per (criterion, expected) bucket.
CASES_PER_BUCKET = 2

# Categories in WCAG ACT terminology
EXPECTED_BUCKETS = ["passed", "failed", "inapplicable"]

# Polite delay between HTML downloads (seconds)
DOWNLOAD_DELAY_SEC = 0.2

# Network timeout
REQUEST_TIMEOUT_SEC = 30


# --------------------------------------------------------------------------- #
#  Network helpers                                                             #
# --------------------------------------------------------------------------- #

def _ssl_context():
    """SSL context that works behind self-signed corp proxies too."""
    return ssl._create_unverified_context()


def fetch_url_bytes(url, timeout=REQUEST_TIMEOUT_SEC):
    """Fetch raw bytes from a URL with a friendly UA."""
    req = urllib.request.Request(url, headers={"User-Agent": "A11yAgents-CorpusBuilder/1.0"})
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=timeout) as response:
        return response.read()


def fetch_url_text(url, timeout=REQUEST_TIMEOUT_SEC):
    """Fetch a URL as UTF-8 text."""
    return fetch_url_bytes(url, timeout=timeout).decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
#  ACT test case filtering                                                     #
# --------------------------------------------------------------------------- #

def criterion_matches(testcase, criterion):
    """
    Return True if this test case is FOR-CONFORMANCE for the given WCAG
    criterion (e.g. '2.1.1'). The ACT JSON uses prefixed keys:
      wcag20:2.1.1, wcag21:2.1.1, wcag22:2.1.1
    and entries with `forConformance: true` indicate the rule directly
    tests that criterion. Secondary references (without forConformance)
    are too loose for a study corpus and are excluded.
    """
    reqs = testcase.get("ruleAccessibilityRequirements") or {}
    for key, value in reqs.items():
        if not isinstance(value, dict):
            continue
        # Match wcag20:X.X.X, wcag21:X.X.X, wcag22:X.X.X
        if ":" not in key:
            continue
        prefix, sc = key.split(":", 1)
        if not prefix.startswith("wcag"):
            continue
        if not prefix[4:].isdigit():
            continue
        if sc != criterion:
            continue
        if value.get("forConformance") is True:
            return True
    return False


def select_cases_for_criterion(testcases, criterion):
    """
    Find all test cases for one criterion, bucket them by expected
    outcome, and return up to CASES_PER_BUCKET per bucket (deterministic
    selection by testcaseId sort).

    Returns:
        {
            "passed": [testcase_dict, ...],
            "failed": [...],
            "inapplicable": [...]
        }
    """
    matching = [tc for tc in testcases if criterion_matches(tc, criterion)]
    matching.sort(key=lambda tc: tc.get("testcaseId", ""))

    buckets = {b: [] for b in EXPECTED_BUCKETS}
    for tc in matching:
        exp = tc.get("expected")
        if exp in buckets and len(buckets[exp]) < CASES_PER_BUCKET:
            buckets[exp].append(tc)

    return buckets


# --------------------------------------------------------------------------- #
#  Corpus building                                                             #
# --------------------------------------------------------------------------- #

def collect_unique_cases(testcases, matrix):
    """
    Walk the matrix, collect the union of (testcaseId, criterion) pairs
    we'll need, and the metadata for each. Returns:
      {
          "selection_by_persona_criterion": {
              (persona, criterion): {bucket: [testcase, ...]}
          },
          "unique_testcases": {testcaseId: testcase}  # for download
      }
    """
    # Cache so we don't reselect the same criterion twice
    criterion_cache = {}
    selection = {}
    unique = {}

    for persona, criteria in matrix.items():
        for criterion in criteria:
            if criterion not in criterion_cache:
                criterion_cache[criterion] = select_cases_for_criterion(
                    testcases, criterion
                )
            buckets = criterion_cache[criterion]
            selection[(persona, criterion)] = buckets

            for cases in buckets.values():
                for tc in cases:
                    unique[tc["testcaseId"]] = tc

    return {
        "selection_by_persona_criterion": selection,
        "unique_testcases": unique,
    }


def _extension_for(tc):
    """Pick the file extension matching the test case URL (.html, .svg, .xml)."""
    url = (tc.get("url") or "").lower()
    for ext in (".html", ".svg", ".xml"):
        if url.endswith(ext):
            return ext
    return ".html"


def download_unique_html(unique_testcases, cache_dir, do_download):
    """
    Download each unique test case once into cache_dir. Returns a dict
    {testcaseId -> local_path} so the layout step can copy from cache
    into per-persona folders.

    Files keep their original extension (.html for most, .svg / .xml for
    a handful of inapplicable cases). If do_download is False, the
    returned paths point to where files WOULD live; useful for inspecting
    selection without hitting the network.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    total = len(unique_testcases)
    print(f"\nDownloading {total} unique test cases into {cache_dir}/ ...")

    for idx, (tc_id, tc) in enumerate(sorted(unique_testcases.items()), start=1):
        ext = _extension_for(tc)
        local = cache_dir / f"{tc_id}{ext}"
        paths[tc_id] = local

        if local.exists():
            continue  # already cached

        if not do_download:
            continue  # dry run

        url = tc.get("url")
        if not url:
            print(f"  [{idx}/{total}] SKIP {tc_id}: no URL")
            continue

        try:
            content = fetch_url_text(url)
            local.write_text(content, encoding="utf-8")
            if idx % 10 == 0 or idx == total:
                print(f"  [{idx}/{total}] {tc_id}{ext}")
            time.sleep(DOWNLOAD_DELAY_SEC)
        except urllib.error.HTTPError as e:
            print(f"  [{idx}/{total}] HTTP {e.code} for {tc_id}: {url}")
        except Exception as e:
            print(f"  [{idx}/{total}] ERROR {tc_id}: {e}")

    return paths


def layout_corpus(selection, html_paths, output_root):
    """
    Walk the selection map, create the corpus tree, and copy HTML +
    write metadata JSON into each persona/criterion/expected/ folder.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    written = 0
    missing = 0

    for (persona, criterion), buckets in selection.items():
        for expected, cases in buckets.items():
            target_dir = output_root / persona / criterion / expected
            target_dir.mkdir(parents=True, exist_ok=True)

            for tc in cases:
                tc_id = tc["testcaseId"]
                ext = _extension_for(tc)
                src_file = html_paths.get(tc_id)
                dst_file = target_dir / f"{tc_id}{ext}"
                dst_json = target_dir / f"{tc_id}.json"

                # Copy content file if available
                if src_file and src_file.exists():
                    shutil.copyfile(src_file, dst_file)
                    written += 1
                else:
                    missing += 1

                # Write metadata regardless of HTML success
                metadata = {
                    "testcaseId": tc_id,
                    "testcaseTitle": tc.get("testcaseTitle"),
                    "expected": tc.get("expected"),
                    "ruleId": tc.get("ruleId"),
                    "ruleName": tc.get("ruleName"),
                    "rulePage": tc.get("rulePage"),
                    "url": tc.get("url"),
                    "approved": tc.get("approved"),
                    "wcag_criterion_in_corpus": criterion,
                    "persona_folder": persona,
                    "ruleAccessibilityRequirements": tc.get(
                        "ruleAccessibilityRequirements"
                    ) or {},
                }
                dst_json.write_text(
                    json.dumps(metadata, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    return {"written": written, "missing": missing}


# --------------------------------------------------------------------------- #
#  Reporting                                                                   #
# --------------------------------------------------------------------------- #

def print_selection_report(selection):
    """Show how many cases per bucket per persona×criterion."""
    print("\n" + "=" * 70)
    print("Selection report (cases per bucket)")
    print("=" * 70)

    short_gaps = []
    for (persona, criterion), buckets in sorted(selection.items()):
        counts = " | ".join(
            f"{b}={len(buckets[b])}" for b in EXPECTED_BUCKETS
        )
        total = sum(len(buckets[b]) for b in EXPECTED_BUCKETS)
        expected_max = CASES_PER_BUCKET * len(EXPECTED_BUCKETS)
        marker = "OK" if total == expected_max else "PARTIAL"
        print(f"  {persona:8s} {criterion:7s} {counts}  [{marker}]")

        for b in EXPECTED_BUCKETS:
            if len(buckets[b]) < CASES_PER_BUCKET:
                short_gaps.append((persona, criterion, b, len(buckets[b])))

    if short_gaps:
        print(f"\nNOTE: {len(short_gaps)} bucket(s) had fewer than "
              f"{CASES_PER_BUCKET} cases available in ACT:")
        for persona, criterion, bucket, count in short_gaps:
            print(f"  {persona} / {criterion} / {bucket}: only {count} case(s)")


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Build the A11yAgents corpus from W3C ACT test cases."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("corpus"),
        help="Corpus root directory (default: ./corpus)",
    )
    parser.add_argument(
        "--no-download", action="store_true",
        help="Build folder structure and metadata only; skip HTML downloads.",
    )
    args = parser.parse_args()

    output_root = args.output.resolve()
    cache_dir = output_root.parent / f".{output_root.name}_cache"

    print(f"Fetching ACT test cases index from:\n  {TESTCASES_URL}")
    try:
        index_text = fetch_url_text(TESTCASES_URL)
    except Exception as e:
        print(f"FATAL: could not fetch testcases.json: {e}", file=sys.stderr)
        return 2

    index = json.loads(index_text)
    testcases = index.get("testcases", [])
    print(f"  loaded {len(testcases)} test cases")

    print("\nSelecting cases per persona x criterion ...")
    bundle = collect_unique_cases(testcases, PERSONA_MATRIX)
    selection = bundle["selection_by_persona_criterion"]
    unique = bundle["unique_testcases"]

    print_selection_report(selection)
    print(f"\n{len(unique)} unique test cases need to be fetched.")

    html_paths = download_unique_html(
        unique, cache_dir, do_download=not args.no_download
    )

    print(f"\nLaying out corpus tree at {output_root}/ ...")
    stats = layout_corpus(selection, html_paths, output_root)
    print(f"  HTMLs copied:    {stats['written']}")
    print(f"  HTMLs missing:   {stats['missing']}")
    print(f"  Metadata files:  one per selected case")

    print("\nDone.")
    if args.no_download:
        print("(Run without --no-download to fetch HTML payloads.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
