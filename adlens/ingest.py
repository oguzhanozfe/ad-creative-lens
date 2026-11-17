"""Load ads from Meta Ad Library API pages or a local folder, and group them into creatives."""
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

GRAPH = "https://graph.facebook.com"
# Non-political ads are only returned when they reached the EU, so EU codes are the useful default.
EU = "AT,BE,BG,HR,CY,CZ,DK,EE,FI,FR,DE,GR,HU,IE,IT,LV,LT,LU,MT,NL,PL,PT,RO,SK,SI,ES,SE".split(",")
FIELDS = ",".join([
    "id", "page_id", "page_name", "ad_creation_time", "ad_delivery_start_time", "ad_delivery_stop_time",
    "ad_creative_bodies", "ad_creative_link_titles", "ad_creative_link_descriptions",
    "ad_creative_link_captions", "ad_snapshot_url", "publisher_platforms", "languages",
])
TOKEN_RE = re.compile(r"(access_token=)[^&\s\"']+")


def scrub(obj):
    """Remove access tokens from every string (paging.next and ad_snapshot_url carry them)."""
    if isinstance(obj, str):
        return TOKEN_RE.sub(r"\1REDACTED", obj)
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj


def parse_date(value):
    """Accept '2026-06-12' and '2026-06-12T08:00:00+0000'. Empty -> None."""
    return date.fromisoformat(value[:10]) if value else None


def normalise(text):
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def ad_text(ad):
    parts = []
    for field in ("ad_creative_bodies", "ad_creative_link_titles",
                  "ad_creative_link_descriptions", "ad_creative_link_captions"):
        for p in ad.get(field) or []:
            if p and p not in parts:
                parts.append(p.strip())
    return " | ".join(parts)


def from_api(ad, genres):
    name = ad.get("page_name") or ad.get("page_id", "unknown")
    return {
        "ad_id": ad["id"], "advertiser": name, "genre": genres.get(name, "unknown"),
        "text": ad_text(ad), "start": parse_date(ad.get("ad_delivery_start_time") or ad.get("ad_creation_time")),
        "stop": parse_date(ad.get("ad_delivery_stop_time")), "media": [], "source": "meta_api",
    }


def load_api_dir(path, genres=None):
    """Read saved ads_archive response pages (*.json). Never follows paging.next."""
    ads = []
    for f in sorted(Path(path).glob("*.json")):
        for ad in json.loads(f.read_text(encoding="utf-8")).get("data", []):
            ads.append(from_api(ad, genres or {}))
    return ads


def load_folder(path, genres=None):
    """ads.csv with ad_id, advertiser, genre, first_seen, last_seen, text, media (';'-separated, relative)."""
    root = Path(path)
    ads = []
    with open(root / "ads.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            media = [str(root / m) for m in (row.get("media") or "").split(";") if m.strip()]
            ads.append({
                "ad_id": row["ad_id"], "advertiser": row["advertiser"],
                "genre": row.get("genre") or (genres or {}).get(row["advertiser"], "unknown"),
                "text": row.get("text", ""), "start": parse_date(row.get("first_seen")),
                "stop": parse_date(row.get("last_seen")), "media": media, "source": "folder",
            })
    return ads


def to_creatives(ads):
    """Same advertiser + same normalised copy = one creative. first/last seen span all its ads."""
    groups = {}
    for ad in sorted(ads, key=lambda a: (a["start"] or date.max, a["ad_id"])):
        groups.setdefault((ad["advertiser"], normalise(ad["text"])), []).append(ad)
    creatives = []
    for members in groups.values():
        first = members[0]
        running = any(m["stop"] is None for m in members)
        stops = [m["stop"] for m in members if m["stop"]]
        creatives.append({
            "creative_id": first["ad_id"], "ad_ids": [m["ad_id"] for m in members],
            "advertiser": first["advertiser"], "genre": first["genre"], "text": first["text"],
            "first_seen": first["start"], "last_seen": None if running else max(stops, default=None),
            "media": sorted({p for m in members for p in m["media"]}), "source": first["source"],
        })
    return creatives


def fetch(token, out_dir, search_terms="", page_ids=(), countries=EU, version="v27.0",
          active_status="ALL", limit=100, max_pages=20, pause=2.0, opener=urllib.request.urlopen):
    """Page through ads_archive and save each page (token scrubbed) as JSON. Returns pages saved."""
    params = {"ad_type": "ALL", "ad_reached_countries": json.dumps(list(countries)),
              "ad_active_status": active_status, "fields": FIELDS, "limit": str(limit),
              "access_token": token}
    if search_terms:
        params["search_terms"] = search_terms
    if page_ids:
        params["search_page_ids"] = json.dumps([int(p) for p in page_ids])
    url = f"{GRAPH}/{version}/ads_archive?" + urllib.parse.urlencode(params)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages = 0
    while url and pages < max_pages:
        body = _get(url, opener, pause)
        pages += 1
        (out / f"page_{pages:03d}.json").write_text(json.dumps(scrub(body), indent=1, ensure_ascii=False))
        if not body.get("data"):
            break
        url = body.get("paging", {}).get("next")
        time.sleep(pause)
    return pages


def _get(url, opener, pause, retries=3):
    for attempt in range(retries + 1):
        try:
            with opener(url, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = scrub(e.read().decode("utf-8", "replace"))
            code = (json.loads(detail).get("error", {}).get("code") if detail.startswith("{") else None)
            if code in (4, 17, 613) and attempt < retries:  # Graph API rate-limit codes
                time.sleep(pause * 30 * (attempt + 1))
                continue
            raise SystemExit(f"Ad Library API error {e.code}: {detail[:500]}") from None
