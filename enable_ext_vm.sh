#!/bin/bash

sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -I FORWARD -i ens18 -o virbr0 -s 172.27.12.0/24 -d 172.27.12.0/24 -j ACCEPT

sudo ip link add vsnes_ext type vxlan id 10 dev ens18 remote 172.27.12.16 dstport 4789
sudo ip link add vsnes_ext type vxlan id 10 dev ens18 group 239.1.1.1 dstport 4789
sudo ip link set vsnes_ext master virbr0
sudo ip link set vsnes_ext up
