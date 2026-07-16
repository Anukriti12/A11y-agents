#!/usr/bin/env python3
"""
build_handauthored.py
======================

Generates hand-authored test cases for WCAG criteria that have no
automated test corpus (W3C ACT, axe-core, IBM Equal Access all skip
them). Writes into the same corpus tree as build_corpus.py.

Each case is grounded in a specific W3C Understanding document and
references the Sufficient Technique (G-series) or Common Failure
(F-series) it demonstrates. Provenance lives in the per-case metadata
JSON so the corpus remains auditable.

SCs covered (all six are empty in ACT for Anukriti's matrix):
  2.4.3 Focus Order              -> Ade
  2.4.5 Multiple Ways            -> Stefan
  2.4.8 Location                 -> Elias, Sophie
  2.5.5 Target Size (AAA)        -> Ade
  3.1.4 Abbreviations            -> Ian, Sophie, Stefan
  3.1.5 Reading Level            -> Ian

Plus targeted backfills for partial buckets that axe also doesn't cover:
  2.4.7 Focus Visible            -> Ade (1 failed needed)
  3.3.1 Error Identification     -> Sophie (1 inapplicable needed)

Run AFTER build_corpus.py and fetch_axe_fixtures.py:
    python build_corpus.py
    python fetch_axe_fixtures.py
    python build_handauthored.py
"""

import argparse
import json
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
#  Persona x WCAG mapping (matches build_corpus.py)                            #
# --------------------------------------------------------------------------- #

PERSONAS_BY_CRITERION = {
    "2.4.3": ["ade"],
    "2.4.5": ["stefan"],
    "2.4.7": ["ade"],
    "2.4.8": ["elias", "sophie"],
    "2.5.5": ["ade"],
    "3.1.4": ["ian", "sophie", "stefan"],
    "3.1.5": ["ian"],
    "3.3.1": ["sophie"],
    "3.3.2": ["sophie"],
}


# --------------------------------------------------------------------------- #
#  Test case authoring helpers                                                 #
# --------------------------------------------------------------------------- #

def html_page(title, body, lang="en", extra_head=""):
    """Wrap body content in a minimal HTML5 page with no leading whitespace."""
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{lang}">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{title}</title>\n"
        f"{extra_head}"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


# --------------------------------------------------------------------------- #
#  Cases                                                                       #
# --------------------------------------------------------------------------- #
# Each case is a dict with keys:
#   id, criterion, expected, title, html, techniques, understanding_url, notes
#
# `techniques` is a list of WCAG technique IDs (G102, H97, F58, etc.)
# `understanding_url` is the canonical W3C URL for the SC
# `notes` is an authoring note kept in the metadata for traceability

CASES = []


# --------------------------------------------------------------------------- #
# 3.1.4 Abbreviations (AAA) — Ian, Sophie, Stefan                              #
#   Understanding: https://www.w3.org/WAI/WCAG21/Understanding/abbreviations
#   Techniques: G102 (expansion), G55 (linked glossary), G62 (in-page glossary),
#               G97 (first-use expansion), H28 (abbr element), F58 (failure)
# --------------------------------------------------------------------------- #

