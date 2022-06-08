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
ip link add link virbr0 name virbr0.3 type vlan id 3
ip link set dev virbr0.3 up
brctl addif brSATEMU virbr0.3
tc qdisc add dev virbr0.3 root handle 3: htb
ip link add link virbr0 name virbr0.4 type vlan id 4
ip link set dev virbr0.4 up
brctl addif brSATEMU virbr0.4
tc qdisc add dev virbr0.4 root handle 4: htb
tc class add dev virbr0.1 parent 1: classid 1:1 htb rate 100mbit
tc qdisc add dev virbr0.1 parent 1:1 handle 11: netem delay 0.000000ms
tc filter add dev virbr0.1 protocol ip parent 1:0 prio 1 u32 match ip src 10.0.0.1/32 flowid 1:1
tc class add dev virbr0.1 parent 1: classid 1:2 htb rate 100mbit
tc qdisc add dev virbr0.1 parent 1:2 handle 12: netem delay 13.193756ms
tc filter add dev virbr0.1 protocol ip parent 1:0 prio 1 u32 match ip src 10.0.0.2/32 flowid 1:2
tc class add dev virbr0.1 parent 1: classid 1:3 htb rate 100mbit
tc qdisc add dev virbr0.1 parent 1:3 handle 13: netem loss 100%
tc filter add dev virbr0.1 protocol ip parent 1:0 prio 1 u32 match ip src 10.0.0.3/32 flowid 1:3
tc class add dev virbr0.1 parent 1: classid 1:4 htb rate 100mbit
tc qdisc add dev virbr0.1 parent 1:4 handle 14: netem loss 100%
tc filter add dev virbr0.1 protocol ip parent 1:0 prio 1 u32 match ip src 10.0.0.4/32 flowid 1:4
tc class add dev virbr0.2 parent 2: classid 2:1 htb rate 100mbit
tc qdisc add dev virbr0.2 parent 2:1 handle 21: netem delay 13.193756ms
tc filter add dev virbr0.2 protocol ip parent 2:0 prio 1 u32 match ip src 10.0.0.1/32 flowid 2:1
tc class add dev virbr0.2 parent 2: classid 2:2 htb rate 100mbit
tc qdisc add dev virbr0.2 parent 2:2 handle 22: netem delay 0.000000ms
tc filter add dev virbr0.2 protocol ip parent 2:0 prio 1 u32 match ip src 10.0.0.2/32 flowid 2:2
tc class add dev virbr0.2 parent 2: classid 2:3 htb rate 100mbit
tc qdisc add dev virbr0.2 parent 2:3 handle 23: netem loss 100%
tc filter add dev virbr0.2 protocol ip parent 2:0 prio 1 u32 match ip src 10.0.0.3/32 flowid 2:3
tc class add dev virbr0.2 parent 2: classid 2:4 htb rate 100mbit
tc qdisc add dev virbr0.2 parent 2:4 handle 24: netem loss 100%
tc filter add dev virbr0.2 protocol ip parent 2:0 prio 1 u32 match ip src 10.0.0.4/32 flowid 2:4
tc class add dev virbr0.3 parent 3: classid 3:1 htb rate 100mbit
tc qdisc add dev virbr0.3 parent 3:1 handle 31: netem loss 100%
tc filter add dev virbr0.3 protocol ip parent 3:0 prio 1 u32 match ip src 10.0.0.1/32 flowid 3:1
tc class add dev virbr0.3 parent 3: classid 3:2 htb rate 100mbit
tc qdisc add dev virbr0.3 parent 3:2 handle 32: netem loss 100%
tc filter add dev virbr0.3 protocol ip parent 3:0 prio 1 u32 match ip src 10.0.0.2/32 flowid 3:2
tc class add dev virbr0.3 parent 3: classid 3:3 htb rate 100mbit
tc qdisc add dev virbr0.3 parent 3:3 handle 33: netem delay 0.000000ms
tc filter add dev virbr0.3 protocol ip parent 3:0 prio 1 u32 match ip src 10.0.0.3/32 flowid 3:3
tc class add dev virbr0.3 parent 3: classid 3:4 htb rate 100mbit
tc qdisc add dev virbr0.3 parent 3:4 handle 34: netem loss 100%
tc filter add dev virbr0.3 protocol ip parent 3:0 prio 1 u32 match ip src 10.0.0.4/32 flowid 3:4
tc class add dev virbr0.4 parent 4: classid 4:1 htb rate 100mbit
tc qdisc add dev virbr0.4 parent 4:1 handle 41: netem loss 100%
tc filter add dev virbr0.4 protocol ip parent 4:0 prio 1 u32 match ip src 10.0.0.1/32 flowid 4:1
tc class add dev virbr0.4 parent 4: classid 4:2 htb rate 100mbit
tc qdisc add dev virbr0.4 parent 4:2 handle 42: netem loss 100%
tc filter add dev virbr0.4 protocol ip parent 4:0 prio 1 u32 match ip src 10.0.0.2/32 flowid 4:2
tc class add dev virbr0.4 parent 4: classid 4:3 htb rate 100mbit
tc qdisc add dev virbr0.4 parent 4:3 handle 43: netem loss 100%
tc filter add dev virbr0.4 protocol ip parent 4:0 prio 1 u32 match ip src 10.0.0.3/32 flowid 4:3
tc class add dev virbr0.4 parent 4: classid 4:4 htb rate 100mbit
tc qdisc add dev virbr0.4 parent 4:4 handle 44: netem delay 0.000000ms
tc filter add dev virbr0.4 protocol ip parent 4:0 prio 1 u32 match ip src 10.0.0.4/32 flowid 4:4
