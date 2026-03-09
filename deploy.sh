#!/bin/bash
set -euo pipefail

TARGET="root@192.168.0.100"
REMOTE_DIR="/root/fueltrack"

echo "Deploying FuelTrack to ansible box (192.168.0.100)..."

/opt/homebrew/bin/rsync -avz --delete \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude 'config.yaml' \
    --exclude 'state.json' \
    --exclude 'stations_dump.json' \
    --exclude '.git/' \
    --exclude '.claude/' \
    --exclude 'test_*.py' \
    --exclude 'explore.py' \
    -e ssh ./ "${TARGET}:${REMOTE_DIR}/"

echo "Setting up Python environment..."
ssh "${TARGET}" bash -s << 'REMOTE'
cd /root/fueltrack

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

venv/bin/pip install -q -r requirements.txt

if [ ! -f "config.yaml" ]; then
    cp config.example.yaml config.yaml
    echo "Created config.yaml from template - edit with your credentials"
fi

cp systemd/fueltrack.service /etc/systemd/system/
cp systemd/fueltrack.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable fueltrack.timer
systemctl start fueltrack.timer

echo ""
echo "Timer status:"
systemctl status fueltrack.timer --no-pager
REMOTE

echo ""
echo "Deployment complete."
