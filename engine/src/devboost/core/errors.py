"""Typed exception hierarchy. All engine failures derive from DevbootError."""

from __future__ import annotations


class DevbootError(Exception):
    """Base class for every dev-boost engine error."""


class ManifestError(DevbootError):
    """A module declaration is invalid (bad metadata, duplicate name, …)."""


class ProfileError(DevbootError):
    """A profile is unknown or references a missing module."""


class DependencyCycle(DevbootError):
    """The module dependency graph contains a cycle."""


class InstallError(DevbootError):
    """A module failed to install."""

    def __init__(self, module: str, command: str, code: int) -> None:
        self.module = module
        self.command = command
        self.code = code
        super().__init__(f"module {module!r}: command {command!r} failed (exit {code})")


class UnsupportedOS(DevbootError):
    """No install path exists for the detected OS."""


class SecretsError(DevbootError):
    """The age-encrypted secrets bundle is missing, undecryptable, or incomplete."""


class GithubError(DevbootError):
    """A GitHub REST API call failed."""
