# Contract: runtime/tool install modules

All escape-hatch, `category="dev-stacks"`, only `[install].fedora`, source `lib/log.sh`+`lib/pkg.sh`.
Pins are context7-verified (research.md); they live in module data and are the in-repo source of truth.

## `uv` (python runtime tool)
- install: `curl -LsSf https://astral.sh/uv/0.11.23/install.sh | sh` (pinned URL). verify: `command -v uv`.

## `web-runtimes` (node/pnpm/bun)
- install: `mise use -g node@22 pnpm@11.8.0 bun@1.3.14`. verify: `mise which node && mise which pnpm && mise which bun` all resolve.

## `ddev` (laravel, container orchestrator)
- install: write `/etc/yum.repos.d/ddev.repo` (`[ddev] name=ddev baseurl=https://pkg.ddev.com/yum/ gpgcheck=0 enabled=1`) only if absent; `sudo dnf install --refresh -y ddev`; `mkcert -install` (idempotent). honor `DEVBOOST_YUM_REPOS_DIR` override for tests. verify: `command -v ddev`. NO host php/composer.

## `dotnet-sdk` (.NET 10 LTS)
- install: `sudo dnf install -y dotnet-sdk-10.0` (Fedora in-distro). verify: `command -v dotnet` && `dotnet --list-sdks` shows a 10.* SDK.

## `aspire` (Aspire CLI)
- install: `dotnet tool install -g Aspire.Cli` (skip if `command -v aspire`). verify: `command -v aspire`.

## `android-sdk` (react-native)
- `mise use -g java@temurin-17`; ensure `ANDROID_HOME=$HOME/Android/Sdk`; download `commandlinetools-linux` zip → unzip to `$ANDROID_HOME/cmdline-tools/latest/`; `sdkmanager "platform-tools" "platforms;android-35" "build-tools;36.0.0" "cmdline-tools;latest"`; `yes | sdkmanager --licenses`. Idempotent: skip if the packages + a license-accepted marker already present. verify: `$ANDROID_HOME/platform-tools/adb` exists AND `mise which java` resolves.

## `devops-tools` (opentofu/kubectl/helm/k9s)
- install: `mise use -g aqua:opentofu/opentofu@1.11.6 aqua:kubernetes/kubectl@1.35.2 aqua:helm/helm@4.1.4 aqua:derailed/k9s@0.51.0`. verify: all four `mise which` resolve.

## Tests (per module, stubbed)
- install command attempted with the right pin (assert against the stub log); verify GREEN after; idempotent skip on re-run; unsupported-OS (non-fedora) → engine failure. No real installs/network/SDK.
