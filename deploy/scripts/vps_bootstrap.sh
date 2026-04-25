#!/usr/bin/env bash
#
# VPS bootstrap V5.9 — runs on a fresh Ubuntu 24.04 server (root over SSH).
# Idempotent — safe to run multiple times.
#
set -euo pipefail
IFS=$'\n\t'

echo "[1/6] System packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl git htop ufw fail2ban ca-certificates gnupg lsb-release \
  certbot python3-certbot-nginx nginx jq

echo "[2/6] Docker..."
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

echo "[3/6] Firewall (UFW)..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "[4/6] SSH hardening..."
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl reload ssh

echo "[5/6] fail2ban..."
systemctl enable --now fail2ban

echo "[6/6] Project dir..."
mkdir -p /opt/uba /var/log/uba /var/backups/uba
chmod 755 /opt/uba

cat > /etc/sysctl.d/99-uba.conf <<EOF
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 4096
vm.overcommit_memory = 1
fs.file-max = 200000
EOF
sysctl --system >/dev/null

echo "[ok] VPS bootstrap complete."
