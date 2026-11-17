import hashlib
import io
import json
import tempfile
import unittest
import unittest.mock
import urllib.error
from datetime import date
from pathlib import Path

from adlens import evaluate, ingest, tagger, trends
from adlens.report import render

FIX = Path(__file__).resolve().parent.parent / "fixtures"
GENRES = json.loads((FIX / "genres.json").read_text())


def fixture_creatives():
    ads = ingest.load_api_dir(FIX / "api", GENRES) + ingest.load_folder(FIX / "folder")
    return ingest.to_creatives(ads)


class FakeClient:
    """Stands in for Ollama: answers with the gold label so pipeline plumbing is tested offline."""
    model = "fake"

    def __init__(self, by_text=None):
        self.by_text, self.calls = by_text or {}, []

    def chat(self, system, user, schema, images=()):
        self.calls.append((user, list(images)))
        if images:
            return {"hook": "fail_challenge", "visuals": ["gameplay_ui", "not-a-tag"]}
        return self.by_text.get(user.split("\n", 1)[1], {"hook": "bogus", "cta": "install", "features": ["pvp", "x"]})


def gold_client(creatives):
    labels = evaluate.load_labels(FIX / "labels.csv")
    by_text = {}
    for c in creatives:
        hit = next((a for a in c["ad_ids"] if a in labels), None)
        if hit:
            by_text[c["text"]] = labels[hit]
    return FakeClient(by_text)


class Ingest(unittest.TestCase):
    def test_api_fixture_shape(self):
        ads = ingest.load_api_dir(FIX / "api", GENRES)
        self.assertEqual(len(ads), 52)
        no_body = next(a for a in ads if a["ad_id"] == "800000000000900")
        self.assertEqual(no_body["text"], "Pinwheel Puzzle")
        two = next(a for a in ads if a["ad_id"] == "800000000000901")
        self.assertIn("The forge never sleeps. | Melt", two["text"])
        self.assertEqual(two["start"], date(2026, 10, 8))  # full timestamp parsed
        self.assertEqual(ads[0]["genre"], "puzzle")

    def test_duplicate_copy_becomes_one_creative(self):
        cs = fixture_creatives()
        dup = next(c for c in cs if "800000000000902" in c["ad_ids"])
        self.assertEqual(dup["ad_ids"], ["800000000000114", "800000000000902"])
        self.assertIsNone(dup["last_seen"])  # one member still running
        self.assertEqual(dup["first_seen"], date(2026, 6, 12))

    def test_folder_media_paths(self):
        ads = ingest.load_folder(FIX / "folder")
        self.assertTrue(Path(ads[0]["media"][0]).exists())
        self.assertEqual(ads[1]["stop"], None)

    def test_scrub_removes_tokens(self):
        body = {"paging": {"next": "https://graph.facebook.com/v23.0/ads_archive?access_token=EAAB123&after=x"},
                "data": [{"ad_snapshot_url": "https://www.facebook.com/ads/archive/render_ad/?id=1&access_token=EAAB123"}]}
        self.assertNotIn("EAAB123", json.dumps(ingest.scrub(body)))

    def test_fetch_pages_and_never_writes_token(self):
        pages = [
            {"data": [{"id": "1"}], "paging": {"next": "https://graph.facebook.com/next?access_token=SECRET&after=a"}},
            {"data": [{"id": "2", "ad_snapshot_url": "https://x/?access_token=SECRET"}], "paging": {}},
        ]
        seen = []

        def opener(url, timeout):
            seen.append(url)
            return io.BytesIO(json.dumps(pages[len(seen) - 1]).encode())

        with tempfile.TemporaryDirectory() as tmp:
            n = ingest.fetch("SECRET", tmp, search_terms="puzzle", opener=opener, pause=0)
            self.assertEqual(n, 2)
            for f in Path(tmp).glob("*.json"):
                self.assertNotIn("SECRET", f.read_text())
        self.assertIn("ad_active_status=ALL", seen[0])
        self.assertIn("ad_reached_countries=%5B%22AT%22", seen[0])

    def test_fetch_api_error_is_scrubbed(self):
        def opener(url, timeout):
            raise urllib.error.HTTPError(url, 400, "bad", {}, io.BytesIO(
                b'{"error":{"code":190,"message":"bad token access_token=SECRET"}}'))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit) as cm:
            ingest.fetch("SECRET", tmp, opener=opener, pause=0)
        self.assertNotIn("SECRET", str(cm.exception))


