# Dual-ISO USB (Live + netinst auto-install) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stage both a Workstation Live ISO (default/manual + injection) and an Everything-netinst ISO (zero-touch `auto_install` + `ks.cfg`) on the USB, driven by an optional per-arch `autoinstall` media in the catalog.

**Architecture:** `catalog.toml` gains an optional `[<os>.autoinstall.<arch>]` table; the loader exposes `autoinstall_for(os_id, arch) -> IsoSpec | None`. `UsbBuildConfig` carries `autoinstall_iso`. `stages.py` generates `ventoy.json` in Python (default→Live, `auto_install`→netinst, injection→both) and stages both ISOs. CLI/wizard resolve the autoinstall spec automatically (always both).

**Tech Stack:** Python 3.12, Pydantic v2, stdlib `json`/`tomllib`. Gates: `pytest`, `mypy --strict`, `ruff` (LL100), run from `engine/`.

## Global Constraints

- All I/O via the injected `Executor`/`Downloader`; sha256 stays the integrity guard for **both** ISOs.
- Pins live in `catalog.toml` (validated at load); checksums are real, from Fedora's signed CHECKSUM (already in hand — see Task 1).
- The wipe gate in `boot_artifacts` and "`update_stage` never `ventoy -i`" invariants are unchanged.
- `from __future__ import annotations`; `mypy --strict` + ruff + pytest green at every task.
- No Claude/Anthropic attribution in commits.
- `__version__` is `"0.1.0"`.

---

### Task 1: Catalog — optional `autoinstall` media

**Files:**
- Modify: `catalog.toml` (repo root)
- Modify: `engine/src/devboost/usb/catalog.py`
- Test: `engine/tests/usb/test_catalog.py`

**Interfaces:**
- Produces: `Os.autoinstall: dict[str, IsoSpec]` (default empty); `autoinstall_for(os_id: str, arch: str) -> IsoSpec | None`.
- The autoinstall `IsoSpec` has `id = f"{os_id}-netinst"`, `edition = "netinst"`.

- [ ] **Step 1: Add the autoinstall tables to `catalog.toml`.** Append under the existing `[fedora-44]` entry (after the `isos` tables):

```toml
[fedora-44.autoinstall.x86_64]
url = "https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.7.iso"
sha256 = "bd285201494dd0ba09b54d05ac707de1401668b8512a573edb5922dcf9d7067e"

[fedora-44.autoinstall.aarch64]
url = "https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/aarch64/iso/Fedora-Everything-netinst-aarch64-44-1.7.iso"
sha256 = "814801fbdda7492d9ee24dab8426c72b29f1635fe98d4ba675ede7e81189d57e"
```

- [ ] **Step 2: Write the failing tests** — add to `engine/tests/usb/test_catalog.py`:

```python
def test_autoinstall_for_returns_netinst_spec() -> None:
    from devboost.usb.catalog import autoinstall_for

    spec = autoinstall_for("fedora-44", "x86_64")
    assert spec is not None
    assert spec.id == "fedora-44-netinst"
    assert "netinst" in spec.url and len(spec.sha256) == 64


def test_autoinstall_for_aarch64_present() -> None:
    from devboost.usb.catalog import autoinstall_for

    assert autoinstall_for("fedora-44", "aarch64") is not None


def test_autoinstall_for_missing_returns_none() -> None:
    from devboost.usb.catalog import autoinstall_for

    assert autoinstall_for("fedora-44", "riscv64") is None  # arch not pinned
    assert autoinstall_for("ubuntu-99", "x86_64") is None   # unknown os


def test_load_catalog_parses_optional_autoinstall(tmp_path: Path) -> None:
    toml = _VALID + (
        "\n[fedora-99.autoinstall.x86_64]\n"
        'url = "https://x/f99-netinst.iso"\n'
        f'sha256 = "{"b" * 64}"\n'
    )
    p = tmp_path / "catalog.toml"
    p.write_text(toml, encoding="utf-8")
    cat = load_catalog(p)
    ai = cat["fedora-99"].autoinstall["x86_64"]
    assert ai.id == "fedora-99-netinst" and ai.edition == "netinst"


def test_load_catalog_entry_without_autoinstall_has_empty_dict(tmp_path: Path) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(_VALID, encoding="utf-8")  # _VALID has no autoinstall table
    assert load_catalog(p)["fedora-99"].autoinstall == {}
```

