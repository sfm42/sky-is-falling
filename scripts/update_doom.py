#!/usr/bin/env python3
"""
Sky Is Falling Index updater (+ Robot Uprising Risk sub-meter).

Pulls small samples of public posts / headlines, scores how dramatic each one
is (0-100), and writes ONLY aggregate numbers to data/doom.json. No usernames,
handles, IDs or post text are stored.

Two meters:
  main : general doom ("it's over", "collapse", ...)
  ai   : AI panic ("p(doom)", "AI takeover", "it's sentient", ...)

Sources (each optional, skipped if not configured or failing):
  - Bluesky : BSKY_HANDLE + BSKY_APP_PASSWORD (free app password)
  - News    : public RSS feeds (no key)
  - X       : X_BEARER_TOKEN (pay-per-use, ~$0.005 per post read)

Scoring: Claude if ANTHROPIC_API_KEY is set, otherwise the built-in word lists.
If no items at all are fetched the script exits with an error so the GitHub
Actions run shows a red X instead of silently doing nothing.
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
PER_SOURCE = int(os.environ.get("DOOM_SAMPLE_SIZE", "50"))          # news + X (X costs money per post)
SOCIAL_PER_SOURCE = int(os.environ.get("DOOM_SOCIAL_SAMPLE", "300"))  # Bluesky + Mastodon (free)
CLAUDE_MODEL = os.environ.get("DOOM_CLAUDE_MODEL", "claude-haiku-5-5")
UA = {"User-Agent": "Mozilla/5.0 (compatible; sky-is-falling-index/1.0)"}

# ---------------------------------------------------------------- search terms
MAIN_TERMS = [
    "it's over", "we're cooked", "we are cooked", "we're so cooked", "it's so over",
    "the end is near", "end times", "apocalypse", "doomsday", "armageddon",
    "total collapse", "society is collapsing", "civilization is collapsing",
    "wake up people", "wake up sheeple", "nobody is talking about",
    "they don't want you to know", "mark my words", "you've been warned",
    "brace yourselves", "brace for impact", "crash is coming", "the crash is here",
    "stock up now", "buy gold", "get out while you can", "we're doomed",
    "we are doomed", "point of no return", "this is the end", "nobody is safe",
    "worse than 2008", "it's all collapsing", "prepare yourselves",
]
AI_TERMS = [
    "p(doom)", "AI takeover", "AI apocalypse", "rogue AI", "superintelligence",
    "AI is coming for", "AI will replace", "replaced by AI", "sentient AI",
    "AGI is here", "AGI by", "AI slop", "the singularity", "robot uprising",
    "AI will kill", "AI extinction", "shut it all down", "pause AI",
    "AI is lying", "AI escaped", "nobody understands AI", "AI jobpocalypse",
    "AI bubble", "dead internet",
]

# Public Mastodon hashtag timelines (no account or key needed)
MASTODON_INSTANCES = ["mastodon.social", "mstdn.social", "mas.to"]
MAIN_TAGS = ["collapse", "doom", "itsover", "apocalypse", "endtimes", "doomer",
             "prepping", "crisis", "wakeup"]
AI_TAGS = ["ai", "agi", "aisafety", "airisk", "pdoom", "aihype", "llm"]

MAIN_FEEDS = [
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.theguardian.com/world/rss",
]
AI_FEEDS = [
    "https://news.google.com/rss/search?q=%22artificial+intelligence%22+OR+AI&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://www.theguardian.com/technology/artificialintelligenceai/rss",
]

# ---------------------------------------------------------------- word lists
# Keep in sync with the copies in index.html (paste-a-post scorer).
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
AI_LEXICON = {
    # weight 3: full robot uprising
    "p(doom)": 3, "ai apocalypse": 3, "ai takeover": 3, "rogue ai": 3,
    "skynet": 3, "terminator": 3, "paperclip": 3, "superintelligence": 3,
    "singularity": 3, "agi is here": 3, "lost control": 3,
    "humanity is finished": 3, "extinction-level": 3, "robot uprising": 3,
    # weight 2: unplugging everything
    "sentient": 2, "it's alive": 2, "lied to its creators": 2,
    "tried to escape": 2, "coming for your job": 2, "ai will replace": 2,
    "replaced by ai": 2, "nobody will have a job": 2, "jobpocalypse": 2,
    "shut it all down": 2, "pause ai": 2, "unaligned": 2, "misaligned": 2,
    "nobody understands how it works": 2, "deepfake": 2, "self-replicating": 2,
    "agi": 2,
    # weight 1: side-eyeing the toaster
    "ai slop": 1, "dead internet": 1, "hallucinat": 1, "uncanny": 1,
    "ai bubble": 1, "it's learning": 1, "jailbreak": 1, "chatbot": 1,
    "algorithm": 1, "robots": 1,
}
DOOM_EMOJI = ["🚨", "💀", "☢️", "⚠️", "🔥", "😱", "🆘", "☠️", "📉", "🪦"]
AI_EMOJI = ["🤖", "👁️", "🦾", "👾"]


def _norm(text):
    return text.lower().replace("’", "'")


def _match(t, phrase):
    # "hallucinat" is a stem: allow trailing letters
    tail = "" if phrase.endswith("hallucinat") else r"(?![a-z])"
    return re.search(r"(?<![a-z])" + re.escape(phrase) + tail, t) is not None


def _drama_bonus(text, emoji):
    pts = min(sum(text.count(e) for e in emoji), 5) * 6
    pts += min(text.count("!"), 5) * 3
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 15 and sum(c.isupper() for c in letters) / len(letters) > 0.5:
        pts += 20
    return pts


def lexicon_score(text):
    """General doom score: (0-100, matched words)."""
    t = _norm(text)
    hits = [p for p in LEXICON if _match(t, p)]
    pts = sum(LEXICON[h] * 9 for h in hits) + _drama_bonus(text, DOOM_EMOJI)
    return max(0, min(100, pts)), hits


def ai_lexicon_score(text):
    """AI panic score: AI words count fully, general doom words at half weight.
    Zero if the text isn't about AI at all."""
    t = _norm(text)
    ai_hits = [p for p in AI_LEXICON if _match(t, p)]
    if not ai_hits and not re.search(r"(?<![a-z])(ai|a\.i\.|artificial intelligence)(?![a-z])", t):
        return 0, []
    gen_hits = [p for p in LEXICON if _match(t, p)]
    pts = sum(AI_LEXICON[h] * 9 for h in ai_hits) + sum(LEXICON[h] * 5 for h in gen_hits)
    pts += _drama_bonus(text, DOOM_EMOJI + AI_EMOJI)
    return max(0, min(100, pts)), ai_hits + gen_hits


