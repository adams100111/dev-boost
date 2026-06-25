import subprocess
from dataclasses import dataclass
from typing import Protocol

from devboost import log
from devboost.plan import PlannedModule


class Executor(Protocol):
    def run(self, cmd: str) -> int: ...


class SubprocessExecutor:
    def run(self, cmd: str) -> int:
        return subprocess.run(["bash", "-lc", cmd], check=False).returncode


@dataclass
class RunResult:
    name: str
    status: str


def run_plan(
    plan: list[PlannedModule],
    executor: Executor,
    *,
    dry_run: bool,
    force: bool,
) -> list[RunResult]:
    results: list[RunResult] = []
    for pm in plan:
        if pm.skip_reason is not None:
            log.skip(f"skip {pm.name} ({pm.skip_reason})")
            results.append(RunResult(pm.name, "skip"))
            continue
        if dry_run:
            log.info(f"would install {pm.name}: {' || '.join(pm.steps)}")
            results.append(RunResult(pm.name, "ok"))
            continue
        if not force and executor.run(pm.verify) == 0:
            log.skip(f"skip {pm.name} (already installed)")
            results.append(RunResult(pm.name, "skip"))
            continue
        installed = False
        for step in pm.steps:
            if executor.run(step) != 0:
                continue
            if executor.run(pm.verify) == 0:
                installed = True
                break
        if installed:
            log.ok(f"installed {pm.name}")
            results.append(RunResult(pm.name, "ok"))
        else:
            log.error(f"FAILED {pm.name}")
            results.append(RunResult(pm.name, "fail"))
    return results
