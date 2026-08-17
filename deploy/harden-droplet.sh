#!/usr/bin/env bash
# =============================================================================
# KinJo — DigitalOcean droplet hardening (Ubuntu 22.04/24.04)
#
# Run ONCE on a fresh droplet, as root, BEFORE deploying:
#   ssh root@<droplet-ip>
#   bash harden-droplet.sh <deploy-username> "<ssh-public-key>"
#
# Idempotent: safe to re-run. Every step prints what it changed.
#
# IMPORTANT: this disables SSH password authentication and root SSH login. If
# the key you pass is wrong you will be locked out. The script verifies the key
# is installed and parseable before it touches sshd, and it never closes your
# current session — test a second SSH session before disconnecting.
# =============================================================================
set -euo pipefail

DEPLOY_USER="${1:-}"
SSH_PUBKEY="${2:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[$(date '+%H:%M:%S')] $*"; }

[[ $EUID -eq 0 ]] || die "run as root"
[[ -n "$DEPLOY_USER" ]] || die "usage: $0 <deploy-username> \"<ssh-public-key>\""
[[ -n "$SSH_PUBKEY" ]] || die "usage: $0 <deploy-username> \"<ssh-public-key>\""

# --- 1. Deploy user ----------------------------------------------------------
# The app must not run as root. This user owns /opt/kinjo and is in the docker
# group (which is root-equivalent on the host — that is inherent to Docker, and
# the reason this user is not also given passwordless sudo).
log "Ensuring deploy user '$DEPLOY_USER'..."
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
echo "$SSH_PUBKEY" > "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"

# Refuse to continue if the key is malformed — otherwise the sshd step below
# locks everyone out of the droplet permanently.
ssh-keygen -l -f "/home/$DEPLOY_USER/.ssh/authorized_keys" >/dev/null \
  || die "the supplied public key is not valid; aborting before sshd is changed"
log "  key fingerprint: $(ssh-keygen -l -f "/home/$DEPLOY_USER/.ssh/authorized_keys")"

# --- 2. Patching -------------------------------------------------------------
log "Applying security updates..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq unattended-upgrades fail2ban ufw ca-certificates curl gnupg

# Security patches apply automatically; a kernel update still needs the reboot
# that 50unattended-upgrades schedules below.
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat >/etc/apt/apt.conf.d/51kinjo-unattended <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
log "  unattended-upgrades on; reboots at 04:00 server time if a kernel needs it"

# --- 3. Firewall -------------------------------------------------------------
# Default deny inbound. Only SSH and the TLS edge are exposed. Postgres (5432)
# and Redis (6379) are deliberately absent: they are reachable only over the
# docker network, and docker-compose.prod.yml never publishes them.
log "Configuring ufw..."
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment 'SSH'
ufw allow 80/tcp   comment 'HTTP (ACME + redirect)'
ufw allow 443/tcp  comment 'HTTPS'
ufw --force enable
ufw status verbose

# NOTE: Docker publishes ports by writing DOCKER-USER iptables rules that bypass
# ufw entirely. A container that maps 0.0.0.0:5432 is reachable from the internet
# even with ufw denying it. That is why the compose files must never publish a
# datastore port — ufw alone will not save you. Verified below.

# --- 4. fail2ban -------------------------------------------------------------
log "Configuring fail2ban for sshd..."
cat >/etc/fail2ban/jail.d/kinjo.conf <<'EOF'
[sshd]
enabled  = true
port     = ssh
backend  = systemd
maxretry = 5
findtime = 10m
bantime  = 1h
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

# --- 5. SSH ------------------------------------------------------------------
log "Hardening sshd..."
cat >/etc/ssh/sshd_config.d/99-kinjo.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
# Validate before reloading. `sshd -t` on a bad config here is the difference
# between a reload that fails safe and a droplet you can only reach via console.
sshd -t || die "sshd config invalid — NOT reloading, your session is safe"
systemctl reload ssh 2>/dev/null || systemctl reload sshd
log "  password auth disabled, root login disabled"

# --- 6. Docker ---------------------------------------------------------------
if ! command -v docker >/dev/null; then
  log "Installing Docker Engine..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$DEPLOY_USER"
systemctl enable --now docker

# Cap container logs. The default json-file driver has NO limit, and a chatty
# container will fill the droplet's disk until Postgres cannot write and the app
# fails in ways that look nothing like "out of space".
cat >/etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "5" },
  "live-restore": true
}
EOF
systemctl restart docker

# --- 7. Swap -----------------------------------------------------------------
# A 2GB droplet running Postgres + Redis + 3 uvicorn workers + 2 celery
# processes will OOM-kill under a large export without swap.
if ! swapon --show | grep -q '/swapfile'; then
  log "Creating 2G swapfile..."
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 >/dev/null
  echo 'vm.swappiness=10' > /etc/sysctl.d/60-kinjo.conf
fi

# --- 8. Application directory ------------------------------------------------
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /opt/kinjo
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /var/backups/kinjo

# --- 9. Verification ---------------------------------------------------------
echo
echo "=================== VERIFICATION ==================="
printf 'ufw:            '; ufw status | head -1
printf 'fail2ban:       '; systemctl is-active fail2ban
printf 'docker:         '; systemctl is-active docker
printf 'swap:           '; swapon --show --noheadings | awk '{print $1, $3}' | tr '\n' ' '; echo
printf 'root ssh login: '; sshd -T 2>/dev/null | grep -i '^permitrootlogin' || echo '?'
printf 'password auth:  '; sshd -T 2>/dev/null | grep -i '^passwordauthentication' || echo '?'
echo
echo "Publicly-bound listeners (datastores must NOT appear here):"
ss -tlnp | awk 'NR==1 || /0\.0\.0\.0|\[::\]/'
echo "===================================================="
echo
echo "NEXT: open a SECOND ssh session as $DEPLOY_USER and confirm it works"
echo "      BEFORE closing this one:  ssh $DEPLOY_USER@<droplet-ip>"
