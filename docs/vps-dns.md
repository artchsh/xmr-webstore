# VPS and DNS Guide

## Recommended VPS size

For small single-seller stores:

- 2 vCPU
- 4 GB RAM
- 40 GB SSD
- Ubuntu 22.04/24.04 LTS

Lower settings can work for testing:

- 1 vCPU, 2 GB RAM, 25 GB SSD

## Network and firewall

Allow inbound:

- TCP `80`
- TCP `443`

Admin stays local-only by default (bound to `127.0.0.1`).

## DNS setup

At your domain provider:

- create `A` record for your shop host (example `shop.example.com`) -> VPS IPv4
- optional: create `AAAA` record -> VPS IPv6

DNS may need a few minutes to propagate.

## TLS certificates

Caddy automatically requests certificates from Let's Encrypt when:

- `SHOP_DOMAIN` is correct
- DNS points to your server
- ports `80` and `443` are reachable
- `ACME_EMAIL` is set
