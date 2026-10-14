#!/bin/bash
# EC2 first boot (Terraform templatefile): install Docker and two services on a private Docker network:
# - healthfolio:     the API and extraction worker (not published on any host port);
# - healthfolio-web: Caddy, with HTTPS (Let's Encrypt), the website files, and /api/* to the app.
# Secrets are read at each start from SSM Parameter Store and Secrets Manager; none are written into
# this script or Terraform.
set -euo pipefail

dnf install -y docker
systemctl enable --now docker
docker network inspect healthfolio >/dev/null 2>&1 || docker network create healthfolio

mkdir -p /opt/healthfolio/site /opt/healthfolio/caddy-data /opt/healthfolio/caddy-config

# ---------- the app ----------
cat > /opt/healthfolio/start-app.sh <<'SCRIPT'
#!/bin/bash
# Pull the latest image, gather settings, (re)start the app container.
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
EMAIL_BACKEND=$(param email_backend)
EMAIL_FROM=$(param email_from)
STORAGE_BACKEND=s3
S3_BUCKET=${bucket}
AWS_DEFAULT_REGION=$REGION
EXTRACTION_ENABLED=true
ENV

docker rm -f healthfolio-api 2>/dev/null || true
exec docker run --name healthfolio-api --rm --network healthfolio --env-file /opt/healthfolio/app.env "$IMAGE"
SCRIPT

# ---------- the website and HTTPS ----------
cat > /opt/healthfolio/start-web.sh <<'SCRIPT'
#!/bin/bash
# Copy the latest website files from S3, then (re)start Caddy for the site's address.
set -euo pipefail
REGION="${region}"
SITE_URL=$(aws ssm get-parameter --region "$REGION" --name "/${name}/site_url" --query Parameter.Value --output text)
SITE_HOST="$${SITE_URL#https://}"

# --exact-timestamps: a rebuilt index.html often has the same size as the old one; copy it anyway.
aws s3 sync "s3://${site_bucket}" /opt/healthfolio/site --delete --exact-timestamps --region "$REGION"

cat > /opt/healthfolio/Caddyfile <<CADDY
$SITE_HOST {
	encode gzip
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		-Server
	}
	handle /api/* {
		reverse_proxy healthfolio-api:8000
	}
	# Built files have unique names: cache them for a year; a missing one is a real 404, never the page.
	handle /assets/* {
		root * /srv/site
		header Cache-Control "public, max-age=31536000, immutable"
		file_server
	}
	# Everything else is the app's page; browsers must re-check it so they never keep an old one.
	handle {
		root * /srv/site
		try_files {path} /index.html
		header Cache-Control "no-cache"
		file_server
	}
}
CADDY

docker rm -f healthfolio-web 2>/dev/null || true
exec docker run --name healthfolio-web --rm --network healthfolio -p 80:80 -p 443:443 \
  -v /opt/healthfolio/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v /opt/healthfolio/site:/srv/site:ro \
  -v /opt/healthfolio/caddy-data:/data \
  -v /opt/healthfolio/caddy-config:/config \
  public.ecr.aws/docker/library/caddy:2
SCRIPT
chmod 700 /opt/healthfolio/start-app.sh /opt/healthfolio/start-web.sh

# ---------- services: restart until settings exist, and after any crash ----------
for unit in healthfolio:start-app healthfolio-web:start-web; do
  service="$${unit%%:*}"
  script="$${unit##*:}"
  cat > "/etc/systemd/system/$service.service" <<UNIT
[Unit]
Description=Healthfolio ($service)
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
ExecStart=/opt/healthfolio/$script.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
done

systemctl daemon-reload
systemctl enable --now healthfolio.service healthfolio-web.service
