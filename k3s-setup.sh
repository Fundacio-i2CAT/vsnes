#!/bin/bash
set -e

NODE_TYPE="$1"  # master-init, master-join, worker
NODE_IP="$2"
JOIN_IP="$3"
TOKEN="satnet-ha-2026"

# Download k3s binary
sudo mkdir -p /opt/k3s /etc/rancher/k3s /var/lib/rancher/k3s
curl -sfL -o /opt/k3s/k3s https://github.com/k3s-io/k3s/releases/download/v1.31.4+k3s1/k3s
chmod +x /opt/k3s/k3s
ln -sf /opt/k3s/k3s /usr/local/bin/k3s

# Download kubectl symlink
ln -sf /opt/k3s/k3s /usr/local/bin/kubectl

case "$NODE_TYPE" in
  master-init)
    /opt/k3s/k3s server \
      --cluster-init \
      --token="$TOKEN" \
      --flannel-iface=eth0 \
      --tls-san="$NODE_IP" \
      --data-dir=/var/lib/rancher/k3s \
      --write-kubeconfig-mode=644 \
      &
    ;;
  master-join)
    /opt/k3s/k3s server \
      --server="https://$JOIN_IP:6443" \
      --token="$TOKEN" \
      --flannel-iface=eth0 \
      --tls-san="$NODE_IP" \
      --data-dir=/var/lib/rancher/k3s \
      --write-kubeconfig-mode=644 \
      &
    ;;
  worker)
    /opt/k3s/k3s agent \
      --server="https://$JOIN_IP:6443" \
      --token="$TOKEN" \
      --flannel-iface=eth0 \
      --data-dir=/var/lib/rancher/k3s \
      &
    ;;
esac

echo "k3s $NODE_TYPE started in background"
