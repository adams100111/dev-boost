# Contract: US1 repos + package manager (`rpmfusion`, `dnf-tune`, `fedora-third-party`, `flatpak`)

All four are logic modules (`module.toml` + `install.sh` sourcing `lib/log.sh`+`lib/pkg.sh`).
Exact commands from design §10c. `requires=[]`; `category="base"`.

## rpmfusion
- `verify`: `rpm -q rpmfusion-free-release rpmfusion-nonfree-release`
- `install.sh`: install both release rpms
  `https://mirrors.rpmfusion.org/{free,nonfree}/fedora/rpmfusion-{free,nonfree}-release-$(rpm -E %fedora).noarch.rpm`,
  then `sudo dnf upgrade --refresh -y`, then `sudo dnf install -y rpmfusion-\*-appstream-data`
  (AppStream post-step). Idempotent (verify guards; appstream install -y is safe re-run).
- MUST be ordered before any non-free consumer (later specs `requires` it).

## dnf-tune
- `verify`: `/etc/dnf/dnf.conf` contains `max_parallel_downloads=10` AND `fastestmirror=true`.
- `install.sh`: `write_kv_conf /etc/dnf/dnf.conf max_parallel_downloads 10` and
  `... fastestmirror true` (reconcile-not-duplicate). Runs early (speeds the bootstrap).

## fedora-third-party
- `verify`: `fedora-third-party query` reports enabled.
- `install.sh`: `sudo fedora-third-party enable`. (Per-tool vendor repos are NOT here —
  they live in each tool's own module per design §10c.)

## flatpak
- `verify`: `flatpak remotes` contains `flathub`.
- `install.sh`: ensure `flatpak` installed; `flatpak remote-add --if-not-exists flathub
  https://flathub.org/repo/flathub.flatpakrepo`; unfilter Fedora's filtered default if
  present (`flatpak remote-modify --no-filter flathub` / remove filter).

## Tests (`tests/repos.bats`) — stubbed dnf/rpm/flatpak/fedora-third-party/sudo
- rpmfusion: both release rpms install attempted + appstream + refresh; verify green after; re-run skipped.
- dnf-tune: dnf.conf has exactly one of each key=value; re-run does not duplicate; an existing different value is reconciled.
- fedora-third-party: enable attempted; verify maps to query state; re-run skipped when already enabled.
- flatpak: flathub added once; not re-added when present; filter removed.
- unsupported OS (no fedora key) → engine reports unsupported (failure), not skipped.
