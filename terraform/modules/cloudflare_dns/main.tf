terraform {
  required_providers {
    cloudflare = { source = "cloudflare/cloudflare" }
  }
}

resource "cloudflare_record" "managed" {
  for_each = { for r in var.records : r.name => r }

  zone_id = var.zone_id
  name    = each.value.name
  type    = each.value.type
  content = each.value.value
  ttl     = each.value.proxied ? 1 : 300
  proxied = each.value.proxied
  comment = "managed by terraform — UBA V5.9"
}

# Sensible default zone-wide settings
resource "cloudflare_zone_settings_override" "this" {
  count   = var.manage_zone_settings ? 1 : 0
  zone_id = var.zone_id

  settings {
    ssl                = "strict"
    always_use_https   = "on"
    min_tls_version    = "1.2"
    automatic_https_rewrites = "on"
    brotli             = "on"
    http3              = "on"
    websockets         = "on"
    security_level     = "medium"
  }
}
