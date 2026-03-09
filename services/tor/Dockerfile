FROM alpine:3.21

RUN apk add --no-cache tor

COPY services/tor/torrc /etc/tor/torrc

EXPOSE 9050

CMD ["tor", "-f", "/etc/tor/torrc"]
