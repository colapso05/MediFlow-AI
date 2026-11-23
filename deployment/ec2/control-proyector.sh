#!/usr/bin/env bash
set -euo pipefail
umask 077
bucket="${1:?Falta el bucket de despliegue}"
region="${2:?Falta la región}"
instancia="${3:?Falta el identificador de la instancia}"
control="s3://$bucket/proyector/$instancia"
trabajo=$(mktemp -d)
trap 'rm -f "$trabajo"/{solicitud,publica.pem,estado,clave.enc}; rmdir "$trabajo"' EXIT
solicitud="$trabajo/solicitud"

if ! aws s3 cp --only-show-errors --region "$region" "$control/solicitud" "$solicitud" 2>/dev/null; then
    exit 0
fi

{
    read -r id
    read -r accion
    cat > "$trabajo/publica.pem"
} < "$solicitud"
[[ "$id" =~ ^[0-9a-f]{32}$ ]] || exit 1
case "$accion" in
    abrir|cerrar) ;;
    *) exit 1 ;;
esac

marca=/run/mediflow-proyector-ultimo
if [[ -e "$marca" ]] && [[ "$(cat "$marca")" == "$id" ]]; then
    exit 0
fi

# Cada solicitud vence a los tres minutos y no reabre un enlace tras reiniciar.
ahora=$(date +%s)
desde=$(aws s3api head-object --bucket "$bucket" --key "proyector/$instancia/solicitud" \
    --region "$region" --query LastModified --output text)
[[ $((ahora - $(date -d "$desde" +%s))) -lt 180 ]] || exit 0

if [[ "$accion" == abrir ]]; then
    if ! curl -fsS --max-time 4 -o /dev/null -u "mediflow:$(cat /opt/mediflow/deployment/ec2/privado/clave-demo)" \
        http://127.0.0.1:8080/api/health; then
        exit 0
    fi
    if ! openssl pkey -pubin -in "$trabajo/publica.pem" -noout; then
        exit 1
    fi
    if /usr/local/bin/mediflow-enlace > "$trabajo/estado" 2>&1; then
        if ! openssl pkeyutl -encrypt -pubin -inkey "$trabajo/publica.pem" \
            -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 \
            -in /opt/mediflow/deployment/ec2/privado/clave-demo \
            -out "$trabajo/clave.enc"; then
            /usr/local/bin/mediflow-enlace cerrar
            exit 1
        fi
        aws s3 cp --only-show-errors --region "$region" "$trabajo/clave.enc" "$control/$id/clave.enc"
    fi
else
    /usr/local/bin/mediflow-enlace cerrar > "$trabajo/estado" 2>&1
fi

aws s3 cp --only-show-errors --region "$region" "$trabajo/estado" "$control/$id/estado"
printf '%s\n' "$id" > "$marca"
