# ☄️ The Sky Is Falling Index

The internet's official-ish panic gauge. Every hour a robot reads a sample of public posts and headlines with doom words in them, rates how dramatic each one sounds, and points the needle somewhere between 🟢 **Mild Concern** and ☄️ **Full Chicken Little**.

A second gauge, **Robot Uprising Risk**, does the same for AI chatter, from 🤖 **Mild Robot Concern** to 💥 **Full Robot Uprising**.

It measures **tone, not topic**, and stores **only overall numbers**. No accounts are named, tracked or saved.

## What's in here

| File | What it does |
|---|---|
| `index.html` | The whole site: gauge, Doom Forecast, trend line, and the paste-a-post Doom-o-Meter |
| `data/doom.json` | The latest reading |
| `scripts/make_cards.py` | Draws the 1200×630 share snapshots (`data/cards/`) and the link-preview pages (`share/`) after each reading |
| `assets/fonts/` | Fonts for the share snapshots (SIL Open Font License, see `OFL.txt`) |
| `scripts/update_doom.py` | Fetches posts, scores them, writes `doom.json`. Standard library only, no installs |
| `.github/workflows/update-doom.yml` | Runs the script every hour and commits the new reading |

## Launch it (about 10 minutes)

1. **Create a repo** on GitHub (e.g. `sky-is-falling`) and upload these files, keeping the folders.
2. **Turn on the site:** Settings → Pages → *Deploy from a branch* → `main` / `(root)`. Your page will be at `https://<you>.github.io/sky-is-falling/`.
3. **Let the robot commit:** Settings → Actions → General → Workflow permissions → *Read and write*.
4. **Add secrets** (Settings → Secrets and variables → Actions). All are optional; add what you have:

| Secret | Why | Cost |
|---|---|---|
| `BSKY_HANDLE` + `BSKY_APP_PASSWORD` | Bluesky posts. Make an app password at bsky.app → Settings → Privacy and security → App passwords | Free |
| `ANTHROPIC_API_KEY` | Claude scores the posts (much smarter than the word list) and writes the daily forecast | Pennies a day with Haiku |
| `X_BEARER_TOKEN` | Adds X posts | ~$0.005 per post read. 50 posts × 24 runs/day ≈ $180/month (lower DOOM_SAMPLE_SIZE or the schedule to cut this) |

News headlines and Mastodon (public hashtag timelines) need no key, so the meter works even with zero secrets. Bluesky is strongly recommended: social posts are where the doom posters live, and when at least 20 social posts are found the index is built from them (headlines still get their own bar).

5. **First reading:** Actions → *Update Doom Index* → *Run workflow*. The sample banner disappears once real data lands.

## How the needle is set

Each reading blends two signals:

- **Panic volume (65%)**: doom posts per hour on Bluesky and Mastodon, estimated from post timestamps and compared with the median of the last ~3 days of readings. Normal = 50, double = 75, quadruple = 100, half = 25. For the first 3 readings it's still learning, so only intensity counts.
- **Intensity (35%)**: how dramatic the loudest half of the posts sound (word list, or Claude if `ANTHROPIC_API_KEY` is set).

Change the blend with the `DOOM_VOLUME_WEIGHT` env var (default `0.65`).

## Sharing

Each meter has a **Share this meter** button. It opens a panel with the current snapshot and one-click posting to X, Bluesky, Threads, Facebook, LinkedIn, Reddit, WhatsApp and email, plus Download image, Copy image and Copy text. On phones a "Share image…" button opens the phone's own share sheet (Instagram, TikTok, Messages…).

Shared links point to `share/main.html` or `share/ai.html`. Those pages carry the snapshot as their link preview, then forward visitors to the site. Every reading gets a uniquely named image so platforms don't show a stale preview.

## Analytics

Traffic is counted with [GoatCounter](https://www.goatcounter.com) (cookieless, no consent banner needed). Dashboard: https://skyisfalling.goatcounter.com

Besides page views, the site sends these click events:

| Event | Meaning |
|---|---|
| `share/main/open`, `share/ai/open` | Share panel opened on a meter |
| `share/<meter>/<platform>` | Platform clicked (`x`, `bluesky`, `threads`, `facebook`, `linkedin`, `reddit`, `whatsapp`, `email`) |
| `share/<meter>/download` · `copy-image` · `copy-text` · `native` | Snapshot downloaded, image copied, text copied, phone share sheet |
| `doom-o-meter/measure` · `example-*` · `copy-result` | Paste-a-post scorer used |

Visitors arriving through a shared link show up with the referrer `shared-sky-is-falling` or `shared-robot-uprising`.

## Tuning

- **How often:** the workflow tries at :07, :27 and :47 each hour and the script skips if a reading under 40 minutes old exists (`DOOM_MIN_GAP_MINUTES`), so you get about one reading an hour even when GitHub drops scheduled runs. Manual runs skip too, unless you tick **force** in the Run workflow dialog.
- **Sample sizes:** `DOOM_SOCIAL_SAMPLE` (Bluesky + Mastodon, free, default 300) and `DOOM_SAMPLE_SIZE` (news + X, default 50). The second is the X cost lever.
- **Doom words:** edit `LEXICON` (general) and `AI_LEXICON` (AI panic) in `scripts/update_doom.py` **and** the matching lists in `index.html` (the paste scorer runs in the browser).
- **What gets searched:** `MAIN_TERMS` / `AI_TERMS` (Bluesky and X searches) and `MAIN_FEEDS` / `AI_FEEDS` (news RSS) at the top of the script.
- **Red X in Actions?** The run fails on purpose when no source returned anything. Open the run's log to see which feeds failed.
- **Level names / jokes:** `LEVELS`, `VERDICTS` and the ticker text are near the top of the script in `index.html`.

## Ground rules (keep it fun and keep it allowed)

- Aggregate only. X's developer terms forbid tracking individual users, so the script never saves handles, IDs or post text.
- Keep it apolitical. The Claude forecast prompt is told to avoid parties, politicians and real people.
- Don't scrape X. Use the API key route or leave X out.

*For entertainment only. If the needle is in the red, drink some water and go outside.*
