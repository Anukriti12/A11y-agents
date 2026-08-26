# Persona-Anchored Barrier Labeling — Master Instructions

## What this study measures

Each specialist labels whether specific web pages present a **barrier** to a
specific person with a disability. This is **not** WCAG conformance checking.
A page can pass WCAG and still be a barrier; it can fail WCAG on something this
person never encounters. We are capturing lived-barrier judgment, which is what
the WCAG labels cannot tell us.

## Who labels what

| Specialist | Personas | Rows |
|---|---|---|
| A | Ade (motor, keyboard-only), Ian (autistic) | 18 |
| B | Lakshmi (blind, NVDA), Elias (low vision + tremor) | 18 |
| C | Sophie (Down syndrome), Stefan (ADHD + dyslexia) | 18 |

Each specialist gets:
- `coding_sheet_specialist_X.xlsx` — the sheet to fill (yellow columns only)
- `pages_specialist_X/` — the HTML pages, named `P0xx_persona.html`
- persona `_card.txt` files — read these first, keep open while labeling
- `barrier_checklists.txt` — the grounding categories to cite for each Barrier
- `MANIFEST.txt` — maps page_id to file

## The three labels

- **Barrier** — this person would be blocked, significantly delayed, or excluded.
- **No-Barrier** — this person encounters the relevant elements but can complete the task.
- **Not-Encountered** — the page has nothing this person's profile makes relevant.

**Not-Encountered is persona-relative.** A page of static text is Not-Encountered
for Ade (nothing to operate by keyboard) but might be a Barrier for Stefan
(dense unreadable text). Judge for the person in that row only.

## For every Barrier, also record

- **BARRIER: what blocks them** — 1-2 sentences, your words.
- **SOURCE category** — which grounding document it matches (dropdown). Every
  Barrier must trace to a source, not intuition.
- **SEVERITY** — Blocking / Frustrating / Minor.

## Always record

- **CONFIDENCE** — High / Medium / Low. Use Low when unsure; it flags the row
  for the consensus discussion.
- **notes** — anything ambiguous.

## How to judge a page

1. Open `pages_specialist_X/P0xx_persona.html` in a browser (rendered view).
2. Open the same file in a text editor (HTML source).
3. Read the persona card. Ask the one task question on the card.
4. Assign one label. If Barrier, fill the barrier detail columns.

Look at **both** rendered and source — some barriers are visual (contrast,
motion), some are in the markup (missing alt text, missing labels).

## Rules

1. Judge each (page, person) row independently.
2. Do not make your label agree with whether the page is "technically correct."
3. Choose Not-Encountered only when the page truly has nothing relevant to this
   person — not just because it looks fine.
4. If torn, use the persona card's task question and set CONFIDENCE = Low.
5. Fill only the yellow columns.

## After labeling: the process (for the researcher)

1. Each specialist labels their 18 rows independently. **They are the primary
   annotator for their personas** — there is one specialist per persona pair,
   so specialist labels are the ground truth of record.
2. For inter-annotator reliability, a **20% validation sample (about 11 rows)**
   is cross-labeled: the researcher independently labels those rows, and where
   possible a second specialist labels a few rows outside their own personas
   using the cards. Agreement is computed on this sample.
3. Disagreements are resolved by discussion into a consensus label. Pre-consensus
   labels are kept for the kappa computation.
4. Run `agreement_analysis.py` on the combined sheets.

## The comparison this enables

Once labeled, the key table is, per persona: **WCAG label vs barrier label**.
- WCAG-pass pages that are barriers → conformance misses real barriers.
- WCAG-fail pages that are Not-Encountered/No-Barrier → conformance over-flags
  for this person.
The divergence rows are the qualitative core of the paper.
