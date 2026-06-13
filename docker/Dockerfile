# syntax=docker/dockerfile:1

###############################################################################
# Stage 1 — compile olsrd (daemon + txtinfo plugin) from source
###############################################################################
FROM debian:12 AS olsrd-build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    bison \
    flex \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin/override with --build-arg OLSRD_REF=v0.9.8 if a tagged release is preferred
ARG OLSRD_REF=master
RUN git clone --depth 1 --branch "${OLSRD_REF}" https://github.com/OLSR/olsrd.git /src/olsrd \
    || git clone --depth 1 https://github.com/OLSR/olsrd.git /src/olsrd

WORKDIR /src/olsrd
# Build the daemon and stage a clean install tree under /out. We deliberately
# avoid `make libs` (builds every plugin — pud/GPS etc. pull in extra deps like
# libgps) and compile only the txtinfo plugin we need for neighbour inspection.
RUN make -j"$(nproc)" \
    && make install DESTDIR=/out \
    && make -j"$(nproc)" -C lib/txtinfo \
    && mkdir -p /out/usr/lib \
    && cp lib/txtinfo/olsrd_txtinfo.so.* /out/usr/lib/

###############################################################################
# Stage 2 — runtime image
#
# NOTE: the base apt install and the k3s download below are kept byte-identical
# to the original Dockerfile and ahead of all mesh additions, so Docker reuses
# the previously-built (cached) k3s layer instead of re-downloading the ~70MB
# binary on every change.
###############################################################################
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

# ---------------------------------------------------------------------------
# Mesh / routing additions (kept after k3s so the k3s layer stays cached)
# ---------------------------------------------------------------------------

# Babel routing daemon (from Debian)
RUN apt-get update && apt-get install -y --no-install-recommends \
    babeld \
    && rm -rf /var/lib/apt/lists/*

# olsrd compiled in stage 1 (binary -> /usr/sbin, plugin -> /usr/lib,
# default config -> /etc/olsrd). ldconfig refreshes the plugin search cache.
COPY --from=olsrd-build /out/ /
RUN ldconfig

# Minimal olsrd config + control helpers for the routing daemons and k3s roles
COPY olsrd.conf /etc/olsrd/olsrd.conf
COPY routing-ctl.sh /usr/local/bin/routing-ctl
COPY k3s-ctl.sh /usr/local/bin/k3s-ctl
RUN sed -i 's/\r$//' /usr/local/bin/routing-ctl /usr/local/bin/k3s-ctl && \
    chmod +x /usr/local/bin/routing-ctl /usr/local/bin/k3s-ctl

# k3s registry mirror config — points all public registries at vsnes-registry
RUN mkdir -p /etc/rancher/k3s
COPY registries.yaml /etc/rancher/k3s/registries.yaml

# Entrypoint (default: plain Debian + SSH — no mesh, no k3s)
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# Persistent data volume
VOLUME ["/var/lib/rancher/k3s"]

# 22 SSH, 6443 k3s API, 698 olsrd, 2006 olsrd txtinfo, 6696/udp babel
EXPOSE 22 6443 698 2006 6696/udp

ENTRYPOINT ["/entrypoint.sh"]
