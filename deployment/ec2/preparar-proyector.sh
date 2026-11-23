#!/usr/bin/env bash
set -euo pipefail
export AWS_PAGER=''
region=us-east-1
repo=https://raw.githubusercontent.com/colapso05/MediFlow-AI/evaluacion-3
asistente="$HOME/mediflow-proyector.sh"
curl -fsSL "$repo/deployment/ec2/proyector.sh" -o "$asistente"

estado=$(aws ec2 describe-instances --region "$region" \
    --filters 'Name=tag:Name,Values=mediflow-ep3' 'Name=tag-key,Values=MediflowBucket' \
    'Name=instance-state-name,Values=pending,running,stopping,stopped' \
    --query 'Reservations[].Instances[].InstanceId' --output text)
if [[ -z "$estado" || "$estado" == None ]]; then
    if [[ "${1:-abrir}" == cerrar ]]; then
        printf 'No hay una instancia de MediFlow en este laboratorio.\n'
        exit 0
    fi
    printf 'El laboratorio se reinició. Restaurando MediFlow en EC2…\n'
    trabajo=$(mktemp -d)
    trap 'rm -r -- "$trabajo"' EXIT
    curl -fsSL https://codeload.github.com/colapso05/MediFlow-AI/zip/refs/heads/evaluacion-3 \
        -o "$trabajo/repositorio.zip"
    unzip -oq "$trabajo/repositorio.zip" -d "$trabajo"
    (
        cd "$trabajo/MediFlow-AI-evaluacion-3"
        zip -qr "$trabajo/mediflow-ep3.zip" .dockerignore Dockerfile requirements.txt \
            agente.py herramientas.py backend database deployment frontend/dist
        bash deployment/ec2/lanzar-desde-cloudshell.sh "$trabajo/mediflow-ep3.zip" proyector
    )
    bucket=$(aws ec2 describe-instances --region "$region" \
        --filters 'Name=tag:Name,Values=mediflow-ep3' 'Name=instance-state-name,Values=pending,running' \
        --query "sort_by(Reservations[].Instances[],&LaunchTime)[-1].Tags[?Key=='MediflowBucket']|[0].Value" \
        --output text)
    printf 'Esperando que arranquen los servicios. Una restauración puede tomar varios minutos.\n'
    for ((i = 0; i < 60; i++)); do
        if aws s3api head-object --region "$region" --bucket "$bucket" \
            --key evidencia/verificacion.json >/dev/null 2>&1; then
            break
        fi
        sleep 8
    done
fi

if [[ "${1:-abrir}" == abrir ]]; then
    if bash "$asistente" "$@"; then
        exit 0
    fi
    printf 'Reintentando el enlace una vez…\n'
fi
bash "$asistente" "$@"
