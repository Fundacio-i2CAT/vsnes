#!/bin/sh
ip link set dev brSATEMU down
brctl delbr brSATEMU
tc qdisc del dev virbr0.1 root handle 1: htb
ip link del link virbr0 name virbr0.1 type vlan id 1
tc qdisc del dev virbr0.2 root handle 2: htb
ip link del link virbr0 name virbr0.2 type vlan id 2
