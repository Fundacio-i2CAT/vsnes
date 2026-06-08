#!/usr/bin/env bash

echo "Starting installation..."

if [ "$EUID" -ne 0 ]; then
  echo "Run this script with sudo or as root."
  exit 1
fi

apt update -y

PACKAGES=(
  qemu qemu-system qemu-kvm libvirt-daemon-system libvirt-clients
  bridge-utils libguestfs-tools genisoimage virtinst libosinfo-bin
  virt-manager sshpass python3-pip
  iproute2 iptables procps
)

apt-get install -y --no-install-recommends "${PACKAGES[@]}"


echo "Enabling and starting libvirtd..."
systemctl enable --now libvirtd || true

# determine the actual non-root user who invoked sudo
ACTUAL_USER="${SUDO_USER:-$USER}"

# add current user to libvirt group if present
if id "$ACTUAL_USER" &>/dev/null; then
  usermod -aG libvirt "$ACTUAL_USER" || true
  echo "User '$ACTUAL_USER' added to libvirt group."
else
  echo "User '$ACTUAL_USER' not found — skipping usermod."
fi

# grant passwordless sudo for vsnes networking commands
SUDOERS_FILE="/etc/sudoers.d/vsnes"
IP_CMD="$(command -v ip)"
BRCTL_CMD="$(command -v brctl)"
IPTABLES_CMD="$(command -v iptables)"
TC_CMD="$(command -v tc)"
SYSCTL_CMD="$(command -v sysctl)"

cat > "$SUDOERS_FILE" << EOF
# Passwordless sudo for vsnes satellite emulator networking
$ACTUAL_USER ALL=(ALL) NOPASSWD: $IP_CMD, $BRCTL_CMD, $IPTABLES_CMD, $TC_CMD, $SYSCTL_CMD
EOF
chmod 440 "$SUDOERS_FILE"
if visudo -cf "$SUDOERS_FILE"; then
  echo "Passwordless sudo configured for '$ACTUAL_USER' in $SUDOERS_FILE."
else
  echo "ERROR: sudoers syntax error — removing $SUDOERS_FILE."
  rm "$SUDOERS_FILE"
  exit 1
fi


systemctl start libvirtd

# Python packages via pip3
PIP_PKGS=(
  pip setuptools wheel
  skyfield toml czml czml3 flask flask-cors julian astropy paramiko
  fastmcp sgp4 numpy httpx requests pydantic
)

pip3 install --upgrade pip setuptools wheel
pip3 install --upgrade "${PIP_PKGS[@]}"


echo "Starting default network..."
virsh --connect=qemu:///system net-start default || true

echo "Default network started."
echo "Setup complete!"
echo "1. Restart the session to apply changes."
echo "2. Download and install a VM for ubuntu debian and alpine"
echo "3. Install optional extra features"


#sudo nano /usr/local/lib/python3.10/dist-packages/czml/czml.py

#from pygeoif.geometry import as_shape as asShape
#from pygeoif.factories import shape as asShape

# cloned machines
# sudo rm /etc/machine-id
# sudo systemd-machine-id-setup
# 'virt-clone', '--original', clone_VM, '--name', name, '--auto-clone'
#virt-clone --original ubuntu18.04 --name SATELLITE-1 --auto-clone

