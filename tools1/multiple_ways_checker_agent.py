"""
WCAG 2.4.5 Multiple Ways — Checker Agent
Detects whether a web page is reachable by more than one navigation method.

Used by: Stefan, Elias (or any persona — criterion applies to all users)

WCAG 2.4.5 requires that more than one way exists to locate a web page
within a set of pages, except where the page is the result of, or a step
in, a process (e.g. checkout, login, form confirmation).

Pass threshold: >= 2 of the following methods detected:
    1. Navigation links   — <nav> or role=navigation with internal links
    2. Search             — search input with a submit mechanism
    3. Sitemap            — visible or <head> link to a sitemap
    4. Breadcrumbs        — aria-label breadcrumb, schema.org, or class-based
"""

import asyncio
import base64
import re
import sys
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright


class MultipleWaysCheckerAgent:
    """
    Checks WCAG 2.4.5: Multiple Ways.

    First determines whether the criterion applies to the page, then
    checks for four distinct navigation methods. A page passes if at
    least two methods are found.
    """

    def execute(self, html: str) -> dict:
        url_or_html = html
        """
        Run the WCAG 2.4.5 check.
        Returns:
            {
                "applicable": bool,
                "applicability_reason": str,
                "navigation_links": list,
                "search": list,
                "sitemap": list,
                "breadcrumbs": list,
                "methods_found": int,
                "tool_name": str,
            }
        """
        return asyncio.run(self._run(url_or_html))

  
    # Loading the page
    async def _load(self, page, url_or_html: str) -> str:
        """
        Load a URL or raw HTML string.
        Returns the resolved URL used for domain-matching in checks.
        """
        if url_or_html.strip().startswith("http"):
            await page.goto(url_or_html, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(800)
            return url_or_html
        else:
            encoded = base64.b64encode(url_or_html.encode()).decode() # data URL to load raw HTML
            await page.goto(
                f"data:text/html;base64,{encoded}",
                wait_until="domcontentloaded",
                timeout=15_000,
            )
            await page.wait_for_timeout(300)
            return "data:local" # Special marker for raw HTML (no domain, all links treated as internal)

    # Main execution flow, async for better performance and to allow Playwright usage
    async def _run(self, url_or_html: str) -> dict:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (compatible; WCAG245Checker/1.0)"
                )
                page = await context.new_page()
                resolved_url = await self._load(page, url_or_html)

                # First check if the criterion should be applicable to the page (only applies when a
                # site has multiple pages and isn't a process step like login/checkout)
                applicable, applicability_reason = await self._check_applicability(
                    page, url_or_html, resolved_url
                )

                if not applicable:
                    await browser.close()
                    return {
                        "applicable": False,
                        "applicability_reason": applicability_reason,
                        "navigation_links": [],
                        "search": [],
                        "sitemap": [],
                        "breadcrumbs": [],
                        "methods_found": 0,
                        "tool_name": "MultipleWaysCheckerAgent",
                    }

                # If applicable, check for the four navigation methods
                navigation_links = await self._detect_navigation_links(page, resolved_url)
                search = await self._detect_search(page)
                sitemap = await self._detect_sitemap(page, resolved_url)
                breadcrumbs = await self._detect_breadcrumbs(page)

            finally:
                await browser.close()
        # Count how many distinct methods were found (each method counts as 1 if any instances of them detected)
        methods_found = sum([
            bool(navigation_links),
            bool(search),
            bool(sitemap),
            bool(breadcrumbs),
        ])

        return {
            "applicable": applicable,
            "applicability_reason": applicability_reason,
            "navigation_links": navigation_links,
            "search": search,
            "sitemap": sitemap,
            "breadcrumbs": breadcrumbs,
            "methods_found": methods_found,
            "tool_name": "MultipleWaysCheckerAgent",
        }

    EXEMPTED_PATH_PATTERNS = [
        r"/login", r"/signin", r"/sign-in",
        r"/register", r"/signup", r"/sign-up",
        r"/checkout", r"/cart", r"/payment", r"/order",
        r"/confirm", r"/thank.?you", r"/success",
        r"/reset.?password", r"/forgot.?password",
        r"/404", r"/500", r"/error",
    ]

    EXEMPTED_TITLE_PATTERNS = [
        r"log.?in", r"sign.?in", r"register",
        r"check.?out", r"order.?confirm", r"thank.?you",
        r"error", r"not.?found",
    ]

    async def _check_applicability(self, page, url_or_html: str, resolved_url: str) -> tuple:
        """
        Return (applicable, reason).
        Not applicable when:
          - The URL path matches a known process step (login, checkout, etc.)
          - The page title matches a known process pattern
          - Only one page is linked from the page (single-page site)
        """
        is_raw_html = not url_or_html.strip().startswith("http")

        if not is_raw_html:
            path = urlparse(url_or_html).path.lower()
            for pattern in self.EXEMPTED_PATH_PATTERNS:
                if re.search(pattern, path):
                    return False, f"URL path matches exempted pattern: {pattern}"

        title = (await page.title()).lower()
        for pattern in self.EXEMPTED_TITLE_PATTERNS:
            if re.search(pattern, title):
                return False, f"Page title matches exempted pattern: {pattern}"

        if not is_raw_html:
            noindex = await page.query_selector('meta[name="robots"][content*="noindex"]')
            if noindex:
                return False, "Page has noindex meta tag (likely a transactional page)"

        page_count = await self._count_internal_pages(page, resolved_url)
        if page_count < 2:
            return False, (
                f"Only {page_count} unique internal page(s) found — "
                "appears to be a single-page site"
            )

        return True, "Page appears to be part of a multi-page site"

    async def _count_internal_pages(self, page, resolved_url: str) -> int:
        """Count distinct internal page paths linked from this page."""
        is_local = resolved_url == "data:local"
        base_domain = urlparse(resolved_url).netloc
        links = await page.query_selector_all("a[href]")
        paths: set = {"/"}

        for link in links:
            href = await link.get_attribute("href")
            if not href or href.startswith("#"):
                continue
            if is_local:
                # Raw HTML: any non-anchor href counts as a distinct page
                paths.add(href)
            else:
                absolute = urljoin(resolved_url, href)
                parsed = urlparse(absolute)
                if (
                    parsed.netloc == base_domain
                    and parsed.path not in ("", "/")
                    and not parsed.path.endswith((".pdf", ".zip", ".png", ".jpg"))
                    and parsed.path != urlparse(resolved_url).path
                ):
                    paths.add(parsed.path)

        return len(paths)


    async def _detect_navigation_links(self, page, resolved_url: str) -> list:
        """
        Check 1: Consistent navigation menu with links to other pages.
        Looks for <nav>, role=navigation, or common header/footer link groups.

        Returns:
            list: Navigation elements found, each with tag and internal link count.
        """
        is_local = resolved_url == "data:local"
        base_domain = urlparse(resolved_url).netloc
        results = []

        try:
            nav_elements = await page.query_selector_all("nav, [role='navigation']")
            for nav in nav_elements:
                aria_label = (await nav.get_attribute("aria-label") or "").lower()
                if "breadcrumb" in aria_label:
                    continue
                links = await nav.query_selector_all("a[href]")
                internal = []
                for link in links:
                    href = await link.get_attribute("href") or ""
                    if href.startswith("#"):
                        continue
                    absolute = urljoin(resolved_url, href)
                    parsed = urlparse(absolute)
                    if is_local or parsed.netloc == base_domain:
                        text = (await link.inner_text()).strip()
                        if text:
                            internal.append(text[:40])
                if len(internal) >= 2:
                    results.append({
                        "type": "nav_element",
                        "internal_link_count": len(internal),
                        "sample_links": internal[:4],
                    })

            # Fallback: header or footer with 3+ internal links
            if not results:
                for selector in ["header", "footer", "#header", "#footer", ".header", ".footer"]:
                    container = await page.query_selector(selector)
                    if not container:
                        continue
                    links = await container.query_selector_all("a[href]")
                    internal = []
                    for link in links:
                        href = await link.get_attribute("href") or ""
                        if href.startswith("#"):
                            continue
                        absolute = urljoin(resolved_url, href)
                        if is_local or urlparse(absolute).netloc == base_domain:
                            internal.append(href)
                    if len(internal) >= 3:
                        results.append({
                            "type": selector,
                            "internal_link_count": len(internal),
                            "sample_links": internal[:4],
                        })
                        break

        except Exception as e:
            print(f"Error detecting navigation links: {e}")

        return results 

    async def _detect_search(self, page) -> list:
        """
        Check 2: Site search functionality.
        Looks for search inputs, role=search landmark, or common search patterns.

        Returns:
            list: Search inputs/landmarks found, each with type and details.
        """
        results = []

        try:
            # role=search landmark
            search_landmarks = await page.query_selector_all("[role='search']")
            for el in search_landmarks:
                results.append({
                    "type": "role_search_landmark",
                    "detail": "element with role='search'",
                })

            # <input type="search">
            search_inputs = await page.query_selector_all("input[type='search']")
            for el in search_inputs:
                if await el.evaluate("el => !!el.closest('[role=\"search\"]')"):
                    continue
                placeholder = await el.get_attribute("placeholder") or ""
                results.append({
                    "type": "input_type_search",
                    "placeholder": placeholder,
                })

            # Heuristic: input with search-related attributes
            if not results:
                candidate_selectors = [
                    "input[aria-label*='search' i]",
                    "input[placeholder*='search' i]",
                    "input[name*='search' i]",
                    "input[id*='search' i]",
                    "input[class*='search' i]",
                ]
                for sel in candidate_selectors:
                    matches = await page.query_selector_all(sel)
                    if matches:
                        for el in matches:
                            placeholder = await el.get_attribute("placeholder") or ""
                            results.append({
                                "type": "heuristic_search_input",
                                "matched_selector": sel,
                                "placeholder": placeholder,
                            })
                        break

        except Exception as e:
            print(f"Error detecting search: {e}")

        return results 

    async def _detect_sitemap(self, page, resolved_url: str) -> list:
        """
        Check 3: Link to an HTML or XML sitemap.
        Checks visible links, footer, and <head> link elements.

        Returns:
            list: Sitemap references found, each with type and href.
        """
        is_local = resolved_url == "data:local"
        base_domain = urlparse(resolved_url).netloc
        results = []
        seen_hrefs: set = set()

        try:
            # Visible links whose href contains 'sitemap'
            for sel in ["a[href*='sitemap']", "a[href*='site-map']", "a[href*='site_map']"]:
                links = await page.query_selector_all(sel)
                for link in links:
                    href = await link.get_attribute("href") or ""
                    absolute = urljoin(resolved_url, href)
                    is_internal = is_local or urlparse(absolute).netloc == base_domain
                    if is_internal and absolute not in seen_hrefs:
                        seen_hrefs.add(absolute)
                        text = (await link.inner_text()).strip() or href
                        results.append({
                            "type": "visible_sitemap_link",
                            "text": text[:60],
                            "href": href,
                        })

            # Visible links whose text says 'sitemap'
            all_links = await page.query_selector_all("a")
            for link in all_links:
                text = (await link.inner_text()).strip().lower()
                if "sitemap" in text or "site map" in text:
                    href = await link.get_attribute("href") or ""
                    absolute = urljoin(resolved_url, href)
                    if absolute not in seen_hrefs:
                        seen_hrefs.add(absolute)
                        results.append({
                            "type": "visible_sitemap_text_link",
                            "text": text[:60],
                            "href": href,
                        })

            # <link rel="sitemap"> in <head>
            head_sitemap = await page.query_selector('link[rel="sitemap"]')
            if head_sitemap:
                href = await head_sitemap.get_attribute("href") or ""
                results.append({
                    "type": "head_link_rel_sitemap",
                    "href": href,
                })

        except Exception as e:
            print(f"Error detecting sitemap: {e}")

        return results

    async def _detect_breadcrumbs(self, page) -> list:
        """
        Check 4: Breadcrumb navigation.
        Looks for aria-label breadcrumb, schema.org BreadcrumbList, or class-based patterns.

        Returns:
            list: Breadcrumb elements found, each with type and detail.
        """
        results = []

        try:
            # ARIA breadcrumb landmark
            aria_bcs = await page.query_selector_all(
                "nav[aria-label*='breadcrumb' i], [aria-label*='breadcrumb' i]"
            )
            for el in aria_bcs:
                aria_label = await el.get_attribute("aria-label") or ""
                results.append({
                    "type": "aria_label_breadcrumb",
                    "aria_label": aria_label,
                })

           
            json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
            for script in json_ld_scripts:
                content = await script.inner_text()
                if "BreadcrumbList" in content:
                    results.append({
                        "type": "schema_org_json_ld",
                        "detail": "BreadcrumbList found in JSON-LD",
                    })
                    break

        
            schema_bc = await page.query_selector('[itemtype*="BreadcrumbList"]')
            if schema_bc:
                results.append({
                    "type": "schema_org_itemtype",
                    "detail": "BreadcrumbList found via itemtype attribute",
                })

           
            if not results:
                heuristics = await page.query_selector_all(
                    "[class*='breadcrumb' i], [id*='breadcrumb' i]"
                )
                for el in heuristics:
                    tag = await el.evaluate("el => el.tagName.toLowerCase()")
                    class_name = await el.get_attribute("class") or ""
                    results.append({
                        "type": "heuristic_breadcrumb",
                        "tag": tag,
                        "class": class_name[:60],
                    })

        except Exception as e:
            print(f"Error detecting breadcrumbs: {e}")

        return results

