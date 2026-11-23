#!/usr/bin/env bash
set -euo pipefail

paquete="${1:-$HOME/mediflow-ep3.zip}"
region="${AWS_REGION:-us-east-1}"
perfil="${MEDIFLOW_INSTANCE_PROFILE:-myS3Role}"
nombre="mediflow-ep3"
modo="${2:-privado}"
case "$modo" in privado|proyector) ;; *) printf 'Usa privado o proyector.\n' >&2; exit 2 ;; esac
export AWS_PAGER=''

if [[ ! -r "$paquete" ]]; then
    printf 'Falta el paquete de despliegue: %s\n' "$paquete" >&2
    exit 1
fi

aws iam get-instance-profile --instance-profile-name "$perfil" >/dev/null
vpc=$(aws ec2 describe-vpcs --region "$region" --filters Name=is-default,Values=true \
    --query 'Vpcs[0].VpcId' --output text)
subred=$(aws ec2 describe-subnets --region "$region" \
    --filters "Name=vpc-id,Values=$vpc" Name=default-for-az,Values=true \
    --query 'Subnets[?MapPublicIpOnLaunch==`true`]|[0].SubnetId' --output text)
ami=$(aws ssm get-parameter --region "$region" \
    --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query Parameter.Value --output text)

cuenta=$(aws sts get-caller-identity --query Account --output text)
revision=$(sha256sum "$paquete" | cut -c1-12)
bucket="mediflow-ep3-$cuenta-$revision"
if ! aws s3api head-bucket --region "$region" --bucket "$bucket" 2>/dev/null; then
    if [[ "$region" == us-east-1 ]]; then
        aws s3api create-bucket --region "$region" --bucket "$bucket" >/dev/null
    else
        aws s3api create-bucket --region "$region" --bucket "$bucket" \
            --create-bucket-configuration "LocationConstraint=$region" >/dev/null
    fi
fi
aws s3api put-public-access-block --region "$region" --bucket "$bucket" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3 cp "$paquete" "s3://$bucket/mediflow-ep3.zip" --region "$region"

grupo=$(aws ec2 describe-security-groups --region "$region" \
    --filters "Name=vpc-id,Values=$vpc" "Name=group-name,Values=$nombre" \
    --query 'SecurityGroups[0].GroupId' --output text)
if [[ "$grupo" == None ]]; then
    grupo=$(aws ec2 create-security-group --region "$region" --vpc-id "$vpc" \
        --group-name "$nombre" --description 'MediFlow EP3 - salida para dependencias, sin ingreso publico' \
        --query GroupId --output text)
fi

bootstrap=$(mktemp)
trap 'rm -f "$bootstrap"' EXIT
{
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'aws s3 cp s3://%s/arranque-aws.sh /tmp/mediflow-arranque.sh --region %s\n' "$bucket" "$region"
    printf 'bash /tmp/mediflow-arranque.sh %s %s %s\n' "$bucket" "$region" "$modo"
} > "$bootstrap"
unzip -p "$paquete" deployment/ec2/arranque-aws.sh | \
    aws s3 cp - "s3://$bucket/arranque-aws.sh" --region "$region"

instancia=$(aws ec2 run-instances --region "$region" --image-id "$ami" --count 1 \
    --instance-type t3.small --subnet-id "$subred" --security-group-ids "$grupo" \
    --iam-instance-profile "Name=$perfil" --key-name vockey --user-data "file://$bootstrap" \
    --metadata-options HttpTokens=required --credit-specification CpuCredits=standard \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$nombre},{Key=Revision,Value=$revision},{Key=MediflowBucket,Value=$bucket}]" \
    --client-token "mediflow-$revision-$modo" --query 'Instances[0].InstanceId' --output text)
printf 'Instancia: %s\nEvidencias: s3://%s/evidencia/\n' "$instancia" "$bucket"
