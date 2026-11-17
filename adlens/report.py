"""Standalone static HTML report from trends.summarise output."""
from html import escape as e

HOOKS = ["fail_challenge", "satisfying", "story", "fake_gameplay", "other"]
COLORS = {"fail_challenge": "#e4572e", "satisfying": "#2a9d8f", "story": "#6c5ce7",
          "fake_gameplay": "#e9a820", "other": "#8a94a6"}
CSS = """
:root{--bg:#fff;--fg:#1c2230;--mut:#5d667a;--line:#d9dde6;--card:#f5f6f9;--warn:#fff4d6;--warnb:#e0b94a}
@media(prefers-color-scheme:dark){:root{--bg:#14171f;--fg:#e6e9f0;--mut:#9aa3b8;--line:#2e3445;--card:#1c202b;--warn:#3a3217;--warnb:#8a7226}}
*{box-sizing:border-box}
body{margin:0 auto;max-width:960px;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.2rem;margin:2em 0 .4em;border-bottom:1px solid var(--line);padding-bottom:.2em}
h3{font-size:1rem;margin:1.2em 0 .3em}p{margin:.4em 0}.mut{color:var(--mut)}
.notice{background:var(--warn);border:1px solid var(--warnb);border-radius:6px;padding:10px 12px;margin:12px 0}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mut);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;margin:.5em 0}.sw{display:inline-block;width:.9em;height:.9em;border-radius:2px;margin-right:4px;vertical-align:-1px}
.row{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:.85rem}.row .m{width:5.5em;flex:none}.row .n{width:3em;flex:none;color:var(--mut)}
.bar{display:flex;flex:1;height:18px;border-radius:3px;overflow:hidden;background:var(--card);min-width:0}.bar div{height:100%}
.run{font-weight:600;color:#2a9d8f}footer{margin:2.5em 0 1em;color:var(--mut);font-size:.85rem}
"""


def legend():
    return '<div class="legend">' + "".join(
        f'<span><i class="sw" style="background:{COLORS[h]}"></i>{e(h)}</span>' for h in HOOKS) + "</div>"


def stacked(title, shares, counts):
    out = [f"<h3>{e(str(title))}</h3>"]
    for m, mix in shares.items():
        segs = "".join(
            f'<div style="width:{mix[h] * 100:.1f}%;background:{COLORS.get(h, COLORS["other"])}" '
            f'title="{e(h)} {mix[h] * 100:.0f}%"></div>'
            for h in HOOKS + sorted(set(mix) - set(HOOKS)) if mix.get(h))
        out.append(f'<div class="row"><span class="m">{e(m)}</span><span class="n">n={counts[m]}</span>'
                   f'<div class="bar">{segs}</div></div>')
    return "".join(out)


def table(head, rows):
    th = "".join(f"<th>{e(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><tr>{th}</tr>{body}</table></div>'


def share_section(heading, shares, counts):
    return f"<h2>{e(heading)}</h2>" + legend() + "".join(stacked(g, shares[g], counts[g]) for g in shares)


def new_table(heading, rows):
    if not rows:
        return f"<h3>{e(heading)}</h3><p class='mut'>None.</p>"
    return f"<h3>{e(heading)}</h3>" + table(
        ["Group", "Hook", "First month", "Creatives", "Example copy"],
        [[e(r["group"]), e(r["value"]), e(r["first_month"]), r["creatives"], e(r["example"])] for r in rows])


def render(summary, model, sources):
    s = summary
    p = [f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>ad-creative-lens report</title><style>{CSS}</style></head><body>',
         "<h1>ad-creative-lens report</h1>",
         f'<p>{s["creatives"]} creatives, {s["ads"]} ads. As of {e(str(s["as_of"]))}. '
         f'Model: {e(model)}. Sources: {e(", ".join(sources)) or "none"}.</p>']
    if "meta_api" in sources or "folder" in sources:
        p.append('<div class="notice">If this is the bundled demo, its data is SYNTHETIC (hand-written fixtures with fictional '
                 "advertisers). Run on your own Ad Library pull or ad folder for real insight.</div>")
    p.append(share_section("Hook share over time by genre", s["hook_share_by_genre"], s["counts_by_genre"]))
    p.append(share_section("Hook share over time by advertiser", s["hook_share_by_advertiser"], s["counts_by_advertiser"]))
    p.append("<h2>New hooks</h2><p>A hook counts as new when a group starts using it after its first two months of activity.</p>")
    p.append(new_table("By genre", s["new_hooks_by_genre"]))
    p.append(new_table("By advertiser", s["new_hooks_by_advertiser"]))
    p.append("<h2>Creative lifespan (proxy for winners)</h2>"
             "<p class='mut'>Long-running creatives are a proxy for performance; the Ad Library exposes no spend or "
             "results for non-political ads, and running ads are right-censored at as_of.</p>")
    rows = []
    for r in s["lifespans"][:15]:
        t = r["text"] if len(r["text"]) <= 140 else r["text"][:139] + "…"
        rows.append([r["days"], '<span class="run">running</span>' if r["running"] else "", e(r["hook"]),
                     e(r["advertiser"]), e(r["first_seen"]), e(r["last_seen"] or "-"), r["ads"], e(t)])
    p.append(table(["Days", "", "Hook", "Advertiser", "First seen", "Last seen", "Ads", "Text"], rows))
    p.append("<h3>Median life by hook</h3>" + table(
        ["Hook", "n", "Median days"], [[e(h), v["n"], v["median_days"]] for h, v in s["median_life_by_hook"].items()]))
    p.append("<h2>Tag mix</h2>")
    for name, d in (("Hook", s["overall"]["hook"]), ("CTA", s["overall"]["cta"]), ("Features", s["features"])):
        p.append(f"<h3>{name}</h3>" + table([name, "Count"], [[e(k), v] for k, v in d.items()]))
    p.append("<h2>Frame tags</h2>")
    if s["frame_tagged"] > 0:
        p.append(f'<p>{s["frame_tagged"]} creatives had keyframes tagged; frame hook matched text hook for '
                 f'{s["frame_vs_text_hook_match"]}.</p>')
    else:
        p.append("<p>No keyframes tagged (text-only run).</p>")
    p.append("<footer>Generated by ad-creative-lens. Tags are LLM output and can be wrong; "
             "see README for measured agreement.</footer></body></html>")
    return "\n".join(p)
