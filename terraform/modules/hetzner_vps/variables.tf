variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "server_type" {
  type = string
}

variable "image" {
  type = string
}

variable "ssh_keys" {
  type = list(string)
}

variable "user_data" {
  type    = string
  default = ""
}

variable "network_zone" {
  type    = string
  default = "eu-central"
}

variable "enable_ipv4" {
  type    = bool
  default = true
}

variable "enable_ipv6" {
  type    = bool
  default = true
}

variable "enable_delete_protection" {
  type    = bool
  default = false
}

variable "firewall_allow_ports" {
  type        = list(number)
  description = "TCP ports to allow inbound on the firewall"
  default     = [22, 80, 443]
}

variable "labels" {
  type    = map(string)
  default = {}
}
