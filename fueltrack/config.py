"""Configuration loading and validation."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class FuelFinderConfig(BaseModel):
    client_id: str
    client_secret: str
    base_url: str = "https://www.fuel-finder.service.gov.uk"


class RegionConfig(BaseModel):
    name: str
    label: str
    keywords: list[str]
    exclude_keywords: list[str] = []


class InfluxDBConfig(BaseModel):
    url: str = "http://localhost:8086"
    token: str = ""
    org: str = "moo"
    bucket: str = "fueltrack"


class GhostConfig(BaseModel):
    url: str = ""
    admin_api_key: str = ""
    page_slug: str = "uk-fuel-prices"
    page_id: str = ""


class Settings(BaseModel):
    fuelfinder: FuelFinderConfig
    regions: list[RegionConfig] = []
    fuel_types: list[str] = ["E5", "E10", "B7_STANDARD"]
    influxdb: InfluxDBConfig = InfluxDBConfig()
    ghost: GhostConfig | None = None


def load_config() -> Settings:
    config_path = os.environ.get(
        "FUELTRACK_CONFIG",
        str(Path(__file__).parent.parent / "config.yaml"),
    )
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return Settings(**data)
