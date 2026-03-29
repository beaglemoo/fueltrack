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


# Prefixes to strip when extracting location (order matters - longer first)
_BRAND_PREFIXES = [
    "WELCOME BREAK", "CENTRAL CO-OP", "CO-OP",
    "SHELL LITTLE WAITROSE", "SHELL HARVEST ENERGY",
    "MFG MORRISONS", "MFG JET", "MFG BP", "MFG ESSO", "MFG TEXACO",
    "TESCO EXTRA", "TESCO EXPRESS", "SAINSBURYS LOCAL",
    "SHELL", "BP ", "ESSO", "TEXACO", "SAINSBURYS", "ASDA", "TESCO",
    "MORRISONS", "COSTCO", "MFG", "RONTEC", "ASCONA", "JET ",
    "GULF", "MURCO", "HARVEST", "SPAR", "APPLEGREEN", "SGN",
]

_LOCATION_SUFFIXES = [
    "PETROL FILLING STATION", "FILLING STATION", "SERVICE STATION",
    "SERVICE AREA", "PETROL STATION", "FUEL EXPRESS AUTOMAT",
    "ESSO EXPRESS", "SF CONNECT", "SUPERSTORE", "SERVICES",
    "GARAGE LTD", "GARAGE", " LTD", " S/S", " SS", " PFS",
    " EXTRA", " EXPRESS",
]


def extract_location(trading_name: str) -> str:
    """Best-effort location extraction from a station trading name."""
    name = trading_name.strip()
    upper = name.upper()

    # Strip brand prefixes (loop to catch compound brands like "ESSO TESCO")
    for _ in range(2):
        for prefix in _BRAND_PREFIXES:
            if upper.startswith(prefix):
                name = name[len(prefix):].strip()
                upper = name.upper()
                break

    # Strip " - " separator (common in superstore names)
    if " - " in name:
        name = name.split(" - ")[0].strip()
        upper = name.upper()

    # Strip trailing suffixes
    changed = True
    while changed:
        changed = False
        for suffix in _LOCATION_SUFFIXES:
            if upper.endswith(suffix):
                name = name[:-len(suffix)].strip()
                upper = name.upper()
                changed = True
                break
        # Strip trailing commas, dashes, parentheses
        name = name.strip(" ,-/()")
        upper = name.upper()

    # Strip directional suffixes
    for d in [" NORTH", " SOUTH", " EAST", " WEST"]:
        if upper.endswith(d) and len(name) > len(d) + 2:
            name = name[:-len(d)].strip()
            upper = name.upper()

    # Title case the result
    if name:
        return name.title()
    return trading_name.title()
