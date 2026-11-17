"""LLM tagging of ad copy (and optionally keyframes) through a local Ollama model."""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HOOKS = ["fail_challenge", "satisfying", "story", "fake_gameplay", "other"]
CTAS = ["install", "play_now", "pre_register", "limited_offer", "none"]
FEATURES = ["levels", "offline", "pvp", "coop", "rewards", "customization", "idle", "story_choices"]
VISUALS = ["gameplay_ui", "hand_or_finger", "character_face", "text_overlay", "fail_screen",
           "before_after", "progress_bar"]
PROMPT_VERSION = "v1"

GUIDE = """You tag mobile game ad copy. Return JSON only.

hook (exactly one):
- fake_gameplay: the copy describes a mini-game puzzle mechanic as the hook (pull the pin, pick the right key/gate/path/tunnel, draw a line, pull the lever, rescue someone from a trap).
- fail_challenge: dares the viewer or cites how many people fail ("only 2% pass", "I bet you can't", "can you beat...", "everyone gets stuck").
- story: a narrative about a specific character and their situation (named person, betrayal, losing a shop, a journey).
- satisfying: sensory or relaxing appeal (satisfying, oddly satisfying, calm, click into place, crunch, stress melts away).
- other: anything else (feature lists, offers, social proof, announcements).
Tie rules: a mini-game mechanic wins over a dare (fake_gameplay beats fail_challenge). A dare wins over story or satisfying. Story wins over satisfying.

cta (exactly one, from explicit call-to-action words only):
- limited_offer: a time-limited deal or event (ends tonight, this weekend only, 48 hours, last chance).
- pre_register: asks to pre-register.
- install: download / install / get it.
- play_now: play now / play free / jetzt spielen.
- none: no explicit call to action.
Tie rules: limited_offer beats pre_register beats install/play_now. Use none for in-game actions ("send a challenge").

features (zero or more), only when explicitly promised in the text:
- levels: a level count or a specific level number. offline: offline or no wifi. pvp: competing against other real players, friends' scores, rivals, leaderboards.
- coop: playing together with others (clans, raids with friends). rewards: free gifts, coins, daily rewards, exclusive items, double/triple rewards.
- customization: skins, decorating, styles. idle: progress while away or asleep. story_choices: the player's choices change the story.
Copy may be in any language; tag the meaning."""

TEXT_SCHEMA = {
    "type": "object",
    "properties": {"hook": {"type": "string", "enum": HOOKS}, "cta": {"type": "string", "enum": CTAS},
                   "features": {"type": "array", "items": {"type": "string", "enum": FEATURES}}},
    "required": ["hook", "cta", "features"],
}
FRAME_SCHEMA = {
    "type": "object",
    "properties": {"hook": {"type": "string", "enum": HOOKS},
                   "visuals": {"type": "array", "items": {"type": "string", "enum": VISUALS}}},
    "required": ["hook", "visuals"],
}
FRAME_GUIDE = ("These are keyframes from one mobile game ad. Pick the hook the visuals suggest using the same "
               "definitions as for copy (fake_gameplay, fail_challenge, story, satisfying, other) and list which "
               "visual elements are present: " + ", ".join(VISUALS) + ". Return JSON only.")


class Ollama:
    def __init__(self, model="qwen3.5:9b", host="http://127.0.0.1:11434", timeout=180):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout

    def _post(self, path, payload, retries=3):
        req = urllib.request.Request(self.host + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except (TimeoutError, urllib.error.URLError):  # a shared Ollama queues requests
                if attempt == retries:
                    raise
                time.sleep(10 * (attempt + 1))

    def has_vision(self):
        return "vision" in self._post("/api/show", {"model": self.model}).get("capabilities", [])

    def digest(self):
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=10) as r:
                return next((m["digest"] for m in json.loads(r.read())["models"] if m["name"] == self.model), None)
        except OSError:
            return None

    def chat(self, system, user, schema, images=()):
        msg = {"role": "user", "content": user}
        if images:
            msg["images"] = [base64.b64encode(Path(p).read_bytes()).decode() for p in images]
        out = self._post("/api/chat", {
            "model": self.model, "stream": False, "think": False, "format": schema,
            "options": {"temperature": 0}, "messages": [{"role": "system", "content": system}, msg]})
        return json.loads(out["message"]["content"])


