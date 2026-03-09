"""Pydantic models for Fuel Finder API responses."""

from datetime import datetime

from pydantic import BaseModel


class FuelPrice(BaseModel):
    fuel_type: str
    price: float
    price_last_updated: datetime
    price_change_effective_timestamp: datetime


class Station(BaseModel):
    node_id: str
    public_phone_number: str | None = None
    trading_name: str
    fuel_prices: list[FuelPrice] = []
