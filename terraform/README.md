# UBA Terraform — V5.9

Infrastructure as Code for the UBA "Usine Bombe Atomique" platform across three providers: **Hetzner Cloud** (compute), **Cloudflare** (DNS / TLS), and **Scaleway** (object-storage backups).

## Layout

```
terraform/
├── main.tf                  # provider config + module composition
├── variables.tf             # root inputs (also accepts TF_VAR_*)
├── outputs.tf
├── terraform.tfvars.example # copy to terraform.tfvars and fill in
├── cloud-init/
│   └── uba.yaml             # bootstrap (Docker, UFW, hardening)
└── modules/
    ├── hetzner_vps/         # server + firewall
    ├── cloudflare_dns/      # records + zone settings
    └── scaleway_backup/     # versioned bucket + lifecycle to Glacier
```

## Quick start

```bash
cp terraform.tfvars.example terraform.tfvars
# fill in tokens and IDs (terraform.tfvars is gitignored)

terraform init
terraform validate
terraform plan -out=uba.tfplan
terraform apply uba.tfplan
```

## Required credentials

| Provider     | Variable                | Where to get it                                     |
|--------------|-------------------------|-----------------------------------------------------|
| Hetzner      | `hcloud_token`          | Hetzner Cloud Console → Project → Security → API   |
| Cloudflare   | `cloudflare_api_token`  | Cloudflare → My Profile → API Tokens (Zone:DNS:Edit) |
| Cloudflare   | `cloudflare_zone_id`    | Zone overview → bottom-right                        |
| Scaleway     | `scaleway_access_key` / `_secret_key` / `_project_id` | Console IAM → API keys |

You can also export them as `TF_VAR_<name>` env vars (preferable in CI).

## Outputs

After `terraform apply`:

```bash
terraform output deployment_summary
# {
#   "backups": "uba-backups",
#   "domain": "uba.dendani.dz",
#   "environment": "production",
#   "vps": "203.0.113.42"
# }
```

## Dual-mode philosophy

Like the rest of UBA V5.9, Terraform here is **dual-mode**: every module supports running without secrets (validation only — `terraform validate` works in CI without any credentials). Real `apply` requires the tokens above.

## Backups

The Scaleway module creates a versioned bucket with:
- **Versioning ON** (immutable history)
- **TLS-only access** (S3 policy denies `aws:SecureTransport=false`)
- **Day 30** → Glacier transition (cheap)
- **Day 365** → expiration (configurable via `backup_retention_days`)

Hook into it from your backup cron with `s3cmd` / `aws-cli` pointed at the Scaleway endpoint:

```bash
aws --endpoint-url https://s3.fr-par.scw.cloud s3 cp /backups/uba-$(date +%F).sql.gz s3://uba-backups/
```

## Production state

The default backend is `local` for safety. **Switch to a remote backend** (Terraform Cloud, S3, etc.) before sharing state across operators:

```hcl
backend "s3" {
  bucket = "uba-tfstate"
  key    = "prod/terraform.tfstate"
  region = "fr-par"
  endpoint = "https://s3.fr-par.scw.cloud"
}
```

## Day-2 operations

| Task                          | Command                                                         |
|-------------------------------|-----------------------------------------------------------------|
| Bump VPS size                 | edit `vps_server_type`, `terraform apply`                       |
| Add a subdomain               | append to `records` in main.tf, `terraform apply`               |
| Rotate DNS only               | `terraform apply -target=module.cloudflare_dns`                  |
| Destroy staging               | `terraform workspace select staging && terraform destroy`        |
| Drift check (CI)              | `terraform plan -detailed-exitcode` (exit 2 = drift)             |

## Compliance

- All Hetzner servers carry the `managed_by=terraform` label (audit trail).
- Cloudflare zone enforces **TLS 1.2+, HTTPS-only, HTTP/3**.
- Scaleway bucket enforces **TLS-only access** + **encryption at rest** (default).
