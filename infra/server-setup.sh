#!/bin/bash
# EC2 first boot (Terraform templatefile): install Docker and a service that starts the Healthfolio
# container. Secrets are read at each start from SSM Parameter Store and Secrets Manager; none are
# written into this script or Terraform.
set -euo pipefail

dnf install -y docker
systemctl enable --now docker

mkdir -p /opt/healthfolio
cat > /opt/healthfolio/start.sh <<'SCRIPT'
#!/bin/bash
# Pull the latest image, gather settings, (re)start the container.
set -euo pipefail
REGION="${region}"
IMAGE="${image}"

param() { aws ssm get-parameter --region "$REGION" --name "/${name}/$1" --with-decryption --query Parameter.Value --output text; }

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$${IMAGE%%/*}"
docker pull "$IMAGE"

DB_PASSWORD=$(aws secretsmanager get-secret-value --region "$REGION" --secret-id "${db_secret_arn}" \
  --query SecretString --output text \
  | python3 -c 'import json, sys, urllib.parse; print(urllib.parse.quote(json.load(sys.stdin)["password"], safe=""))')
SITE_URL=$(param site_url)

umask 077
cat > /opt/healthfolio/app.env <<ENV
APP_ENV=production
DATABASE_URL=postgresql://healthfolio:$DB_PASSWORD@${db_host}:5432/healthfolio?sslmode=require
JWT_SECRET=$(param jwt_secret)
GROQ_API_KEY=$(param groq_api_key)
CORS_ORIGINS=$SITE_URL
FRONTEND_BASE_URL=$SITE_URL
COOKIE_SECURE=true
LOG_LEVEL=INFO
EMAIL_BACKEND=disabled
STORAGE_BACKEND=s3
S3_BUCKET=${bucket}
AWS_DEFAULT_REGION=$REGION
EXTRACTION_ENABLED=true
ENV

docker rm -f healthfolio-api 2>/dev/null || true
exec docker run --name healthfolio-api --rm -p 8000:8000 --env-file /opt/healthfolio/app.env "$IMAGE"
SCRIPT
chmod 700 /opt/healthfolio/start.sh

cat > /etc/systemd/system/healthfolio.service <<'UNIT'
[Unit]
Description=Healthfolio API and extraction worker
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
ExecStart=/opt/healthfolio/start.sh
# Retries until the settings exist (e.g. before the two secrets are added) and after any crash.
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now healthfolio.service
