#!/usr/bin/env bash
set -euo pipefail

unidad=mediflow-enlace.service
origen=http://127.0.0.1:8080
clave=/opt/mediflow/deployment/ec2/privado/clave-demo

case "${1:-abrir}" in
    cerrar)
        if systemctl is-active --quiet "$unidad"; then
            systemctl stop "$unidad"
        fi
        printf 'Enlace cerrado.\n'
        exit 0
        ;;
    abrir) ;;
    *) printf 'Uso: sudo mediflow-enlace [cerrar]\n' >&2; exit 2 ;;
esac

# Evitar abrir un túnel si el CRM local no está protegido o aún no responde.
sin_clave=$(curl -sS --max-time 4 -o /dev/null -w '%{http_code}' "$origen/crm" || true)
if [[ "$sin_clave" != 401 ]] || ! curl -fsS --max-time 5 -o /dev/null \
    -u "mediflow:$(cat "$clave")" "$origen/crm"; then
    printf 'El CRM debe responder y requerir su clave antes de abrir el enlace.\n' >&2
    exit 1
fi

if ! systemctl is-active --quiet "$unidad"; then
    if [[ ! -x /usr/local/bin/cloudflared ]]; then
        printf 'Falta instalar cloudflared en EC2.\n' >&2
        exit 1
    fi
    systemd-run --quiet --collect --unit="$unidad" --property=RuntimeMaxSec=2h \
        --property=DynamicUser=yes \
        /usr/local/bin/cloudflared tunnel --no-autoupdate --protocol http2 --url "$origen"
fi

for ((i = 0; i < 35; i++)); do
    invocacion=$(systemctl show -p InvocationID --value "$unidad")
    if [[ -n "$invocacion" && "$invocacion" != 00000000000000000000000000000000 ]]; then
        enlace=$(journalctl --quiet --no-pager -o cat "_SYSTEMD_INVOCATION_ID=$invocacion" |
            sed -nE 's@.*(https://[a-z0-9-]+\.trycloudflare\.com).*@\1@p' | tail -n 1)
        if [[ -n "$enlace" ]]; then
            estado=$(curl -sS --max-time 2 -o /dev/null -w '%{http_code}' "$enlace/crm" 2>/dev/null || true)
            if [[ "$estado" == 401 ]]; then
                printf 'Abre en el navegador: %s/crm\n' "$enlace"
                printf 'Usuario: mediflow · El enlace vence dentro de 2 horas desde su apertura.\n'
                exit 0
            fi
        fi
    fi
    systemctl is-active --quiet "$unidad" || break
    sleep 1
done

if systemctl is-active --quiet "$unidad"; then
    systemctl stop "$unidad"
fi
printf 'No se pudo verificar el acceso HTTPS. Revisa: sudo journalctl -u %s -n 25\n' "$unidad" >&2
exit 1
