from __future__ import annotations

import pytest

from devboost.core.errors import DependencyCycle, ManifestError
from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.registry import _check_cycles, _validate, load
from devboost.model import Ctx, Installer, Module


class _FedoraOnly:
    def install(self, ctx: Ctx) -> None: ...
    def verify(self, ctx: Ctx) -> bool:
        return True


def test_per_os_module_delegates_to_strategy(fedora_ctx: Ctx) -> None:
    strat: Installer = _FedoraOnly()

    class M(Module):
        name = "m"
        per_os = OsMap(fedora=strat)

    assert M().verify(fedora_ctx) is True


def test_uniform_module_without_override_raises(fedora_ctx: Ctx) -> None:
    class Bare(Module):
        name = "bare"

    with pytest.raises(NotImplementedError):
        Bare().install(fedora_ctx)


def test_unsupported_os_returns_none() -> None:
    ubuntu = OsInfo("ubuntu", "debian", "x86_64")
    m: OsMap[Installer] = OsMap(fedora=_FedoraOnly())
    assert m.get(ubuntu) is None


def test_validate_rejects_unknown_dependency() -> None:
    class Dep(Module):
        name = "dep"

    class Needs(Module):
        name = "needs"
        requires = (Dep,)

    with pytest.raises(ManifestError):
        _validate({"needs": Needs})  # 'dep' not in the dict


def test_check_cycles_detects_cycle() -> None:
    class A(Module):
        name = "a"

    class B(Module):
        name = "b"

    A.requires = (B,)
    B.requires = (A,)
    with pytest.raises(DependencyCycle):
        _check_cycles({"a": A, "b": B})


def test_load_discovers_tracer_modules() -> None:
    modules = load()
    assert {"ripgrep", "docker", "ddev"} <= set(modules)
