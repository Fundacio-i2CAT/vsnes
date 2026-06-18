# Deploying workloads to VSNES satellite k3s clusters

Example: `nginx-iperf` — an nginx web page on `:80` plus an iperf3 server on
`:5201`, exposed via NodePort and tested from the ground station (Ibi_ES).

## Files

| File | Purpose |
|------|---------|
| `nginx-iperf/Dockerfile`    | nginx:alpine + iperf3 + custom page |
| `nginx-iperf/entrypoint.sh` | starts iperf3 server, then nginx (foreground) |
| `nginx-iperf/index.html`    | the served web page |
| `nginx-iperf.yaml`          | Deployment + NodePort Service (30080 http, 30201 iperf) |

## The registry path (important)

- k3s nodes pull from **`172.27.12.200:5000`** over **HTTP**.
- `docker/registries.yaml` mirrors `docker.io → http://172.27.12.200:5000`.
- **Reference images via the `docker.io` mirror**, e.g. `docker.io/vsnes/nginx-iperf:latest`.
  Do **not** reference `172.27.12.200:5000/...` directly — containerd then uses
  HTTPS against the HTTP-only registry and fails with
  *"server gave HTTP response to HTTPS client"*.
- The host can't `docker push` to `172.27.12.200:5000` (not in its
  insecure-registries list). Bridge it with a one-off socat forwarder on
  `127.0.0.1:5001` (which *is* insecure), then push there. The registry stores
  by repo path, so pushing `localhost:5001/vsnes/nginx-iperf` and pulling
  `docker.io/vsnes/nginx-iperf` hit the same `vsnes/nginx-iperf` repository.

## Build → push → deploy → test

```bash
# 1. Build
docker build -t localhost:5001/vsnes/nginx-iperf:latest deploy/nginx-iperf/

# 2. Push (temporary forwarder: localhost:5001 -> registry 172.27.12.200:5000)
docker run -d --name reg-fwd --network vsnes_net -p 127.0.0.1:5001:5001 \
    alpine/socat tcp-listen:5001,fork,reuseaddr tcp-connect:172.27.12.200:5000
docker push localhost:5001/vsnes/nginx-iperf:latest
docker rm -f reg-fwd                       # forwarder no longer needed
curl -s http://172.27.12.200:5000/v2/vsnes/nginx-iperf/tags/list   # verify

# 3. Deploy to a satellite's cluster (e.g. SAT-1)
docker cp deploy/nginx-iperf.yaml SAT-1:/tmp/nginx-iperf.yaml
docker exec SAT-1 k3s kubectl apply -f /tmp/nginx-iperf.yaml
docker exec SAT-1 k3s kubectl rollout status deploy/nginx-iperf

# 4. Test from the ground station (Ibi_ES = 172.27.12.201)
docker exec Ibi_ES curl -s http://172.27.12.101:30080          # web page
docker exec Ibi_ES iperf3 -c 172.27.12.101 -p 30201 -t 5       # throughput
```

`172.27.12.101` is SAT-1's address; NodePorts are reachable on the node's own
`172.27.x` IP. In `uniq` mode each SAT is its own cluster, so deploy to (and hit
the NodePort of) whichever satellite you want.

## Notes

- iperf3 is not pre-installed on the GS; `apt-get install -y iperf3` (the GS has
  internet) gives you the client.
- Throughput reflects the **current link state**: if the sim isn't shaping the
  GS↔SAT path (in contact / no rate limit), you'll see near-bridge speed. Apply
  a channel/contact window to see netem delay + rate take effect.