PROVIDERS = {  # name: (OpenAI-compatible base URL, key env var, default model, accepts images)
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-3.5-flash-lite", True),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY", "deepseek-chat", False),
}


class OpenAICompat:
    """Any OpenAI-compatible chat endpoint. The key is read from the environment and never logged."""

    def __init__(self, provider="gemini", model=None, timeout=90, key=None):
        base, env, default_model, self.vision = PROVIDERS[provider]
        self.key = key or os.environ.get(env)
        if not self.key:
            raise SystemExit(f"set {env} to use the {provider} backend (or use --backend ollama / --offline)")
        self.base, self.model, self.timeout = base, model or default_model, timeout
        self.provider, self.usage = provider, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def has_vision(self):
        return self.vision

    def digest(self):
        return None  # hosted models expose no weights digest; the model id is the version we can record

    def chat(self, system, user, schema, images=()):
        content = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": "data:image/%s;base64,%s" % (
                    Path(p).suffix.lstrip(".").lower().replace("jpg", "jpeg"),
                    base64.b64encode(Path(p).read_bytes()).decode())}} for p in images]
        fmt = ({"type": "json_schema", "json_schema": {"name": "tags", "schema": schema}} if self.provider == "gemini"
               else {"type": "json_object"})
        sys_text = system if self.provider == "gemini" else system + "\nJSON schema: " + json.dumps(schema)
        payload = {"model": self.model, "temperature": 0, "response_format": fmt,
                   "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": content}]}
        out = self._post(payload)
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self.usage[k] += (out.get("usage") or {}).get(k) or 0
        self.usage["calls"] += 1
        text = re.sub(r"<thought>.*?</thought>", "", out["choices"][0]["message"]["content"] or "", flags=re.S)
        text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()  # some models fence their JSON
        return json.loads(text)

    def _post(self, payload, retries=5):
        req = urllib.request.Request(self.base + "/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + self.key})
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code in (500, 503) and attempt < retries:  # transient; 429 (quota) fails fast
                    time.sleep(min(60, 5 * 2 ** attempt))
                    continue
                raise SystemExit(f"{self.provider} API error {e.code}: {e.read()[:300]!r}") from None
            except (TimeoutError, urllib.error.URLError):
                if attempt >= 1:  # one retry on a timeout, then give up
                    raise
                time.sleep(5)


def default_model(backend):
    return "qwen3.5:9b" if backend == "ollama" else PROVIDERS[backend][2]


def make_client(backend, model=None, ollama_host="http://127.0.0.1:11434"):
    if backend == "ollama":
        return Ollama(model or "qwen3.5:9b", ollama_host)
    return OpenAICompat(backend, model)


def clean_text_tags(raw):
    feats = raw.get("features") or []
    return {"hook": raw.get("hook") if raw.get("hook") in HOOKS else "other",
            "cta": raw.get("cta") if raw.get("cta") in CTAS else "none",
            "features": sorted({f for f in feats if f in FEATURES})}


def clean_frame_tags(raw):
    return {"hook": raw.get("hook") if raw.get("hook") in HOOKS else "other",
            "visuals": sorted({v for v in raw.get("visuals") or [] if v in VISUALS})}


class Cache:
    """JSONL cache keyed by model + prompt version + input, so reruns and the offline demo are reproducible."""

    def __init__(self, path=None):
        self.path, self.data = (Path(path) if path else None), {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.data[row["key"]] = row["tags"]

    @staticmethod
    def key(model, kind, payload):
        return hashlib.sha256(f"{PROMPT_VERSION}|{model}|{kind}|{payload}".encode()).hexdigest()[:24]

    def get(self, key):
        return self.data.get(key)

    def put(self, key, tags):
        self.data[key] = tags
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "tags": tags}) + "\n")


