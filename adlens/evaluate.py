"""Agreement between the tagger and a hand-labelled set."""
import csv
import hashlib
from collections import Counter

from .tagger import CTAS, FEATURES, HOOKS


def load_labels(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["ad_id"]: {"hook": r["hook"], "cta": r["cta"],
                             "features": sorted(x for x in r["features"].split(",") if x)}
                for r in csv.DictReader(f)}


def split_of(ad_id):
    """Stable 50/50 dev/test split. The prompt was written against 'dev' only."""
    return "dev" if int(hashlib.sha256(ad_id.encode()).hexdigest(), 16) % 2 == 0 else "test"


def pairs(creatives, labels):
    """(split, gold, predicted) per labelled creative. A creative is labelled if any of its ad ids is."""
    out = []
    for c in creatives:
        hit = next((a for a in c["ad_ids"] if a in labels), None)
        if hit:
            out.append((split_of(hit), labels[hit], c["tags"]))
    return out


def kappa(gold, pred, classes):
    n = len(gold)
    if not n:
        return None
    po = sum(g == p for g, p in zip(gold, pred)) / n
    gc, pc = Counter(gold), Counter(pred)
    pe = sum(gc[k] * pc[k] for k in classes) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def single_label(rows, field, classes):
    gold = [g[field] for g, _ in rows]
    pred = [p[field] for _, p in rows]
    per = {}
    for k in classes:
        tp = sum(g == k and p == k for g, p in zip(gold, pred))
        support, predicted = gold.count(k), pred.count(k)
        per[k] = {"support": support, "predicted": predicted,
                  "precision": tp / predicted if predicted else None,
                  "recall": tp / support if support else None}
    n = len(gold)
    return {"n": n, "accuracy": sum(g == p for g, p in zip(gold, pred)) / n if n else None,
            "kappa": kappa(gold, pred, classes), "per_class": per}


def multi_label(rows):
    per = {}
    for f in FEATURES:
        g = [f in gd["features"] for gd, _ in rows]
        p = [f in pd["features"] for _, pd in rows]
        tp = sum(a and b for a, b in zip(g, p))
        per[f] = {"support": sum(g), "predicted": sum(p),
                  "agreement": sum(a == b for a, b in zip(g, p)) / len(rows) if rows else None,
                  "precision": tp / sum(p) if sum(p) else None, "recall": tp / sum(g) if sum(g) else None}
    exact = sum(gd["features"] == pd["features"] for gd, pd in rows)
    return {"n": len(rows), "exact_set_match": exact / len(rows) if rows else None, "per_label": per}


def evaluate(creatives, labels):
    result = {}
    allpairs = pairs(creatives, labels)
    for split in ("dev", "test", "all"):
        rows = [(g, p) for s, g, p in allpairs if split in ("all", s)]
        result[split] = {"hook": single_label(rows, "hook", HOOKS), "cta": single_label(rows, "cta", CTAS),
                         "features": multi_label(rows)}
    result["disagreements"] = [{"split": s, "gold": g, "pred": p} for s, g, p in allpairs if g != p]
    return result


def _f(x):
    return "-" if x is None else f"{x:.2f}"


def to_markdown(res, model):
    lines = [f"Model: `{model}`. Gold labels: single annotator, synthetic copy (see README).", "",
             "| split | n | hook acc | hook kappa | cta acc | cta kappa | features exact-set |",
             "|---|---|---|---|---|---|---|"]
    for s in ("dev", "test", "all"):
        r = res[s]
        lines.append(f"| {s} | {r['hook']['n']} | {_f(r['hook']['accuracy'])} | {_f(r['hook']['kappa'])} | "
                     f"{_f(r['cta']['accuracy'])} | {_f(r['cta']['kappa'])} | {_f(r['features']['exact_set_match'])} |")
    for field in ("hook", "cta"):
        lines += ["", f"Per-class `{field}` on the test split (support = gold count):", "",
                  "| class | support | predicted | precision | recall |", "|---|---|---|---|---|"]
        for k, v in res["test"][field]["per_class"].items():
            lines.append(f"| {k} | {v['support']} | {v['predicted']} | {_f(v['precision'])} | {_f(v['recall'])} |")
    lines += ["", "Per-feature on the test split:", "",
              "| feature | support | predicted | agreement | precision | recall |", "|---|---|---|---|---|---|"]
    for k, v in res["test"]["features"]["per_label"].items():
        lines.append(f"| {k} | {v['support']} | {v['predicted']} | {_f(v['agreement'])} | "
                     f"{_f(v['precision'])} | {_f(v['recall'])} |")
    return "\n".join(lines) + "\n"