(The existing `_VALID` constant in this file defines a `fedora-99` entry with only `isos`.)

- [ ] **Step 3: Run, verify fail** — `cd engine && uv run pytest tests/usb/test_catalog.py -q -k autoinstall` → FAIL (no `autoinstall_for`, `Os` has no `autoinstall`).

- [ ] **Step 4: Edit `engine/src/devboost/usb/catalog.py`.** Add `autoinstall` to the `Os` dataclass, the `_OsRow` model, the loader, and the accessor.

In the `Os` dataclass, add a field (after `isos`):
```python
    autoinstall: dict[str, IsoSpec]
```
In `_OsRow`, add (after `isos`):
```python
    autoinstall: dict[str, _IsoRow] = {}
```
In `load_catalog`, build the autoinstall specs and pass them to `Os(...)`:
```python
    return {
        os_id: Os(
            id=os_id,
            name=row.name,
            distro=row.distro,
            version=row.version,
            edition=row.edition,
            isos={
                arch: IsoSpec(id=os_id, url=iso.url, sha256=iso.sha256, edition=row.edition)
                for arch, iso in row.isos.items()
            },
            autoinstall={
                arch: IsoSpec(
                    id=f"{os_id}-netinst", url=iso.url, sha256=iso.sha256, edition="netinst"
                )
                for arch, iso in row.autoinstall.items()
            },
        )
        for os_id, row in rows.items()
    }
```
Add the accessor (after `iso_for`):
```python
def autoinstall_for(os_id: str, arch: str) -> IsoSpec | None:
    """The pinned zero-touch (netinst) IsoSpec for *os_id*+*arch*, or None if not pinned."""
    os_entry = catalog().get(os_id)
    if os_entry is None:
        return None
    return os_entry.autoinstall.get(arch)
```

- [ ] **Step 5: Run, verify pass** — `uv run pytest tests/usb/test_catalog.py -q` → PASS (new + existing). The existing `test_supported_returns_friendly_named_entries` / `default_os` still hold (autoinstall is additive).

- [ ] **Step 6: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add ../catalog.toml src/devboost/usb/catalog.py tests/usb/test_catalog.py
git commit -m "feat(usb): optional per-arch autoinstall (netinst) media in the catalog"
```

---

### Task 2: Config + stages — generate ventoy.json, stage both ISOs

**Files:**
- Modify: `engine/src/devboost/usb/config.py` (add `autoinstall_iso`)
- Modify: `engine/src/devboost/usb/stages.py` (rewrite `render_ventoy_json`; stage both ISOs)
- Delete: `ventoy/ventoy.json` (now generated in Python)
- Modify: `engine/tests/usb/test_stages.py` (update the ventoy.json tests; assert both ISOs)

**Interfaces:**
- Consumes: `cfg.iso` (Live, id `fedora-44`) and `cfg.autoinstall_iso: IsoSpec | None` (netinst, id `fedora-44-netinst`).
- Produces: `render_ventoy_json(*, default_iso: str, autoinstall_iso: str | None) -> str`; `boot_artifacts`/`update_stage` stage both ISOs.

- [ ] **Step 1: Add the config field.** In `engine/src/devboost/usb/config.py`, in `UsbBuildConfig` (after `iso`):
```python
    autoinstall_iso: IsoSpec | None = None
