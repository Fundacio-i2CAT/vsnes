#!/bin/bash
set -e

NODE_TYPE="$1"  # master-init, master-join, worker
NODE_IP="$2"    # this node's IP on the emulated network (e.g. 10.0.0.2)
JOIN_IP="$3"    # master IP (for master-join / worker)
TOKEN="satnet-ha-2026"

# Interface carrying the emulated network. VSNES puts the emulated channel
# on a VLAN sub-interface (e.g. eth0.1) — using plain eth0 would bypass the
# tc/netem channel emulation entirely.
IFACE="${VSNES_IFACE:-eth0.1}"

# VSNES NTP server (simulation time). The emulator host serves NTP on UDP
# 12345 reading simulation_time.txt. systemd-timesyncd cannot use custom
# ports, so chrony is used. Set NTP_SERVER="" to skip NTP configuration.
NTP_SERVER="${NTP_SERVER:-}"
NTP_PORT="${NTP_PORT:-12345}"

if [ -n "$NTP_SERVER" ]; then
  echo "Configuring chrony to sync with VSNES NTP server $NTP_SERVER:$NTP_PORT"
  if ! command -v chronyd >/dev/null; then
    sudo apt-get update -y && sudo apt-get install -y --no-install-recommends chrony
  fi
  sudo tee /etc/chrony/sources.d/vsnes.sources > /dev/null << EOF
server $NTP_SERVER port $NTP_PORT iburst minpoll 2 maxpoll 4
EOF
  # Allow large steps: simulation time can be far from (and faster than) real time
  sudo tee /etc/chrony/conf.d/vsnes.conf > /dev/null << EOF
makestep 1 -1
maxdistance 16
EOF
  sudo systemctl restart chrony || sudo service chrony restart || true
fi

# Download k3s binary
sudo mkdir -p /opt/k3s /etc/rancher/k3s /var/lib/rancher/k3s
sudo curl -sfL -o /opt/k3s/k3s https://github.com/k3s-io/k3s/releases/download/v1.31.4+k3s1/k3s
sudo chmod +x /opt/k3s/k3s
sudo ln -sf /opt/k3s/k3s /usr/local/bin/k3s

# Download kubectl symlink
sudo ln -sf /opt/k3s/k3s /usr/local/bin/kubectl

case "$NODE_TYPE" in
  master-init)
    sudo /opt/k3s/k3s server \
      --cluster-init \
      --token="$TOKEN" \
      --node-ip="$NODE_IP" \
      --flannel-iface="$IFACE" \
      --tls-san="$NODE_IP" \
      --data-dir=/var/lib/rancher/k3s \
      --write-kubeconfig-mode=644 \
      &
    ;;
  master-join)
    sudo /opt/k3s/k3s server \
      --server="https://$JOIN_IP:6443" \
      --token="$TOKEN" \
      --node-ip="$NODE_IP" \
      --flannel-iface="$IFACE" \
      --tls-san="$NODE_IP" \
      --data-dir=/var/lib/rancher/k3s \
      --write-kubeconfig-mode=644 \
      &
    ;;
  worker)
    sudo /opt/k3s/k3s agent \
      --server="https://$JOIN_IP:6443" \
      --token="$TOKEN" \
      --node-ip="$NODE_IP" \
      --flannel-iface="$IFACE" \
      --data-dir=/var/lib/rancher/k3s \
      &
    ;;
  *)
    echo "Usage: $0 {master-init|master-join|worker} NODE_IP [JOIN_IP]"
    echo "Env: VSNES_IFACE (default eth0.1), NTP_SERVER (empty = skip), NTP_PORT (default 12345)"
    exit 1
    ;;
esac

echo "k3s $NODE_TYPE started in background"
