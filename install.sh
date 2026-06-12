#!/usr/bin/env bash
#
# VSNES installer.
#
# Usage:
#   sudo ./install.sh             # base install (no QEMU/libvirt — external VMs / WSL friendly)
#   sudo ./install.sh --with-vm   # base install + QEMU/libvirt internal-VM support
#
# The base install is everything needed to run the emulator core:
# API/MCP/NTP/Web servers, contact-window computation, and tc/netem
# channel emulation on VLAN sub-interfaces (works inside WSL2).
# Internal VM support (cloning/managing VMs with libvirt) is optional
# and requires nested virtualization (not always available in WSL).

set -u

WITH_VM=0
for arg in "$@"; do
  case "$arg" in
    --with-vm) WITH_VM=1 ;;
    -h|--help)
      grep '^#' "$0" | head -n 14
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (use --with-vm or --help)"
      exit 1
      ;;
  esac
done

echo "Starting installation..."

if [ "$EUID" -ne 0 ]; then
  echo "Run this script with sudo or as root."
  exit 1
fi

# Detect WSL
IS_WSL=0
if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
  IS_WSL=1
  echo "WSL environment detected."
fi

# Detect whether systemd is the running init (WSL needs systemd=true in /etc/wsl.conf)
HAS_SYSTEMD=0
if [ -d /run/systemd/system ]; then
  HAS_SYSTEMD=1
fi

apt update -y

# --- Base packages: emulator core + networking ---
BASE_PACKAGES=(
  bridge-utils sshpass python3-pip
  iproute2 iptables procps
)

apt-get install -y --no-install-recommends "${BASE_PACKAGES[@]}"

# --- Optional packages: QEMU/libvirt internal-VM support ---
if [ "$WITH_VM" -eq 1 ]; then
  echo "Installing QEMU/libvirt internal-VM support..."
  VM_PACKAGES=(
    qemu-system qemu-kvm libvirt-daemon-system libvirt-clients
    libguestfs-tools genisoimage virtinst libosinfo-bin
    virt-manager
  )
  apt-get install -y --no-install-recommends "${VM_PACKAGES[@]}"

  if [ "$HAS_SYSTEMD" -eq 1 ]; then
    echo "Enabling and starting libvirtd..."
    systemctl enable --now libvirtd || true
  else
    echo "WARNING: systemd is not running — start libvirtd manually (e.g. 'sudo libvirtd -d')."
    if [ "$IS_WSL" -eq 1 ]; then
      echo "  Tip: enable systemd in WSL by adding to /etc/wsl.conf:"
      echo "    [boot]"
      echo "    systemd=true"
      echo "  then run 'wsl --shutdown' from Windows and reopen the distro."
    fi
  fi
else
  echo "Skipping QEMU/libvirt (internal VMs). Re-run with --with-vm to add them."
  echo "Without it, use external VMs / containers (is_external_vm = 1 in the config)."
fi

# determine the actual non-root user who invoked sudo
ACTUAL_USER="${SUDO_USER:-$USER}"

# add current user to libvirt group if libvirt was installed
if [ "$WITH_VM" -eq 1 ] && id "$ACTUAL_USER" &>/dev/null && getent group libvirt >/dev/null; then
  usermod -aG libvirt "$ACTUAL_USER" || true
  echo "User '$ACTUAL_USER' added to libvirt group."
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

# Python packages via pip3
PIP_PKGS=(
  pip setuptools wheel
  skyfield toml czml czml3 flask flask-cors julian astropy paramiko
  fastmcp sgp4 numpy httpx requests pydantic
)

# Newer Debian/Ubuntu (incl. WSL default distros) mark the system Python
# as externally managed; --break-system-packages keeps the old behaviour.
PIP_FLAGS=""
if pip3 install --help 2>/dev/null | grep -q break-system-packages; then
  PIP_FLAGS="--break-system-packages"
fi

pip3 install --upgrade $PIP_FLAGS pip setuptools wheel

# Some apt-provided packages (e.g. blinker 1.4 on Ubuntu 22.04) were installed
# with distutils and pip cannot uninstall them to upgrade. --ignore-installed
# makes pip install the new version on top instead of failing.
if ! pip3 install --upgrade $PIP_FLAGS "${PIP_PKGS[@]}"; then
  echo "pip upgrade hit a distutils-installed package — retrying with --ignore-installed..."
  if ! pip3 install --upgrade $PIP_FLAGS --ignore-installed "${PIP_PKGS[@]}"; then
    echo "ERROR: Python package installation failed."
    exit 1
  fi
fi

if [ "$WITH_VM" -eq 1 ] && command -v virsh >/dev/null; then
  echo "Starting default libvirt network..."
  virsh --connect=qemu:///system net-start default || true
  echo "Default network started."
fi

echo "Setup complete!"
echo "1. Restart the session to apply changes."
if [ "$WITH_VM" -eq 1 ]; then
  echo "2. Download and install a VM for ubuntu, debian and alpine."
  echo "3. Install optional extra features (extra_install.sh)."
else
  echo "2. Internal VMs are disabled. Use external VMs/containers (is_external_vm = 1),"
  echo "   or re-run with --with-vm to install QEMU/libvirt."
fi
if [ "$IS_WSL" -eq 1 ]; then
  echo "WSL notes:"
  echo " - Channel emulation (tc/netem) works inside WSL2."
  echo " - To reach the web UI from Windows, use localhost (WSL2 forwards ports automatically)."
  echo " - For internal VMs, nested virtualization must be enabled for your WSL2 VM."
fi
