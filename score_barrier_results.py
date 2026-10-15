"""
Score barrier-task results against the specialist labels.

Repetitions are collapsed by majority vote per (page, condition, model);
ties and all-error rows count as "error" (wrong). Reports, per condition:
  - 3-way accuracy and Cohen's kappa (Barrier / No-Barrier / Not-Encountered)
  - binary accuracy (Barrier vs. not), Barrier precision / recall / F1
  - binary accuracy per persona

With --wcag-xlsx, the earlier WCAG-task outputs (results/wcag_eval_analysis*.xlsx)
are scored on the same rows after mapping failed->Barrier,
passed->No-Barrier, inapplicable->Not-Encountered. That is the "same systems,
different ground truth / different question" comparison.

Usage:
    python score_barrier_results.py results/barrier/barrier_sonnet46.jsonl
    python score_barrier_results.py results/barrier/*.jsonl --wcag-xlsx results/wcag_eval_analysis1.xlsx
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_LABELS = ROOT / "barrier_study" / "ground_truth" / "barrier_labels_v0.csv"
LABELS = ["Barrier", "No-Barrier", "Not-Encountered"]
WCAG_TO_BARRIER = {"failed": "Barrier", "passed": "No-Barrier", "inapplicable": "Not-Encountered"}
WCAG_SHEETS = ["A_axe", "B_persona_llm", "C_persona_agent", "D_vanilla_llm", "E_vanilla_agent"]


def majority(votes):
    c = Counter(votes).most_common()
    if len(c) > 1 and c[0][1] == c[1][1]:
        return "error"
    return c[0][0]


def cohen_kappa(gold, pred):
    n = len(gold)
    if n == 0:
        return float("nan")
    po = sum(g == p for g, p in zip(gold, pred)) / n
    cg, cp = Counter(gold), Counter(pred)
    pe = sum(cg[k] * cp[k] for k in set(cg) | set(cp)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def score(name, preds, gold, persona_of):
    """preds/gold: dict page_id -> label. Only pages present in both are scored."""
    ids = sorted(p for p in preds if p in gold)
    g = [gold[p] for p in ids]
    p = [preds[p] for p in ids]
    n = len(ids)
    if n == 0:
        return None
    acc3 = sum(a == b for a, b in zip(g, p)) / n
    gb = [x == "Barrier" for x in g]
    pb = [x == "Barrier" for x in p]
    tp = sum(a and b for a, b in zip(gb, pb))
    fp = sum(b and not a for a, b in zip(gb, pb))
    fn = sum(a and not b for a, b in zip(gb, pb))
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if tp else 0.0
    accb = sum(a == b for a, b in zip(gb, pb)) / n
    per = defaultdict(lambda: [0, 0])
    for pid, a, b in zip(ids, gb, pb):
        per[persona_of[pid]][0] += a == b
        per[persona_of[pid]][1] += 1
    return {
        "condition": name, "n": n, "errors": p.count("error"),
        "acc_3way": acc3, "kappa_3way": cohen_kappa(g, p),
        "acc_binary": accb, "barrier_P": prec, "barrier_R": rec, "barrier_F1": f1,
        "tp": tp, "fp": fp, "fn": fn,
        "per_persona_binary": {k: f"{v[0]}/{v[1]}" for k, v in sorted(per.items())},
    }


def load_barrier_jsonl(paths):
    votes = defaultdict(list)
    for path in paths:
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            votes[(r["condition"], r["model"], r["page_id"])].append(r["evaluated"])
    preds = defaultdict(dict)
    for (cond, model, pid), v in votes.items():
        preds[f"barrier-task {cond} [{model}]"][pid] = majority(v)
    return preds


def load_wcag_xlsx(path, rows):
    import openpyxl
    key_to_page = {(r["snippet_id"], r["persona"], r["wcag"]): r["page_id"] for r in rows}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    preds = defaultdict(dict)
    for sheet in WCAG_SHEETS:
        if sheet not in wb.sheetnames:
            continue
        it = wb[sheet].iter_rows(values_only=True)
        header = next(it)
        ix = {k: i for i, k in enumerate(header)}
        votes = defaultdict(list)
        models = set()
        for r in it:
            if not r or r[0] is None:
                continue
            pid = key_to_page.get((r[ix["snippet_id"]], r[ix["persona"]], str(r[ix["wcag_criterion"]])))
            if pid:
                votes[pid].append(WCAG_TO_BARRIER.get(r[ix["evaluated"]], "error"))
                models.add(str(r[ix["model"]]))
        name = f"wcag-task {sheet.split('_', 1)[1]} [{','.join(sorted(models))}]"
        for pid, v in votes.items():
            preds[name][pid] = majority(v)
    return preds


def fmt(x):
    return "  nan" if x != x else f"{x:5.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="*", help="barrier-task .jsonl files")
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--wcag-xlsx", default=None,
                    help="Also score the WCAG-task outputs from this analysis workbook")
    ap.add_argument("--csv", default=None, help="Write the summary table to this CSV")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.labels, encoding="utf-8")))
    gold = {r["page_id"]: r["label"] for r in rows}
    persona_of = {r["page_id"]: r["persona"] for r in rows}

    preds = {}
    preds["reference: WCAG label as prediction"] = {
        r["page_id"]: WCAG_TO_BARRIER[r["wcag_label"]] for r in rows}
    if args.wcag_xlsx:
        preds.update(load_wcag_xlsx(args.wcag_xlsx, rows))
    if args.results:
        preds.update(load_barrier_jsonl(args.results))

    print(f"Ground truth: {args.labels}  ({len(gold)} rows; {dict(Counter(gold.values()))})\n")
    header = f"{'condition':52} {'n':>3} {'err':>3} {'acc3':>5} {'kappa':>5} {'accB':>5} {'P':>5} {'R':>5} {'F1':>5}"
    print(header)
    print("-" * len(header))
    results = []
    for name, p in preds.items():
        s = score(name, p, gold, persona_of)
        if not s:
            continue
        results.append(s)
        print(f"{name:52} {s['n']:3d} {s['errors']:3d} {fmt(s['acc_3way'])} {fmt(s['kappa_3way'])} "
              f"{fmt(s['acc_binary'])} {fmt(s['barrier_P'])} {fmt(s['barrier_R'])} {fmt(s['barrier_F1'])}")
    print("\nBinary accuracy per persona:")
    for s in results:
        print(f"  {s['condition']:52} {s['per_persona_binary']}")
    print("\nn is small and the v0 labels come from one annotator per persona with the WCAG\n"
          "label visible to them. Treat these numbers as a development-set pilot.")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[k for k in results[0] if k != "per_persona_binary"] + ["per_persona_binary"])
            w.writeheader()
            for s in results:
                w.writerow({**s, "per_persona_binary": json.dumps(s["per_persona_binary"])})
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()
