#!/usr/bin/env python3
"""
Sky Is Falling Index updater.

Pulls a small sample of public posts / headlines containing doom words,
scores how dramatic each one is (0-100), and writes ONLY aggregate numbers
to data/doom.json. No usernames, handles, IDs or post text are stored.

Sources (each optional, skipped quietly if not configured or failing):
  - Bluesky   : needs BSKY_HANDLE + BSKY_APP_PASSWORD (free app password)
  - News      : Google News RSS top stories (no key)
  - X         : needs X_BEARER_TOKEN (pay-per-use, ~$0.005 per post read)

Scoring:
  - If ANTHROPIC_API_KEY is set, Claude rates each item and writes the forecast.
  - Otherwise a built-in doom word list does the scoring.
"""
import json
import os
import re
import sys
import datetime as dt
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "doom.json")
HISTORY_LEN = 168         # readings kept for the trend line (1 week hourly)
PER_SOURCE = int(os.environ.get("DOOM_SAMPLE_SIZE", "50"))
CLAUDE_MODEL = os.environ.get("DOOM_CLAUDE_MODEL", "claude-haiku-5-5")

SEARCH_TERMS = [
    "it's over", "we're cooked", "collapse", "wake up", "the end is near",
    "nobody is talking about", "doomed", "crash is coming", "apocalypse",
]

# ---------------------------------------------------------------- word list
# Keep in sync with the copy in index.html (paste-a-post scorer).
LEXICON = {
    # weight 3: full Chicken Little
    "apocalypse": 3, "armageddon": 3, "end times": 3, "the end is near": 3,
    "civilization": 3, "extinction": 3, "total collapse": 3, "doomsday": 3,
    "bunker": 3, "we're cooked": 3, "it's over": 3, "its over": 3,
    "nobody is safe": 3, "point of no return": 3,
    # weight 2: stockpiling beans
    "collapse": 2, "crash": 2, "catastrophe": 2, "catastrophic": 2,
    "crisis": 2, "doomed": 2, "panic": 2, "wake up": 2, "brace yourselves": 2,
    "nobody is talking about": 2, "they don't want you to know": 2,
    "mark my words": 2, "imminent": 2, "meltdown": 2, "chaos": 2,
    "stock up": 2, "terrifying": 2, "unprecedented": 2, "breaking": 2,
    # weight 1: clutching pearls
    "warning": 1, "alarming": 1, "dangerous": 1, "threat": 1, "fear": 1,
    "worst": 1, "disaster": 1, "scary": 1, "urgent": 1, "shocking": 1,
    "red flag": 1, "uh oh": 1, "yikes": 1, "bad news": 1,
}
DOOM_EMOJI = ["🚨", "💀", "☢️", "⚠️", "🔥", "😱", "🆘", "☠️", "📉", "🪦"]


def lexicon_score(text: str) -> tuple[int, list[str]]:
    """Return (0-100 drama score, matched words)."""
    t = text.lower().replace("’", "'")
    hits, pts = [], 0
    for phrase, w in LEXICON.items():
        if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", t):
            hits.append(phrase)
            pts += w * 9
    pts += min(sum(text.count(e) for e in DOOM_EMOJI), 5) * 6
    pts += min(text.count("!"), 5) * 3
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 15:
        caps = sum(c.isupper() for c in letters) / len(letters)
        if caps > 0.5:
            pts += 20
    return max(0, min(100, pts)), hits


