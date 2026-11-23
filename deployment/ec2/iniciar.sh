#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p privado

if [[ ! -e .env ]]; then
    printf 'POSTGRES_PASSWORD=%s\nRABBITMQ_PASSWORD=%s\n' \
        "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" > .env
fi

if [[ ! -e privado/tls.key ]]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 60 \
        -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' \
        -keyout privado/tls.key -out privado/tls.crt
fi

if [[ ! -e privado/usuarios ]]; then
    printf '%s\n' "$(openssl rand -hex 16)" > privado/clave-demo
    printf 'mediflow:%s\n' "$(openssl passwd -apr1 -stdin < privado/clave-demo)" > privado/usuarios
    chmod 644 privado/usuarios
fi

docker compose up -d --build --wait --wait-timeout 180
