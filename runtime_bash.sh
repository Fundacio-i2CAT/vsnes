#!/bin/sh
brctl addbr brSATEMU
ip link set dev brSATEMU up
ip link add link virbr0 name virbr0.1 type vlan id 1
ip link set dev virbr0.1 up
brctl addif brSATEMU virbr0.1
tc qdisc add dev virbr0.1 root handle 1: htb
ip link add link virbr0 name virbr0.2 type vlan id 2
ip link set dev virbr0.2 up
brctl addif brSATEMU virbr0.2
tc qdisc add dev virbr0.2 root handle 2: htb
tc class add dev virbr0.1 parent 1: classid 1:1 htb rate 100mbit
tc qdisc add dev virbr0.1 parent 1:1 handle 11: netem delay 0.000000ms
tc filter add dev virbr0.1 protocol ip parent 1:0 prio 1 u32 match ip src 10.0.0.1/32 flowid 1:1
tc class add dev virbr0.1 parent 1: classid 1:2 htb rate 100mbit
tc qdisc add dev virbr0.1 parent 1:2 handle 12: netem loss 100%
tc filter add dev virbr0.1 protocol ip parent 1:0 prio 1 u32 match ip src 10.0.0.2/32 flowid 1:2
tc class add dev virbr0.2 parent 2: classid 2:1 htb rate 100mbit
tc qdisc add dev virbr0.2 parent 2:1 handle 21: netem loss 100%
tc filter add dev virbr0.2 protocol ip parent 2:0 prio 1 u32 match ip src 10.0.0.1/32 flowid 2:1
tc class add dev virbr0.2 parent 2: classid 2:2 htb rate 100mbit
tc qdisc add dev virbr0.2 parent 2:2 handle 22: netem delay 0.000000ms
tc filter add dev virbr0.2 protocol ip parent 2:0 prio 1 u32 match ip src 10.0.0.2/32 flowid 2:2
