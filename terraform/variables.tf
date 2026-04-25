/**
 * Root variables. Provide via terraform.tfvars or env vars TF_VAR_*.
 */

variable "environment" {
  type        = string
  description = "Deployment environment (production / staging / dev)"
  default     = "production"
  validation {
    condition     = contains(["production", "staging", "dev"], var.environment)
    error_message = "environment must be one of: production, staging, dev"
  }
}

# ---- Hetzner ---------------------------------------------------------------

variable "hcloud_token" {
  type        = string
  description = "Hetzner Cloud API token"
  sensitive   = true
}

variable "vps_name" {
  type    = string
  default = "uba-prod"
}

variable "vps_location" {
  type        = string
  description = "Hetzner location (fsn1, nbg1, hel1, ash, hil)"
  default     = "nbg1"
}

variable "vps_server_type" {
  type        = string
  description = "Hetzner server type (cpx21, cpx31, cpx41, ccx13, ccx23 ...)"
  default     = "cpx31"
}

variable "vps_image" {
  type    = string
  default = "ubuntu-24.04"
}

variable "vps_ssh_keys" {
  type        = list(string)
  description = "SSH public key names registered in Hetzner Cloud"
  default     = []
}

variable "vps_network_zone" {
  type    = string
  default = "eu-central"
}

# ---- Cloudflare ------------------------------------------------------------

variable "cloudflare_api_token" {
  type        = string
  sensitive   = true
  description = "Cloudflare API token (Zone:DNS edit)"
}

variable "cloudflare_zone_id" {
  type        = string
  description = "Cloudflare zone ID for the domain"
}

variable "domain" {
  type        = string
  description = "Apex domain (e.g. uba.dendani.dz)"
  default     = "uba.dendani.dz"
}

# ---- Scaleway --------------------------------------------------------------

variable "scaleway_access_key" {
  type      = string
  sensitive = true
}

variable "scaleway_secret_key" {
  type      = string
  sensitive = true
}

variable "scaleway_project_id" {
  type        = string
  description = "Scaleway project ID"
}

variable "scaleway_region" {
  type    = string
  default = "fr-par"
}

variable "scaleway_zone" {
  type    = string
  default = "fr-par-1"
}

variable "backup_bucket_name" {
  type    = string
  default = "uba-backups"
}

variable "backup_retention_days" {
  type    = number
  default = 90
}