class Tagging(unittest.TestCase):
    def test_invalid_model_output_is_coerced(self):
        cs = fixture_creatives()[:1]
        tagger.tag_creatives(cs, FakeClient())
        self.assertEqual(cs[0]["tags"], {"hook": "other", "cta": "install", "features": ["pvp"]})

    def test_cache_and_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "c.jsonl"
            cs = fixture_creatives()[:3]
            client = FakeClient()
            tagger.tag_creatives(cs, client, tagger.Cache(cache))
            self.assertEqual(len(client.calls), 3)
            again = fixture_creatives()[:3]
            tagger.tag_creatives(again, FakeClient(), tagger.Cache(cache), offline=True)
            self.assertEqual([c["tags"] for c in again], [c["tags"] for c in cs])
            with self.assertRaises(SystemExit):
                tagger.tag_creatives(fixture_creatives()[3:4], FakeClient(), tagger.Cache(cache), offline=True)

    def test_frames_sent_for_images_only(self):
        cs = [c for c in fixture_creatives() if c["media"]]
        client = FakeClient()
        tagger.tag_creatives(cs, client, vision=True)
        self.assertEqual(cs[0]["frame_tags"], {"hook": "fail_challenge", "visuals": ["gameplay_ui"]})
        self.assertTrue(any(images for _, images in client.calls))

    def test_batch_with_skipped_item_falls_back_to_single(self):
        cs = fixture_creatives()[:3]

        class Batchy(FakeClient):
            def chat(self, system, user, schema, images=()):
                self.calls.append((user, []))
                if schema is tagger.BATCH_SCHEMA:
                    return {"items": [{"i": 0, "hook": "story", "cta": "none", "features": []},
                                      {"i": 2, "hook": "satisfying", "cta": "install", "features": []},
                                      {"i": 9, "hook": "story", "cta": "none", "features": []}]}
                return {"hook": "fail_challenge", "cta": "none", "features": []}
        client = Batchy()
        tagger.tag_creatives(cs, client, batch_size=15)
        self.assertEqual([c["tags"]["hook"] for c in cs], ["story", "fail_challenge", "satisfying"])
        self.assertEqual(len(client.calls), 2)

    def test_video_without_ffmpeg_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = Path(tmp) / "ad.mp4"
            v.write_bytes(b"\0")
            if not tagger.shutil.which("ffmpeg"):
                self.assertEqual(tagger.keyframes(v, tmp), [])

    def test_prompt_change_requires_version_bump(self):
        # The cache key uses PROMPT_VERSION. If you edit GUIDE, bump PROMPT_VERSION and update this hash.
        self.assertEqual(tagger.PROMPT_VERSION, "v1")
        self.assertEqual(hashlib.sha256(tagger.GUIDE.encode()).hexdigest()[:12], GUIDE_HASH)


GUIDE_HASH = "5e2b104cd887"


class CloudClient(unittest.TestCase):
    def test_missing_key_is_a_clear_error(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True), self.assertRaises(SystemExit):
            tagger.OpenAICompat("gemini")

    def test_payload_and_usage(self):
        c = tagger.OpenAICompat("gemini", key="FAKE-KEY-123")
        sent = []

        def fake_post(payload):
            sent.append(payload)
            return {"choices": [{"message": {"content": '{"hook": "story", "visuals": []}'}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}}
        c._post = fake_post
        img = FIX / "folder" / "media" / "tp-001.png"
        self.assertEqual(c.chat("sys", "u", tagger.FRAME_SCHEMA, [img])["hook"], "story")
        parts = sent[0]["messages"][1]["content"]
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(sent[0]["response_format"]["type"], "json_schema")
        self.assertEqual(c.usage["total_tokens"], 13)
        self.assertNotIn("FAKE-KEY-123", json.dumps(sent[0]))


class Eval(unittest.TestCase):
    def test_perfect_tagger_scores_one(self):
        cs = fixture_creatives()
        tagger.tag_creatives(cs, gold_client(cs))
        res = evaluate.evaluate(cs, evaluate.load_labels(FIX / "labels.csv"))
        self.assertEqual(res["all"]["hook"]["n"], 59)
        self.assertEqual(res["all"]["hook"]["accuracy"], 1.0)
        self.assertEqual(res["all"]["cta"]["kappa"], 1.0)
        self.assertEqual(res["all"]["features"]["exact_set_match"], 1.0)
        self.assertEqual(res["disagreements"], [])
        self.assertEqual(res["dev"]["hook"]["n"] + res["test"]["hook"]["n"], 59)

    def test_kappa_chance_level(self):
        self.assertAlmostEqual(evaluate.kappa(["a", "b", "a", "b"], ["a", "a", "b", "b"], ["a", "b"]), 0.0)


class Trends(unittest.TestCase):
    def setUp(self):
        self.cs = fixture_creatives()
        tagger.tag_creatives(self.cs, gold_client(self.cs))

    def test_shares_sum_to_one(self):
        shares, counts = trends.share_by_month(self.cs, "genre")
        for g, months in shares.items():
            for m, s in months.items():
                self.assertAlmostEqual(sum(s.values()), 1.0)
        self.assertEqual(sum(sum(v.values()) for v in counts.values()), len(self.cs))

    def test_new_hooks_use_baseline(self):
        rows = trends.new_hooks(self.cs, "advertiser")
        ironhold = {r["value"]: r["first_month"] for r in rows if r["group"] == "Ironhold Games"}
        self.assertEqual(ironhold, {"story": "2026-07", "fail_challenge": "2026-09", "fake_gameplay": "2026-09"})
        self.assertFalse(any(r["group"] == "Ironhold Games" and r["value"] == "other" for r in rows))

    def test_lifespan_censoring_and_as_of(self):
        self.assertEqual(trends.as_of_date(self.cs), date(2026, 10, 30))
        rows = trends.lifespans(self.cs)
        running = next(r for r in rows if r["creative_id"] == "800000000000102")
        self.assertTrue(running["running"])
        self.assertEqual(running["days"], (date(2026, 10, 30) - date(2026, 5, 21)).days)
        self.assertEqual(rows, sorted(rows, key=lambda r: (-r["days"], r["creative_id"])))

    def test_report_escapes_and_labels_proxy(self):
        self.cs[0]["text"] = "<script>alert(1)</script>"
        page = render(trends.summarise(self.cs), "fake", ["meta_api"])
        self.assertNotIn("<script>alert", page)
        self.assertIn("proxy", page.lower())


if __name__ == "__main__":
    unittest.main()
