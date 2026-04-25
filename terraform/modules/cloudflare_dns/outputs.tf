output "record_names" {
  value = [for r in cloudflare_record.managed : r.hostname]
}

output "record_ids" {
  value = { for k, r in cloudflare_record.managed : k => r.id }
}
