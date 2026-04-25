output "server_id" {
  value = hcloud_server.this.id
}

output "ipv4_address" {
  value = hcloud_server.this.ipv4_address
}

output "ipv6_address" {
  value = hcloud_server.this.ipv6_address
}

output "datacenter" {
  value = hcloud_server.this.datacenter
}

output "firewall_id" {
  value = hcloud_firewall.this.id
}

output "name" {
  value = hcloud_server.this.name
}
