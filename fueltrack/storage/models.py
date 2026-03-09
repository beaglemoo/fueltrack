"""InfluxDB point builder functions."""

from datetime import datetime

from influxdb_client import Point


def fuel_price_point(
    station_id: str,
    station_name: str,
    brand: str,
    region: str,
    fuel_type: str,
    price_pence: float,
    timestamp: datetime,
) -> Point:
    """Build an InfluxDB point for a fuel price reading."""
    return (
        Point("fuel_price")
        .tag("station_id", station_id)
        .tag("station_name", station_name)
        .tag("brand", brand)
        .tag("region", region)
        .tag("fuel_type", fuel_type)
        .field("price_pence", price_pence)
        .time(timestamp)
    )
