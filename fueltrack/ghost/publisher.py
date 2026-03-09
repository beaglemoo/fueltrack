"""Ghost page publisher - updates fuel prices page on sillymoo.dev."""

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone

import httpx

from ..api.models import Station
from ..collectors.prices import classify_station, extract_brand
from ..config import RegionConfig

logger = logging.getLogger(__name__)


def _build_token(api_key: str) -> str:
    """Build a Ghost Admin API JWT token."""
    import jwt

    key_id, secret = api_key.split(":")
    iat = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}
    return jwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)


def _format_price(price: float | None) -> str:
    """Format price for display."""
    if price is None:
        return "-"
    if price < 10:
        return f"{price}p"
    return f"{price:.1f}p"


def generate_html(
    stations: list[Station],
    regions: list[RegionConfig],
    fuel_types: list[str],
) -> str:
    """Generate HTML content for the Ghost fuel prices page."""
    now = datetime.now(timezone.utc).strftime("%d %B %Y at %H:%M UTC")

    # Build station data with classification
    station_rows = []
    for s in stations:
        if not s.fuel_prices:
            continue
        region = classify_station(s, regions)
        brand = extract_brand(s.trading_name)
        prices = {fp.fuel_type: fp.price for fp in s.fuel_prices}

        # Skip stations with obviously wrong prices (< 50p or > 300p)
        valid_prices = {k: v for k, v in prices.items() if 50 < v < 300}
        if not valid_prices:
            continue

        station_rows.append({
            "name": s.trading_name,
            "brand": brand,
            "region": region,
            "prices": valid_prices,
        })

    # Sort by cheapest E10, then B7_STANDARD
    def sort_key(s):
        return s["prices"].get("E10", s["prices"].get("B7_STANDARD", 999))

    station_rows.sort(key=sort_key)

    # Build HTML
    html_parts = []
    html_parts.append(f'<p><strong>Last updated:</strong> {now}</p>')
    html_parts.append(f'<p><strong>Total stations reporting prices:</strong> {len(station_rows):,}</p>')
    html_parts.append('<p>Data from the <a href="https://www.fuel-finder.service.gov.uk/">GOV.UK Fuel Finder</a> service. '
                      'Prices update within 30 minutes of changes at the pump. '
                      'This page refreshes every 4 hours.</p>')
    html_parts.append('<hr>')

    # Regional summaries
    for region in regions:
        region_stations = [s for s in station_rows if s["region"] == region.name]
        if not region_stations:
            continue

        html_parts.append(f'<h2>{region.label}</h2>')

        # Cheapest per fuel type
        for ft in ["E10", "E5", "B7_STANDARD", "B7_PREMIUM"]:
            ft_label = {"E10": "Unleaded (E10)", "E5": "Super Unleaded (E5)",
                        "B7_STANDARD": "Diesel", "B7_PREMIUM": "Premium Diesel"}.get(ft, ft)
            stations_with_ft = [(s, s["prices"][ft]) for s in region_stations if ft in s["prices"]]
            if not stations_with_ft:
                continue
            stations_with_ft.sort(key=lambda x: x[1])
            cheapest = stations_with_ft[0]
            html_parts.append(
                f'<p><strong>Cheapest {ft_label}:</strong> {cheapest[1]:.1f}p - {cheapest[0]["name"]}</p>'
            )

        # Table for region
        html_parts.append('<table>')
        html_parts.append('<thead><tr>'
                          '<th>Station</th><th>Brand</th>'
                          '<th>Unleaded</th><th>Super</th>'
                          '<th>Diesel</th><th>Premium</th>'
                          '</tr></thead>')
        html_parts.append('<tbody>')

        for s in region_stations:
            html_parts.append(
                f'<tr>'
                f'<td>{s["name"]}</td>'
                f'<td>{s["brand"]}</td>'
                f'<td>{_format_price(s["prices"].get("E10"))}</td>'
                f'<td>{_format_price(s["prices"].get("E5"))}</td>'
                f'<td>{_format_price(s["prices"].get("B7_STANDARD"))}</td>'
                f'<td>{_format_price(s["prices"].get("B7_PREMIUM"))}</td>'
                f'</tr>'
            )

        html_parts.append('</tbody></table>')

    # National top 20 cheapest
    html_parts.append('<hr>')
    html_parts.append('<h2>UK Top 20 Cheapest - Unleaded (E10)</h2>')
    html_parts.append('<table>')
    html_parts.append('<thead><tr><th>#</th><th>Station</th><th>Brand</th><th>Price</th></tr></thead>')
    html_parts.append('<tbody>')
    e10_sorted = [(s, s["prices"]["E10"]) for s in station_rows if "E10" in s["prices"]]
    e10_sorted.sort(key=lambda x: x[1])
    for i, (s, price) in enumerate(e10_sorted[:20], 1):
        html_parts.append(f'<tr><td>{i}</td><td>{s["name"]}</td><td>{s["brand"]}</td><td>{price:.1f}p</td></tr>')
    html_parts.append('</tbody></table>')

    html_parts.append('<h2>UK Top 20 Cheapest - Diesel (B7)</h2>')
    html_parts.append('<table>')
    html_parts.append('<thead><tr><th>#</th><th>Station</th><th>Brand</th><th>Price</th></tr></thead>')
    html_parts.append('<tbody>')
    b7_sorted = [(s, s["prices"]["B7_STANDARD"]) for s in station_rows if "B7_STANDARD" in s["prices"]]
    b7_sorted.sort(key=lambda x: x[1])
    for i, (s, price) in enumerate(b7_sorted[:20], 1):
        html_parts.append(f'<tr><td>{i}</td><td>{s["name"]}</td><td>{s["brand"]}</td><td>{price:.1f}p</td></tr>')
    html_parts.append('</tbody></table>')

    # Footer
    html_parts.append('<hr>')
    html_parts.append('<p><small>Powered by <a href="https://github.com/beaglemoo/fueltrack">FuelTrack</a> '
                      '| Data: GOV.UK Fuel Finder (Open Government Licence v3.0) '
                      '| Updates every 4 hours</small></p>')

    return "\n".join(html_parts)


async def update_ghost_page(
    ghost_url: str,
    admin_api_key: str,
    page_slug: str,
    html_content: str,
    page_id: str = "",
):
    """Update a Ghost page with fuel price data."""
    token = _build_token(admin_api_key)
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Get page by ID or slug
        if page_id:
            url = f"{ghost_url}/ghost/api/admin/pages/{page_id}/?source=html"
        else:
            url = f"{ghost_url}/ghost/api/admin/pages/slug/{page_slug}/?source=html"

        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

        page = resp.json()["pages"][0]
        pid = page["id"]
        updated_at = page["updated_at"]

        resp = await client.put(
            f"{ghost_url}/ghost/api/admin/pages/{pid}/?source=html",
            headers=headers,
            json={
                "pages": [{
                    "html": html_content,
                    "updated_at": updated_at,
                }]
            },
        )
        resp.raise_for_status()
        logger.info("Updated Ghost page: %s", page_slug)
