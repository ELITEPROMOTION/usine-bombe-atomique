output "vps_id" {
  value       = module.hetzner_vps.server_id
  description = "Hetzner server ID"
}

output "vps_ipv4" {
  value       = module.hetzner_vps.ipv4_address
  description = "VPS public IPv4"
}

output "vps_ipv6" {
  value       = module.hetzner_vps.ipv6_address
  description = "VPS public IPv6"
}

output "domain" {
  value       = var.domain
  description = "Apex domain"
}

output "dns_records" {
  value       = module.cloudflare_dns.record_names
  description = "List of Cloudflare DNS records under management"
}

output "backup_bucket" {
  value       = module.scaleway_backup.bucket_name
  description = "Scaleway S3 bucket for backups"
}

output "backup_bucket_endpoint" {
  value       = module.scaleway_backup.endpoint
  description = "Scaleway S3 endpoint URL"
}

output "deployment_summary" {
  value = {
    environment = var.environment
    vps         = module.hetzner_vps.ipv4_address
    domain      = var.domain
    backups     = module.scaleway_backup.bucket_name
  }
  description = "One-shot summary of provisioned infra"
}
