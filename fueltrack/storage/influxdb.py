"""InfluxDB writer for fuel price data."""

import logging

from influxdb_client import InfluxDBClient, BucketRetentionRules
from influxdb_client.client.write_api import SYNCHRONOUS

from ..config import InfluxDBConfig

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
RETENTION_DAYS = 365


class InfluxWriter:
    """Writes fuel price points to InfluxDB."""

    def __init__(self, config: InfluxDBConfig):
        self._config = config
        self._client = InfluxDBClient(
            url=config.url,
            token=config.token,
            org=config.org,
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    def ensure_bucket(self):
        """Create the bucket if it doesn't exist."""
        buckets_api = self._client.buckets_api()
        existing = buckets_api.find_bucket_by_name(self._config.bucket)
        if existing:
            logger.info("Bucket '%s' exists", self._config.bucket)
            return

        retention = BucketRetentionRules(
            type="expire",
            every_seconds=RETENTION_DAYS * 86400,
        )
        orgs = self._client.organizations_api().find_organizations(org=self._config.org)
        if not orgs:
            raise RuntimeError(f"Organization '{self._config.org}' not found")

        buckets_api.create_bucket(
            bucket_name=self._config.bucket,
            retention_rules=retention,
            org_id=orgs[0].id,
        )
        logger.info("Created bucket '%s' (%d-day retention)", self._config.bucket, RETENTION_DAYS)

    def write_points(self, points: list):
        """Write points to InfluxDB in batches."""
        if not points:
            return

        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i : i + BATCH_SIZE]
            try:
                self._write_api.write(
                    bucket=self._config.bucket,
                    org=self._config.org,
                    record=batch,
                )
            except Exception as e:
                if "outside retention policy" in str(e):
                    logger.warning("Some points outside retention policy, skipping")
                else:
                    raise

        logger.info("Wrote %d points to InfluxDB", len(points))

    def close(self):
        self._client.close()
