---
title: Libvirt dashboard
nav_order: 7
---

Libvirt Dashboard utilizes Prometheus to visualize metrics of VMs in Grafana.

### 0. Install Prometheus and Grafana
Install Prometheus

`$ sudo apt install prometheus`

`$ sudo systemctl status prometheus`

Install Grafana

`$ sudo apt-get install -y apt-transport-https software-properties-common wget`

`$ sudo mkdir -p /etc/apt/keyrings/`

`$ echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list`

`$ echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com beta main" | sudo tee -a /etc/apt/sources.list.d/grafana.list`

`$ sudo apt-get update`

`$ sudo apt-get install grafana`

`$ sudo systemctl daemon-reload`

`$ sudo systemctl start grafana-server`

`$ sudo systemctl enable grafana-server`

`$ sudo systemctl status grafana-server`

### 1. Install prometheus-libvirt-exporter
Install prometheus-libvirt-exporter (https://github.com/zhangjianweibj/prometheus-libvirt-exporter)

`$ sudo apt install golang-go`

`$ go install github.com/goreleaser/goreleaser@latest`

`$ go install github.com/go-task/task/v3/cmd/task@latest`

`$ git clone https://github.com/zhangjianweibj/prometheus-libvirt-exporter.git`

`$ cd prometheus-libvirt-exporter/`

`$ go mod tidy`

`$ go mod vendor`

`$ go build ./...`

`$ go build`

Configure Prometheus

`$ nano /etc/prometheus/prometheus.yml`

At the end of the file `/etc/prometheus/prometheus.yml` (within `scrape_configs:`), add the following:

```
  - job_name: 'libvirt_exporter'
    static_configs:
      - targets: ['localhost:9000']
```

`$ sudo systemctl restart prometheus`

### 2. Add prometheus-libvirt-exporter to Grafana
Add a new data source connection of type Prometheus to Grafana. Include `http://localhost:9090` as the connection URL.

### 3. Import the dashboard
Download or copy the dashboard in JSON: https://grafana.com/grafana/dashboards/15682-libvirt/

Import or paste it in Grafana

### 4. Run prometheus-libvirt-exporter
Run prometheus-libvirt-exporter to start capturing metrics (Grafana will visualize them automatically)

`$ cd prometheus-libvirt-exporter`

`$ ./prometheus-libvirt-exporter`
