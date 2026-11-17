"""Trend views over tagged creatives. Counts are by launch month (first_seen) of each creative."""
from collections import Counter, defaultdict


def month(d):
    return f"{d.year:04d}-{d.month:02d}"


def months_between(a, b):
    out, (y, m) = [], (a.year, a.month)
    while (y, m) <= (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def as_of_date(creatives):
    """Latest date in the data. Used instead of today so outputs are reproducible."""
    return max(d for c in creatives for d in (c["first_seen"], c["last_seen"]) if d)


def share_by_month(creatives, by="genre", field="hook"):
    """{group: {month: {value: share}}}, plus counts {group: {month: n}}."""
    counts = defaultdict(lambda: defaultdict(Counter))
    for c in creatives:
        if c["first_seen"]:
            counts[c[by]][month(c["first_seen"])][c["tags"][field]] += 1
    shares, totals = {}, {}
    for g, per_month in counts.items():
        shares[g] = {m: {v: n / sum(cnt.values()) for v, n in cnt.items()} for m, cnt in sorted(per_month.items())}
        totals[g] = {m: sum(cnt.values()) for m, cnt in sorted(per_month.items())}
    return shares, totals


def new_hooks(creatives, by="advertiser", field="hook", baseline_months=2):
    """Hooks a group starts using after its first `baseline_months` months of activity.

    The baseline window keeps a group's first appearance from flagging every hook as new."""
    per_group = defaultdict(list)
    for c in creatives:
        if c["first_seen"]:
            per_group[c[by]].append(c)
    found = []
    for g, items in sorted(per_group.items()):
        start = min(c["first_seen"] for c in items)
        window = set(months_between(start, as_of_date(items))[:baseline_months])
        known = {c["tags"][field] for c in items if month(c["first_seen"]) in window}
        first = {}
        for c in sorted(items, key=lambda c: c["first_seen"]):
            v = c["tags"][field]
            if v not in known and v != "other":  # "other" is the absence of a hook, not a new one
                first.setdefault(v, []).append(c)
        for v, cs in first.items():
            found.append({"group": g, "value": v, "first_month": month(cs[0]["first_seen"]),
                          "creatives": len(cs), "example": cs[0]["text"]})
    return sorted(found, key=lambda r: (r["first_month"], r["group"]))


def lifespans(creatives, as_of=None):
    """Days between first and last seen. Still-running creatives are measured to as_of and flagged
    'running' (right-censored). Long life is a PROXY for a winning creative, not a measure of performance."""
    as_of = as_of or as_of_date(creatives)
    rows = []
    for c in creatives:
        if not c["first_seen"]:
            continue
        end = c["last_seen"] or as_of
        rows.append({"creative_id": c["creative_id"], "advertiser": c["advertiser"], "genre": c["genre"],
                     "hook": c["tags"]["hook"], "first_seen": c["first_seen"].isoformat(),
                     "last_seen": c["last_seen"].isoformat() if c["last_seen"] else None,
                     "days": (end - c["first_seen"]).days, "running": c["last_seen"] is None,
                     "ads": len(c["ad_ids"]), "text": c["text"]})
    return sorted(rows, key=lambda r: (-r["days"], r["creative_id"]))


def median_life_by(rows, key="hook"):
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r["days"])
    out = {}
    for k, v in groups.items():
        v = sorted(v)
        mid = len(v) // 2
        out[k] = {"n": len(v), "median_days": v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2}
    return dict(sorted(out.items()))


def summarise(creatives, as_of=None, baseline_months=2):
    rows = lifespans(creatives, as_of)
    out = {"as_of": (as_of or as_of_date(creatives)).isoformat(), "creatives": len(creatives),
           "ads": sum(len(c["ad_ids"]) for c in creatives),
           "overall": {f: dict(Counter(c["tags"][f] for c in creatives).most_common()) for f in ("hook", "cta")},
           "features": dict(Counter(x for c in creatives for x in c["tags"]["features"]).most_common()),
           "lifespans": rows, "median_life_by_hook": median_life_by(rows)}
    for by in ("genre", "advertiser"):
        out[f"hook_share_by_{by}"], out[f"counts_by_{by}"] = share_by_month(creatives, by)
        out[f"new_hooks_by_{by}"] = new_hooks(creatives, by, baseline_months=baseline_months)
    frames = [c for c in creatives if c.get("frame_tags")]
    out["frame_tagged"] = len(frames)
    out["frame_vs_text_hook_match"] = sum(c["frame_tags"]["hook"] == c["tags"]["hook"] for c in frames)
    return out
