# Feature Specification: gnome-desktop

**Feature Branch**: `004-gnome-desktop`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: "gnome-desktop — declarative GNOME desktop configuration: dconf/gsettings settings, headlessly-installed pinned extensions, the manager apps, and an opt-in theming bundle (design §10c gnome; roadmap Spec 4)."

## Overview

This feature configures the GNOME desktop declaratively so a freshly-built machine
matches the reference desktop: the system look-and-feel settings are applied, a curated
set of GNOME Shell extensions is installed and enabled **without needing a logged-in
graphical session**, the extension-manager apps and tweak tool are present, and an opt-in
theming bundle is available. It ships as self-contained modules over the existing engine,
reusing the chezmoi-managed config pattern (Spec 3) and the escape-hatch + bats harness
patterns (Specs 1–2). GNOME is the Fedora-Workstation desktop; on non-GNOME / other OSes
these modules are reported unsupported, never silently skipped.

## Clarifications

### Session 2026-06-20 (self-answered from the design doc — source of truth; user autonomous / "take over")

- Q: How are extensions enabled unattended, when `gnome-extensions enable` needs a live gnome-shell/dbus session the bootstrap doesn't have? → A: **Two-step, session-free**: (1) DOWNLOAD/INSTALL each extension by pinned UUID + the detected GNOME Shell version from extensions.gnome.org via the `gext`/`gnome-extensions-cli` tool into the per-user extensions directory (no session needed); (2) ENABLE by writing the `org.gnome.shell enabled-extensions` dconf/gsettings key (the enable list), which the next GNOME session reads. This avoids any dependency on a running shell during bootstrap.
- Q: Where do the GNOME settings live? → A: a chezmoi-managed dconf dump applied with `dconf load` (idempotent, re-runnable), reusing the Spec-3 dotfiles/chezmoi-source pattern; the enabled-extensions key is part of that managed state.
- Q: Are the aesthetics extensions and the theme bundle in the default `gnome` profile? → A: NO. The default `gnome` profile is the settings + the FUNCTIONAL extension set + the manager/tweak apps. The aesthetics sub-bundle and the `gnome-theme` bundle are SEPARATE opt-in profiles, not in `full` (design §10c).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Desktop settings applied (Priority: P1)

After base, the operator's GNOME desktop comes up with the reference look-and-feel: dark
mode, the correct display scaling behavior, the expected window-button layout, windows
centered, tap-to-click on, and the accent color set — all applied automatically and
re-runnable without harm.

**Why this priority**: The settings are the visible foundation of the desktop experience
and are independent of any extension. This is the MVP slice.

**Independent Test**: On a fixture host with the desktop tooling mocked, run the settings
module and assert each setting key is written to the expected value; re-running changes
nothing (idempotent).

**Acceptance Scenarios**:

1. **Given** base is in place, **When** the settings module runs, **Then** dark mode, the display-scaling option, the window-button layout, center-new-windows, tap-to-click, and the accent color are all set to the reference values.
2. **Given** the settings were applied, **When** the module runs again, **Then** nothing changes (idempotent) and it reports already-satisfied.
3. **Given** a non-GNOME or unsupported environment, **When** the settings module runs, **Then** it is reported unsupported, never silently skipped.

---

### User Story 2 - Functional extensions installed and enabled (no session) (Priority: P2)

The operator's desktop has the curated set of functional GNOME extensions installed and
enabled — tray icons, clipboard history, sleep-inhibitor, phone integration, a persistent
dock, and an emoji picker — all provisioned without a logged-in graphical session, so they
are active on first login.

**Why this priority**: The functional extensions deliver the reference workflow, but
depend on the settings/dconf mechanism (US1) being in place.

**Independent Test**: With the extension tooling and dconf mocked, run the extensions
module and assert each pinned extension is fetched by its exact identifier and version,
that authorship/identifier is verified at install, that each is added to the
enabled-extensions list, and that a re-run installs/enables nothing new (idempotent).

**Acceptance Scenarios**:

1. **Given** the settings mechanism is present, **When** the extensions module runs, **Then** each curated functional extension is installed by its pinned identifier for the detected desktop-shell version, and added to the enabled list — without requiring a live graphical session.
2. **Given** an extension's published identifier/author does not match the pinned value, **When** the module runs, **Then** it fails naming that extension rather than installing an unverified one.
3. **Given** the extensions are installed and enabled, **When** the module runs again, **Then** nothing is re-installed or duplicated in the enabled list (idempotent).
4. **Given** the extensions were enabled, **When** the operator logs into a graphical session, **Then** the extensions are active (the enable list was honored).

---

### User Story 3 - Manager apps, tweak tool, and opt-in bundles (Priority: P3)

The operator has the official extension-manager app, a third-party manager for in-app
discovery, and the tweak tool for manual adjustments; and can opt in to an aesthetics
extension sub-bundle and a full reproducible theming bundle.

**Why this priority**: Convenience/escape-hatch tooling and optional polish; depends on the
core desktop (US1/US2) being in place.

**Independent Test**: Run the manager/tweak module and assert each app is installed; run
the opt-in aesthetics and theme modules and assert their extensions/theme/icon/cursor/font
artifacts are provisioned reproducibly (no manual download flow); re-run is a no-op.

**Acceptance Scenarios**:

1. **Given** the desktop is configured, **When** the manager module runs, **Then** the official extension-manager app, the third-party discovery app, and the tweak tool are installed.
2. **Given** the operator selects the aesthetics sub-bundle, **When** it runs, **Then** the aesthetics extensions are installed + enabled the same session-free way as the functional set.
3. **Given** the operator selects the theme bundle, **When** it runs, **Then** the user-themes enabler, a pinned theme, a packaged icon theme, a cursor theme, and the UI font are installed reproducibly (no manual website download), and applied via the managed settings.
4. **Given** any of these ran, **When** they run again, **Then** nothing changes (idempotent).

### Edge Cases

- A pinned extension is unavailable for the detected shell version → reported as a failure naming the extension (not silently skipped).
- An extension's author/identifier mismatches the pinned value → install refused, named.
- The enabled-extensions list already contains an extension → not duplicated on re-run.
- A setting already at the reference value → not rewritten / no churn; re-run is clean.
- Non-GNOME desktop or a server with no desktop → all these modules reported unsupported.
- dconf schema/keys differ across GNOME versions (fragile state) → the module targets the detected version and fails clearly if a key is absent, rather than corrupting state.
- The manager/discovery app is already installed → skipped, not reinstalled.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST apply the reference desktop settings (dark mode, display-scaling option, window-button layout, center-new-windows, tap-to-click, accent color) declaratively and idempotently.
- **FR-002**: The settings MUST be applied from managed configuration (a dconf dump under the chezmoi-managed source), and re-applying MUST cause no change.
- **FR-003**: The system MUST install each curated functional extension by its PINNED identifier for the detected desktop-shell version, WITHOUT requiring a live graphical session.
- **FR-004**: The system MUST verify each extension's authorship/identifier against the pinned value at install time and MUST refuse (failing, named) an extension whose published author/identifier does not match.
- **FR-005**: The system MUST enable extensions by writing the desktop's enabled-extensions setting (so they activate on next login), without duplicating entries on re-run.
- **FR-006**: The system MUST install the official extension-manager app, a third-party discovery app, and the desktop tweak tool.
- **FR-007**: The system MUST provide an OPT-IN aesthetics extension sub-bundle (installed/enabled the same session-free way) that is NOT part of the default profile.
- **FR-008**: The system MUST provide an OPT-IN theming bundle (a user-themes enabler, a pinned theme, a packaged icon theme, a cursor theme, and a UI font) provisioned REPRODUCIBLY with no manual website-download step, applied via managed settings; NOT part of the default profile.
- **FR-009**: Every module MUST be idempotent and verify-guarded: a top-level verify determines already-satisfied state and is evaluated before any install/apply action.
- **FR-010**: These modules MUST be reported UNSUPPORTED on a non-GNOME or no-desktop environment, never silently skipped; OS/desktop differences MUST be expressed as data.
- **FR-011**: Dependency ordering MUST be expressed via `requires` (e.g. the extensions/enable step after the settings/dconf mechanism), reusing the engine's existing ordering — no engine control-flow change.
- **FR-012**: A failure in any module MUST name the module and the exact operation that failed.
- **FR-013**: No module may write secrets into version control; managed desktop configuration MUST contain no secrets.

### Key Entities *(include if feature involves data)*

- **Desktop settings dump**: the chezmoi-managed dconf state (look-and-feel keys + the enabled-extensions list).
- **Curated extensions**: the functional set (default) and the aesthetics set (opt-in), each identified by a pinned identifier + verified author.
- **Manager/tweak apps**: the official extension manager, the third-party discovery app, the tweak tool.
- **Theme bundle**: user-themes enabler, pinned theme, packaged icon theme, cursor theme, UI font (opt-in, reproducible).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the `gnome` profile on a base machine completes with **zero interactive prompts** and ends with all modules verifying green.
- **SC-002**: Re-running the `gnome` profile is a **no-op** — every module reports already-satisfied; no enabled-extensions entry is duplicated.
- **SC-003**: After the run and a first graphical login, the desktop shows the reference settings (dark mode, scaling, buttons, accent) and the curated functional extensions are active — with **no manual step** taken during bootstrap.
- **SC-004**: Every curated extension is installed at its **pinned identifier** and its authorship was verified; a mismatch causes a named failure, not a silent install.
- **SC-005**: On a non-GNOME / no-desktop host, the modules report **unsupported** (a failure), never a silent skip.
- **SC-006**: The aesthetics sub-bundle and theme bundle are **opt-in** (absent from the default profile) and, when selected, are provisioned reproducibly with no manual website download.
- **SC-007**: Automated tests cover settings apply + idempotency, extension install/enable + authorship-verify + no-duplicate-enable, the unsupported-environment path, and the opt-in bundles, with no real installs or desktop session (mocked).

## Assumptions

- Base (Spec 2) is present: flatpak (for the manager/discovery apps), dnf, chezmoi, and the package tuning are available.
- The reference desktop is GNOME on Fedora Workstation; other desktops/OSes are unsupported for these modules (reported, not skipped).
- Extensions are provisioned by pinned identifier for the detected shell version; enabling is done by writing the enabled-extensions setting so a live session is not required at bootstrap.
- The curated functional set, aesthetics set, and theme components are the design-doc lists (pinned identifiers + verified authors); exact identifiers/versions are pinned in the plan.
- "Reproducible theming" means packaged or pinned-script provisioning; the manual download-and-drag flow is explicitly out of scope (design §10c rejected method).
- This feature is built test-first with the project's existing harness, mocking the desktop/package tooling so no real installs or graphical session occur.