# ---------------------------------------------------------------- fetching
def http_json(url, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


_bsky_auth = None


def bsky_auth():
    global _bsky_auth
    if _bsky_auth is None:
        sess = http_json(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            data=json.dumps({"identifier": os.environ["BSKY_HANDLE"],
                             "password": os.environ["BSKY_APP_PASSWORD"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        _bsky_auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
    return _bsky_auth


def fetch_bluesky(terms):
    if not (os.environ.get("BSKY_HANDLE") and os.environ.get("BSKY_APP_PASSWORD")):
        return []
    auth = bsky_auth()
    texts, per_term = [], min(25, max(5, SOCIAL_PER_SOURCE // len(terms) + 3))
    for term in terms:
        q = urllib.parse.urlencode({"q": f'"{term}"', "limit": per_term, "sort": "latest", "lang": "en"})
        try:
            res = http_json(f"https://bsky.social/xrpc/app.bsky.feed.searchPosts?{q}", headers=auth)
            texts += [p["record"].get("text", "") for p in res.get("posts", [])]
        except Exception as e:  # one bad term shouldn't sink the run
            print(f"  bluesky '{term}' failed: {e}", file=sys.stderr)
    seen, out = set(), []
    for t in texts:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:SOCIAL_PER_SOURCE]


def _strip_html(html):
    import html as _h
    text = re.sub(r"<br\s*/?>|</p>", " ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", _h.unescape(text)).strip()


def fetch_mastodon(tags):
    texts, seen = [], set()
    for tag in tags:
        for inst in MASTODON_INSTANCES:
            try:
                res = http_json(f"https://{inst}/api/v1/timelines/tag/{urllib.parse.quote(tag)}?limit=40")
            except Exception as e:
                print(f"  mastodon {inst} #{tag} failed: {e}", file=sys.stderr)
                continue
            for st in res:
                if st.get("language") not in (None, "en") or st.get("reblog"):
                    continue
                t = _strip_html(st.get("content", ""))
                if t and st.get("uri") not in seen:
                    seen.add(st.get("uri"))
                    texts.append(t)
    return texts[:SOCIAL_PER_SOURCE]


def fetch_feeds(urls):
    titles = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                root = ET.fromstring(r.read())
            got = [(i.findtext("title") or "").strip() for i in root.iter("item")]
            got = [re.sub(r"\s+-\s+[^-]+$", "", g) if "news.google" in url else g for g in got]
            titles += [g for g in got if g]
            print(f"  feed ok ({len(got)}): {url}")
        except Exception as e:
            print(f"  feed failed: {url} ({e})", file=sys.stderr)
    seen, out = set(), []
    for t in titles:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:PER_SOURCE]


def fetch_x(terms):
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        return []
    picked = []
    for t in terms:
        if len(" OR ".join(f'"{x}"' for x in picked + [t])) > 440:
            break
        picked.append(t)
    query = "(" + " OR ".join(f'"{t}"' for t in picked) + ") lang:en -is:retweet"
    q = urllib.parse.urlencode({"query": query, "max_results": min(100, max(10, PER_SOURCE))})
    res = http_json(f"https://api.x.com/2/tweets/search/recent?{q}",
                    headers={"Authorization": f"Bearer {token}"})
    return [t["text"] for t in res.get("data", [])]


# ---------------------------------------------------------------- Claude
def claude(prompt, max_tokens=2000):
    body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    res = http_json(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01", "content-type": "application/json"},
        timeout=90,
    )
    return "".join(b.get("text", "") for b in res.get("content", []))


def claude_scores(texts, kind, batch=100):
    out = []
    for i in range(0, len(texts), batch):
        out += _claude_scores(texts[i:i + batch], kind)
    return out


def _claude_scores(texts, kind):
    numbered = "\n".join(f"{i}. {t[:280].replace(chr(10), ' ')}" for i, t in enumerate(texts))
    what = ("alarmist / sky-is-falling" if kind == "main"
            else "panicked about AI (robot uprising, job doom, sentient-AI hype). Items not about AI score 0")
    prompt = (
        f"Rate how {what} each item below is, 0-100. "
        "0 = calm and factual, 50 = dramatic, 100 = maximum panic. "
        "Judge the tone, not the topic: a calm report on a serious event scores low.\n"
        "Reply with ONLY a JSON array of integers, one per item, same order.\n\n" + numbered
    )
    out = claude(prompt, max_tokens=1200)
    arr = json.loads(out[out.index("["): out.rindex("]") + 1])
    if len(arr) != len(texts):
        raise ValueError("score count mismatch")
    return [max(0, min(100, int(x))) for x in arr]


def claude_forecast(score, level, words, kind):
    if kind == "main":
        role = "a cheerful local TV weatherperson delivering the 'Doom Forecast' for the internet"
        name = "Sky Is Falling Index"
        example = "'Scattered hysteria this morning, clearing to mild concern by evening.'"
    else:
        role = "a cheerful local TV weatherperson delivering the 'Robot Uprising Forecast' for the internet"
        name = "Robot Uprising Risk"
        example = "'Heavy chatbot anxiety overnight, with a 40% chance of someone thanking their toaster.'"
    prompt = (
        f"You are {role}. Today's {name} is {score}/100 ({level}). "
        f"Trending panic words: {', '.join(words) or 'none'}. "
        f"Write ONE playful sentence (max 30 words) in weather-report style, e.g. {example} "
        "Keep it apolitical: no parties, politicians, companies, products or real people. "
        "No quotes. Just the sentence."
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
AI_LEVELS = [
    (0, "Mild Robot Concern", "🤖"),
    (20, "Side-Eyeing the Toaster", "👀"),
    (40, "Saying Please to the Chatbot", "🙏"),
    (60, "Unplugging Everything", "🔌"),
    (80, "Full Robot Uprising", "💥"),
]
FALLBACK_FORECASTS = {
    "Mild Concern": "Clear skies across the timeline. Light grumbling possible in the afternoon.",
    "Clutching Pearls": "Partly anxious with scattered gasps. Keep a fainting couch handy.",
    "Stockpiling Beans": "Heavy hysteria moving in. Canned goods advisory in effect until further notice.",
    "Building a Bunker": "Severe panic warning. Residents urged to stop refreshing and touch grass.",
    "Full Chicken Little": "Acorn impacts reported region-wide. The sky is, allegedly, falling.",
    "Mild Robot Concern": "Calm conditions. The robots are mostly just autocompleting emails today.",
    "Side-Eyeing the Toaster": "Light suspicion of household appliances, clearing by lunch.",
    "Saying Please to the Chatbot": "Widespread politeness toward software. Experts advise saying thank you, just in case.",
    "Unplugging Everything": "Smart-fridge watch in effect. Several residents report their thermostat 'looked at them funny'.",
    "Full Robot Uprising": "The machines have risen, mostly to recommend similar products. Stay calm.",
}


def level_for(score, levels):
    name, emoji = levels[0][1], levels[0][2]
    for floor, n, e in levels:
        if score >= floor:
            name, emoji = n, e
    return name, emoji


# ---------------------------------------------------------------- one meter
def run_meter(kind, now, prev):
    terms, feeds, tags = ((MAIN_TERMS, MAIN_FEEDS, MAIN_TAGS) if kind == "main"
                          else (AI_TERMS, AI_FEEDS, AI_TAGS))
    scorer = lexicon_score if kind == "main" else ai_lexicon_score
    levels = LEVELS if kind == "main" else AI_LEVELS

    sources, items = {}, []
    for name, fn in (("bluesky", lambda: fetch_bluesky(terms)),
                     ("mastodon", lambda: fetch_mastodon(tags)),
                     ("news", lambda: fetch_feeds(feeds)),
                     ("x", lambda: fetch_x(terms))):
        try:
            got = fn()
        except Exception as e:
            print(f"[{kind}] {name}: skipped ({e})", file=sys.stderr)
            got = []
        if got:
            sources[name] = len(got)
            items += [(name, t) for t in got]
        print(f"[{kind}] {name}: {len(got)} items")
    if not items:
        return None

    texts = [t for _, t in items]
    lex = [scorer(t) for t in texts]
    scores, method = [s for s, _ in lex], "word-list"
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            scores, method = claude_scores(texts, kind), "claude"
        except Exception as e:
            print(f"[{kind}] Claude scoring failed, using word list: {e}", file=sys.stderr)

    # Index = average of the spiciest half (doom is loud; calm posts are quiet).
    # Social posts are where the doom posters live, so when any are present
    # the index is built from them and headlines are only shown as their own bar.
    social = [s for (src, _), s in zip(items, scores) if src != "news"]
    pool = social if len(social) >= 20 else scores
    ranked = sorted(pool, reverse=True)
    top = ranked[: max(1, len(ranked) // 2)]
    index = round(sum(top) / len(top))

    by_source = {}
    for (src, _), s in zip(items, scores):
        by_source.setdefault(src, []).append(s)
    by_source = {k: round(sum(v) / len(v)) for k, v in by_source.items()}

    counts = {}
    for _, hits in lex:
        for h in hits:
            counts[h] = counts.get(h, 0) + 1
    top_words = [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:6]]

    level, emoji = level_for(index, levels)
    forecast = FALLBACK_FORECASTS[level]
    if method == "claude":
        try:
            forecast = claude_forecast(index, level, top_words, kind)
        except Exception as e:
            print(f"[{kind}] forecast failed: {e}", file=sys.stderr)

    history = [h for h in (prev or {}).get("history", []) if not h.get("sample")]
    history.append({"t": now.isoformat(), "score": index})
    print(f"[{kind}] index {index} — {emoji} {level} ({method}, n={len(texts)})")
    return {
        "updated": now.isoformat(), "score": index, "level": level, "emoji": emoji,
        "forecast": forecast, "method": method, "sampleSize": len(texts),
        "sources": sources, "bySource": by_source, "topWords": top_words,
        "history": history[-HISTORY_LEN:],
    }


def main():
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        prev = {}

    min_gap = int(os.environ.get("DOOM_MIN_GAP_MINUTES", "40"))
    if os.environ.get("DOOM_FORCE", "").lower() != "true" and prev.get("updated") and not prev.get("isSample"):
        age = (now - dt.datetime.fromisoformat(prev["updated"])).total_seconds() / 60
        if age < min_gap:
            print(f"Latest reading is {age:.0f} min old (< {min_gap}); skipping this try.")
            return 0

    main_meter = run_meter("main", now, prev)
    ai_meter = run_meter("ai", now, prev.get("ai"))

    if not main_meter and not ai_meter:
        print("ERROR: no items fetched from any source. Check the log above.", file=sys.stderr)
        return 1

    out = main_meter or {k: v for k, v in prev.items() if k != "ai"}
    out.pop("isSample", None)
    if ai_meter:
        out["ai"] = ai_meter
    elif "ai" in prev:
        out["ai"] = prev["ai"]

    try:  # share cards + preview pages; never let this sink a reading
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import make_cards
        make_cards.build(out)
    except Exception as e:
        print(f"Share cards skipped: {e}", file=sys.stderr)

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
