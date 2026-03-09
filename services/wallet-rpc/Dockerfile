FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl bzip2 torsocks \
    && rm -rf /var/lib/apt/lists/*

COPY services/wallet-rpc/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

EXPOSE 18083

ENTRYPOINT ["/entrypoint.sh"]
