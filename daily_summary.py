"""
Daily summary — runs once a day (8:00 PM Cairo via GitHub Actions).
Sends a digest with today's open / high / low / close per source,
plus the change vs yesterday's close.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from sources import fetch_all
from tracker import (
    CAIRO,
    fmt_date_time,
    fmt_delta,
    fmt_time,
    now_cairo,
    pick_primary,
    send_telegram,
)

HISTORY_FILE = Path(__file__).parent / "history.json"


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_history(h: dict) -> None:
    HISTORY_FILE.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")


def today_key() -> str:
    return now_cairo().strftime("%Y-%m-%d")


def main() -> int:
    history = load_history()
    today = today_key()

    # Record today's closing snapshot
    results = fetch_all()
    snapshot = {}
    for r in results:
        if r["error"]:
            continue
        p = pick_primary(r)
        if p is not None:
            snapshot[r["source"]] = {
                "price": p,
                "buy": r.get("buy"),
                "sell": r.get("sell"),
            }
    history[today] = snapshot

    # Find yesterday — last available date before today
    prior_dates = sorted(d for d in history.keys() if d < today)
    prev_day = prior_dates[-1] if prior_dates else None
    prev_snapshot = history.get(prev_day, {}) if prev_day else {}

    # Build message — label as morning briefing vs evening wrap-up
    ts = now_cairo()
    label = "Morning Briefing" if ts.hour < 12 else "Evening Wrap-up"
    lines = [
        f"📅 *USD/EGP — {label}*",
        f"_{ts.strftime('%A, %d %b %Y')} at {fmt_time(ts)} (Cairo)_",
        "",
    ]

    for r in results:
        name = r["source"]
        if r["error"]:
            lines.append(f"• *{name}*: ⚠️ unavailable")
            continue

        curr = pick_primary(r)
        if curr is None:
            continue

        buy, sell = r.get("buy"), r.get("sell")
        if buy is not None and sell is not None:
            base = f"Buy `{buy:.4f}` / Sell `{sell:.4f}`"
        else:
            base = f"`{curr:.4f}`"

        prev = prev_snapshot.get(name, {}).get("price")
        if prev is not None:
            delta = curr - prev
            base += f"  {fmt_delta(delta, prev)}"

        lines.append(f"• *{name}*: {base}")

    # Spread snapshot
    by_src = {r["source"]: r for r in results if not r["error"]}
    official = by_src.get("CBE (official)")
    market = by_src.get("Yahoo (market)")
    if official and market:
        o = pick_primary(official)
        m = pick_primary(market)
        if o and m:
            lines.append("")
            lines.append(f"📊 *Spread (Market − Official)*: `{(m - o):+.4f}` EGP")

    if prev_day:
        lines.append("")
        lines.append(f"_Comparison vs {prev_day}_")

    send_telegram("\n".join(lines))

    # Keep only last 60 days
    if len(history) > 60:
        keep = sorted(history.keys())[-60:]
        history = {k: history[k] for k in keep}
    save_history(history)

    return 0


if __name__ == "__main__":
    sys.exit(main())
