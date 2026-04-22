"""
Daily summary — 8 AM + 8 PM Cairo. Full report with CIB + CBE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sources import fetch_all
from tracker import (
    CAIRO,
    arrow,
    fmt_date_time,
    fmt_time,
    now_cairo,
    pick_primary,
    send_telegram,
)

CHART_URL = "https://www.google.com/finance/quote/USD-EGP"
HISTORY_FILE = Path(__file__).parent / "history.json"


def fmt_delta(delta: float, base: float | None) -> str:
    if base and base > 0:
        pct = (delta / base) * 100
        return f"{arrow(delta)} {delta:+.4f} ({pct:+.2f}%)"
    return f"{arrow(delta)} {delta:+.4f}"


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_history(h: dict) -> None:
    HISTORY_FILE.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    history = load_history()
    today = now_cairo().strftime("%Y-%m-%d")

    results = fetch_all()
    snapshot = {}
    for r in results:
        if r["error"]:
            continue
        p = pick_primary(r)
        if p is not None:
            snapshot[r["source"]] = {"price": p, "buy": r.get("buy"), "sell": r.get("sell")}
    history[today] = snapshot

    prev_dates = sorted(d for d in history if d < today)
    prev_day = prev_dates[-1] if prev_dates else None
    prev_snap = history.get(prev_day, {}) if prev_day else {}

    ts = now_cairo()
    label = "Morning Briefing" if ts.hour < 12 else "Evening Wrap-up"
    lines = [
        f"📅 *USD/EGP — {label}*",
        f"_{ts.strftime('%A, %d %b %Y')} at {fmt_time(ts)} (Cairo)_",
        "",
        "💡 *How much is 1 US Dollar worth in Egyptian Pounds today?*",
        "",
    ]

    for r in results:
        name = r["source"]
        if r["error"]:
            lines.append(f"• *{name}*: ⚠️ unavailable")
            continue
        buy, sell = r.get("buy"), r.get("sell")
        curr = pick_primary(r)
        if buy is not None and sell is not None:
            line = f"• *{name}*: Buy `{buy:.2f}` / Sell `{sell:.2f}`"
        else:
            line = f"• *{name}*: `{curr:.2f}`"
        prev = prev_snap.get(name, {}).get("price")
        if prev is not None:
            line += f"  {fmt_delta(curr - prev, prev)}"
        lines.append(line)

    # CIB vs CBE spread
    by_src = {r["source"]: r for r in results if not r["error"]}
    cib = by_src.get("CIB")
    cbe = by_src.get("CBE")
    if cib and cbe:
        c1, c2 = pick_primary(cib), pick_primary(cbe)
        if c1 and c2:
            lines.append("")
            lines.append(f"📊 *CIB vs CBE spread*: `{(c1 - c2):+.4f}` EGP")

    # 7-day trend
    week_dates = sorted(d for d in history if d < today)[-7:]
    if len(week_dates) >= 2 and "CIB" in history[week_dates[0]] and "CIB" in snapshot:
        old_p = history[week_dates[0]]["CIB"]["price"]
        new_p = snapshot["CIB"]["price"]
        lines.append(f"📅 *7-day trend (CIB)*: `{old_p:.2f}` → `{new_p:.2f}`  {fmt_delta(new_p - old_p, old_p)}")

    if prev_day:
        lines.append(f"_vs {prev_day}_")

    lines.append("")
    lines.append(f"📈 [Google Finance chart]({CHART_URL})")

    send_telegram("\n".join(lines))

    if len(history) > 60:
        keep = sorted(history)[-60:]
        history = {k: history[k] for k in keep}
    save_history(history)
    return 0


if __name__ == "__main__":
    sys.exit(main())
