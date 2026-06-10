"""Load persona fixtures with dates always relative to today.

Dates in the JSON files are treated as relative offsets to each other.
On load, all dates are shifted so the newest transaction lands on `today`
(defaults to ``date.today()``), and only the most recent 90 days are kept.

Category IDs are resolved from the merchant name using the system category
mapping seeded by the initial migration (leaf UUIDs are deterministic).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent
_WINDOW_DAYS = 90

PERSONAS = ["meiko_tokyo"]


def _lid(n: int) -> str:
    return f"00000000-0000-7000-8002-{n:012d}"


# Leaf category IDs (match 000000000001_squash.py _LEAVES)
CAT_GROCERIES = _lid(1)
CAT_RESTAURANTS = _lid(2)
CAT_CAFES = _lid(3)
CAT_CONVENIENCE = _lid(5)
CAT_RENT = _lid(6)
CAT_UTILITIES = _lid(7)
CAT_HOME_GOODS = _lid(8)
CAT_PUBLIC_TRANSIT = _lid(9)
CAT_TAXI = _lid(10)
CAT_FITNESS = _lid(13)
CAT_ELECTRONICS = _lid(15)
CAT_GENERAL_SHOPPING = _lid(16)
CAT_STREAMING = _lid(20)
CAT_SALARY = _lid(27)
CAT_FREELANCE = _lid(29)
CAT_GIFTS = _lid(26)

# merchant substring (lowercase) → category_id
_MERCHANT_MAP: dict[str, str] = {
    # convenience stores
    "lawson": CAT_CONVENIENCE,
    "familymart": CAT_CONVENIENCE,
    "family mart": CAT_CONVENIENCE,
    "7-eleven": CAT_CONVENIENCE,
    "konbini": CAT_CONVENIENCE,
    # cafes
    "starbucks": CAT_CAFES,
    "doutor": CAT_CAFES,
    "coffee": CAT_CAFES,
    # restaurants
    "yoshinoya": CAT_RESTAURANTS,
    "mos burger": CAT_RESTAURANTS,
    "sushiro": CAT_RESTAURANTS,
    "saizeriya": CAT_RESTAURANTS,
    "matsuya": CAT_RESTAURANTS,
    "sukiya": CAT_RESTAURANTS,
    "mcdonalds": CAT_RESTAURANTS,
    "mcdonald": CAT_RESTAURANTS,
    # groceries
    "seiyu": CAT_GROCERIES,
    "aeon": CAT_GROCERIES,
    "пятёрочка": CAT_GROCERIES,
    "pyaterochka": CAT_GROCERIES,
    "supermarket": CAT_GROCERIES,
    # rent
    "landlord": CAT_RENT,
    "rent": CAT_RENT,
    "loyer": CAT_RENT,
    # utilities
    "tokyo gas": CAT_UTILITIES,
    "tokyo electric": CAT_UTILITIES,
    "electric power": CAT_UTILITIES,
    "tepco": CAT_UTILITIES,
    "edf": CAT_UTILITIES,
    # public transit
    "jr east": CAT_PUBLIC_TRANSIT,
    "suica": CAT_PUBLIC_TRANSIT,
    "pasmo": CAT_PUBLIC_TRANSIT,
    "metro": CAT_PUBLIC_TRANSIT,
    "ratp": CAT_PUBLIC_TRANSIT,
    "navigo": CAT_PUBLIC_TRANSIT,
    # taxi
    "яндекс.такси": CAT_TAXI,
    "yandex": CAT_TAXI,
    "uber": CAT_TAXI,
    "grab": CAT_TAXI,
    # fitness
    "sports club": CAT_FITNESS,
    "gym": CAT_FITNESS,
    "fitness": CAT_FITNESS,
    # electronics
    "yamada denki": CAT_ELECTRONICS,
    "yodobashi": CAT_ELECTRONICS,
    "bic camera": CAT_ELECTRONICS,
    # streaming & subscriptions
    "netflix": CAT_STREAMING,
    "spotify": CAT_STREAMING,
    "amazon prime": CAT_STREAMING,
    "adobe": CAT_STREAMING,
    "hulu": CAT_STREAMING,
    "apple": CAT_STREAMING,
    # general shopping
    "amazon.co.jp": CAT_GENERAL_SHOPPING,
    "amazon": CAT_GENERAL_SHOPPING,
    "rakuten": CAT_GENERAL_SHOPPING,
    # salary / employment
    "acme corp": CAT_SALARY,
    "salary": CAT_SALARY,
    "payroll": CAT_SALARY,
    # freelance / self-employment
    "dupont": CAT_FREELANCE,
    "martin sas": CAT_FREELANCE,
    "studio": CAT_FREELANCE,
    "invoice": CAT_FREELANCE,
    "freelance": CAT_FREELANCE,
    # gifts
    "gift": CAT_GIFTS,
    "donation": CAT_GIFTS,
    # airlines → transport
    "airlines": CAT_PUBLIC_TRANSIT,
    "airways": CAT_PUBLIC_TRANSIT,
    "airline": CAT_PUBLIC_TRANSIT,
    "lufthansa": CAT_PUBLIC_TRANSIT,
    "delta": CAT_PUBLIC_TRANSIT,
    "united airlines": CAT_PUBLIC_TRANSIT,
    "bvg": CAT_PUBLIC_TRANSIT,
    "deutsche bahn": CAT_PUBLIC_TRANSIT,
    # taxis in other cities
    "lyft": CAT_TAXI,
    "taxi": CAT_TAXI,
    # hotels → rent (temporary accommodation)
    "hotel": CAT_RENT,
    "marriott": CAT_RENT,
    "hyatt": CAT_RENT,
    "sofitel": CAT_RENT,
    "cerulean": CAT_RENT,
    "palace hotel": CAT_RENT,
    # western supermarkets
    "safeway": CAT_GROCERIES,
    "whole foods": CAT_GROCERIES,
    # travel restaurants / dining
    "izakaya": CAT_RESTAURANTS,
    "ramen": CAT_RESTAURANTS,
    "restaurant": CAT_RESTAURANTS,
    "per se": CAT_RESTAURANTS,
    "ballhaus": CAT_RESTAURANTS,
}


def resolve_category(merchant: str | None, tx_type: str) -> str | None:
    if not merchant:
        return None
    key = merchant.lower()
    for substr, cat_id in _MERCHANT_MAP.items():
        if substr in key:
            return cat_id
    return None


def load_fixture(persona: str, today: date | None = None) -> dict:
    """Return the fixture dict for *persona* with dates anchored to *today*.

    Transactions outside the 90-day window are dropped.
    Recurring rule start_dates are shifted by the same offset.
    category_id is resolved from merchant name where possible.
    """
    if today is None:
        today = datetime.now(UTC).date()

    path = _FIXTURES_DIR / f"{persona}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError(f"Unknown fixture version in {path}")

    raw_txs: list[dict] = data["transactions"]
    max_date = max(date.fromisoformat(tx["date"]) for tx in raw_txs)
    offset = today - max_date
    cutoff = today - timedelta(days=_WINDOW_DAYS)

    def _shift(d: str) -> str:
        return (date.fromisoformat(d) + offset).isoformat()

    transactions = [
        {
            **tx,
            "date": _shift(tx["date"]),
            "category_id": resolve_category(tx.get("merchant"), tx.get("type", "")),
        }
        for tx in raw_txs
        if cutoff <= date.fromisoformat(tx["date"]) + offset <= today
    ]

    recurring = [
        {
            **r,
            "start_date": _shift(r["start_date"]),
            "category_id": resolve_category(r.get("merchant"), r.get("type", "")),
        }
        for r in data.get("recurring", [])
    ]

    return {**data, "transactions": transactions, "recurring": recurring}
