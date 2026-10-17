# Healthfolio on AWS

Terraform for the AWS deployment (region `ap-south-1`). The live app is at https://65-0-63-32.sslip.io.

For the overall picture (architecture, document pipeline, testing, AI evaluation), see [docs/END_TO_END.md](../docs/END_TO_END.md).

![Healthfolio on AWS](../docs/architecture/healthfolio-architecture.png)

## What Terraform creates

| File | Resources |
|---|---|
| `versions.tf` | AWS provider; state in the S3 bucket `healthfolio-tfstate-<account>` |
| `compute.tf` | EC2 server (`t3.small`, Amazon Linux 2023, encrypted disk, IMDSv2), Elastic IP, firewall (ports 80 and 443 only), `site_url` setting |
| `server-setup.sh` | The server's first-boot script: Docker, and two systemd services (`healthfolio`: the app, `healthfolio-web`: Caddy) |
| `database.tf` | RDS PostgreSQL 16 (`db.t4g.micro`, private, encrypted, deletion protection, final snapshot), its firewall and subnet group |
| `storage.tf` | S3 buckets for documents and the website (private, encrypted, public access blocked) |
| `container.tf` | ECR repository `healthfolio-api` (scans on push, keeps the last 5 images) |
| `iam.tf` | The server's IAM role: S3, ECR pull, the database secret, `/healthfolio/*` settings, SES send, Session Manager |
| `email.tf` | SES sender identity, and the `email_backend` / `email_from` settings |
| `budget.tf` | Monthly cost budget with email alerts |
| `github_deploy.tf` | GitHub Actions sign-in (OIDC), the deploy-only role (push the API image, publish the website, run two fixed restart commands), and those two SSM commands |
| `variables.tf`, `outputs.tf` | Inputs (see step 2) and the addresses used below |

## Security

- **Server:** accepts only HTTPS, plus HTTP that redirects to HTTPS, on Caddy. The app container is not exposed. There is no SSH; you reach the server with Session Manager.
- **AWS access:** the server's IAM role covers S3 (documents, website files), ECR, the database secret, SES and the settings below. There are no access keys anywhere.
- **No secret is stored in Terraform, its state, the image, or this repository:**
  - AWS generates the database password and keeps it in Secrets Manager.
  - You put the Groq key and the JWT secret in SSM Parameter Store.
  - The server reads them each time it starts.
- **CloudFront is not used yet.** The AWS account must be verified first, through an AWS Support case; Lightsail containers and CodeBuild are also unavailable on this account for now. Once verified, CloudFront can be put in front so the server is no longer reachable from the internet directly.

## Before you start

- AWS CLI logged in to the account (`aws sts get-caller-identity`), Terraform 1.9+, Docker, Node.js 20+.
- The Terraform state bucket `healthfolio-tfstate-<account>` exists (private, encrypted, versioned). This is a one-time setup and is already done.
- **On Windows, Git Bash** rewrites arguments that start with `/` into Windows paths. For example, `/api/v1` becomes `C:/Program Files/Git/api/v1`, and `/healthfolio/...` breaks too. Prefix those commands with `MSYS_NO_PATHCONV=1`, or use PowerShell.

## 1. Store the two secrets (AWS console, Systems Manager → Parameter Store)

Create two parameters. For each, set the tier to **Standard**, the type to **SecureString**, and keep the default KMS key:

| Name | Value |
|---|---|
| `/healthfolio/groq_api_key` | your Groq key |
| `/healthfolio/jwt_secret` | output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

The server retries every 30 seconds until both exist, so steps 1 and 2 can be done in either order.

## 2. Create the infrastructure

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # not committed; fill in the values below
terraform init
terraform plan -out healthfolio.tfplan          # review what will be created
terraform apply healthfolio.tfplan
terraform output                                # addresses used below
```

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `alert_email` | yes | — | Receives the budget alerts |
| `sender_email` | yes | — | Sender of password-reset emails; AWS emails it a verification link |
| `email_backend` | no | `disabled` | `ses` sends reset emails; `disabled` turns reset off (the page says so) |
| `instance_type` | no | `t3.small` | Server size (2 GB is enough for OCR) |
| `db_instance_class` | no | `db.t4g.micro` | Database size |
| `budget_limit_usd` | no | `20` | Monthly budget for the alerts |

The database takes about 10 minutes to create.

## 3. Push the API image

```bash
cd backend
docker build -t healthfolio-api .
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.ap-south-1.amazonaws.com
docker tag healthfolio-api <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
```

On its first start, the server installs Docker, pulls `latest`, and starts the app; database migrations run inside the container. Caddy gets the HTTPS certificate on its first start, usually within a minute. The image's base comes from `public.ecr.aws`, so the build does not depend on Docker Hub.

## 4. Publish the website

```bash
cd frontend
MSYS_NO_PATHCONV=1 VITE_API_BASE_URL=/api/v1 npm run build
aws s3 sync dist s3://<site_bucket> --delete
aws ssm send-command --instance-ids <api_instance_id> --document-name AWS-RunShellScript \
  --parameters 'commands=["systemctl restart healthfolio-web"]'
