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

from sources import fetch_all

# ---------- Config ----------
STATE_FILE = Path(__file__).parent / "state.json"
CAIRO = ZoneInfo("Africa/Cairo")

# Minimum absolute EGP change to consider "significant" (avoids tick-noise spam).
# Override by setting env var MIN_CHANGE (e.g. 0.10 for 10 piasters).
MIN_CHANGE = float(os.environ.get("MIN_CHANGE", "0.05"))

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
    if delta > 0:
        return "🔺"
    if delta < 0:
        return "🔻"
    return "➖"


def fmt_delta(delta: float, base: float | None) -> str:
    if base and base > 0:
        pct = (delta / base) * 100
        return f"{arrow(delta)} {delta:+.4f} ({pct:+.2f}%)"
    return f"{arrow(delta)} {delta:+.4f}"


# ---------- Message building ----------

def build_message(results: list[dict], prev: dict, changes: list[tuple]) -> str:
    ts = now_cairo()
    lines = [f"💱 *USD / EGP Update*", f"_{fmt_date_time(ts)} (Cairo)_", ""]

    # Per-source block
    for r in results:
        name = r["source"]
        if r["error"]:
            lines.append(f"• *{name}*: ⚠️ unavailable")
            continue

        buy, sell, mid = r["buy"], r["sell"], r["mid"]
        line = f"• *{name}*: "
        if buy is not None and sell is not None:
            line += f"Buy `{buy:.4f}` / Sell `{sell:.4f}`"
        elif mid is not None:
            line += f"`{mid:.4f}`"
        else:
            line += "—"

        # Append change vs previous
        prev_price = prev.get(name, {}).get("price")
        curr_price = pick_primary(r)
        if prev_price is not None and curr_price is not None:
            delta = curr_price - prev_price
            if abs(delta) >= 0.0001:
                line += f"  {fmt_delta(delta, prev_price)}"
        lines.append(line)

    # Spread (CBE vs Yahoo market)
    by_src = {r["source"]: r for r in results if not r["error"]}
    official = by_src.get("CBE (official)")
    market = by_src.get("Yahoo (market)")
    if official and market:
        off_mid = pick_primary(official)
        mkt_mid = pick_primary(market)
        if off_mid and mkt_mid:
            spread = mkt_mid - off_mid
            lines.append("")
            lines.append(f"📊 *Spread (Market − Official)*: `{spread:+.4f}` EGP")

    # Summary of changes
    if changes:
        lines.append("")
        lines.append("*Changed since last check:*")
        for name, prev_p, curr_p in changes:
            d = curr_p - prev_p
            lines.append(f"  _{name}_: `{prev_p:.4f}` → `{curr_p:.4f}`  {fmt_delta(d, prev_p)}")

    return "\n".join(lines)


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

    # Detect significant changes
    changes: list[tuple] = []
    new_rates = {}
    for r in results:
        name = r["source"]
        curr_price = pick_primary(r)
        if curr_price is None:
            # Don't overwrite last known good value on failure
            if name in prev_rates:
                new_rates[name] = prev_rates[name]
            continue

        new_rates[name] = {
            "price": curr_price,
            "buy": r.get("buy"),
            "sell": r.get("sell"),
            "ts": now_cairo().isoformat(),
        }

        prev_price = prev_rates.get(name, {}).get("price")
        if prev_price is None:
            # First observation — don't count as change
            continue
        if abs(curr_price - prev_price) >= MIN_CHANGE:
            changes.append((name, prev_price, curr_price))

    # Compose and send only if something changed
    first_run = not prev_rates
    if changes or first_run:
        msg = build_message(results, prev_rates, changes)
        if first_run:
            msg = "🟢 *Tracker started — baseline snapshot*\n\n" + msg
        send_telegram(msg)
    else:
        print("No significant change — skipping Telegram send.")

    # Persist state
    save_state({
        "rates": new_rates,
        "last_run": now_cairo().isoformat(),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
