#!/bin/sh
# Start the iperf3 server in the background, then run nginx in the foreground
# (nginx must be PID-foreground so the container stays alive / k8s sees it).
set -e

echo "[entrypoint] starting iperf3 server on :5201"
iperf3 -s -D -p 5201

echo "[entrypoint] starting nginx on :80"
exec nginx -g 'daemon off;'
