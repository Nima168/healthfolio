# Healthfolio on AWS

Terraform for the AWS deployment (region `ap-south-1`).

```
Browser ── HTTPS ── EC2 server (Elastic IP, https://<ip-with-dashes>.sslip.io)
                     ├── Caddy: HTTPS certificate (Let's Encrypt), website files, /api/* →
                     └── API + extraction worker (Docker, private network)
                            ├── RDS PostgreSQL (private; only the server may connect)
                            ├── S3 (uploaded documents, encrypted; website files are copied from S3)
                            └── Groq API (AI extraction)
```

CloudFront is not used yet: the AWS account must be verified first (an AWS Support case). Once verified, CloudFront can be put in front again so the server is no longer reachable from the internet directly.

- **Server:** accepts only HTTPS and HTTP (redirected to HTTPS) on Caddy. The app container is not exposed. There is no SSH; you reach the server with Session Manager.
- **AWS access:** the server's IAM role covers S3 (documents, website files), ECR, the database secret and the settings below. There are no access keys anywhere.
- **No secret is stored in Terraform or in this repository:**
  - AWS generates the database password and keeps it in Secrets Manager.
  - You put the Groq key and the JWT secret in SSM Parameter Store.
  - The server reads all three each time it starts.

## One-time setup (already done)

- The Terraform state bucket `healthfolio-tfstate-<account>` (private, encrypted, versioned).

## 1. Store the two secrets (AWS console, Systems Manager → Parameter Store)

Create two parameters. For each, set the tier to **Standard**, the type to **SecureString**, and keep the default KMS key:

| Name | Value |
|---|---|
| `/healthfolio/groq_api_key` | your Groq key |
| `/healthfolio/jwt_secret` | output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

The server retries every 30 seconds until both exist, so the order of steps 1 and 2 doesn't matter.

## 2. Create the infrastructure

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # set alert_email
terraform init
terraform plan -out healthfolio.tfplan          # review what will be created
terraform apply healthfolio.tfplan
terraform output                                # addresses used below
```

## 3. Push the API image

```bash
cd backend
docker build -t healthfolio-api .
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.ap-south-1.amazonaws.com
docker tag healthfolio-api <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
```

On its first start, the server installs Docker, pulls `latest`, and starts the app. Database migrations run inside the container. Caddy gets the HTTPS certificate on its first start, usually within a minute.

## 4. Publish the website

```bash
cd frontend
VITE_API_BASE_URL=/api/v1 npm run build
aws s3 sync dist s3://<site_bucket> --delete
aws ssm send-command --instance-ids <api_instance_id> --document-name AWS-RunShellScript   --parameters 'commands=["systemctl restart healthfolio-web"]'
```

The web service copies the files from S3 each time it starts.

Open `<site_url>`.

## Updating

- **API:**
  1. Repeat step 3.
  2. Restart the app on the server so it pulls the new image:
     ```bash
     aws ssm send-command --instance-ids <api_instance_id> --document-name AWS-RunShellScript \
       --parameters 'commands=["systemctl restart healthfolio"]'
     ```
- **Website:** repeat step 4.
- **Secrets:** change the parameter, then restart the app as above.
- **Infrastructure:** edit the `.tf` files, then run `terraform plan` and `terraform apply`.
- **Logs:**
  - In the console: **Systems Manager → Session Manager → Start session**, then run `journalctl -u healthfolio -f`.
  - Or run `docker logs healthfolio-api`.

## Notes

- **Costs:**
  - EC2 `t3.small`: about $15 a month.
  - Elastic IP: about $3.60 a month.
  - RDS `db.t4g.micro`: about $15 a month.
  - Secrets Manager: about $0.40 a month.
  - S3 and SSM: small at demo traffic.
  - On eligible accounts, the free tier covers EC2 and RDS.
  - A budget alert emails `alert_email` at 80% (forecast) and 100% of `budget_limit_usd`.
- **Deletion:**
  - The database has deletion protection and takes a final snapshot.
  - To remove everything, first set `deletion_protection = false` and apply.
  - Then run `terraform destroy`.
- **Password reset** is unavailable because no email service is configured (`EMAIL_BACKEND=disabled`).