```

In PowerShell, build with `$env:VITE_API_BASE_URL='/api/v1'; npm run build`.

Each time the web service starts, it copies the files from S3, including files whose size did not change.

On caching:
- Built files in `/assets/` have unique names and are cached for a year.
- A missing one returns 404, never the page.
- The page itself is sent with `Cache-Control: no-cache`, so browsers always get the newest version.

## 5. Verify

```bash
curl https://<site_host>/api/v1/health/ready      # {"status":"ready","checks":{"database":"ok"}}
```

Then open `<site_url>`, create an account, and upload a **synthetic** lab report.

AI accuracy has not been rigorously validated (planned for the future), so the deployed app is for demonstration with synthetic documents only.

## Deploying from GitHub (CI/CD)

`.github/workflows/deploy.yml` releases a merge to `main` (or **Actions → Deploy → Run workflow**) after the tests pass and the `production` environment is approved. One-time setup:

1. Apply `github_deploy.tf` (`terraform plan`, then `terraform apply`).
2. In GitHub, **Settings → Environments → New environment** `production`; add yourself as a required reviewer.
3. In **Settings → Secrets and variables → Actions → Variables**, add these from `terraform output` (none is a secret):

| Variable | Value |
|---|---|
| `AWS_REGION` | `ap-south-1` |
| `AWS_DEPLOY_ROLE_ARN` | `github_deploy_role_arn` |
| `ECR_REPOSITORY_URL` | `ecr_repository_url` |
| `SITE_BUCKET` | `site_bucket` |
| `API_INSTANCE_ID` | `api_instance_id` |
| `SITE_URL` | `site_url` |

Only runs of this repository's `production` environment can assume the role. The manual steps below still work.

## Updating

| Change | Steps |
|---|---|
| API code or website | Merge to `main` and approve the Deploy run (see above), or by hand: |
| API code (by hand) | Repeat step 3, then restart the app: `aws ssm send-command … --parameters 'commands=["systemctl restart healthfolio"]'`. It pulls `latest` and runs any new migrations. |
| Website | Repeat step 4. |
| A secret or setting | Change the parameter, or `terraform.tfvars` and apply, then restart the app. |
| Infrastructure | Edit the `.tf` files, then `terraform plan` and `terraform apply`. |
| `server-setup.sh` | Replaces the server on apply: about 5 minutes offline and a new HTTPS certificate. Let's Encrypt allows only a few repeats a week for the same address, so batch such changes. The Elastic IP and database stay. |
| Roll back the API | Point `latest` at an earlier image (ECR console, or `aws ecr batch-get-image` + `put-image` with that image's manifest), then restart the app. |

**Logs:** in the console, choose **Systems Manager → Session Manager → Start session**. Then run:
- `journalctl -u healthfolio -f` for the app;
- `journalctl -u healthfolio-web -f` for Caddy;
- `docker ps` to see the running containers.

## Email (SES)

- **Off by default:** password reset is off (`email_backend = "disabled"`). The API answers `PASSWORD_RESET_UNAVAILABLE`, and the page says reset is not available.
- **To turn it on:**
  1. After the first apply, click the verification link AWS emails to `sender_email`.
  2. Request production access: **SES console → Account dashboard → Request production access**. Until then, the account is in the SES *sandbox*, where mail reaches only verified addresses.
  3. Set `email_backend = "ses"`, apply, and restart the app.
- **Spam:** with a Gmail sender, some messages may land in spam. A sender on your own domain fixes that.

## Costs and deletion

- **Costs:**
  - EC2 `t3.small`: about $15 a month.
  - Elastic IP: about $3.60 a month.
  - RDS `db.t4g.micro`: about $15 a month.
  - Secrets Manager: about $0.40 a month.
  - S3, SSM, SES and ECR: small at demo traffic.
  - On eligible accounts, the free tier covers EC2 and RDS.
  - The budget alert emails `alert_email` at 80% (forecast) and 100% of `budget_limit_usd`.
- **Deletion:**
  - The database has deletion protection and takes a final snapshot.
  - To remove everything, first set `deletion_protection = false` and apply.
  - Then run `terraform destroy`.
  - The state bucket and the two SecureString parameters are not managed by Terraform; delete them by hand if no longer needed.
