terraform {
  required_providers {
    hcloud = { source = "hetznercloud/hcloud" }
  }
}

resource "hcloud_server" "this" {
  name         = var.name
  location     = var.location
  server_type  = var.server_type
  image        = var.image
  ssh_keys     = var.ssh_keys
  user_data    = var.user_data
  labels       = var.labels

  public_net {
    ipv4_enabled = var.enable_ipv4
    ipv6_enabled = var.enable_ipv6
  }

  delete_protection  = var.enable_delete_protection
  rebuild_protection = var.enable_delete_protection
}

resource "hcloud_firewall" "this" {
  name   = "${var.name}-fw"
  labels = var.labels

  dynamic "rule" {
    for_each = var.firewall_allow_ports
    content {
      direction  = "in"
      protocol   = "tcp"
      port       = tostring(rule.value)
      source_ips = ["0.0.0.0/0", "::/0"]
    }
  }

  rule {
    direction       = "in"
    protocol        = "icmp"
    source_ips      = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_firewall_attachment" "this" {
  firewall_id = hcloud_firewall.this.id
  server_ids  = [hcloud_server.this.id]
}
