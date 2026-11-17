"""CLI: python -m adlens {demo,run,eval,fetch}"""
import argparse
import json
import os
import sys
import urllib.request
from argparse import Namespace
from datetime import date
from pathlib import Path

from . import ingest, tagger, trends
from .evaluate import evaluate, load_labels, to_markdown

TOKEN_ENV = "META_AD_LIBRARY_TOKEN"
FIX = Path(__file__).resolve().parent.parent / "fixtures"
RECORDED = {"model": "gemini-3.5-flash-lite", "date": "2026-11-17"}  # the run that wrote fixtures/tag_cache.jsonl
DEMO_BANNER = ("SYNTHETIC DEMO DATA: hand-written ads from fictional advertisers, not real Meta Ad Library data. "
               "Trends below describe this made-up set only.")


def resolve_backend(ollama_host):
    """Demo model order: a cloud key in the environment, else a reachable local Ollama, else None (replay)."""
    for backend, (_, env, _, _) in tagger.PROVIDERS.items():
        if os.environ.get(env):
            return backend
    try:
        with urllib.request.urlopen(ollama_host.rstrip("/") + "/api/tags", timeout=2) as r:
            names = {m["name"] for m in json.loads(r.read()).get("models", [])}
        if tagger.default_model("ollama") in names:
            return "ollama"
    except (OSError, ValueError):
        pass
    return None


def demo(a):
    base = dict(api_dir=[str(FIX / "api")], folder=[str(FIX / "folder")], genres=str(FIX / "genres.json"),
                model=None, vision=True, vision_backend=None, vision_model=None, batch_size=None, ollama=a.ollama)
    backend = None if a.replay else resolve_backend(a.ollama)
    creatives = None
    if backend:
        print(f"mode: live {backend}/{tagger.default_model(backend)} (responses cached in {a.out}/demo_cache.jsonl)")
        try:
            args = Namespace(**base, backend=backend, offline=False, cache=str(Path(a.out) / "demo_cache.jsonl"))
            creatives = load_creatives(args)
            label = f"{backend}/{args.client.model}"
        except (SystemExit, OSError, ValueError) as err:
            print(f"live {backend} failed ({str(err)[:200]}); falling back to replay", file=sys.stderr)
    if creatives is None:
        print(f"mode: replay (recorded {RECORDED['model']}, {RECORDED['date']})")
        args = Namespace(**base, backend="gemini", offline=True, cache=str(FIX / "tag_cache.jsonl"))
        creatives = load_creatives(args)
        label = f"replay of recorded {RECORDED['model']} tags ({RECORDED['date']})"
    from .report import render
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = trends.summarise(creatives)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    sources = sorted({c["source"] for c in creatives})
    (out / "index.html").write_text(render(summary, label, sources, banner=DEMO_BANNER), encoding="utf-8")
    print(f"{summary['creatives']} creatives from {summary['ads']} ads -> {out / 'index.html'}")


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

    d = sub.add_parser("demo", help="tag the bundled synthetic ads and build the report; no key needed")
    d.add_argument("--replay", action="store_true", help="skip live models; use the recorded tags")
    d.add_argument("--out", default="out")
    d.add_argument("--ollama", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))

    f = sub.add_parser("fetch", help=f"download ads_archive pages (token from ${TOKEN_ENV})")
    f.add_argument("--out", required=True)
    f.add_argument("--search-terms", default="")
    f.add_argument("--page-ids", default="", help="comma-separated Facebook page ids (max 10)")
    f.add_argument("--countries", default=",".join(ingest.EU))
    f.add_argument("--active-status", default="ALL", choices=["ALL", "ACTIVE", "INACTIVE"])
    f.add_argument("--version", default="v27.0", help="Graph API version (docs showed v27.0 in Nov 2026)")
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

    if a.cmd == "demo":
        demo(a)
        return
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
