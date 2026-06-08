#!/bin/bash

virsh list --all | egrep 'running' | awk '{print $2}' | xargs -t -I {} virsh shutdown {}