CASES.append({
    "id": "ha-3-1-4-pass-01-abbr-with-title",
    "criterion": "3.1.4",
    "expected": "passed",
    "title": "All abbreviations marked with abbr title attribute",
    "techniques": ["H28", "G102"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/abbreviations.html",
    "notes": "Every abbreviation uses <abbr> with a non-empty title expansion. Technique H28.",
    "html": html_page(
        "Web standards overview",
        """\
  <h1>Web standards overview</h1>
  <p>The <abbr title="World Wide Web Consortium">W3C</abbr> develops standards
  for the web. The <abbr title="Web Content Accessibility Guidelines">WCAG</abbr>
  documents are maintained by the <abbr title="Accessibility Guidelines Working
  Group">AG WG</abbr>. Browsers communicate with servers using
  <abbr title="HyperText Transfer Protocol">HTTP</abbr>.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-4-pass-02-first-use-expansion",
    "criterion": "3.1.4",
    "expected": "passed",
    "title": "First-use expansion before each abbreviation",
    "techniques": ["G97"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/abbreviations.html",
    "notes": "Abbreviations are spelled out in full immediately before their first parenthetical use. Technique G97.",
    "html": html_page(
        "Course registration",
        """\
  <h1>Course registration</h1>
  <p>Submit your registration through the Learning Management System (LMS).
  The LMS will route your request to your academic advisor. Make sure your
  Frequently Asked Questions (FAQ) responses are current. The FAQ section is
  reviewed twice per term.</p>
  <p>If you have a problem, file a Pull Request (PR) against the documentation
  repository. PRs are reviewed within three business days.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-4-fail-01-bare-acronyms",
    "criterion": "3.1.4",
    "expected": "failed",
    "title": "Multiple bare acronyms with no expansion mechanism",
    "techniques": ["F58"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/abbreviations.html",
    "notes": "Multiple acronyms (REST, JSON, CRUD, ORM, ETL) appear with no <abbr> markup, no first-use expansion, and no glossary link. Failure F58 pattern.",
    "html": html_page(
        "API design notes",
        """\
  <h1>API design notes</h1>
  <p>The new endpoint exposes a REST interface returning JSON. CRUD operations
  map cleanly onto HTTP verbs. The persistence layer uses an ORM backed by
  PostgreSQL. Data ingestion runs through an ETL pipeline on a nightly
  schedule.</p>
  <p>ANSI escape sequences in the CLI output should be stripped before
  forwarding to the CI logs.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-4-fail-02-empty-abbr-title",
    "criterion": "3.1.4",
    "expected": "failed",
    "title": "abbr elements with empty or self-referential title",
    "techniques": ["F58"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/abbreviations.html",
    "notes": "Abbreviations are marked with <abbr> but the title attribute is either empty or just repeats the abbreviation. No actual expansion.",
    "html": html_page(
        "Lab procedures",
        """\
  <h1>Lab procedures</h1>
  <p>Run the <abbr title="">PCR</abbr> using the standard thermocycler. Store
  the <abbr title="DNA">DNA</abbr> samples at minus eighty degrees Celsius.
  Document your <abbr>SOP</abbr> deviations in the lab notebook.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-4-inap-01-no-abbreviations",
    "criterion": "3.1.4",
    "expected": "inapplicable",
    "title": "Page contains no abbreviations",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/abbreviations.html",
    "notes": "Body text uses no abbreviations or acronyms, so the criterion does not apply.",
    "html": html_page(
        "Welcome to the garden",
        """\
  <h1>Welcome to the garden</h1>
  <p>The community garden opens at sunrise and closes at sunset. Members may
  bring family and friends. Tools are stored in the wooden shed by the gate.
  Please return them clean.</p>
  <p>Water the seedlings in the morning when the air is cool. Pull weeds
  before they go to seed.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-4-inap-02-only-common-words",
    "criterion": "3.1.4",
    "expected": "inapplicable",
    "title": "Only abbreviations that have become common words",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/abbreviations.html",
    "notes": "Words like radar, scuba, and laser are technically acronyms but are part of standard vocabulary; the criterion notes these need not be expanded.",
    "html": html_page(
        "Marine research",
        """\
  <h1>Marine research</h1>
  <p>Researchers use radar to track surface vessels and scuba equipment for
  shallow dives. Laser-based ranging gives precise distance measurements
  through clear water. Crews monitor conditions throughout the night.</p>""",
    ),
})


# --------------------------------------------------------------------------- #
# 3.1.5 Reading Level (AAA) — Ian                                              #
#   Understanding: https://www.w3.org/WAI/WCAG21/Understanding/reading-level
#   Techniques: G86 (text summary), G103 (illustrations), G153 (simpler text),
#               G160 (sign language), G79 (audio version)
# --------------------------------------------------------------------------- #

CASES.append({
    "id": "ha-3-1-5-pass-01-with-summary",
    "criterion": "3.1.5",
    "expected": "passed",
    "title": "Technical text with prominent plain-language summary",
    "techniques": ["G86"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/reading-level.html",
    "notes": "A complex passage is preceded by an explicit Plain Language Summary written at lower-secondary reading level. Technique G86.",
    "html": html_page(
        "Mitochondrial inheritance",
        """\
  <h1>Mitochondrial inheritance</h1>

  <section aria-label="Plain language summary">
    <h2>Plain language summary</h2>
    <p>Most of your genes come from both parents. But the tiny power plants
    inside your cells, called mitochondria, come only from your mother. This
    is why some diseases pass only from mothers to their children.</p>
  </section>

  <section>
    <h2>Detail</h2>
    <p>Mitochondrial DNA is inherited matrilineally because the cytoplasm of
    the zygote derives almost exclusively from the ovum. Paternal mitochondria
    introduced during fertilization are subsequently degraded by ubiquitin
    tagging. Disorders associated with deleterious mitochondrial variants
    therefore exhibit a characteristic non-Mendelian inheritance pattern.</p>
  </section>""",
    ),
})

CASES.append({
    "id": "ha-3-1-5-pass-02-simple-prose",
    "criterion": "3.1.5",
    "expected": "passed",
    "title": "Prose written at lower-secondary reading level throughout",
    "techniques": ["G153"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/reading-level.html",
    "notes": "Short sentences, common vocabulary, no jargon. Should test as lower-secondary reading level by readability indices.",
    "html": html_page(
        "How to wash your hands",
        """\
  <h1>How to wash your hands</h1>
  <p>Hand washing keeps you healthy. It stops germs from spreading.</p>
  <ol>
    <li>Turn on the water. Make it warm.</li>
    <li>Get your hands wet.</li>
    <li>Put soap on your hands.</li>
    <li>Rub your hands together for twenty seconds.</li>
    <li>Rinse off the soap.</li>
    <li>Dry your hands with a clean towel.</li>
  </ol>
  <p>Wash your hands before you eat. Wash them after you use the bathroom.
  Wash them when they look dirty.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-5-fail-01-dense-academic",
    "criterion": "3.1.5",
    "expected": "failed",
    "title": "Dense academic prose with no simplification offered",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/reading-level.html",
    "notes": "Long compound sentences, specialized vocabulary, passive voice, multiple subordinate clauses. No summary, no glossary, no illustration. Reading indices should land well above lower-secondary.",
    "html": html_page(
        "Phenomenological reduction",
        """\
  <h1>Phenomenological reduction in twentieth-century continental thought</h1>
  <p>The phenomenological reduction, as it was elaborated by Husserl in the
  course of his lectures on the constitution of intersubjectively shared
  meaning, presupposes the methodological suspension, or epoche, of the
  natural attitude that ordinarily takes for granted the mind-independent
  existence of the objects encountered in everyday perceptual experience,
  and only by means of this suspension does the analysis of the noetic
  structures through which such objects are intentionally constituted in
  consciousness become possible.</p>
  <p>The subsequent reception of this methodological commitment by
  Merleau-Ponty, who simultaneously appropriated and transformed it by
  reintroducing the embodied subject as the locus of perceptual synthesis,
  represents one of several divergent post-Husserlian trajectories whose
  reverberations continue to inform contemporary discussions of intentionality
  and embodiment within the broader phenomenological tradition.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-5-fail-02-legal-density",
    "criterion": "3.1.5",
    "expected": "failed",
    "title": "Legal-style disclaimer with no plain-language alternative",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/reading-level.html",
    "notes": "Stacked clauses, archaic conjunctions, no summary, no simpler version offered.",
    "html": html_page(
        "Terms of service",
        """\
  <h1>Terms of service</h1>
  <p>By accessing this site, the user, hereinafter referred to as the Party of
  the Second Part, acknowledges, represents, and warrants that the Party of
  the Second Part has read, understood, and agrees to be bound by the totality
  of the provisions enumerated herein, including but not limited to the
  limitations on liability, indemnification obligations, and the choice-of-law
  provisions specified in section twelve, and further acknowledges that the
  failure to comply with any provision herein may result in the immediate
  termination of access, without prejudice to any other remedies available to
  the Party of the First Part under applicable law.</p>""",
    ),
})

CASES.append({
    "id": "ha-3-1-5-inap-01-minimal-text",
    "criterion": "3.1.5",
    "expected": "inapplicable",
    "title": "Page contains insufficient prose to evaluate reading level",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/reading-level.html",
    "notes": "Page is a contact form with field labels and minimal instructional text. Not running prose, so reading-level analysis is not applicable.",
    "html": html_page(
        "Contact",
        """\
  <h1>Contact</h1>
  <form action="/submit" method="post">
    <p><label for="name">Name</label> <input id="name" name="name" type="text"></p>
    <p><label for="email">Email</label> <input id="email" name="email" type="email"></p>
    <p><label for="msg">Message</label> <textarea id="msg" name="msg"></textarea></p>
    <p><button type="submit">Send</button></p>
  </form>""",
    ),
})

CASES.append({
    "id": "ha-3-1-5-inap-02-proper-names",
    "criterion": "3.1.5",
    "expected": "inapplicable",
    "title": "Page consists primarily of proper names and lists",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/reading-level.html",
    "notes": "Faculty directory listing. Names and titles, not running prose, so reading-level evaluation does not apply.",
    "html": html_page(
        "Faculty directory",
        """\
  <h1>Faculty directory</h1>
  <ul>
    <li>Dr. Aniket Patel, Professor</li>
    <li>Dr. Caroline Yu, Associate Professor</li>
    <li>Dr. Mehmet Aydin, Assistant Professor</li>
    <li>Dr. Priya Chandrasekaran, Lecturer</li>
    <li>Dr. Joaquin Reyes, Postdoctoral Researcher</li>
  </ul>""",
    ),
})


# --------------------------------------------------------------------------- #
# 2.4.5 Multiple Ways (AA) — Stefan                                            #
#   Understanding: https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways
#   Techniques: G125 (links to related pages), G126 (list of links), G63 (sitemap),
#               G64 (TOC), G161 (search), H59 (link element)
# --------------------------------------------------------------------------- #

CASES.append({
    "id": "ha-2-4-5-pass-01-nav-plus-search",
    "criterion": "2.4.5",
    "expected": "passed",
    "title": "Navigation menu and search both present",
    "techniques": ["G125", "G161"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways.html",
    "notes": "Page has primary navigation plus a search form. Two independent ways to locate content.",
    "html": html_page(
        "Library home",
        """\
  <header>
    <nav aria-label="Primary">
      <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/catalog">Catalog</a></li>
        <li><a href="/research">Research guides</a></li>
        <li><a href="/services">Services</a></li>
        <li><a href="/about">About</a></li>
      </ul>
    </nav>
    <form action="/search" method="get" role="search">
      <label for="q">Search the catalog</label>
      <input id="q" name="q" type="search">
      <button type="submit">Search</button>
    </form>
  </header>
  <main>
    <h1>University library</h1>
    <p>Welcome to the library home page.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-5-pass-02-nav-sitemap-breadcrumb",
    "criterion": "2.4.5",
    "expected": "passed",
    "title": "Navigation, sitemap link, and breadcrumb",
    "techniques": ["G125", "G63"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways.html",
    "notes": "Three independent ways to locate content: primary nav, sitemap, and breadcrumb path.",
    "html": html_page(
        "Astronomy resources",
        """\
  <header>
    <nav aria-label="Primary">
      <a href="/">Home</a> | <a href="/subjects">Subjects</a> |
      <a href="/sitemap">Sitemap</a>
    </nav>
    <nav aria-label="Breadcrumb">
      <ol>
        <li><a href="/">Home</a></li>
        <li><a href="/subjects">Subjects</a></li>
        <li><a href="/subjects/science">Science</a></li>
        <li aria-current="page">Astronomy</li>
      </ol>
    </nav>
  </header>
  <main>
    <h1>Astronomy resources</h1>
    <p>Selected references and databases.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-5-fail-01-nav-only",
    "criterion": "2.4.5",
    "expected": "failed",
    "title": "Only a navigation menu, no second discovery method",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways.html",
    "notes": "Only one mechanism (nav menu). No search, no sitemap, no breadcrumb, no TOC.",
    "html": html_page(
        "Department of biology",
        """\
  <header>
    <nav aria-label="Primary">
      <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/people">People</a></li>
        <li><a href="/research">Research</a></li>
        <li><a href="/courses">Courses</a></li>
      </ul>
    </nav>
  </header>
  <main>
    <h1>Department of biology</h1>
    <p>The department covers organismal and molecular biology.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-5-fail-02-search-only",
    "criterion": "2.4.5",
    "expected": "failed",
    "title": "Only a search box, no second discovery method",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways.html",
    "notes": "Search is present but no menu, sitemap, or any other location aid.",
    "html": html_page(
        "Knowledge base",
        """\
  <main>
    <h1>Knowledge base</h1>
    <form action="/find" method="get" role="search">
      <label for="kb-q">Search articles</label>
      <input id="kb-q" name="q" type="search">
      <button type="submit">Find</button>
    </form>
    <p>Type a keyword to search the knowledge base.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-5-inap-01-process-page",
    "criterion": "2.4.5",
    "expected": "inapplicable",
    "title": "Page is a step in a process and exempt from 2.4.5",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways.html",
    "notes": "Checkout confirmation page. SC 2.4.5 explicitly exempts pages that are a step in a process.",
    "html": html_page(
        "Order confirmation",
        """\
  <main>
    <h1>Order confirmation</h1>
    <p>Thank you. Your order number is 4827-AX. A confirmation email has
    been sent to the address on file.</p>
    <p><a href="/orders/4827-AX">View order details</a></p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-5-inap-02-login-page",
    "criterion": "2.4.5",
    "expected": "inapplicable",
    "title": "Standalone authentication page",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/multiple-ways.html",
    "notes": "Login page. Exempt as a step in the authentication process.",
    "html": html_page(
        "Sign in",
        """\
  <main>
    <h1>Sign in</h1>
    <form action="/auth" method="post">
      <p><label for="u">Username</label> <input id="u" name="u" type="text"></p>
      <p><label for="p">Password</label> <input id="p" name="p" type="password"></p>
      <p><button type="submit">Sign in</button></p>
    </form>
  </main>""",
    ),
})


# --------------------------------------------------------------------------- #
# 2.4.8 Location (AAA) — Elias, Sophie                                         #
#   Understanding: https://www.w3.org/WAI/WCAG21/Understanding/location
#   Techniques: G65 (breadcrumb), G63 (sitemap), G127 (current location in
#               hierarchy), H59 (link element)
# --------------------------------------------------------------------------- #

CASES.append({
    "id": "ha-2-4-8-pass-01-breadcrumb-with-current",
    "criterion": "2.4.8",
    "expected": "passed",
    "title": "Breadcrumb shows full path and current page",
    "techniques": ["G65"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/location.html",
    "notes": "Breadcrumb trail terminates with the current page marked aria-current=\"page\". Technique G65.",
    "html": html_page(
        "Quarterly report",
        """\
  <nav aria-label="Breadcrumb">
    <ol>
      <li><a href="/">Home</a></li>
      <li><a href="/reports">Reports</a></li>
      <li><a href="/reports/2026">2026</a></li>
      <li aria-current="page">Q1 quarterly report</li>
    </ol>
  </nav>
  <main>
    <h1>Q1 quarterly report</h1>
    <p>Summary of first-quarter activity.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-8-pass-02-current-link-highlighted",
    "criterion": "2.4.8",
    "expected": "passed",
    "title": "Navigation marks the current page with aria-current",
    "techniques": ["G127"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/location.html",
    "notes": "Primary nav indicates current section using aria-current=\"page\". Reader knows where they are within the site structure.",
    "html": html_page(
        "Admissions",
        """\
  <nav aria-label="Primary">
    <ul>
      <li><a href="/">Home</a></li>
      <li><a href="/about">About</a></li>
      <li><a href="/admissions" aria-current="page">Admissions</a></li>
      <li><a href="/programs">Programs</a></li>
    </ul>
  </nav>
  <main>
    <h1>Admissions</h1>
    <p>Information about applying for graduate programs.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-8-fail-01-deep-page-no-trail",
    "criterion": "2.4.8",
    "expected": "failed",
    "title": "Deeply nested page with no breadcrumb or location indicator",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/location.html",
    "notes": "Page is three levels deep in the site hierarchy but provides no breadcrumb, no current-page indicator, and the nav does not show which section is active.",
    "html": html_page(
        "Photosynthesis lab procedure",
        """\
  <nav aria-label="Primary">
    <a href="/">Home</a> | <a href="/courses">Courses</a> | <a href="/help">Help</a>
  </nav>
  <main>
    <h1>Lab procedure</h1>
    <p>Set up the apparatus as shown in figure one. Record the readings every
    thirty seconds for ten minutes.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-8-fail-02-breadcrumb-missing-current",
    "criterion": "2.4.8",
    "expected": "failed",
    "title": "Breadcrumb omits the current location",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/location.html",
    "notes": "Breadcrumb shows ancestor pages but does not include the current page, leaving the user unsure where they are within the hierarchy.",
    "html": html_page(
        "Hardware troubleshooting",
        """\
  <nav aria-label="Breadcrumb">
    <ol>
      <li><a href="/">Home</a></li>
      <li><a href="/support">Support</a></li>
    </ol>
  </nav>
  <main>
    <h1>Hardware troubleshooting</h1>
    <p>Diagnose and resolve common hardware issues.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-8-inap-01-homepage",
    "criterion": "2.4.8",
    "expected": "inapplicable",
    "title": "Homepage has no parent location to indicate",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/location.html",
    "notes": "Top-level homepage with no ancestors. Location indicators do not apply because the page IS home.",
    "html": html_page(
        "Welcome",
        """\
  <header>
    <h1>Welcome to the community center</h1>
  </header>
  <main>
    <p>Our doors are open Monday through Saturday.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-8-inap-02-single-page-app",
    "criterion": "2.4.8",
    "expected": "inapplicable",
    "title": "Single-purpose page with no site hierarchy",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/location.html",
    "notes": "Page is a standalone calculator with no surrounding site structure. Location indicator would have nothing to indicate.",
    "html": html_page(
        "Unit converter",
        """\
  <main>
    <h1>Unit converter</h1>
    <p><label for="cm">Centimeters</label> <input id="cm" type="number"></p>
    <p><label for="inch">Inches</label> <input id="inch" type="number"></p>
    <p><button type="button">Convert</button></p>
  </main>""",
    ),
})


# --------------------------------------------------------------------------- #
# 2.4.3 Focus Order (A) — Ade                                                  #
#   Understanding: https://www.w3.org/WAI/WCAG21/Understanding/focus-order
#   Techniques: G59 (DOM order matches presentation), H4 (positive tabindex
#               avoided), F44 (failure: tabindex disrupts order)
# --------------------------------------------------------------------------- #

CASES.append({
    "id": "ha-2-4-3-pass-01-natural-dom-order",
    "criterion": "2.4.3",
    "expected": "passed",
    "title": "Form follows natural DOM order matching visual order",
    "techniques": ["G59"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html",
    "notes": "Form fields appear in source order matching visual top-to-bottom order. No tabindex overrides.",
    "html": html_page(
        "Sign up",
        """\
  <main>
    <h1>Sign up</h1>
    <form action="/signup" method="post">
      <p><label for="fn">First name</label> <input id="fn" name="fn" type="text"></p>
      <p><label for="ln">Last name</label> <input id="ln" name="ln" type="text"></p>
      <p><label for="em">Email</label> <input id="em" name="em" type="email"></p>
      <p><label for="pw">Password</label> <input id="pw" name="pw" type="password"></p>
      <p><button type="submit">Create account</button></p>
    </form>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-3-pass-02-modal-focus-trap",
    "criterion": "2.4.3",
    "expected": "passed",
    "title": "Modal dialog keeps focus inside the dialog",
    "techniques": ["G59"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html",
    "notes": "Open modal with focusable controls. Background content is inert. Focus order is dialog-internal and matches reading order.",
    "html": html_page(
        "Delete account",
        """\
  <main inert>
    <h1>Account</h1>
    <p>Background content is inert while the dialog is open.</p>
  </main>
  <div role="dialog" aria-modal="true" aria-labelledby="dlg-h">
    <h2 id="dlg-h">Delete account?</h2>
    <p>This action cannot be undone.</p>
    <button type="button">Cancel</button>
    <button type="button">Delete account</button>
  </div>""",
    ),
})

CASES.append({
    "id": "ha-2-4-3-fail-01-positive-tabindex",
    "criterion": "2.4.3",
    "expected": "failed",
    "title": "Positive tabindex values disrupt natural focus order",
    "techniques": ["F44"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html",
    "notes": "Positive tabindex values (3, 1, 2) cause tab order to jump around relative to visual order. Failure F44.",
    "html": html_page(
        "Survey",
        """\
  <main>
    <h1>Survey</h1>
    <form action="/submit" method="post">
      <p><label for="q1">Question 1</label> <input id="q1" name="q1" tabindex="3"></p>
      <p><label for="q2">Question 2</label> <input id="q2" name="q2" tabindex="1"></p>
      <p><label for="q3">Question 3</label> <input id="q3" name="q3" tabindex="2"></p>
      <p><button type="submit" tabindex="4">Submit</button></p>
    </form>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-3-fail-02-visual-reorder-css",
    "criterion": "2.4.3",
    "expected": "failed",
    "title": "CSS flex order does not match DOM order",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html",
    "notes": "Visual order via CSS flexbox order property does not match source order. Keyboard users tab through fields in source order while seeing them in visual order, producing confusion.",
    "html": html_page(
        "Address form",
        """\
  <style>
    .row { display: flex; }
    .row :nth-child(1) { order: 3; }
    .row :nth-child(2) { order: 1; }
    .row :nth-child(3) { order: 2; }
  </style>
  <main>
    <h1>Address</h1>
    <form action="/save" method="post">
      <div class="row">
        <label>Street <input name="street"></label>
        <label>City <input name="city"></label>
        <label>State <input name="state"></label>
      </div>
    </form>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-3-inap-01-static-content",
    "criterion": "2.4.3",
    "expected": "inapplicable",
    "title": "Page has no focusable elements",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html",
    "notes": "Static article with no interactive elements. Focus order is not applicable.",
    "html": html_page(
        "About the project",
        """\
  <main>
    <h1>About the project</h1>
    <p>This project began in 2024 and is run by a small team of volunteers.
    Materials are released under a permissive license.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-4-3-inap-02-single-interactive",
    "criterion": "2.4.3",
    "expected": "inapplicable",
    "title": "Page has only one focusable element",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html",
    "notes": "Page has a single button. With only one focusable element, focus order has no sequence to evaluate.",
    "html": html_page(
        "Maintenance",
        """\
  <main>
    <h1>Maintenance window</h1>
    <p>The system is currently undergoing scheduled maintenance.</p>
    <p><button type="button">Refresh</button></p>
  </main>""",
    ),
})


# --------------------------------------------------------------------------- #
# 2.5.5 Target Size (AAA) — Ade                                                #
#   Understanding: https://www.w3.org/WAI/WCAG21/Understanding/target-size
#   2.5.5 AAA threshold is 44x44 CSS px. Note: distinct from 2.5.8 AA (24x24).
# --------------------------------------------------------------------------- #

CASES.append({
    "id": "ha-2-5-5-pass-01-large-buttons",
    "criterion": "2.5.5",
    "expected": "passed",
    "title": "Buttons sized at or above 44x44 CSS pixels",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/target-size.html",
    "notes": "Both action buttons have explicit min-width and min-height of 48px, exceeding the 44px AAA threshold.",
    "html": html_page(
        "Settings",
        """\
  <style>
    .action { min-width: 48px; min-height: 48px; padding: 8px 16px;
              margin: 12px; font-size: 16px; }
  </style>
  <main>
    <h1>Notification settings</h1>
    <button class="action" type="button">Save changes</button>
    <button class="action" type="button">Cancel</button>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-5-5-pass-02-icon-with-padding",
    "criterion": "2.5.5",
    "expected": "passed",
    "title": "Small icon with generous touch padding reaches 44x44",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/target-size.html",
    "notes": "Visual icon is 16x16 but the surrounding clickable area is 48x48 through padding.",
    "html": html_page(
        "Toolbar",
        """\
  <style>
    .icon-btn {
      width: 48px; height: 48px;
      padding: 16px;
      box-sizing: border-box;
      background: transparent;
      border: 1px solid #888;
    }
    .icon { width: 16px; height: 16px; display: block; }
  </style>
  <main>
    <h1>Document toolbar</h1>
    <button class="icon-btn" aria-label="Bold">
      <span class="icon">B</span>
    </button>
    <button class="icon-btn" aria-label="Italic">
      <span class="icon">I</span>
    </button>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-5-5-fail-01-tiny-icons",
    "criterion": "2.5.5",
    "expected": "failed",
    "title": "Tightly packed icon buttons well below 44x44",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/target-size.html",
    "notes": "Icon buttons sized 20x20 with no padding. Below both 2.5.8 AA (24x24) and 2.5.5 AAA (44x44) thresholds.",
    "html": html_page(
        "Image gallery",
        """\
  <style>
    .icon-btn {
      width: 20px; height: 20px;
      padding: 0; margin: 2px;
      font-size: 10px;
      border: 1px solid #888;
    }
  </style>
  <main>
    <h1>Photo</h1>
    <div>
      <button class="icon-btn" aria-label="Previous">&lt;</button>
      <button class="icon-btn" aria-label="Zoom in">+</button>
      <button class="icon-btn" aria-label="Zoom out">-</button>
      <button class="icon-btn" aria-label="Next">&gt;</button>
    </div>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-5-5-fail-02-short-buttons",
    "criterion": "2.5.5",
    "expected": "failed",
    "title": "Standard buttons styled below 44px height",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/target-size.html",
    "notes": "Buttons are wide enough horizontally but only 28px tall, below the 44px AAA threshold.",
    "html": html_page(
        "Form actions",
        """\
  <style>
    button { height: 28px; padding: 0 12px; margin: 4px;
             font-size: 13px; }
  </style>
  <main>
    <h1>Edit profile</h1>
    <button type="button">Save</button>
    <button type="button">Discard</button>
    <button type="button">Preview</button>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-5-5-inap-01-inline-link-in-text",
    "criterion": "2.5.5",
    "expected": "inapplicable",
    "title": "Only interactive element is an inline link within text",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/target-size.html",
    "notes": "WCAG 2.5.5 explicitly exempts inline links within a sentence. The only target on the page is one such inline link.",
    "html": html_page(
        "About",
        """\
  <main>
    <h1>About our team</h1>
    <p>We started in 2024. You can read more on our
    <a href="/history">history page</a>.</p>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-2-5-5-inap-02-no-interactive",
    "criterion": "2.5.5",
    "expected": "inapplicable",
    "title": "Page has no interactive targets at all",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/target-size.html",
    "notes": "Information-only page with no buttons, links, or other targets. Target size has nothing to evaluate.",
    "html": html_page(
        "Closure notice",
        """\
  <main>
    <h1>Office closure notice</h1>
    <p>The office is closed for the federal holiday. Normal hours resume
    tomorrow.</p>
  </main>""",
    ),
})


# --------------------------------------------------------------------------- #
# Targeted partial backfills                                                   #
# --------------------------------------------------------------------------- #

# Ade 2.4.7 needs 1 failed; axe doesn't cover. One hand-authored failed.
CASES.append({
    "id": "ha-2-4-7-fail-01-focus-suppressed",
    "criterion": "2.4.7",
    "expected": "failed",
    "title": "Focus indicator suppressed via CSS outline removal",
    "techniques": ["F78"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/focus-visible.html",
    "notes": "Global CSS sets outline:none on focusable elements with no replacement, eliminating any visible focus indicator. Failure F78.",
    "html": html_page(
        "Newsletter",
        """\
  <style>
    a, button, input, select, textarea { outline: none; }
    a:focus, button:focus, input:focus { outline: none; box-shadow: none; }
  </style>
  <main>
    <h1>Newsletter signup</h1>
    <form>
      <p><label for="ne">Email</label> <input id="ne" name="email" type="email"></p>
      <p><button type="submit">Subscribe</button></p>
      <p><a href="/privacy">Privacy policy</a></p>
    </form>
  </main>""",
    ),
})

# Sophie 3.3.1 needs 1 inapplicable; hand-author a page with no form at all
CASES.append({
    "id": "ha-3-3-1-inap-01-no-form",
    "criterion": "3.3.1",
    "expected": "inapplicable",
    "title": "Page has no form fields and no error states",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/error-identification.html",
    "notes": "Page is informational with no inputs and no submitted-form error UI. SC 3.3.1 has nothing to evaluate.",
    "html": html_page(
        "Reading list",
        """\
  <main>
    <h1>Suggested reading</h1>
    <ul>
      <li>Designing for accessibility</li>
      <li>Inclusive design patterns</li>
      <li>Practical accessibility</li>
    </ul>
  </main>""",
    ),
})


# --------------------------------------------------------------------------- #
# 3.3.2 Labels or Instructions (A) — Sophie                                    #
#   Understanding: https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions
#   Techniques: G131 (descriptive labels), H44 (label element), H71 (fieldset
#               and legend for groups), G89 (expected data format), G184 (text
#               instructions at start of form)
# --------------------------------------------------------------------------- #

CASES.append({
    "id": "ha-3-3-2-pass-01-labels-and-instructions",
    "criterion": "3.3.2",
    "expected": "passed",
    "title": "All inputs have labels and format instructions are given",
    "techniques": ["H44", "G89", "G184"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html",
    "notes": "Every input has a <label>. Format requirements stated inline (date format, phone format). Required fields marked with text, not color alone.",
    "html": html_page(
        "Appointment booking",
        """\
  <main>
    <h1>Book an appointment</h1>
    <p>Fields marked (required) must be filled in.</p>
    <form action="/book" method="post">
      <p>
        <label for="name">Full name (required)</label>
        <input id="name" name="name" type="text" required>
      </p>
      <p>
        <label for="dob">Date of birth (required, format YYYY-MM-DD)</label>
        <input id="dob" name="dob" type="text" required>
      </p>
      <p>
        <label for="phone">Phone (format: 555-123-4567)</label>
        <input id="phone" name="phone" type="tel">
      </p>
      <p><button type="submit">Book</button></p>
    </form>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-3-3-2-pass-02-fieldset-grouped",
    "criterion": "3.3.2",
    "expected": "passed",
    "title": "Radio group with fieldset and legend",
    "techniques": ["H71", "H44"],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html",
    "notes": "Radio button group is wrapped in a fieldset with a legend describing the question. Each option has an explicit label.",
    "html": html_page(
        "Notification preferences",
        """\
  <main>
    <h1>Notification preferences</h1>
    <form action="/prefs" method="post">
      <fieldset>
        <legend>How should we contact you about your order?</legend>
        <p>
          <input id="c-email" name="contact" type="radio" value="email">
          <label for="c-email">Email</label>
        </p>
        <p>
          <input id="c-sms" name="contact" type="radio" value="sms">
          <label for="c-sms">Text message</label>
        </p>
        <p>
          <input id="c-none" name="contact" type="radio" value="none">
          <label for="c-none">Do not contact me</label>
        </p>
      </fieldset>
      <p><button type="submit">Save</button></p>
    </form>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-3-3-2-inap-01-no-inputs",
    "criterion": "3.3.2",
    "expected": "inapplicable",
    "title": "Page has no user input fields",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html",
    "notes": "Page is a news article with no form inputs at all. SC 3.3.2 only applies where users provide input.",
    "html": html_page(
        "City announces park renovation",
        """\
  <main>
    <article>
      <h1>City announces park renovation</h1>
      <p>The city council voted Tuesday to approve a renovation of the
      central park. Work is expected to begin in the spring and complete
      by the end of summer.</p>
      <p>Improvements include new walking paths, additional benches, and
      replacement playground equipment.</p>
    </article>
  </main>""",
    ),
})

CASES.append({
    "id": "ha-3-3-2-inap-02-only-hidden-inputs",
    "criterion": "3.3.2",
    "expected": "inapplicable",
    "title": "Page contains only hidden form inputs not requiring user input",
    "techniques": [],
    "understanding_url": "https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html",
    "notes": "Form contains only hidden inputs (CSRF token, session id) with a single submit button. No user-facing inputs to label.",
    "html": html_page(
        "Log out",
        """\
  <main>
    <h1>Log out</h1>
    <p>Click the button below to end your session.</p>
    <form action="/logout" method="post">
      <input type="hidden" name="csrf_token" value="abc123xyz">
      <input type="hidden" name="session_id" value="s-987654">
      <button type="submit">Log out</button>
    </form>
  </main>""",
    ),
})


# --------------------------------------------------------------------------- #
#  Writer                                                                      #
# --------------------------------------------------------------------------- #

def write_case(case, output_root):
    """Write one hand-authored case to every persona folder for its criterion."""
    criterion = case["criterion"]
    personas = PERSONAS_BY_CRITERION.get(criterion, [])
    if not personas:
        print(f"  SKIP {case['id']}: no persona uses {criterion}")
        return 0

    written = 0
    for persona in personas:
        target_dir = output_root / persona / criterion / case["expected"]
        target_dir.mkdir(parents=True, exist_ok=True)

        html_path = target_dir / f"{case['id']}.html"
        json_path = target_dir / f"{case['id']}.json"

        html_path.write_text(case["html"], encoding="utf-8")

        metadata = {
            "testcaseId": case["id"],
            "testcaseTitle": case["title"],
            "expected": case["expected"],
            "source": "hand-authored from W3C Understanding",
            "wcag_techniques": case.get("techniques", []),
            "understanding_url": case["understanding_url"],
            "authoring_notes": case["notes"],
            "wcag_criterion_in_corpus": criterion,
            "persona_folder": persona,
        }
        json_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        written += 1

    return written


def main():
    parser = argparse.ArgumentParser(
        description="Add hand-authored cases to the A11yAgents corpus."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("corpus"),
        help="Corpus root directory (default: ./corpus)",
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

    print(f"Writing {len(CASES)} hand-authored cases into {output_root}/ ...\n")

    # Per-criterion report
    by_criterion = {}
    total_files = 0
    for case in CASES:
        c = case["criterion"]
        by_criterion.setdefault(c, {"passed": 0, "failed": 0, "inapplicable": 0})
        by_criterion[c][case["expected"]] += 1
        total_files += write_case(case, output_root)

    print("\nPer-criterion case counts (unique cases, before persona duplication):")
    for c in sorted(by_criterion):
        b = by_criterion[c]
        personas = PERSONAS_BY_CRITERION.get(c, [])
        print(
            f"  {c:7s} passed={b['passed']} failed={b['failed']} "
            f"inapplicable={b['inapplicable']}  "
            f"(personas: {', '.join(personas)})"
        )
    print(f"\nTotal files written (incl. cross-persona duplication): {total_files}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
