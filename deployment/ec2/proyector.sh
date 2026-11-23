#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_PAGER=''
region=us-east-1
accion=${1:-abrir}
case "$accion" in
    abrir|cerrar) ;;
    *) printf 'Uso: bash proyector.sh [cerrar]\n' >&2; exit 2 ;;
esac

consulta=$(aws ec2 describe-instances --region "$region" \
    --filters 'Name=tag:Name,Values=mediflow-ep3' 'Name=instance-state-name,Values=running,pending,stopped,stopping' \
    --query "sort_by(Reservations[].Instances[],&LaunchTime)[-1].[InstanceId,State.Name,Tags[?Key=='MediflowBucket']|[0].Value]" --output text)
read -r instancia estado bucket <<< "$consulta"
if [[ "$instancia" != i-* || "$bucket" != mediflow-ep3-* ]]; then
    printf 'No se encontró un despliegue con el enlace de proyector instalado.\n' >&2
    exit 1
fi

if [[ "$accion" == abrir && "$estado" == stopping ]]; then
    aws ec2 wait instance-stopped --region "$region" --instance-ids "$instancia"
    estado=stopped
fi
if [[ "$estado" == stopped && "$accion" == abrir ]]; then
    printf 'Iniciando MediFlow en AWS…\n'
    aws ec2 start-instances --region "$region" --instance-ids "$instancia" >/dev/null
fi
if [[ "$estado" == stopped && "$accion" == cerrar ]]; then
    printf 'EC2 ya está detenida.\n'
    exit 0
fi

trabajo=$(mktemp -d)
trap 'rm -f "$trabajo"/{privada.pem,publica.pem,solicitud,estado,clave.enc}; rmdir "$trabajo"' EXIT
id=$(openssl rand -hex 16)
control="s3://$bucket/proyector/$instancia"
if [[ "$accion" == abrir ]]; then
    openssl genpkey -quiet -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$trabajo/privada.pem"
    openssl pkey -in "$trabajo/privada.pem" -pubout -out "$trabajo/publica.pem"
fi
{
    printf '%s\n%s\n' "$id" "$accion"
    if [[ "$accion" == abrir ]]; then
        cat "$trabajo/publica.pem"
    fi
} > "$trabajo/solicitud"
aws s3 cp --only-show-errors --region "$region" "$trabajo/solicitud" "$control/solicitud"

printf 'Esperando la respuesta de EC2…\n'
for ((i = 0; i < 26; i++)); do
    if aws s3 cp --only-show-errors --region "$region" "$control/$id/estado" "$trabajo/estado" 2>/dev/null; then
        cat "$trabajo/estado"
        if [[ "$accion" == abrir ]]; then
            if ! grep -q '^Abre en el navegador:' "$trabajo/estado"; then
                exit 1
            fi
            aws s3 cp --only-show-errors --region "$region" "$control/$id/clave.enc" "$trabajo/clave.enc"
            printf 'Clave de la demo (antes de proyectar): '
            openssl pkeyutl -decrypt -inkey "$trabajo/privada.pem" \
                -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -in "$trabajo/clave.enc"
        else
            aws ec2 stop-instances --region "$region" --instance-ids "$instancia" >/dev/null
            printf 'Detención de EC2 solicitada.\n'
        fi
        exit 0
    fi
    sleep 5
done

printf 'La instancia no respondió. Revisa el estado de EC2 en N. Virginia.\n' >&2
exit 1
