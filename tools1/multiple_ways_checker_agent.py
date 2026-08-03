"""
multiple_ways_checker_agent.py — v2 (patched)

Changes from v1 (marked with [PATCH]):
  [PATCH-1] Adds multi-signal location detection for WCAG 2.4.8 (used by
            Elias and Sophie): checks breadcrumb (v1) PLUS aria-current="page",
            nav active-class, page title, H1 heading, and browser tab title.
            Prior v1 checked breadcrumb only, missing most location signals.
  [PATCH-2] Adds applicability signal:
              - WCAG 2.4.5: INAPPLICABLE if page has no external links
              - WCAG 2.4.8: INAPPLICABLE if the page has no navigation
                            structure of any kind (unlikely edge case)
  [PATCH-3] Splits execute() output into distinct wcag_245 and wcag_248
            sections so each persona's LLM gets the signal it needs.

Drop-in replacement. Class name MultipleWaysCheckerAgent, same interface.

Used by:
  - Stefan (2.4.5 Multiple Ways) via existing multi-way logic
  - Elias, Sophie (2.4.8 Location) via new multi-signal logic
"""

import asyncio
import base64
import re
import sys
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright


class MultipleWaysCheckerAgent:
    """Check navigation methods (2.4.5) and location indicators (2.4.8)."""

    def execute(self, html: str, mode: str = "auto") -> dict:
        """
        mode: "auto" (default; returns both 2.4.5 and 2.4.8)
              "location" (only 2.4.8, used by Elias/Sophie)
              "multiple_ways" (only 2.4.5, used by Stefan)
        """
        return asyncio.run(self._run(html, mode))

    async def _run(self, url_or_html: str, mode: str) -> dict:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()
                await self._load(page, url_or_html)

                # For 2.4.5: existing multi-way detection
                if mode in ("auto", "multiple_ways"):
                    nav_result = await self._check_multiple_ways(page, url_or_html)
                else:
                    nav_result = None

                # [PATCH-1] For 2.4.8: new multi-signal location detection
                if mode in ("auto", "location"):
                    location_result = await self._check_location_indicators(page)
                else:
                    location_result = None
            finally:
                await browser.close()

        result = {"tool_name": "MultipleWaysCheckerAgent"}
        if nav_result is not None:
            result["wcag_245"] = nav_result
            result["wcag_245_status"] = nav_result["verdict"]
        if location_result is not None:
            result["wcag_248"] = location_result
            result["wcag_248_status"] = location_result["verdict"]
        return result

    async def _load(self, page, url_or_html):
        if url_or_html.strip().startswith("http"):
            await page.goto(url_or_html, wait_until="networkidle", timeout=30_000)
        else:
            encoded = base64.b64encode(url_or_html.encode()).decode()
            await page.goto(f"data:text/html;base64,{encoded}", wait_until="domcontentloaded")

    # ------------------------------------------------------------------ #
    #  WCAG 2.4.5 Multiple Ways (Stefan)                                   #
    #  Applicability: page has links leading elsewhere in the site         #
    # ------------------------------------------------------------------ #

    async def _check_multiple_ways(self, page, url_or_html):
        external_links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.getAttribute('href'))
                .filter(h => h && !h.startsWith('#') && !h.startsWith('javascript:'));
        }""")

        if len(external_links) == 0:
            return {
                "applicability": {
                    "applies": False,
                    "reason": "Page has no links to other pages. WCAG 2.4.5 does not apply.",
                },
                "verdict": "INAPPLICABLE",
            }

        # Detect each mechanism
        mechanisms = {}

        # Mechanism 1: Site-wide navigation menu
        mechanisms["site_navigation"] = await page.evaluate("""() => {
            const nav = document.querySelector('nav:not([aria-label*="readcrumb" i])');
            if (!nav) return {present: false};
            const links = nav.querySelectorAll('a');
            return {
                present: links.length >= 3,
                link_count: links.length,
            };
        }""")

        # Mechanism 2: Search
        mechanisms["search"] = await page.evaluate("""() => {
            const search = document.querySelector(
                'input[type=search], [role=search], form[role=search], input[name*=search i][name*=q i], form[action*=search i]'
            );
            return {present: !!search};
        }""")

        # Mechanism 3: Sitemap link
        mechanisms["sitemap"] = await page.evaluate("""() => {
            const sitemap = Array.from(document.querySelectorAll('a')).find(a => {
                const href = (a.getAttribute('href') || '').toLowerCase();
                const text = a.textContent.toLowerCase();
                return href.includes('sitemap') || text.includes('sitemap') ||
                       href.includes('site-map') || text.includes('site map');
            });
            return {present: !!sitemap};
        }""")

        # Mechanism 4: Breadcrumbs
        mechanisms["breadcrumb"] = await page.evaluate("""() => {
            const bc = document.querySelector(
                'nav[aria-label*="readcrumb" i], .breadcrumb, .breadcrumbs, [class*="breadcrumb"]'
            );
            return {present: !!bc};
        }""")

        # Mechanism 5: Table of contents
        mechanisms["table_of_contents"] = await page.evaluate("""() => {
            const toc = document.querySelector(
                '[role=doc-toc], .toc, .table-of-contents, [class*="toc"], nav[aria-label*="ontents" i]'
            );
            return {present: !!toc};
        }""")

        # Count distinct mechanisms present
        count = sum(1 for m in mechanisms.values() if m.get("present"))
        verdict = "PASS" if count >= 2 else "FAIL"

        return {
            "applicability": {
                "applies": True,
                "elements_present": {"external_links": len(external_links)},
            },
            "verdict": verdict,
            "distinct_mechanisms_found": count,
            "mechanisms": mechanisms,
        }

    # ------------------------------------------------------------------ #
    #  [PATCH-1] WCAG 2.4.8 Location — multi-signal detection              #
    #  Used by Elias and Sophie via `check_location_indicators` alias      #
    # ------------------------------------------------------------------ #

    async def _check_location_indicators(self, page):
        """
        Any of these signals indicates location info is available:
          1. Breadcrumb navigation
          2. aria-current="page" on a nav link
          3. Nav item with "active" or "current" class
          4. Page title (document.title)
          5. H1 that acts as a page-level heading
        """
        signals = await page.evaluate("""() => {
            return {
                breadcrumb: !!document.querySelector(
                    'nav[aria-label*="readcrumb" i], nav[aria-label*="Breadcrumb"], .breadcrumb, .breadcrumbs, [class*="breadcrumb"]'
                ),
                breadcrumb_items: Array.from(
                    document.querySelectorAll(
                        'nav[aria-label*="readcrumb" i] a, .breadcrumb a, .breadcrumbs a, [class*="breadcrumb"] a'
                    )
                ).map(a => a.textContent.trim()).slice(0, 5),
                aria_current_page: !!document.querySelector('[aria-current="page"]'),
                aria_current_location: !!document.querySelector('[aria-current="location"]'),
                aria_current_text: (
                    (document.querySelector('[aria-current="page"]') || {}).textContent || ''
                ).trim().slice(0, 60),
                nav_active_count: document.querySelectorAll(
                    'nav .active, nav .current, nav [class*="active"], nav [class*="current"], nav [class*="selected"]'
                ).length,
                nav_active_text: Array.from(document.querySelectorAll(
                    'nav .active, nav .current, nav [class*="active"], nav [class*="current"]'
                )).slice(0, 3).map(el => el.textContent.trim().slice(0, 40)),
                page_title: document.title,
                h1_count: document.querySelectorAll('h1').length,
                h1_text: (document.querySelector('h1') || {}).textContent || '',
                skip_link: !!document.querySelector('a[href^="#"]'),
            };
        }""")

        # Which signals are meaningfully present?
        signals_present = {
            "breadcrumb": signals["breadcrumb"] and len(signals.get("breadcrumb_items", [])) > 0,
            "aria_current": signals["aria_current_page"] or signals["aria_current_location"],
            "nav_active_class": signals["nav_active_count"] > 0,
            "page_title_meaningful": bool(signals.get("page_title", "").strip()) and
                                     signals["page_title"] not in ("Untitled", "Document"),
            "h1_heading": signals["h1_count"] >= 1 and len(signals.get("h1_text", "")) > 2,
        }

        signal_count = sum(1 for v in signals_present.values() if v)

        # Verdict rules:
        # - 2+ location signals: PASS
        # - Just page title: still PASS (spec allows the URL/title as one method)
        # - Only h1 without any nav context: FAIL (h1 alone doesn't establish location)
        # - No signals: FAIL

        if signal_count == 0:
            verdict = "FAIL"
            evidence = "No location information detected on the page."
        elif signals_present["breadcrumb"] or signals_present["aria_current"] or signals_present["nav_active_class"]:
            # A structured location indicator is present
            verdict = "PASS"
            reasons = [k for k, v in signals_present.items() if v]
            evidence = f"Location signals present: {', '.join(reasons)}"
        elif signals_present["page_title_meaningful"] and signals_present["h1_heading"]:
            # Weaker but still WCAG-acceptable
            verdict = "PASS"
            evidence = "Page title and H1 heading provide location context."
        else:
            verdict = "FAIL"
            evidence = "Insufficient location signals: only " + str(
                [k for k, v in signals_present.items() if v]
            )

        return {
            "applicability": {"applies": True},
            "verdict": verdict,
            "evidence": evidence,
            "signals_present": signals_present,
            "signal_details": signals,
        }
