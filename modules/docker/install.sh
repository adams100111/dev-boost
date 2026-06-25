#!/usr/bin/env bash
# modules/docker/install.sh — install Docker CE + compose plugin; enable service; add user to group.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME, USER.
# No prompts; idempotent (safe to re-run).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if [[ "${OS_FAMILY}" == "debian" ]]; then
  # ---------------------------------------------------------------------------
  # Debian/Ubuntu: add Docker's official apt repository (add-if-absent),
  # then install docker-ce and docker-compose-plugin.
  # DOCKER_APT_SOURCES_FILE / DOCKER_APT_KEYRINGS_DIR are overridable for tests.
  # ---------------------------------------------------------------------------
  _docker_list="${DOCKER_APT_SOURCES_FILE:-/etc/apt/sources.list.d/docker.list}"
  _docker_keyrings="${DOCKER_APT_KEYRINGS_DIR:-/etc/apt/keyrings}"
  _id="$(. "${OS_RELEASE_FILE:-/etc/os-release}"; echo "${ID}")"              # ubuntu | debian
  _codename="$(. "${OS_RELEASE_FILE:-/etc/os-release}"; echo "${VERSION_CODENAME}")"
  if [[ ! -f "${_docker_list}" ]]; then
    log_info "docker: adding Docker apt repository"
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d "${_docker_keyrings}"
    sudo curl -fsSL "https://download.docker.com/linux/${_id}/gpg" -o "${_docker_keyrings}/docker.asc"
    sudo chmod a+r "${_docker_keyrings}/docker.asc"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=${_docker_keyrings}/docker.asc] https://download.docker.com/linux/${_id} ${_codename} stable" \
      | sudo tee "${_docker_list}" >/dev/null
    sudo apt-get update -y
    log_ok "docker: repository added"
  else
    log_skip "docker: repository already configured"
  fi
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

else
  # ---------------------------------------------------------------------------
  # Fedora: add docker-ce repo if not already present (add-if-absent).
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
  # Install docker-ce and docker-compose-plugin
  # ---------------------------------------------------------------------------
  log_info "docker: installing docker-ce and docker-compose-plugin"
  dnf_install docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# ---------------------------------------------------------------------------
# Shared: enable and start docker service
# ---------------------------------------------------------------------------
log_info "docker: enabling docker service"
sudo systemctl enable --now docker

# ---------------------------------------------------------------------------
# Shared: add $USER to the docker group only if not already a member
# ---------------------------------------------------------------------------
if getent group docker | grep -qw "${USER}"; then
  log_skip "docker: user '${USER}' already in docker group"
else
  log_info "docker: adding user '${USER}' to docker group"
  sudo usermod -aG docker "${USER}"
  log_warn "docker: re-login required for group membership to take effect in new sessions"
fi

log_ok "docker: setup complete"
