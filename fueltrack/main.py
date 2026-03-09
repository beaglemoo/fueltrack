"""FuelTrack - UK fuel price collector.

Fetches fuel prices from the GOV.UK Fuel Finder API,
stores them in InfluxDB for Grafana dashboards.
"""

import asyncio
import logging
import sys

from .config import load_config
from .api.auth import TokenManager
from .api.client import FuelFinderClient
from .collectors.prices import classify_station, extract_brand
from .storage.influxdb import InfluxWriter
from .storage.models import fuel_price_point

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fueltrack")


async def run():
    config = load_config()
    logger.info("FuelTrack starting")
    logger.info(
        "Tracking fuel types: %s across %d regions",
        ", ".join(config.fuel_types),
        len(config.regions),
    )

    # Set up API client
    token_manager = TokenManager(
        base_url=config.fuelfinder.base_url,
        client_id=config.fuelfinder.client_id,
        client_secret=config.fuelfinder.client_secret,
    )

    writer = InfluxWriter(config.influxdb)
    writer.ensure_bucket()

    try:
        async with FuelFinderClient(
            config.fuelfinder.base_url, token_manager
        ) as client:
            # Fetch all stations
            stations = await client.fetch_all_prices()

            # Build points for ALL stations (so everything is searchable)
            points = []
            region_counts: dict[str, int] = {}

            for station in stations:
                if not station.fuel_prices:
                    continue

                region = classify_station(station, config.regions) or "other"
                brand = extract_brand(station.trading_name)

                for fp in station.fuel_prices:
                    if fp.fuel_type not in config.fuel_types:
                        continue

                    point = fuel_price_point(
                        station_id=station.node_id,
                        station_name=station.trading_name,
                        brand=brand,
                        region=region,
                        fuel_type=fp.fuel_type,
                        price_pence=fp.price,
                        timestamp=fp.price_change_effective_timestamp,
                    )
                    points.append(point)

                region_counts[region] = region_counts.get(region, 0) + 1

            # Log region breakdown
            for region_name, count in sorted(region_counts.items()):
                if region_name != "other":
                    logger.info("Region '%s': %d stations", region_name, count)
            logger.info("Unclassified stations: %d", region_counts.get("other", 0))

            # Write to InfluxDB
            writer.write_points(points)
            logger.info("Collection complete: %d price points", len(points))

            # Update Ghost page if configured
            if config.ghost and config.ghost.url and config.ghost.admin_api_key:
                try:
                    from .ghost.publisher import generate_html, update_ghost_page

                    html = generate_html(stations, config.regions, config.fuel_types)
                    await update_ghost_page(
                        ghost_url=config.ghost.url,
                        admin_api_key=config.ghost.admin_api_key,
                        page_slug=config.ghost.page_slug,
                        html_content=html,
                        page_id=config.ghost.page_id,
                    )
                except Exception:
                    logger.exception("Failed to update Ghost page (non-fatal)")

    finally:
        writer.close()


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(0)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