# Tests
if __name__ == "__main__":
    agent = MultipleWaysCheckerAgent()
 
    print("=" * 60)
    print("TEST 1: Nav + search present (expect 2 methods)")
    print("=" * 60)
 
    html1 = """<!DOCTYPE html><html><body>
      <nav>
        <a href="/about">About</a>
        <a href="/products">Products</a>
        <a href="/contact">Contact</a>
      </nav>
      <form role="search">
        <input type="search" placeholder="Search...">
        <button type="submit">Go</button>
      </form>
    </body></html>"""
 
    r1 = agent.execute(html1)
    print(f"Nav links: {len(r1['navigation_links'])}")
    print(f"Search: {len(r1['search'])}")
    print(f"Methods: {r1['methods_found']}/4")
    assert r1["methods_found"] >= 2, f"Expected >= 2 methods, got {r1['methods_found']}"
    print("✓ PASS\n")
 
    print("=" * 60)
    print("TEST 2: Sitemap + breadcrumbs (expect 2 methods)")
    print("=" * 60)
 
    html2 = """<!DOCTYPE html><html><head>
      <link rel="sitemap" href="/sitemap.xml">
    </head><body>
      <nav aria-label="Breadcrumb">
        <a href="/">Home</a> › <a href="/shop">Shop</a> › <span>Widget</span>
      </nav>
      <a href="/about">About</a>
      <a href="/blog">Blog</a>
    </body></html>"""
 
    r2 = agent.execute(html2)
    print(f"Sitemap: {len(r2['sitemap'])}")
    print(f"Breadcrumbs: {len(r2['breadcrumbs'])}")
    print(f"Methods: {r2['methods_found']}/4")
    assert r2["methods_found"] >= 2, f"Expected >= 2 methods, got {r2['methods_found']}"
    print("✓ PASS\n")
 
    print("=" * 60)
    print("TEST 3: Only nav, nothing else (expect 1 method)")
    print("=" * 60)
 
    html3 = """<!DOCTYPE html><html><body>
      <nav>
        <a href="/about">About</a>
        <a href="/contact">Contact</a>
      </nav>
      <main><p>No search, no sitemap, no breadcrumbs.</p></main>
    </body></html>"""
 
    r3 = agent.execute(html3)
    print(f"Nav links: {len(r3['navigation_links'])}")
    print(f"Methods: {r3['methods_found']}/4")
    assert r3["methods_found"] == 1, f"Expected 1 method, got {r3['methods_found']}"
    print("✓ PASS\n")
 
    print("=" * 60)
    print("TEST 4: Login page by title (expect not applicable)")
    print("=" * 60)
 
    html4 = """<!DOCTYPE html><html>
    <head><title>Log in to your account</title></head>
    <body>
      <h1>Log in</h1>
      <form>
        <input type="email" placeholder="Email">
        <input type="password" placeholder="Password">
        <button type="submit">Log in</button>
      </form>
    </body></html>"""
 
    r4 = agent.execute(html4)
    print(f"Applicable: {r4['applicable']}")
    print(f"Reason: {r4['applicability_reason']}")
    print(f"Methods: {r4['methods_found']}/4")
    assert r4["applicable"] is False, "Expected not applicable"
    assert r4["methods_found"] == 0, f"Expected 0 methods, got {r4['methods_found']}"
    print("✓ PASS\n")
 
    print("=" * 60)
    print("TEST 5: Single page, no links out (expect not applicable)")
    print("=" * 60)
 
    html5 = """<!DOCTYPE html><html><body>
      <h1>My Landing Page</h1>
      <p>One page only, nothing else here.</p>
    </body></html>"""
 
    r5 = agent.execute(html5)
    print(f"Applicable: {r5['applicable']}")
    print(f"Reason: {r5['applicability_reason']}")
    print(f"Methods: {r5['methods_found']}/4")
    assert r5["applicable"] is False, "Expected not applicable"
    assert r5["methods_found"] == 0, f"Expected 0 methods, got {r5['methods_found']}"
    print("✓ PASS\n")
 
    print("=" * 60)
    print("TEST 6: All four methods present (expect 4 methods)")
    print("=" * 60)
 
    html6 = """<!DOCTYPE html><html><head>
      <link rel="sitemap" href="/sitemap.xml">
    </head><body>
      <nav>
        <a href="/home">Home</a>
        <a href="/about">About</a>
        <a href="/shop">Shop</a>
      </nav>
      <form role="search">
        <input type="search" placeholder="Search the site">
        <button type="submit">Search</button>
      </form>
      <nav aria-label="Breadcrumb">
        <a href="/">Home</a> › <span>Shop</span>
      </nav>
      <footer><a href="/sitemap.html">Sitemap</a></footer>
    </body></html>"""
 
    r6 = agent.execute(html6)
    print(f"Nav links: {len(r6['navigation_links'])}")
    print(f"Search: {len(r6['search'])}")
    print(f"Sitemap: {len(r6['sitemap'])}")
    print(f"Breadcrumbs: {len(r6['breadcrumbs'])}")
    print(f"Methods: {r6['methods_found']}/4")
    assert r6["methods_found"] == 4, f"Expected 4 methods, got {r6['methods_found']}"
    print("✓ PASS\n")
 
    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)