```

- [ ] **Step 2: Write the failing tests** — replace the existing `test_render_ventoy_json_binds_to_staged_iso_name` in `engine/tests/usb/test_stages.py` and add a both-ISOs assertion. New renderer tests:

```python
def test_render_ventoy_json_default_only_omits_auto_install() -> None:
    import json

    from devboost.usb.stages import render_ventoy_json

    data = json.loads(render_ventoy_json(default_iso="fedora-44.iso", autoinstall_iso=None))
    assert data["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/fedora-44.iso"
    assert data["injection"] == [
        {"image": "/ISO/fedora-44.iso", "archive": "/Bootstrap/devboost.tar.gz"}
    ]
    assert "auto_install" not in data


def test_render_ventoy_json_with_autoinstall_binds_both() -> None:
    import json

    from devboost.usb.stages import render_ventoy_json

    data = json.loads(
        render_ventoy_json(default_iso="fedora-44.iso", autoinstall_iso="fedora-44-netinst.iso")
    )
    assert data["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/fedora-44.iso"
    assert data["auto_install"] == [
        {"image": "/ISO/fedora-44-netinst.iso", "template": "/Bootstrap/ks.cfg"}
    ]
    # injection lists BOTH ISOs
    images = sorted(e["image"] for e in data["injection"])
    assert images == ["/ISO/fedora-44-netinst.iso", "/ISO/fedora-44.iso"]
```

- [ ] **Step 3: Update the `boot_artifacts` integration test** in `test_stages.py`. The current test monkeypatches `resource_path` for `("ventoy", "ventoy.json")` and asserts the rendered file. Since `ventoy.json` is no longer read from resources, (a) drop the `("ventoy", "ventoy.json")` branch from the `fake_resource_path` (leave `ks.cfg` and `dist`), and (b) add an `autoinstall_iso` to the config + a fake netinst blob, then assert BOTH ISOs are staged and the generated `ventoy.json` binds them. Concretely, in `test_boot_artifacts_installs_ventoy_and_stages_files`:

```python
    # give the build a netinst auto-install ISO too
    netinst_bytes = b"fedora-netinst"
    netinst_sha = hashlib.sha256(netinst_bytes).hexdigest()
    netinst = IsoSpec(id="fedora-44-netinst", url="https://x/n.iso", sha256=netinst_sha,
                      edition="netinst")
    # add to the FakeDownloader blob map and the config:
    dl = FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes, "https://x/n.iso": netinst_bytes})
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, autoinstall_iso=netinst,
        profiles=("cli",), cache_dir=cache.cache_dir, assume_yes=True,
    )
