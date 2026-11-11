FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates iproute2 iptables iputils-ping wireguard-tools wireguard-go \
    && rm -rf /var/lib/apt/lists/*
COPY docker/wireguard/entrypoint.sh /usr/local/bin/wg-entrypoint
RUN chmod +x /usr/local/bin/wg-entrypoint
ENTRYPOINT ["/usr/local/bin/wg-entrypoint"]
