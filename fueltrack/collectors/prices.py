"""Fuel price collection and region classification."""

import logging

from ..api.models import Station
from ..config import RegionConfig

logger = logging.getLogger(__name__)


def classify_station(station: Station, regions: list[RegionConfig]) -> str | None:
    """Match a station to a region based on keywords. Returns region name or None."""
    name = station.trading_name.upper()

    for region in regions:
        # Check exclusions first
        if any(kw.upper() in name for kw in region.exclude_keywords):
            continue
        if any(kw.upper() in name for kw in region.keywords):
            return region.name

    return None


def extract_brand(trading_name: str) -> str:
    """Extract the brand from a station trading name."""
    name = trading_name.upper()

    brands = {
        "SHELL": "Shell",
        "BP ": "BP",
        "ESSO": "Esso",
        "TEXACO": "Texaco",
        "SAINSBURYS": "Sainsburys",
        "ASDA": "ASDA",
        "TESCO": "Tesco",
        "MORRISONS": "Morrisons",
        "COSTCO": "Costco",
        "MFG": "MFG",
        "WELCOME BREAK": "Welcome Break",
        "RONTEC": "Rontec",
        "ASCONA": "Ascona",
        "CO-OP": "Co-op",
        "CENTRAL CO-OP": "Co-op",
        "JET": "Jet",
        "GULF": "Gulf",
        "MURCO": "Murco",
        "HARVEST": "Harvest",
    }

    # Check if name contains "SUPERSTORE" or "EXTRA" (Tesco patterns)
    if "SUPERSTORE" in name or "EXTRA" in name:
        if not any(b in name for b in ["SHELL", "BP", "ESSO", "SAINSBURYS", "ASDA"]):
            return "Tesco"

    for keyword, brand in brands.items():
        if keyword in name:
            return brand

    return "Independent"
