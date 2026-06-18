# nginx-iperf — serves a VSNES web page on :80 and runs an iperf3 server on :5201
FROM nginx:alpine

# iperf3 server for throughput testing from the ground station
RUN apk add --no-cache iperf3

COPY index.html /usr/share/nginx/html/index.html
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80 5201
ENTRYPOINT ["/entrypoint.sh"]
