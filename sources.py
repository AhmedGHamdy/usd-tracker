"""
USD/EGP rate fetchers — CIB (primary) + CBE (daily report).
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}
TIMEOUT = 15


def _result(source: str, buy=None, sell=None, mid=None, error=None) -> dict:
    if mid is None and buy is not None and sell is not None:
        mid = round((buy + sell) / 2, 4)
    return {"source": source, "buy": buy, "sell": sell, "mid": mid, "error": error}


# ---------- CIB — clean JSON API ----------

def fetch_cib() -> dict:
    try:
        r = requests.get(
            "https://www.cibeg.com/api/currency/rates",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        for row in r.json().get("rates", []):
            if (row.get("currencyID") or "").upper() == "USD":
                return _result("CIB", buy=float(row["buyRate"]), sell=float(row["sellRate"]))
        return _result("CIB", error="USD not in payload")
    except Exception as e:
        return _result("CIB", error=str(e))


# ---------- CBE official (scrape) ----------

def fetch_cbe() -> dict:
    try:
        r = requests.get(
            "https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates",
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.find_all("tr"):
            text = row.get_text(" ", strip=True).upper()
            if "US DOLLAR" in text or "USD" in text.split():
                nums = re.findall(r"\d+\.\d{2,4}", row.get_text(" "))
                if len(nums) >= 2:
                    return _result("CBE", buy=float(nums[0]), sell=float(nums[1]))
        return _result("CBE", error="USD row not found")
    except Exception as e:
        return _result("CBE", error=str(e))


# ---------- Orchestrator ----------

ALL_FETCHERS = [fetch_cib, fetch_cbe]


def fetch_all() -> list[dict]:
    return [fn() for fn in ALL_FETCHERS]
