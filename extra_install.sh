#!/bin/bash

# Prometheus, Grafana, and LibVirt Exporter Installation Script
set -e

echo "Starting Prometheus, Grafana & LibVirt Exporter Setup..."


sudo apt update


# Install Prometheus
echo "Installing Prometheus..."
sudo apt install -y prometheus
sudo systemctl enable prometheus
sudo systemctl start prometheus
echo "Prometheus installed and running on http://localhost:9090"

# Install Grafana
echo "Installing Grafana..."
sudo apt-get install -y apt-transport-https software-properties-common wget
sudo mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com beta main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install -y grafana
sudo systemctl daemon-reload
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
echo "Grafana installed and running on http://localhost:3000 (admin/admin)"

# Install Go
echo "Installing Go..."
sudo apt install -y golang-go

# Install prometheus-libvirt-exporter
echo "Installing prometheus-libvirt-exporter..."
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin


WORK_DIR="$HOME/prometheus-libvirt-exporter"
if [ -d "$WORK_DIR" ]; then
    rm -rf "$WORK_DIR"
fi

git clone https://github.com/zhangjianweibj/prometheus-libvirt-exporter.git "$WORK_DIR"
cd "$WORK_DIR"
go mod tidy
go mod vendor
go build ./...
go build
chmod +x ./prometheus-libvirt-exporter
sudo cp ./prometheus-libvirt-exporter /usr/local/bin/
cd - > /dev/null

# Create systemd service
echo "Creating systemd service for libvirt exporter..."
sudo tee /etc/systemd/system/prometheus-libvirt-exporter.service > /dev/null << EOF
[Unit]
Description=Prometheus LibVirt Exporter
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/prometheus-libvirt-exporter
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable prometheus-libvirt-exporter
sudo systemctl start prometheus-libvirt-exporter

# Configure Prometheus
echo "Configuring Prometheus..."
sudo cp /etc/prometheus/prometheus.yml /etc/prometheus/prometheus.yml.backup

if ! grep -q "libvirt_exporter" /etc/prometheus/prometheus.yml; then
    cat << EOF | sudo tee -a /etc/prometheus/prometheus.yml > /dev/null

  - job_name: 'libvirt_exporter'
    static_configs:
      - targets: ['localhost:9000']
EOF
fi

sudo systemctl restart prometheus

# Download dashboard
echo "Downloading Grafana dashboard..."
mkdir -p "$HOME/grafana-dashboards"
wget -O "$HOME/grafana-dashboards/libvirt-dashboard.json" "https://grafana.com/api/dashboards/15682/revisions/1/download"

echo "Setup complete!"
echo "1. Access Grafana at http://localhost:3000"
echo "2. Add Prometheus data source: http://localhost:9090"
echo "3. Import dashboard from: $HOME/grafana-dashboards/libvirt-dashboard.json"
