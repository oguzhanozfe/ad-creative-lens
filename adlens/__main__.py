"""CLI: python -m adlens {fetch,run,eval}"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import ingest, tagger, trends
from .evaluate import evaluate, load_labels, to_markdown

TOKEN_ENV = "META_AD_LIBRARY_TOKEN"


def load_creatives(args):
    genres = json.loads(Path(args.genres).read_text()) if args.genres else {}
    ads = []
    for d in args.api_dir or []:
        ads += ingest.load_api_dir(d, genres)
    for d in args.folder or []:
        ads += ingest.load_folder(d, genres)
    if not ads:
        sys.exit("no ads: pass --api-dir and/or --folder")
    creatives = ingest.to_creatives(ads)
    def build(backend, model):
        if args.offline:  # cache only; no key or model needed
            return type("Offline", (), {"model": model or tagger.default_model(backend)})()
        return tagger.make_client(backend, model, args.ollama)

    args.client = client = build(args.backend, args.model)
    frame_client, vision = None, False
    if args.vision:
        frame_client = build(args.vision_backend or args.backend, args.vision_model)
        vision = args.offline or frame_client.has_vision()
        if not vision:
            print(f"{frame_client.model} has no vision capability; text-only tags", file=sys.stderr)
    args.frame_client = frame_client
    tagger.tag_creatives(creatives, client, tagger.Cache(args.cache), vision=vision, offline=args.offline,
                         log=lambda m: print(m, file=sys.stderr), frame_client=frame_client,
                         batch_size=args.batch_size if args.batch_size else (1 if args.backend == "ollama" else 15))
    return creatives


def main(argv=None):
    p = argparse.ArgumentParser(prog="adlens", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help=f"download ads_archive pages (token from ${TOKEN_ENV})")
    f.add_argument("--out", required=True)
    f.add_argument("--search-terms", default="")
    f.add_argument("--page-ids", default="", help="comma-separated Facebook page ids (max 10)")
    f.add_argument("--countries", default=",".join(ingest.EU))
    f.add_argument("--active-status", default="ALL", choices=["ALL", "ACTIVE", "INACTIVE"])
    f.add_argument("--version", default="v23.0", help="Graph API version")
    f.add_argument("--max-pages", type=int, default=20)

    for name in ("run", "eval"):
        s = sub.add_parser(name)
        s.add_argument("--api-dir", action="append", help="folder of saved ads_archive JSON pages")
        s.add_argument("--folder", action="append", help="folder with ads.csv (+ media files)")
        s.add_argument("--genres", help="JSON {advertiser name: genre}")
        s.add_argument("--backend", default="gemini", choices=["gemini", "deepseek", "ollama"],
                       help="gemini (GEMINI_API_KEY), deepseek (DEEPSEEK_API_KEY) or local ollama")
        s.add_argument("--model", help="override the backend's default model")
        s.add_argument("--batch-size", type=int, help="ad copies per request (default 15 cloud, 1 ollama)")
        s.add_argument("--vision-backend", choices=["gemini", "deepseek", "ollama"],
                       help="backend for keyframes (default: same as --backend)")
        s.add_argument("--vision-model", help="override the vision backend's default model")
        s.add_argument("--ollama", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
        s.add_argument("--cache", default="out/tag_cache.jsonl")
        s.add_argument("--offline", action="store_true", help="use cached tags only; fail on a miss")
        s.add_argument("--vision", action="store_true", help="also tag image/video keyframes if the model can")
        s.add_argument("--out", default="out")
    sub.choices["run"].add_argument("--as-of", type=date.fromisoformat,
                                    help="date for still-running ads (default: latest date in data)")
    sub.choices["run"].add_argument("--baseline-months", type=int, default=2)
    sub.choices["eval"].add_argument("--labels", required=True)
    a = p.parse_args(argv)

    if a.cmd == "fetch":
        token = os.environ.get(TOKEN_ENV)
        if not token:
            sys.exit(f"set {TOKEN_ENV} to your own Ad Library API access token")
        n = ingest.fetch(token, a.out, a.search_terms, [x for x in a.page_ids.split(",") if x],
                         a.countries.split(","), a.version, a.active_status, max_pages=a.max_pages)
        print(f"saved {n} page(s) to {a.out}")
        return

    creatives = load_creatives(a)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "run":
        from .report import render
        summary = trends.summarise(creatives, a.as_of, a.baseline_months)
        sources = sorted({c["source"] for c in creatives})
        (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
        (out / "report.html").write_text(render(summary, model=f"{a.backend}/{a.client.model}" + (
            f", frames: {a.frame_client.model}" if a.frame_client else ""), sources=sources), encoding="utf-8")
        print(f"{summary['creatives']} creatives from {summary['ads']} ads -> {out / 'report.html'}")
    else:
        res = evaluate(creatives, load_labels(a.labels))
        res.update(backend=a.backend, model=a.client.model,
                   frame_model=getattr(a.frame_client, "model", None), prompt_version=tagger.PROMPT_VERSION, batch_size=a.batch_size or (1 if a.backend == "ollama" else 15),
                   model_digest=None if a.offline else a.client.digest(),
                   usage_this_run=getattr(a.client, "usage", None))
        (out / "eval.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
        md = to_markdown(res, f"{a.backend}/{a.client.model}")
        (out / "eval.md").write_text(md)
        print(md)


if __name__ == "__main__":
    main()