def keyframes(path, workdir, n=3):
    """Images are their own keyframe. Videos need ffmpeg; without it they are skipped (returns [])."""
    p = Path(path)
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return [p]
    if not shutil.which("ffmpeg"):
        return []
    pattern = str(Path(workdir) / f"{p.stem}_%02d.jpg")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-vf", "fps=1/2,scale=512:-1",
                    "-frames:v", str(n), pattern], check=False)
    return sorted(Path(workdir).glob(f"{p.stem}_*.jpg"))


BATCH_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"i": {"type": "integer"}, **TEXT_SCHEMA["properties"]},
    "required": ["i", "hook", "cta", "features"]}}}, "required": ["items"]}


def tag_batch(client, texts):  # ponytail: shares the cache key with single-copy tagging; batch mode is not in the key
    """Tag several ad copies in one request. Returns {index: tags}; indexes the model skipped are absent
    and get tagged one by one by the caller."""
    user = "Tag each ad copy independently. Return one item per ad with its index i.\n\n" + "\n".join(
        f"[{i}] {t}" for i, t in enumerate(texts))
    out = {}
    for item in client.chat(GUIDE, user, BATCH_SCHEMA).get("items", []):
        if isinstance(item, dict) and isinstance(item.get("i"), int) and 0 <= item["i"] < len(texts):
            out.setdefault(item["i"], clean_text_tags(item))
    return out


def tag_creatives(creatives, client, cache=None, vision=False, offline=False, log=print, frame_client=None,
                  batch_size=1):
    """Adds 'tags' (and 'frame_tags' when vision is on and media exists) to each creative.
    frame_client tags keyframes; it defaults to client (text and vision models can differ)."""
    cache = cache or Cache()
    model = getattr(client, "model", "none")
    frame_client = frame_client or client
    fmodel = getattr(frame_client, "model", "none")
    misses = [c for c in creatives if cache.get(Cache.key(model, "text", c["text"])) is None]
    if misses and offline:
        raise SystemExit(f"offline mode: no cached tags for creative {misses[0]['creative_id']}")
    size = max(1, batch_size)
    for i in range(0, len(misses), size):
        chunk = misses[i:i + size]
        log(f"tagging {i + len(chunk)}/{len(misses)} uncached creatives with {model}")
        got = tag_batch(client, [c["text"] for c in chunk]) if size > 1 else {}
        for j, c in enumerate(chunk):
            tags = got.get(j) or clean_text_tags(client.chat(GUIDE, "Ad copy:\n" + c["text"], TEXT_SCHEMA))
            cache.put(Cache.key(model, "text", c["text"]), tags)
    for c in creatives:
        c["tags"] = cache.get(Cache.key(model, "text", c["text"]))
        if vision and c["media"]:
            with tempfile.TemporaryDirectory() as tmp:
                frames = [f for m in c["media"] for f in keyframes(m, tmp)][:4]
                if not frames:
                    log(f"skip frames for {c['creative_id']}: no image and no ffmpeg for video")
                    continue
                fk = Cache.key(fmodel, "frames", "|".join(hashlib.sha256(Path(f).read_bytes()).hexdigest()
                                                          for f in frames))
                ftags = cache.get(fk)
                if ftags is None:
                    if offline:
                        raise SystemExit(f"offline mode: no cached frame tags for {c['creative_id']}")
                    ftags = clean_frame_tags(frame_client.chat(FRAME_GUIDE, "Keyframes attached.", FRAME_SCHEMA, frames))
                    cache.put(fk, ftags)
                c["frame_tags"] = ftags
    return creatives
