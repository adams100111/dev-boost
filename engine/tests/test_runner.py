from devboost.plan import PlannedModule
from devboost.runner import RunResult, run_plan


class FakeExecutor:
    """verify returns nonzero until an install step has run; installs succeed."""

    def __init__(self, installed: set[str] | None = None) -> None:
        self.installed = installed or set()
        self.calls: list[str] = []

    def run(self, cmd: str) -> int:
        self.calls.append(cmd)
        if cmd.startswith("verify:"):
            return 0 if cmd[len("verify:"):] in self.installed else 1
        self.installed.add(cmd)  # any install "command" marks itself installed
        return 0


def _pm(name: str, steps: tuple[str, ...], skip: str | None = None) -> PlannedModule:
    return PlannedModule(name, f"verify:{name}", steps, skip)


def test_runs_install_when_verify_red() -> None:
    ex = FakeExecutor()
    # verify:eza red -> runs step "eza" -> but verify checks 'eza' membership, step adds 'eza'
    plan = [_pm("eza", ("eza",))]
    results = run_plan(plan, ex, dry_run=False, force=False)
    assert results == [RunResult("eza", "ok")]
    assert "eza" in ex.calls


def test_skips_when_verify_green() -> None:
    ex = FakeExecutor(installed={"eza"})
    results = run_plan([_pm("eza", ("eza",))], ex, dry_run=False, force=False)
    assert results == [RunResult("eza", "skip")]


def test_honors_skip_reason() -> None:
    ex = FakeExecutor()
    results = run_plan([_pm("ghostty", ("g",), skip="headless-gui")], ex, dry_run=False, force=False)
    assert results == [RunResult("ghostty", "skip")]
    assert ex.calls == []


def test_dry_run_executes_nothing() -> None:
    ex = FakeExecutor()
    results = run_plan([_pm("eza", ("eza",))], ex, dry_run=True, force=False)
    assert results == [RunResult("eza", "ok")]
    assert ex.calls == []


def test_fallback_step_used_when_first_fails() -> None:
    class FirstFails(FakeExecutor):
        def run(self, cmd: str) -> int:
            self.calls.append(cmd)
            if cmd.startswith("verify:"):
                return 0 if "good" in self.installed else 1
            if cmd == "bad":
                return 1
            self.installed.add("good")
            return 0

    ex = FirstFails()
    results = run_plan([_pm("eza", ("bad", "good"))], ex, dry_run=False, force=False)
    assert results == [RunResult("eza", "ok")]
    assert ex.calls == ["verify:eza", "bad", "good", "verify:eza"]
