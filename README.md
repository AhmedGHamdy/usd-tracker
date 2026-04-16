# USD / EGP Telegram Tracker

Tracks the US-Dollar to Egyptian-Pound exchange rate across multiple sources
and pings your phone on Telegram the moment anything changes.

- ⏱ **Every 15 minutes (8 AM – midnight Cairo)** → instant alert if any rate moved ≥ 0.05 EGP
  Silent between 12 AM – 8 AM so the bot never wakes you up.
- 📅 **8 AM Cairo → Morning Briefing** and **8 PM Cairo → Evening Wrap-up**, both with day-over-day deltas
- 🏦 **5 sources:** CBE official · CIB (JSON API) · Yahoo Finance market rate · open.er-api · fawazahmed0 currency-api
- 🕐 All timestamps shown in **12-hour format** (Cairo time)
- ☁️ Runs **100% free** on GitHub Actions — no PC / VPS required

> **Why not NBE / Banque Misr?** Both sites are behind an F5 Big-IP WAF that
> rejects all non-browser HTTP requests. A reliable scraper would need a headless
> browser (Playwright), which is too heavy for a 15-min cron. CBE and CIB already
> give you an accurate official + bank reading, and the three market APIs cover
> the parallel side.

---

## One-time setup (≈ 5 minutes)

### 1. Create your Telegram bot

1. Open Telegram → search for **`@BotFather`** → start a chat
2. Send `/newbot`
3. Pick a name (e.g. `USD EGP Tracker`) and a username ending in `bot` (e.g. `myusdegp_bot`)
4. BotFather replies with a **token** that looks like:
   ```
   123456789:ABCdefGhIJKlmNoPQRstuVWXyz
   ```
   Copy it — this is your `TELEGRAM_BOT_TOKEN`.

### 2. Get your chat ID

1. Open your new bot in Telegram and press **Start** (or send it any message like `hi`).
2. In your browser, open:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   (replace `<YOUR_TOKEN>` with the token from step 1)
3. Look for `"chat":{"id": 123456789, ...}` in the JSON. That number is your `TELEGRAM_CHAT_ID`.

### 3. Push this project to GitHub

```bash
cd E:\usd
git init
git add .
git commit -m "initial: USD/EGP tracker"
# Create a new repo on github.com (can be private), then:
git branch -M main
git remote add origin https://github.com/<your-username>/usd-egp-tracker.git
git push -u origin main
```

### 4. Add secrets to the repo

On GitHub: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
| ---- | ----- |
| `TELEGRAM_BOT_TOKEN` | the token from step 1 |
| `TELEGRAM_CHAT_ID`   | the chat ID from step 2 |

*(Optional)* Under **Variables** → add `MIN_CHANGE` (default `0.05`) to tune the alert threshold in EGP.

### 5. Enable Actions & kick off the first run

1. Go to the **Actions** tab → accept the prompt to enable workflows.
2. Open **USD-EGP Tracker** → click **Run workflow** → **Run**.
3. Within ~1 minute you should get your first Telegram message (a *baseline snapshot*).

From then on it runs automatically every 15 minutes, and sends a daily summary at 8 PM Cairo.

---

## How it works

```
GitHub Actions (cron */15) ──► tracker.py
                                   │
                                   ├─ fetch all 7 sources (sources.py)
                                   ├─ diff vs state.json
                                   ├─ if change ≥ MIN_CHANGE → send Telegram
                                   └─ commit updated state.json back to repo
```

`state.json` holds the last observed price per source so the next run can
compute the delta. The workflow auto-commits it after every run, giving you
a free 15-min-resolution price log in your git history.

`history.json` stores one snapshot per day for the daily summary.

## Running locally (optional, for testing)

```powershell
cd E:\usd
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Set creds for this shell only
$env:TELEGRAM_BOT_TOKEN = "123:abc..."
$env:TELEGRAM_CHAT_ID   = "123456789"

python tracker.py
```

Without the env vars it prints the message to stdout instead of sending.

## Tuning

| What | Where |
| --- | --- |
| Alert threshold (EGP) | repo variable `MIN_CHANGE` or env var of same name |
| Check frequency | `.github/workflows/tracker.yml` → `cron` |
| Daily summary time | `.github/workflows/daily.yml` → `cron` (UTC; Cairo = UTC+2) |
| Add / remove a source | edit `ALL_FETCHERS` in `sources.py` |

## Notes

- **Bank scrapers are best-effort.** NBE / CIB / Banque Misr occasionally change
  their rate-page HTML; when that happens the row shows `⚠️ unavailable` and
  the other sources keep working. Fix = update the URL or selector in
  `sources.py`.
- **GitHub Actions cron drift:** GitHub cannot guarantee exact 15-minute
  intervals during peak load. Expect occasional 5–25 min delays — normal.
- **Free tier limits:** public repos get unlimited Actions minutes; private
  repos get 2000 min/month, well above this workflow's needs.
