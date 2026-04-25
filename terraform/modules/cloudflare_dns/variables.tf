variable "zone_id" {
  type        = string
  description = "Cloudflare zone ID"
}

variable "domain" {
  type        = string
  description = "Apex domain"
}

variable "vps_ipv4" {
  type        = string
  description = "VPS public IPv4"
}

variable "vps_ipv6" {
  type        = string
  description = "VPS public IPv6"
  default     = ""
}

variable "enable_proxy" {
  type        = bool
  description = "Default: route through Cloudflare proxy"
  default     = true
}

variable "manage_zone_settings" {
  type        = bool
  description = "Apply opinionated zone-wide settings (TLS, HTTPS, HTTP3...)"
  default     = true
}

variable "records" {
  type = list(object({
    name    = string
    type    = string
    value   = string
    proxied = bool
  }))
  description = "DNS records to manage"
  default     = []
}
