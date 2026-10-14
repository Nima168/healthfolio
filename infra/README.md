# Healthfolio on AWS

Terraform for the AWS deployment (region `ap-south-1`).

```
Browser ── CloudFront ──┬── /*      → S3 (website files)
                        └── /api/*  → Lightsail container (API + extraction worker)
                                          ├── RDS PostgreSQL (private, via Lightsail VPC peering)
                                          ├── S3 (uploaded documents, encrypted)
                                          └── Groq API (AI extraction)
```

No secret is stored in Terraform or in this repository:
- AWS generates the **database password** and keeps it in Secrets Manager.
- You enter the **app's AWS access key**, the **Groq key**, and the **JWT secret** in the Lightsail console.

## One-time setup (already done)

- The Terraform state bucket `healthfolio-tfstate-<account>` (private, encrypted, versioned).
- Lightsail VPC peering with the default VPC: `aws lightsail peer-vpc`.

## 1. Create the infrastructure

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # set alert_email
terraform init
terraform plan -out healthfolio.tfplan          # review what will be created
terraform apply healthfolio.tfplan              # the database takes about 10 minutes
terraform output                                # addresses used below
```

## 2. Push the API image

```bash
cd backend
docker build -t healthfolio-api .
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.ap-south-1.amazonaws.com
docker tag healthfolio-api <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
```

## 3. Create the app's access key (AWS console)

1. Go to **IAM → Users → `healthfolio-app` → Security credentials → Create access key**.
2. Choose **Application running outside AWS**.
3. Keep the two values for step 5. The user can only read, write, and delete objects in the documents bucket.

## 4. Get the database password (AWS console)

1. Go to **Secrets Manager**, open the secret named in `terraform output db_password_secret_arn`, and choose **Retrieve secret value**.
2. URL-encode the password before putting it into `DATABASE_URL`, because special characters would break the URL:

```bash
python -c "import urllib.parse, getpass; print(urllib.parse.quote(getpass.getpass(), safe=''))"
```

## 5. Deploy the container (Lightsail console)

1. Go to **Lightsail → Containers → `healthfolio-api` → Deployments → Create your first deployment**.
2. Set the container:
   - Image: `<ecr_repository_url>:latest`
   - Port: `8000` (HTTP)
3. Add these environment variables:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | `postgresql://healthfolio:<encoded password>@<db_endpoint>:5432/healthfolio` |
| `JWT_SECRET` | output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ORIGINS` / `FRONTEND_BASE_URL` | `<site_url>` |
| `COOKIE_SECURE` | `true` |
| `LOG_LEVEL` | `INFO` |
| `EMAIL_BACKEND` | `disabled` |
| `STORAGE_BACKEND` | `s3` |
| `S3_BUCKET` | `<documents_bucket>` |
| `AWS_DEFAULT_REGION` | `ap-south-1` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | from step 3 |
| `EXTRACTION_ENABLED` | `true` |
| `GROQ_API_KEY` | your Groq key |

4. Set the public endpoint:
   - Container: `healthfolio-api`
   - Health check path: `/api/v1/health/live`
5. Save and deploy. Database migrations run when the container starts.

## 6. Publish the website

```bash
cd frontend
VITE_API_BASE_URL=/api/v1 npm run build
aws s3 sync dist s3://<site_bucket> --delete
aws cloudfront create-invalidation --distribution-id <cloudfront_distribution_id> --paths "/*"
```

Open `<site_url>`.

## Updating

- **API:**
  1. Repeat step 2.
  2. In Lightsail, choose **Modify your deployment**.
  3. Keep the settings and save. Lightsail pulls the new image.
- **Website:** repeat step 6.
- **Infrastructure:** edit the `.tf` files, then run `terraform plan` and `terraform apply`.

## Notes

- **Costs:**
  - Lightsail `micro`: about $10 a month.
  - RDS `db.t4g.micro`: free for 12 months on eligible accounts.
  - Secrets Manager: about $0.40 a month.
  - S3 and CloudFront: small at demo traffic.
  - A budget alert emails `alert_email` at 80% (forecast) and 100% of `budget_limit_usd`.
- **Deletion:**
  - The database has deletion protection and takes a final snapshot.
  - To remove everything, first set `deletion_protection = false` and apply.
  - Then run `terraform destroy`.
- **Password reset** is unavailable because no email service is configured (`EMAIL_BACKEND=disabled`).
