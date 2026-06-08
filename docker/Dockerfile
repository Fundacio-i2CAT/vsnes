FROM debian:12

# Install SSH, network tools, sudo, curl, and k3s dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    iproute2 \
    iptables \
    iputils-ping \
    arp-scan \
    net-tools \
    sudo \
    procps \
    kmod \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create SSH run directory
RUN mkdir -p /run/sshd

# Create user 'debian' with password 'debian' and sudo privileges
RUN useradd -m -s /bin/bash debian && \
    echo 'debian:debian' | chpasswd && \
    echo 'debian ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Allow root login for SSH
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Download k3s binary
ARG K3S_VERSION=v1.31.4+k3s1
RUN mkdir -p /opt/k3s && \
    curl -sfL -o /opt/k3s/k3s "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s" && \
    chmod +x /opt/k3s/k3s && \
    ln -sf /opt/k3s/k3s /usr/local/bin/k3s && \
    ln -sf /opt/k3s/k3s /usr/local/bin/kubectl && \
    ln -sf /opt/k3s/k3s /usr/local/bin/ctr && \
    ln -sf /opt/k3s/k3s /usr/local/bin/crictl

# Fix /dev/kmsg for kubelet inside containers
RUN echo '#!/bin/sh\nexec cat /dev/null' > /usr/local/bin/kmsg-hack && chmod +x /usr/local/bin/kmsg-hack

# Copy scripts
COPY entrypoint.sh /entrypoint.sh
COPY k3s-join.sh /opt/k3s/k3s-join.sh
RUN chmod +x /entrypoint.sh /opt/k3s/k3s-join.sh

# Persistent data volume
VOLUME ["/var/lib/rancher/k3s"]

EXPOSE 22 6443

ENTRYPOINT ["/entrypoint.sh"]
