# Dual-ISO USB (Live + netinst auto-install) — Design

**Status:** Approved for implementation (2026-06-26)
**Builds on:** the USB experience layer (`2026-06-26-usb-experience-layer-design.md`) and the
external `catalog.toml` it introduced.

---

## 1. Summary

`devboost usb` currently stages **one** ISO and binds Ventoy's default-image, `auto_install`, and
`injection` to it. That forces a single edition to serve two incompatible jobs: **Workstation Live**
is the right *manual* media (boot to desktop / `curl|bash` / graphical install) but installs from a
prebuilt squashfs and handles a custom-partition Kickstart unevenly; the **Everything-netinst** media
is the right *zero-touch* media for the snapshot-ready BTRFS auto-install but is a poor manual
experience.

This spec makes the stick carry **both**: Workstation Live as the default/manual media, and
Everything-netinst as the dedicated zero-touch `auto_install` media bound to `ks.cfg`. Both are always
staged, verified, and cached.

## 2. Decisions locked

| # | Question | Decision |
|---|----------|----------|
| 1 | Carry both ISOs? | **Yes, always** — stage Live + netinst (per the user). No skip flag. |
| 2 | Default boot / injection | **Live** — manual boot, `curl\|bash`, live desktop; dev-boost binary injected. |
| 3 | `auto_install` | **netinst** + `/Bootstrap/ks.cfg` — the unattended BTRFS layout install. |
| 4 | Injection scope | **Both** ISOs get the `devboost.tar.gz` injection (binary available on either boot path). |
| 5 | Catalog shape | `Os` gains an **optional** per-arch `autoinstall` media alongside `isos`. Absent ⇒ no zero-touch entry (still valid). |
| 6 | ventoy.json | **Generated in Python** (json.dumps) so the `auto_install` block can be omitted cleanly; supersedes the string-replace template + resource file. |

## 3. Catalog (`catalog.toml` + loader)

```toml
[fedora-44]
name = "Fedora 44 — Workstation (Live)"
distro = "fedora"
version = "44"
edition = "Workstation-Live"

[fedora-44.isos.x86_64]            # default/manual media (Live)
url = ".../Workstation/x86_64/iso/Fedora-Workstation-Live-44-1.7.x86_64.iso"
sha256 = "1620295f6a00c27c3208f0c00b8ece4eab1ec69b9002152d97488bf26a426ddf"
[fedora-44.isos.aarch64]
url = ".../Workstation/aarch64/iso/Fedora-Workstation-Live-44-1.7.aarch64.iso"
sha256 = "162ba3c552a2d241c7c63ec26777af0255ee1b5a135adc0be986ceed999933ef"

[fedora-44.autoinstall.x86_64]     # zero-touch Kickstart media (Everything-netinst)
url = ".../Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.7.iso"
sha256 = "bd285201494dd0ba09b54d05ac707de1401668b8512a573edb5922dcf9d7067e"
[fedora-44.autoinstall.aarch64]
url = ".../Everything/aarch64/iso/Fedora-Everything-netinst-aarch64-44-1.7.iso"
sha256 = "814801fbdda7492d9ee24dab8426c72b29f1635fe98d4ba675ede7e81189d57e"
```

- `Os` gains `autoinstall: dict[str, IsoSpec]` (default `{}`).
- The autoinstall `IsoSpec.id` is `"<os_id>-netinst"` (so its staged filename — `fedora-44-netinst.iso`
  — differs from the Live `fedora-44.iso`), and its `edition` is `"Everything-netinst"`.
- New loader accessor: `autoinstall_for(os_id, arch) -> IsoSpec | None` (None when the entry has no
  autoinstall media for that arch). The Pydantic `_OsRow` gains an optional `autoinstall: dict[str, _IsoRow] = {}`.
- Validation unchanged in spirit: each autoinstall sha256 is still 64-hex (same `_IsoRow`).

## 4. Config

`UsbBuildConfig` gains `autoinstall_iso: IsoSpec | None = None` (the resolved netinst spec for the
chosen OS+arch, or None).

## 5. Stages

- **`render_ventoy_json(*, default_iso: str, autoinstall_iso: str | None) -> str`** — builds the JSON in
  Python:
  - `control`: `VTOY_MENU_TIMEOUT=10`, `VTOY_DEFAULT_IMAGE=/ISO/<default_iso>`.
  - `injection`: the default ISO, **plus** the autoinstall ISO when present (both get `devboost.tar.gz`).
  - `auto_install`: present **only** when `autoinstall_iso` is set → `{image:/ISO/<autoinstall_iso>,
    template:/Bootstrap/ks.cfg}`.
  - Returns `json.dumps(..., indent=2)`. Replaces the `__DEVBOOST_ISO__` placeholder approach; the
    resource `ventoy/ventoy.json` is deleted (`ks.cfg` stays a resource).
- **`_stage_payload`** writes the generated `ventoy.json` using `cfg.iso.id + ".iso"` and (if
  `cfg.autoinstall_iso`) `cfg.autoinstall_iso.id + ".iso"`.
- **`boot_artifacts` / `update_stage`** stage the default ISO as today, and — when
  `cfg.autoinstall_iso is not None` — also `dl.fetch(...)` + copy the netinst ISO to
  `ISO/<autoinstall.id>.iso`, with a `reporter.step`. (Update mode: the netinst ISO is re-fetched only
  under `--refresh-iso`, same rule as the Live ISO.)

## 6. CLI / wizard

- Both paths resolve the autoinstall spec: `autoinstall_for(os_id, arch)` → `cfg.autoinstall_iso`.
  No new prompts (it's automatic; "always both").
- `_iso_note` (dry-run size) sums the Live + netinst sizes when both are uncached.
- `_summary_text` / `preview.render_plan` note the zero-touch media, e.g.
  `media: Workstation Live + netinst (zero-touch)`.

## 7. Error handling & testing

- `autoinstall_for` returns None (never raises) when the OS has no autoinstall media for the arch;
  `iso_for` is unchanged (raises on unpinned default arch).
- Tests (hermetic):
  - catalog: `autoinstall_for` hit (returns netinst spec, id `fedora-44-netinst`) / miss (None); the
    loader parses the `autoinstall` table; both netinst sha256s are 64-hex.
  - stages: `render_ventoy_json` with/without autoinstall (auto_install present/omitted; injection lists
    both when present); `boot_artifacts` stages **both** ISOs and writes a `ventoy.json` whose
    `auto_install` points at `fedora-44-netinst.iso` and whose default/injection point at `fedora-44.iso`.
  - cli/preview: summary + dry-run reflect both media.
- `mypy --strict` + ruff + pytest gates green.

## 8. Constitution alignment

Typed Python; pins remain in-repo validated `catalog.toml` (Principle III); all I/O via the
Executor/Downloader; sha256 stays the integrity guard for both ISOs. No new deps. No bash added.
