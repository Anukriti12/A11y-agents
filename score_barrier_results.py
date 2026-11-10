"""
Score barrier-task results against the specialist labels, two labels:
Barrier vs. No-Barrier (Not-Encountered counts as No-Barrier, in the labels
and in any older 3-label results).

One table per model. Axe has no model, so it is repeated in every model's
table as a reference row. Repetitions are collapsed by majority vote per
(page, condition, model); ties and all-error pages count as wrong.

Per condition: the confusion matrix (TP, FN, FP, TN with Barrier as the
positive class), accuracy, precision, recall, specificity and Cohen's kappa,
then accuracy per persona.

Usage:
    python score_barrier_results.py results/barrier/barrier_claude-sonnet-4-6_binary.jsonl results/barrier/barrier_luna-5.6_binary.jsonl
    python score_barrier_results.py results/barrier/*.jsonl --labels barrier_study/ground_truth/barrier_labels_v1.csv
    python score_barrier_results.py results/barrier/*.jsonl --show-wcag   # adds "WCAG label as prediction" (failed -> Barrier)
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_LABELS = ROOT / "barrier_study" / "ground_truth" / "barrier_labels_v1.csv"
CONDITION_ORDER = ["axe", "persona_llm", "vanilla_llm", "persona_agent", "vanilla_agent"]
PERSONAS = ["ade", "elias", "ian", "lakshmi", "sophie", "stefan"]


def to_binary(label):
    if label == "Barrier":
        return "Barrier"
    if label in ("No-Barrier", "Not-Encountered"):
        return "No-Barrier"
    return "error"


def majority(votes):
    c = Counter(votes).most_common()
    if len(c) > 1 and c[0][1] == c[1][1]:
        return "error"
    return c[0][0]


def kappa(gold, pred):
    n = len(gold)
    po = sum(g == p for g, p in zip(gold, pred)) / n
    cg, cp = Counter(gold), Counter(pred)
    pe = sum(cg[k] * cp[k] for k in set(cg) | set(cp)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def ratio(a, b):
    return a / b if b else float("nan")


def fmt(x):
    return "  nan" if x != x else f"{x:5.2f}"


def score(preds, gold):
    ids = sorted(p for p in preds if p in gold)
    g = [gold[p] for p in ids]
    p = [preds[p] for p in ids]
    tp = sum(a == "Barrier" and b == "Barrier" for a, b in zip(g, p))
    fn = sum(a == "Barrier" and b != "Barrier" for a, b in zip(g, p))
    fp = sum(a != "Barrier" and b == "Barrier" for a, b in zip(g, p))
    tn = sum(a != "Barrier" and b == "No-Barrier" for a, b in zip(g, p))
    err = p.count("error")
    n = len(ids)
    return {"n": n, "tp": tp, "fn": fn, "fp": fp, "tn": tn, "err": err,
            "acc": ratio(tp + tn, n), "prec": ratio(tp, tp + fp),
            "rec": ratio(tp, tp + fn), "spec": ratio(tn, tn + fp),
            "kappa": kappa(g, p) if n else float("nan")}


def load_results(paths):
    """-> {model: {condition: {page_id: majority binary label}}}"""
    votes = defaultdict(list)
    for path in paths:
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            votes[(r["model"], r["condition"], r["page_id"])].append(to_binary(r["evaluated"]))
    out = defaultdict(lambda: defaultdict(dict))
    for (model, cond, pid), v in votes.items():
        out[model][cond][pid] = majority(v)
    return out


def cond_sort(name):
    base = name.split("[")[0]
    return (CONDITION_ORDER.index(base) if base in CONDITION_ORDER else 99, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+", help="barrier-task .jsonl files")
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--show-wcag", action="store_true",
                    help="Add the WCAG label (failed -> Barrier) as a reference row")
    ap.add_argument("--csv", default=None, help="Write all table rows to this CSV")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.labels, encoding="utf-8")))
    gold = {r["page_id"]: r.get("label_binary") or to_binary(r["label"]) for r in rows}
    persona_of = {r["page_id"]: r["persona"] for r in rows}
    wcag_pred = {r["page_id"]: "Barrier" if r["wcag_label"] == "failed" else "No-Barrier" for r in rows}

    results = load_results(args.results)
    axe = results.pop("n/a", {})
    models = sorted(results) or ["(axe only)"]

    print(f"Ground truth: {args.labels}")
    print(f"  {len(gold)} pages: {dict(Counter(gold.values()))}; per persona {dict(Counter(persona_of.values()))}\n")

    table_rows = []
    for model in models:
        conds = dict(axe)
        conds.update(results.get(model, {}))
        if args.show_wcag:
            conds["WCAG label (reference)"] = wcag_pred
        print(f"=== {model} ===")
        header = (f"{'condition':26} {'n':>3} {'TP':>3} {'FN':>3} {'FP':>3} {'TN':>3} {'err':>3}"
                  f" {'acc':>5} {'prec':>5} {'rec':>5} {'spec':>5} {'kappa':>5}")
        print(header)
        print("-" * len(header))
        for name in sorted(conds, key=cond_sort):
            s = score(conds[name], gold)
            if not s["n"]:
                continue
            print(f"{name:26} {s['n']:3d} {s['tp']:3d} {s['fn']:3d} {s['fp']:3d} {s['tn']:3d} {s['err']:3d}"
                  f" {fmt(s['acc'])} {fmt(s['prec'])} {fmt(s['rec'])} {fmt(s['spec'])} {fmt(s['kappa'])}")
            table_rows.append({"model": model, "condition": name, "persona": "all", **s})
        present = [p for p in PERSONAS if p in persona_of.values()]
        print(f"\n  accuracy per persona (correct / pages)")
        print(f"  {'condition':26} " + " ".join(f"{p:>8}" for p in present))
        for name in sorted(conds, key=cond_sort):
            cells = []
            for per in present:
                sub = {pid: lab for pid, lab in conds[name].items() if persona_of.get(pid) == per}
                g = {pid: gold[pid] for pid in gold if persona_of[pid] == per}
                s = score(sub, g)
                cells.append(f"{s['tp'] + s['tn']}/{s['n']}" if s["n"] else "-")
                if s["n"]:
                    table_rows.append({"model": model, "condition": name, "persona": per, **s})
            print(f"  {name:26} " + " ".join(f"{c:>8}" for c in cells))
        print()

    print("Barrier is the positive class. n is small; treat differences of a few pages as noise.")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(table_rows[0]))
            w.writeheader()
            w.writerows(table_rows)
        print(f"Wrote {args.csv}")


if __name__ == "__main__":
    main()
