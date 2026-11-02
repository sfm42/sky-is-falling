# ☄️ The Sky Is Falling Index

The internet's official-ish panic gauge. A few times a day a robot reads a sample of public posts and headlines with doom words in them, rates how dramatic each one sounds, and points the needle somewhere between 🟢 **Mild Concern** and ☄️ **Full Chicken Little**.

It measures **tone, not topic**, and stores **only overall numbers**. No accounts are named, tracked or saved.

## What's in here

| File | What it does |
|---|---|
| `index.html` | The whole site: gauge, Doom Forecast, trend line, and the paste-a-post Doom-o-Meter |
| `data/doom.json` | The latest reading (starts with sample data) |
| `scripts/update_doom.py` | Fetches posts, scores them, writes `doom.json`. Standard library only, no installs |
| `.github/workflows/update-doom.yml` | Runs the script every 6 hours and commits the new reading |

## Launch it (about 10 minutes)

1. **Create a repo** on GitHub (e.g. `sky-is-falling`) and upload these files, keeping the folders.
2. **Turn on the site:** Settings → Pages → *Deploy from a branch* → `main` / `(root)`. Your page will be at `https://<you>.github.io/sky-is-falling/`.
3. **Let the robot commit:** Settings → Actions → General → Workflow permissions → *Read and write*.
4. **Add secrets** (Settings → Secrets and variables → Actions). All are optional; add what you have:

| Secret | Why | Cost |
|---|---|---|
| `BSKY_HANDLE` + `BSKY_APP_PASSWORD` | Bluesky posts. Make an app password at bsky.app → Settings → Privacy and security → App passwords | Free |
| `ANTHROPIC_API_KEY` | Claude scores the posts (much smarter than the word list) and writes the daily forecast | Pennies a day with Haiku |
| `X_BEARER_TOKEN` | Adds X posts | ~$0.005 per post read. 50 posts × 4 runs/day ≈ $30/month |

News headlines (Google News RSS) need no key, so the meter works even with zero secrets.

5. **First reading:** Actions → *Update Doom Index* → *Run workflow*. The sample banner disappears once real data lands.

## Tuning

- **How often:** edit the `cron` line in the workflow (`17 */6 * * *` = every 6 hours).
- **Sample size per source:** set a `DOOM_SAMPLE_SIZE` env var in the workflow (default 50). This is the main X cost lever.
- **Doom words:** edit `LEXICON` in `scripts/update_doom.py` **and** the matching list in `index.html` (the paste scorer runs in the browser).
- **Level names / jokes:** `LEVELS`, `VERDICTS` and the ticker text are near the top of the script in `index.html`.

## Ground rules (keep it fun and keep it allowed)

- Aggregate only. X's developer terms forbid tracking individual users, so the script never saves handles, IDs or post text.
- Keep it apolitical. The Claude forecast prompt is told to avoid parties, politicians and real people.
- Don't scrape X. Use the API key route or leave X out.

*For entertainment only. If the needle is in the red, drink some water and go outside.*
