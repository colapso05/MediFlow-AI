#!/usr/bin/env bash
set -euo pipefail

bucket="${1:?Bucket privado de despliegue}"
region="${2:-us-east-1}"
destino=/opt/mediflow
exec > >(tee -a /var/log/mediflow-arranque.log /dev/console) 2>&1

publicar_evidencia() {
    aws s3 cp /var/log/mediflow-arranque.log "s3://$bucket/evidencia/arranque.log" --region "$region" || true
}
trap publicar_evidencia EXIT

dnf install -y docker openssl unzip
systemctl enable --now docker
directorio_compose=/usr/local/lib/docker/cli-plugins
mkdir -p "$directorio_compose"
if ! docker compose version >/dev/null 2>&1; then
    curl --fail --silent --show-error --location --retry 3 \
        https://github.com/docker/compose/releases/download/v2.39.4/docker-compose-linux-x86_64 \
        -o "$directorio_compose/docker-compose"
    chmod 755 "$directorio_compose/docker-compose"
fi

mkdir -p "$destino"
aws s3 cp "s3://$bucket/mediflow-ep3.zip" "$destino/mediflow-ep3.zip" --region "$region"
unzip -oq "$destino/mediflow-ep3.zip" -d "$destino"
cd "$destino/deployment/ec2"
bash iniciar.sh
install -m 0755 demo-en-vivo.sh /usr/local/bin/mediflow-demo
if [[ "${3:-}" == proyector ]]; then
    curl --fail --silent --show-error --location --retry 3 \
        https://github.com/cloudflare/cloudflared/releases/download/2026.11.1/cloudflared-linux-amd64 \
        -o "$destino/cloudflared"
    printf '%s  %s\n' '97bb3b02d23a5980fc9c15a1a270e692da1923f103f920d5b16d4931d5ab55e7' \
        "$destino/cloudflared" | sha256sum --check --status
    install -m 0755 "$destino/cloudflared" /usr/local/bin/cloudflared
    install -m 0755 enlace-crm.sh /usr/local/bin/mediflow-enlace
    install -m 0755 control-proyector.sh /usr/local/bin/mediflow-control
    install -m 0644 mediflow-control.{service,timer} /etc/systemd/system/
    token=$(curl -fsS -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token)
    instancia=$(curl -fsS -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/instance-id)
    printf 'MEDIFLOW_BUCKET=%s\nMEDIFLOW_REGION=%s\nMEDIFLOW_INSTANCE=%s\n' "$bucket" "$region" "$instancia" \
        > /etc/mediflow-proyector
    systemctl daemon-reload
    systemctl enable --now mediflow-control.timer
fi
python3 verificar.py | tee /var/log/mediflow-verificacion.json
aws s3 cp /var/log/mediflow-verificacion.json "s3://$bucket/evidencia/verificacion.json" --region "$region"
docker compose logs --no-color --tail 8 consumidor | tee /var/log/mediflow-eventos.log
aws s3 cp /var/log/mediflow-eventos.log "s3://$bucket/evidencia/eventos.log" --region "$region"
printf 'MEDIFLOW_EP3_VERIFICADO\n'
