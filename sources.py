"""
USD/EGP rate fetchers. Each function returns:
    {"source": str, "buy": float|None, "sell": float|None, "mid": float|None, "error": str|None}

All functions are defensive — on any failure they return an 'error' string
instead of raising, so one broken source doesn't kill the whole run.
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
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}
TIMEOUT = 15


def _result(source: str, buy=None, sell=None, mid=None, error=None) -> dict:
    if mid is None and buy is not None and sell is not None:
        mid = round((buy + sell) / 2, 4)
    return {"source": source, "buy": buy, "sell": sell, "mid": mid, "error": error}


# ---------- Free forex APIs (mid-market) ----------

def fetch_open_er_api() -> dict:
    """open.er-api.com — free, no key."""
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=TIMEOUT)
        r.raise_for_status()
        egp = float(r.json()["rates"]["EGP"])
        return _result("Forex (open.er-api)", mid=round(egp, 4))
    except Exception as e:
        return _result("Forex (open.er-api)", error=str(e))


def fetch_currency_api() -> dict:
    """fawazahmed0 currency-api mirror — free, no key, daily-refreshed."""
    try:
        r = requests.get(
            "https://latest.currency-api.pages.dev/v1/currencies/usd.json",
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        egp = float(r.json()["usd"]["egp"])
        return _result("Forex (currency-api)", mid=round(egp, 4))
    except Exception as e:
        return _result("Forex (currency-api)", error=str(e))


# ---------- Yahoo Finance — market rate ----------

def fetch_yahoo() -> dict:
    """Yahoo Finance USDEGP=X — realtime market rate."""
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/USDEGP=X",
            params={"interval": "1m", "range": "1d"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        price = result["meta"].get("regularMarketPrice")
        if price is None:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
            price = closes[-1] if closes else None
        if price is None:
            return _result("Yahoo (market)", error="no price in response")
        return _result("Yahoo (market)", mid=round(float(price), 4))
    except Exception as e:
        return _result("Yahoo (market)", error=str(e))


# ---------- CBE official rate (scrape) ----------

def fetch_cbe() -> dict:
    """Scrape the Central Bank of Egypt daily exchange rates page."""
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
                    return _result("CBE (official)", buy=float(nums[0]), sell=float(nums[1]))
        return _result("CBE (official)", error="USD row not found on page")
    except Exception as e:
        return _result("CBE (official)", error=str(e))


# ---------- CIB — clean JSON API ----------

def fetch_cib() -> dict:
    """CIB's public JSON endpoint used by their currency-converter page."""
    try:
        r = requests.get(
            "https://www.cibeg.com/api/currency/rates",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        for row in data.get("rates", []):
            if (row.get("currencyID") or "").upper() == "USD":
                return _result("CIB", buy=float(row["buyRate"]), sell=float(row["sellRate"]))
        return _result("CIB", error="USD not in rates payload")
    except Exception as e:
        return _result("CIB", error=str(e))


# ---------- Orchestrator ----------

ALL_FETCHERS = [
    fetch_cbe,
    fetch_cib,
    fetch_yahoo,
    fetch_open_er_api,
    fetch_currency_api,
]


def fetch_all() -> list[dict]:
    return [fn() for fn in ALL_FETCHERS]
