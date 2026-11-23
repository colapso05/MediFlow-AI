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
python3 verificar.py | tee /var/log/mediflow-verificacion.json
aws s3 cp /var/log/mediflow-verificacion.json "s3://$bucket/evidencia/verificacion.json" --region "$region"
docker compose logs --no-color --tail 8 consumidor | tee /var/log/mediflow-eventos.log
aws s3 cp /var/log/mediflow-eventos.log "s3://$bucket/evidencia/eventos.log" --region "$region"
printf 'MEDIFLOW_EP3_VERIFICADO\n'
