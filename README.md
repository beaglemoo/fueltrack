# FuelTrack

UK fuel price tracker using the GOV.UK Fuel Finder API. Collects fuel prices from every petrol station in the UK and stores them in InfluxDB for Grafana dashboards and trend analysis.

## What it does

- Fetches live fuel prices for **all ~7,400 UK petrol stations** from the GOV.UK Fuel Finder API
- Stores price data in InfluxDB with station name, brand, and region tags
- Classifies stations into configurable regions (e.g. by city/area) for comparison
- Runs on a schedule via systemd timer (every 4 hours by default)
- Data visualised in Grafana dashboards

## Data source

Prices come from the [GOV.UK Fuel Finder](https://www.fuel-finder.service.gov.uk/) service. Under UK regulations, fuel retailers must report price changes within 30 minutes.

### Available fuel types

| Code | Fuel |
|------|------|
| E5 | Super Unleaded |
| E10 | Unleaded |
| B7_STANDARD | Diesel |
| B7_PREMIUM | Premium Diesel |

## Setup

### 1. Register for API access

1. Go to [developer.fuel-finder.service.gov.uk](https://www.developer.fuel-finder.service.gov.uk/)
2. Sign in with GOV.UK One Login
3. Create an application as an Information Recipient
4. Copy your `client_id` and `client_secret`

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your API credentials and InfluxDB connection details. Add regions with keywords to classify stations near you:

```yaml
regions:
  - name: "my-area"
    label: "My Area"
    keywords:
      - "TOWN_NAME"
      - "NEARBY_TOWN"
```

### 3. Install and run

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m fueltrack.main
```

### 4. Deploy (optional)

The included `deploy.sh` rsyncs to a remote server and sets up systemd timer:

```bash
./deploy.sh
```

## InfluxDB schema

Bucket: `fueltrack` (365-day retention)

| Measurement | Tags | Fields |
|---|---|---|
| fuel_price | station_id, station_name, brand, region, fuel_type | price_pence |

## Region classification

Stations are classified into regions by matching their trading name against configured keywords. Stations that don't match any region are tagged as "other" but still stored -- all data is searchable in Grafana.

## Rate limits

The Fuel Finder API allows 30 requests per minute. A full collection run uses 15-16 requests (one per batch of 500 stations). Running every 4 hours is well within limits.

## License

Data from the GOV.UK Fuel Finder service is available under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
