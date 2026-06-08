#!/bin/bash
set -e

# kubelet needs /dev/kmsg. In containers we symlink it to /dev/null
if [ ! -e /dev/kmsg ]; then
    ln -s /dev/null /dev/kmsg 2>/dev/null || true
fi

# Start SSH daemon in foreground
exec /usr/sbin/sshd -D