# ---------------------------------------------------------------- fetching
def http_json(url, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_bluesky():
    handle, pw = os.environ.get("BSKY_HANDLE"), os.environ.get("BSKY_APP_PASSWORD")
    if not (handle and pw):
        return []
    sess = http_json(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        data=json.dumps({"identifier": handle, "password": pw}).encode(),
        headers={"Content-Type": "application/json"},
    )
    auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
    texts, per_term = [], max(5, PER_SOURCE // len(SEARCH_TERMS))
    for term in SEARCH_TERMS:
        q = urllib.parse.urlencode({"q": f'"{term}"', "limit": per_term, "sort": "latest", "lang": "en"})
        try:
            res = http_json(f"https://bsky.social/xrpc/app.bsky.feed.searchPosts?{q}", headers=auth)
            texts += [p["record"].get("text", "") for p in res.get("posts", [])]
        except Exception as e:  # one bad term shouldn't sink the run
            print(f"  bluesky '{term}' failed: {e}", file=sys.stderr)
    return [t for t in texts if t][:PER_SOURCE]


def fetch_news():
    req = urllib.request.Request(
        "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
        headers={"User-Agent": "Mozilla/5.0 (doom-meter)"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    titles = [i.findtext("title") or "" for i in root.iter("item")]
    # strip " - Publisher" suffix
    return [re.sub(r"\s+-\s+[^-]+$", "", t) for t in titles if t][:PER_SOURCE]


def fetch_x():
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        return []
    query = "(" + " OR ".join(f'"{t}"' for t in SEARCH_TERMS[:6]) + ") lang:en -is:retweet"
    q = urllib.parse.urlencode({"query": query, "max_results": min(100, max(10, PER_SOURCE))})
    res = http_json(
        f"https://api.x.com/2/tweets/search/recent?{q}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return [t["text"] for t in res.get("data", [])]


# ---------------------------------------------------------------- Claude
def claude(prompt: str, max_tokens=2000) -> str:
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    res = http_json(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        timeout=90,
    )
    return "".join(b.get("text", "") for b in res.get("content", []))


def claude_scores(texts):
    numbered = "\n".join(f"{i}. {t[:280].replace(chr(10), ' ')}" for i, t in enumerate(texts))
    prompt = (
        "Rate how alarmist / sky-is-falling each item below is, 0-100. "
        "0 = calm and factual, 50 = dramatic, 100 = full Chicken Little. "
        "Judge the tone, not the topic: a calm report on a serious event scores low.\n"
        "Reply with ONLY a JSON array of integers, one per item, same order.\n\n" + numbered
    )
    out = claude(prompt)
    arr = json.loads(out[out.index("["): out.rindex("]") + 1])
    if len(arr) != len(texts):
        raise ValueError("score count mismatch")
    return [max(0, min(100, int(x))) for x in arr]


def claude_forecast(score, level, words):
    prompt = (
        f"You are a cheerful local TV weatherperson delivering the 'Doom Forecast' for the internet. "
        f"Today's Sky Is Falling Index is {score}/100 ({level}). Trending doom words: {', '.join(words) or 'none'}. "
        "Write ONE playful sentence (max 30 words) in weather-report style, e.g. "
        "'Scattered hysteria this morning, clearing to mild concern by evening.' "
        "Keep it apolitical: no parties, politicians, groups or real people. No quotes. Just the sentence."
    )
    return claude(prompt, 120).strip().strip('"')


# ---------------------------------------------------------------- levels
LEVELS = [
    (0, "Mild Concern", "🟢"),
    (20, "Clutching Pearls", "🟡"),
    (40, "Stockpiling Beans", "🟠"),
    (60, "Building a Bunker", "🔴"),
    (80, "Full Chicken Little", "☄️"),
]


def level_for(score):
    name, emoji = LEVELS[0][1], LEVELS[0][2]
    for floor, n, e in LEVELS:
        if score >= floor:
            name, emoji = n, e
    return name, emoji


FALLBACK_FORECASTS = {
    "Mild Concern": "Clear skies across the timeline. Light grumbling possible in the afternoon.",
    "Clutching Pearls": "Partly anxious with scattered gasps. Keep a fainting couch handy.",
    "Stockpiling Beans": "Heavy hysteria moving in. Canned goods advisory in effect until further notice.",
    "Building a Bunker": "Severe panic warning. Residents urged to stop refreshing and touch grass.",
    "Full Chicken Little": "Acorn impacts reported region-wide. The sky is, allegedly, falling.",
}


# ---------------------------------------------------------------- main
def main():
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    sources, all_items = {}, []
    for name, fn in (("bluesky", fetch_bluesky), ("news", fetch_news), ("x", fetch_x)):
        try:
            items = fn()
        except Exception as e:
            print(f"{name}: skipped ({e})", file=sys.stderr)
            items = []
        if items:
            sources[name] = len(items)
            all_items += [(name, t) for t in items]
        print(f"{name}: {len(items)} items")

    if not all_items:
        print("No items fetched; leaving data unchanged.")
        return 0

    texts = [t for _, t in all_items]
    lex = [lexicon_score(t) for t in texts]
    method = "word-list"
    scores = [s for s, _ in lex]
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            scores = claude_scores(texts)
            method = "claude"
        except Exception as e:
            print(f"Claude scoring failed, using word list: {e}", file=sys.stderr)

    # Index = average of the spiciest half (doom is loud; calm posts are quiet)
    ranked = sorted(scores, reverse=True)
    top = ranked[: max(1, len(ranked) // 2)]
    index = round(sum(top) / len(top))

    by_source = {}
    for (src, _), s in zip(all_items, scores):
        by_source.setdefault(src, []).append(s)
    by_source = {k: round(sum(v) / len(v)) for k, v in by_source.items()}

    counts = {}
    for _, hits in lex:
        for h in hits:
            counts[h] = counts.get(h, 0) + 1
    top_words = [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:6]]

    level, emoji = level_for(index)
    forecast = FALLBACK_FORECASTS[level]
    if method == "claude":
        try:
            forecast = claude_forecast(index, level, top_words)
        except Exception as e:
            print(f"Forecast failed: {e}", file=sys.stderr)

    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        prev = {}
    history = [h for h in prev.get("history", []) if not h.get("sample")]
    history.append({"t": now.isoformat(), "score": index})
    history = history[-HISTORY_LEN:]

    out = {
        "updated": now.isoformat(),
        "score": index,
        "level": level,
        "emoji": emoji,
        "forecast": forecast,
        "method": method,
        "sampleSize": len(texts),
        "sources": sources,
        "bySource": by_source,
        "topWords": top_words,
        "history": history,
    }
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Index {index} — {emoji} {level} ({method}, n={len(texts)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
