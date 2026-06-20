#!/usr/bin/env bash
# modules/docker/install.sh — install Docker CE + compose plugin; enable service; add user to group.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME, USER.
# No prompts; idempotent (safe to re-run).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: add docker-ce repo if not already present (add-if-absent)
# ---------------------------------------------------------------------------
# Use a marker file under XDG_CONFIG_HOME (or ~/.config) as a per-user sentinel.
_docker_repo_marker="${XDG_CONFIG_HOME:-${HOME}/.config}/docker-ce.repo"
if [[ ! -f "${_docker_repo_marker}" ]]; then
  log_info "docker: adding Docker CE repository"
  sudo dnf config-manager --add-repo \
    https://download.docker.com/linux/fedora/docker-ce.repo
  touch "${_docker_repo_marker}"
  log_ok "docker: repository added"
else
  log_skip "docker: repository already configured"
fi

# ---------------------------------------------------------------------------
# Step 2: install docker-ce and docker-compose-plugin
# ---------------------------------------------------------------------------
log_info "docker: installing docker-ce and docker-compose-plugin"
dnf_install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# ---------------------------------------------------------------------------
# Step 3: enable and start docker service
# ---------------------------------------------------------------------------
log_info "docker: enabling docker service"
sudo systemctl enable --now docker

# ---------------------------------------------------------------------------
# Step 4: add $USER to the docker group only if not already a member
# ---------------------------------------------------------------------------
if getent group docker | grep -qw "${USER}"; then
  log_skip "docker: user '${USER}' already in docker group"
else
  log_info "docker: adding user '${USER}' to docker group"
  sudo usermod -aG docker "${USER}"
  log_warn "docker: re-login required for group membership to take effect in new sessions"
fi

log_ok "docker: setup complete"
