# dev-boost implementation audit — 2026-06-27

Five parallel subagents audited the complete implementation against the mission. **Verdict: the test
suite is green and the architecture is sound, but the end-to-end product does not work on real
hardware** — neither the USB-build path nor the on-machine `install full` path. The hermetic tests
(FakeExecutor / FakeDownloader / monkeypatched `resource_path`) never exercise the real integration
points, so none of these were caught.

Severity: **CRITICAL** = breaks the core promise / cannot work; **HIGH** = major gap/bug.

---

## A. The USB builder cannot build a USB

- **[CRITICAL]** Ventoy is **never downloaded or installed**. `stages.py:106/121` runs a bare
  `ventoy -i/-u`, but nothing fetches Ventoy and there is no `ventoy` binary on Fedora — the real CLI
  is `Ventoy2Disk.sh -i/-u`. `cache.py`'s docstring says it caches "ISO, binary, **Ventoy**" — the
  intent existed, the implementation doesn't. → first real run aborts "command not found".
  *Fix:* pin Ventoy in `catalog.toml`, download+verify+extract it, invoke `Ventoy2Disk.sh` by path.
- **[CRITICAL]** The **VTOY partition is never mounted** before writing. `boot_artifacts`/`update_stage`
  `mkdir` + `copyfile` into `vtoy_mount` (`/run/media/$USER/VTOY`) which is never programmatically
  mounted → multi-GB ISOs are silently written to the **local disk**, not the USB. No `umount`/`sync`
  after, either. (The read-only `probe.py` does mount correctly — the write path doesn't.)
  *Fix:* mount the VTOY partition after `ventoy -i`, write, `umount`/`sync` in a `finally`.
- **[CRITICAL]** The **frozen binary can't find the injection archive**. `stages.py:71`
  `resource_path("dist", …tar.gz)` resolves to `_MEIPASS/dist/…` in the frozen binary, but
  `build-bundle.sh` never `--add-data`s `dist/` → `VentoyError` fires on **every** `installer` run from
  the shipped binary. (Found independently by 3 of 5 agents.) *Fix:* bundle the tarball, or resolve it
  next to `sys.executable`.
- **[HIGH]** `vtoy_mount` uses `$USER`, which is `root` under `sudo` → `/run/media/root/VTOY` (wrong;
  udisks mounts under `$SUDO_USER`). `installer.py:115`.
- **[HIGH]** `devices.validate()` uses `lsblk -d` (no children) so a **mounted USB partition isn't
  detected** — the safety guard can miss a mounted target. `devices.py:17`.

## B. The zero-touch Kickstart path is broken

- **[CRITICAL]** **Ventoy injection lands the binary in the installer's overlay, not the installed
  system.** `ks.cfg`'s `%post` (chrooted) never copies `/opt/dev-boost/devboost` into `/mnt/sysimage`,
  so on first boot `ConditionPathExists=/opt/dev-boost/devboost` fails and the firstboot service
  **silently never runs** → a bare Fedora install, no provisioning. *Fix:* add `%post --nochroot` to
  copy the binary (and secrets) into the target.
- **[CRITICAL]** `ks.cfg:16` hardcodes `ignoredisk --only-use=sda` (comment says "auto-detected" — it
  isn't). NVMe (`nvme0n1`) and virtio (`vda`) targets — i.e. most real laptops/VMs — abort or wipe the
  wrong disk. The VM test passes only because it forces a SATA bus. *Fix:* `%pre` disk autodetect.
- **[HIGH]** `age-key.txt` is **never staged** and `DEVBOOST_SECRETS_KEY` is never set → secrets
  decryption fails even if A/B above were fixed. `secrets.age` also isn't in the injection archive.
  firstboot service + `_stage_payload` (`stages.py:75-77`).
- **[HIGH]** `bootloader --location=mbr` on a UEFI/ESP install — wrong/ignored. `ks.cfg:18`.

## C. `devboost install full` doesn't produce a working workstation

- **[CRITICAL]** `secrets._bootstrap_root()` falls back to **CWD (`"."`)** → on firstboot looks for
  `/secrets.age`, fails, and the **entire credential chain cascades** (chezmoi-repo, ssh-setup,
  obsidian-sync, pass-store). `secrets.py:19`.
- **[CRITICAL]** All `gui=True` modules are **headless-skipped** on an unattended firstboot (no
  display) — ghostty, vscode, all 7 flatpak apps, all 3 gnome modules, btrfs-assistant (~15 modules).
  No terminal, IDE, GUI apps, or GNOME config; no re-run mechanism. `osinfo.is_headless` + `plan.py`.
- **[CRITICAL]** Every **mise-managed tool fails verify-after-install** (~10 modules: node/pnpm/bun,
  android, claude-code, all LSPs) — mise's shim dir isn't on the subprocess `PATH` on a fresh boot, so
  `which()` fails right after install. `dev_stacks.py`, `claude_code.py`, `_lsp.py`.
- **[CRITICAL]** Docker installed but **daemon never enabled and user never added to `docker` group**
  → ddev, data-services, aspire-gc, nvidia-container all fail. `docker.py:17`.
- **[CRITICAL]** **Android cmdline-tools unzip → wrong path** (`…/cmdline-tools/cmdline-tools/…` but
  code expects `…/latest/…`) → sdkmanager never runs → React Native/Android fully broken.
  `dev_stacks.py:223`.
- **[HIGH]** `pkg.Dnf.install()` **discards the result** — dnf failures (GPG/network/missing pkg) are
  silent; `InstallError` is never raised. `pkg.py:27`.
- **[HIGH]** Dotfiles **not bundled** in the frozen binary (`build-bundle.sh` omits `dotfiles/`) → shell/
  terminal config never applied; `BashConfig` no-ops. `shell.py:91`.
- **[HIGH]** `runner.run_plan` has **no dependency-aware abort** — a failed `secrets` still runs all
  dependents → N cascade failures with no causal attribution. `runner.py:29`.
- **[HIGH]** `mkcert -install` called but **mkcert never installed** → ddev TLS dead. `ddev.py:33`.
- **[HIGH]** earlyoom config written to Debian path `/etc/default/earlyoom`; Fedora reads
  `/etc/sysconfig/earlyoom` → config ignored, `verify()` masks it. `system.py:157`.
- **[HIGH]** GPU auto-detect writes a marker but **nothing triggers the NVIDIA stack** (hardware-nvidia
  is opt-in, never auto-injected) — contradicts the "GPU auto-detected → driver applied" claim.
  `system.py:203`.
- **[HIGH]** `ChezmoiRepo` is a **silent no-op** when `DEVBOOST_DOTFILES_REPO` is unset. `base.py:138`.
- **[HIGH]** `restic-backup` timer written but **never enabled**. `system.py:187`.
- **[HIGH]** `doctor` checks `jq` (never used) but **not `curl`** (used by chezmoi/uv/nerd-fonts/
  android/claude-code). `doctor.py:16`.
- **[MEDIUM]** `gnome-manager-apps` calls flatpak but lacks `requires=(Flatpak,)` → may run before
  flatpak exists. `gnome.py:62`.
- **[MEDIUM]** `lazydocker` COPR is `atim/lazygit` (wrong repo name). `cli_tools.py:182`.
- **[MEDIUM]** Speculative version pins may not resolve (`pnpm@11.8.0`, `bun@1.3.14`, `postgres:18`).
- **[MEDIUM]** `expo` / `data-services` `install()` are explicit no-ops; verify checks template text only.

## D. Download & cache (the points you raised)

- **on-demand:** ✓ the build path is on-demand; **but** `--dry-run` fires real HTTP HEADs and creates
  the cache dir — not "touch nothing". `installer.py:_iso_note`.
- **[CRITICAL]** **no TTL/eviction** — multi-GB ISOs persist in `/tmp/devboost-usb` (tmpfs/RAM on
  Fedora) forever. `cache.py`.
- **[HIGH]** caching is **always-on, not opt-in** — no `--no-cache`, downloads always staged through
  cache then copied (2× disk). `installer.py:150`.
- **[HIGH]** `.part` file **leaked on network failure** (no `finally` cleanup) → disk-full feedback
  loop. `download.py:40`.
- **[MEDIUM]** silent download when server omits `Content-Length`; **[LOW]** no resume; cache claims
  "content-addressed" but is name-addressed.

---

## Root cause & path forward

**Root cause:** the tests are hermetic by design and mock every real-world seam, so "all green" never
implied "works on hardware". There is **no integration/VM test** that builds a real USB or runs a real
firstboot — exactly where every CRITICAL lives.

**Remediation order (blockers first):**
1. USB build: Ventoy bootstrap + correct CLI; mount/unmount lifecycle; frozen injection-archive
   delivery; sudo-mount path.
2. Kickstart: `%post --nochroot` binary+secrets copy; disk autodetect; `age-key.txt` staging; UEFI
   bootloader.
3. install: secrets bootstrap path; mise PATH; docker enable+group; headless/two-pass GUI; android
   unzip; dnf error propagation; dotfiles bundling.
4. cache: opt-in + `--no-cache`; TTL/eviction; `.part` cleanup; honest dry-run.
5. **Add a real VM integration test** (`vm-test.sh`) as a merge gate so these can't regress silently.