```
Drop the `fake_ventoy_json` fake and the `("ventoy","ventoy.json")` branch. After `boot_artifacts(...)`:
```python
    import json
    assert (vtoy / "ISO" / "fedora-44.iso").exists()
    assert (vtoy / "ISO" / "fedora-44-netinst.iso").exists()   # both staged
    vj = json.loads((vtoy / "ventoy" / "ventoy.json").read_text())
    assert vj["auto_install"][0]["image"] == "/ISO/fedora-44-netinst.iso"
    assert vj["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/fedora-44.iso"
```
(Keep the existing `ventoy -i` and `ks.cfg` assertions.)

- [ ] **Step 4: Run, verify fail** — `uv run pytest tests/usb/test_stages.py -q` → FAIL (renderer signature changed; netinst not staged).

- [ ] **Step 5: Rewrite `render_ventoy_json` and the staging in `engine/src/devboost/usb/stages.py`.** Add `import json`. Replace the current `render_ventoy_json`:

```python
def render_ventoy_json(*, default_iso: str, autoinstall_iso: str | None) -> str:
    """Generate ventoy.json: default boot + injection on the Live media; auto_install on netinst.

    ``default_iso``/``autoinstall_iso`` are bare filenames (e.g. ``fedora-44.iso``). The
    ``auto_install`` block is emitted only when an autoinstall ISO is present; injection covers
    every staged ISO so the dev-boost binary is available on whichever path boots.
    """
    injection = [{"image": f"/ISO/{default_iso}", "archive": "/Bootstrap/devboost.tar.gz"}]
    data: dict[str, list[dict[str, str]]] = {
        "control": [
            {"VTOY_MENU_TIMEOUT": "10"},
            {"VTOY_DEFAULT_IMAGE": f"/ISO/{default_iso}"},
        ],
        "injection": injection,
    }
    if autoinstall_iso is not None:
        injection.append(
            {"image": f"/ISO/{autoinstall_iso}", "archive": "/Bootstrap/devboost.tar.gz"}
        )
        data["auto_install"] = [
            {"image": f"/ISO/{autoinstall_iso}", "template": "/Bootstrap/ks.cfg"}
        ]
    return json.dumps(data, indent=2)
```

In `_stage_payload`, replace the ventoy.json read+render block with the generated write:
```python
    ai_name = f"{cfg.autoinstall_iso.id}.iso" if cfg.autoinstall_iso is not None else None
    (vtoy_mount / "ventoy" / "ventoy.json").write_text(
        render_ventoy_json(default_iso=f"{cfg.iso.id}.iso", autoinstall_iso=ai_name),
        encoding="utf-8",
    )
```
(Remove the `resource_path("ventoy", "ventoy.json")` read entirely.)

Add a shared helper to stage the autoinstall ISO and call it from both `boot_artifacts` and `update_stage`. After the default-ISO `dl.fetch`+copy in `boot_artifacts`:
```python
    _stage_autoinstall_iso(cfg, dl, vtoy_mount=vtoy_mount, reporter=reporter)
```
And in `update_stage`, inside the `if cfg.refresh_iso:` block (after the default-ISO refresh):
```python
        _stage_autoinstall_iso(cfg, dl, vtoy_mount=vtoy_mount, reporter=reporter)
```
The helper:
```python
def _stage_autoinstall_iso(
    cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    if cfg.autoinstall_iso is None:
        return
    spec = cfg.autoinstall_iso
    iso_path = dl.fetch(spec.url, f"{spec.id}.iso", spec.sha256)
    shutil.copyfile(iso_path, vtoy_mount / "ISO" / f"{spec.id}.iso")
    reporter.step(f"Zero-touch ISO staged ({spec.id})")
```
**Note on `boot_artifacts`:** the default-ISO fetch always runs; the autoinstall fetch runs whenever `cfg.autoinstall_iso` is set. In `update_stage` the autoinstall fetch is gated by `--refresh-iso` (mirrors the Live-ISO rule).

- [ ] **Step 6: Delete the resource template** — `git rm ventoy/ventoy.json` (it is now generated; `ventoy/ks.cfg` stays).

- [ ] **Step 7: Run, verify pass** — `uv run pytest tests/usb/test_stages.py -q` then full `uv run pytest -q` → PASS.

- [ ] **Step 8: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add src/devboost/usb/config.py src/devboost/usb/stages.py tests/usb/test_stages.py
git rm ../ventoy/ventoy.json
git commit -m "feat(usb): stage both ISOs + generate ventoy.json (Live default, netinst auto_install)"
```

---

### Task 3: CLI + wizard wiring, preview/summary, docs

**Files:**
- Modify: `engine/src/devboost/cli/usb.py` (resolve `autoinstall_iso`; dry-run size; summary)
- Modify: `engine/src/devboost/usb/wizard.py` (resolve `autoinstall_iso` into the config)
- Modify: `engine/src/devboost/usb/preview.py` (note the zero-touch media)
- Modify: `engine/tests/usb/test_cli_usb.py`, `engine/tests/usb/test_preview.py`
- Modify: `docs/ventoy.md`, `README.md`

**Interfaces:**
- Consumes: `autoinstall_for(os_id, arch)` from catalog; `cfg.autoinstall_iso`.

- [ ] **Step 1: Wire the CLI.** In `engine/src/devboost/cli/usb.py`, import `autoinstall_for`:
```python
from devboost.usb.catalog import autoinstall_for, default_iso, iso_for
```
In the flags path, resolve the os id used for the default ISO and pass the autoinstall spec into the config. The default ISO is resolved from `iso or default_iso().id`; reuse that id:
```python
        os_id = iso or default_iso().id
        cfg = UsbBuildConfig(
            device=device,
            arch=resolved_arch,
            iso=iso_for(os_id, resolved_arch),
            autoinstall_iso=autoinstall_for(os_id, resolved_arch),
            ...
        )
```
(Keep the `try/except UsbError` wrapper. `iso_for(os_id, ...)` replaces the prior `iso_for(iso, ...) if iso else iso_for(default_iso().id, ...)` — `os_id` already defaults correctly.)

- [ ] **Step 2: Update `_iso_note` for the combined size.** Replace the body so it sums the Live + (optional) netinst sizes (still never raises):
```python
def _iso_note(cfg: UsbBuildConfig) -> str:
    """Best-effort combined ISO download size for the dry-run preview (never raises)."""
    specs = [cfg.iso] + ([cfg.autoinstall_iso] if cfg.autoinstall_iso is not None else [])
    try:
        cache = Cache(cfg.cache_dir)
        total = 0
        all_cached = True
        for spec in specs:
            if cache.has(f"{spec.id}.iso", spec.sha256):
                continue
            all_cached = False
            req = urllib.request.Request(spec.url, method="HEAD")
            with urllib.request.urlopen(req) as resp:
                total += int(resp.headers.get("Content-Length", 0) or 0)
        if all_cached:
            return "cached"
        return f"≈{total / 1e9:.1f} GB" if total else "unknown"
    except OSError:
        return "unknown"
```

- [ ] **Step 3: Note the media in `_summary_text`.** After the head line is built, include the zero-touch note when present. Replace the `head = (...)` block's trailing assembly so the media is named:
```python
    media = "Workstation Live" + (
        " + netinst (zero-touch)" if cfg.autoinstall_iso is not None else ""
    )
    head = (
        f"✅ {verb} {cfg.device} — {cfg.iso.id} ({cfg.arch}) · media: {media} · "
        f"profiles: {' '.join(cfg.profiles)}{tail}"
    )
```
(Keep the `verb`/`tail`/`body` logic as-is.)

- [ ] **Step 4: Wire the wizard.** In `engine/src/devboost/usb/wizard.py`, import `autoinstall_for` and set it on the returned config:
```python
from devboost.usb.catalog import autoinstall_for, default_os, iso_for, supported
```
In the `return UsbBuildConfig(...)`:
```python
        iso=iso_for(os_id, arch),
        autoinstall_iso=autoinstall_for(os_id, arch),
```

- [ ] **Step 5: Note the media in the preview.** In `engine/src/devboost/usb/preview.py` `render_plan`, after the OS line add:
```python
    if cfg.autoinstall_iso is not None:
        lines.append("Zero-touch    : netinst auto-install staged")
```

- [ ] **Step 6: Update tests.** 

In `engine/tests/usb/test_preview.py`, add a case asserting the zero-touch line appears when `autoinstall_iso` is set:
```python
def test_render_plan_notes_autoinstall_media() -> None:
    out = render_plan(_cfg(autoinstall_iso=_ISO), DiskState("blank"))
    assert "Zero-touch" in out
```
(`_ISO` is the module's existing `IsoSpec` fixture; reusing it is fine for the presence check.)

In `engine/tests/usb/test_cli_usb.py`, the existing dry-run/devboost tests still pass (autoinstall is auto-resolved from the real catalog, which now has it). Add one assertion to `test_usb_dry_run_previews_without_building` that the plan mentions the zero-touch media:
```python
    assert "Zero-touch" in clean or "netinst" in clean
```

- [ ] **Step 7: Run, verify pass** — `cd engine && uv run pytest -q` → PASS; `uv run mypy --strict src`; `uv run ruff check src tests`.

- [ ] **Step 8: Docs.** In `docs/ventoy.md`, update the "Which OS gets installed" section to state the stick carries **both** a Workstation Live ISO (default/manual boot + injection) and an Everything-netinst ISO (zero-touch `auto_install` + `ks.cfg`), both pinned per-arch in `catalog.toml`. In `README.md`, tweak the `devboost usb` row to mention "stages both the Live (manual) and netinst (zero-touch) ISOs". (Exact prose at the implementer's discretion, matching the surrounding style; no placeholders.)

- [ ] **Step 9: Commit**

```bash
git add engine/src/devboost/cli/usb.py engine/src/devboost/usb/wizard.py engine/src/devboost/usb/preview.py engine/tests/usb/test_cli_usb.py engine/tests/usb/test_preview.py docs/ventoy.md README.md
git commit -m "feat(usb): resolve + surface the netinst auto-install media (cli, wizard, preview, docs)"
```

---

## Self-Review

**Spec coverage:** catalog `autoinstall` + `autoinstall_for` (Task 1); config `autoinstall_iso` + both-ISO staging + Python-generated ventoy.json with default→Live / auto_install→netinst / injection→both (Task 2); CLI+wizard auto-resolution, combined dry-run size, summary/preview media note, docs (Task 3). ✅

**Placeholder scan:** every code step has complete code; the only discretion is doc prose (Task 3 Step 8), bounded to match existing style. ✅

**Type consistency:** `render_ventoy_json(*, default_iso: str, autoinstall_iso: str | None)` is used identically in `_stage_payload` and the tests. `autoinstall_for(os_id, arch) -> IsoSpec | None` is used in cli + wizard. `UsbBuildConfig.autoinstall_iso: IsoSpec | None` is consumed in stages, cli, preview. `Os.autoinstall: dict[str, IsoSpec]`. The autoinstall IsoSpec id is `f"{os_id}-netinst"` everywhere (filename `fedora-44-netinst.iso`).

**Cross-task breakage:** Task 2 deletes `ventoy/ventoy.json` and removes its `resource_path` read + the test fake — handled in-task; build-bundle.sh still bundles `ventoy/` for `ks.cfg`. Task 1's autoinstall is additive (existing catalog tests unaffected).
