"""
Main tracker — runs every 15 minutes via GitHub Actions.
Fetches all USD/EGP sources, compares with last state, and
sends a Telegram alert if anything changed beyond the threshold.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# Force UTF-8 stdout/stderr so emoji messages print on Windows consoles.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _load_dotenv() -> None:
    """Minimal .env loader. Reads KEY=VALUE lines and populates os.environ
    (without overwriting values already set — GitHub Actions secrets win)."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

from sources import fetch_all

# ---------- Config ----------
STATE_FILE = Path(__file__).parent / "state.json"
CAIRO = ZoneInfo("Africa/Cairo")

# Minimum absolute EGP change to consider "significant" (avoids tick-noise spam).
# Override by setting env var MIN_CHANGE (e.g. 0.10 for 10 piasters).
MIN_CHANGE = float(os.environ.get("MIN_CHANGE", "0.05"))

# Only this source triggers alerts. Daily summary still shows all sources.
PRIMARY_SOURCE = os.environ.get("PRIMARY_SOURCE", "CIB")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# ---------- Helpers ----------

def now_cairo() -> datetime:
    return datetime.now(CAIRO)


def fmt_time(dt: datetime) -> str:
    """12-hour format, e.g. '2:45 PM'."""
    # %#I on Windows / %-I on Linux strip leading zero; use lstrip as safe fallback.
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_date_time(dt: datetime) -> str:
    return dt.strftime("%a %d %b %Y, ") + fmt_time(dt)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def pick_primary(r: dict) -> float | None:
    """Primary comparable number per source — prefer mid, else sell, else buy."""
    return r.get("mid") or r.get("sell") or r.get("buy")


def arrow(delta: float) -> str:
    """User prefers chart-arrow glyphs: 📈 up, 📉 down, — flat."""
    if delta > 0:
        return "📈"
    if delta < 0:
        return "📉"
    return "—"


# ---------- Message building ----------

def build_price_message(price: float) -> str:
    """One line. That's it."""
    return f"1 USD equals {price:.2f} EGP"


# ---------- Telegram ----------

def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — printing only.", file=sys.stderr)
        print("---- message ----")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    if not resp.ok:
        print(f"Telegram error {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()


# ---------- Main ----------

def main() -> int:
    # Quiet hours: 12:00 AM – 7:59 AM Cairo. Exit silently so no Telegram fires
    # during sleep. Uses ZoneInfo so DST transitions are handled automatically.
    cairo_now = now_cairo()
    if cairo_now.hour < 8:
        print(f"Quiet hours ({fmt_time(cairo_now)} Cairo) — skipping run.")
        return 0

    prev = load_state()
    prev_rates = prev.get("rates", {})

    print(f"Running at {fmt_date_time(cairo_now)} (Cairo)")
    results = fetch_all()

    # Update state for ALL sources (daily summary needs this data).
    new_rates = {}
    for r in results:
        name = r["source"]
        curr_price = pick_primary(r)
        if curr_price is None:
            if name in prev_rates:
                new_rates[name] = prev_rates[name]
            continue
        new_rates[name] = {
            "price": curr_price,
            "buy": r.get("buy"),
            "sell": r.get("sell"),
            "ts": now_cairo().isoformat(),
        }

    # Alert only on the primary source.
    primary_curr = new_rates.get(PRIMARY_SOURCE, {}).get("price")
    primary_prev = prev_rates.get(PRIMARY_SOURCE, {}).get("price")
    first_run = not prev_rates

    if primary_curr is None:
        print(f"Primary source '{PRIMARY_SOURCE}' unavailable — no alert.")
    elif first_run:
        # First-ever run: confirm bot is live with the current price.
        send_telegram(build_price_message(primary_curr))
    elif primary_prev is None:
        print(f"No previous price for '{PRIMARY_SOURCE}' — baselining only.")
    elif abs(primary_curr - primary_prev) >= MIN_CHANGE:
        send_telegram(build_price_message(primary_curr))
    else:
        print(f"No significant change on '{PRIMARY_SOURCE}' — skipping Telegram send.")

    # Persist state
    save_state({
        "rates": new_rates,
        "last_run": now_cairo().isoformat(),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
