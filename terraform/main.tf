/**
 * UBA infra V5.9 — multi-cloud (Hetzner + Cloudflare + Scaleway).
 * Pin every provider; never auto-upgrade in production.
 */

terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.48"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.45"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Pre-prod: local backend. Prod: switch to a remote S3/Terraform Cloud backend.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

provider "hcloud" {
  token = var.hcloud_token
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

provider "scaleway" {
  access_key      = var.scaleway_access_key
  secret_key      = var.scaleway_secret_key
  project_id      = var.scaleway_project_id
  region          = var.scaleway_region
  zone            = var.scaleway_zone
}

# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

module "hetzner_vps" {
  source = "./modules/hetzner_vps"

  name             = var.vps_name
  location         = var.vps_location
  server_type      = var.vps_server_type
  image            = var.vps_image
  ssh_keys         = var.vps_ssh_keys
  network_zone     = var.vps_network_zone
  enable_ipv4      = true
  enable_ipv6      = true
  firewall_allow_ports = [22, 80, 443]
  user_data        = file("${path.module}/cloud-init/uba.yaml")
  labels           = local.common_labels
}

module "cloudflare_dns" {
  source = "./modules/cloudflare_dns"

  zone_id      = var.cloudflare_zone_id
  domain       = var.domain
  vps_ipv4     = module.hetzner_vps.ipv4_address
  vps_ipv6     = module.hetzner_vps.ipv6_address
  enable_proxy = true
  records = [
    { name = var.domain,                  type = "A",     value = module.hetzner_vps.ipv4_address, proxied = true },
    { name = "api.${var.domain}",         type = "A",     value = module.hetzner_vps.ipv4_address, proxied = true },
    { name = "staging.${var.domain}",     type = "A",     value = module.hetzner_vps.ipv4_address, proxied = true },
    { name = "grafana.${var.domain}",     type = "A",     value = module.hetzner_vps.ipv4_address, proxied = true },
    { name = "www.${var.domain}",         type = "CNAME", value = var.domain,                       proxied = true },
  ]
}

module "scaleway_backup" {
  source = "./modules/scaleway_backup"

  bucket_name      = var.backup_bucket_name
  region           = var.scaleway_region
  retention_days   = var.backup_retention_days
  enable_versioning = true
  lifecycle_glacier_transition_days = 30
  lifecycle_expiration_days         = 365
  tags             = local.common_labels
}

# ---------------------------------------------------------------------------
# Local values (shared)
# ---------------------------------------------------------------------------

locals {
  common_labels = {
    project     = "uba"
    environment = var.environment
    managed_by  = "terraform"
    version     = "v5.9"
  }
}
