"""git over the executor, scoped to the password store. Hook disabled for our own calls."""

from __future__ import annotations

from pathlib import Path

from devboost.core.errors import InstallError
from devboost.exec.executor import Result
from devboost.model import Ctx

#: Our own commits/pushes must not re-trigger the post-commit hook (D10).
NO_HOOK_ENV: dict[str, str] = {"DEVBOOST_PASS_HOOK": "off"}


def _git(ctx: Ctx, store: Path, *args: str) -> Result:
    return ctx.ex.run(["git", "-C", str(store), *args], env=NO_HOOK_ENV)


def _lines(res: Result) -> list[str]:
    return [ln.strip() for ln in res.stdout.splitlines() if ln.strip()] if res.ok else []


def clone(ctx: Ctx, url: str, dest: Path) -> Result:
    return ctx.ex.run(["git", "clone", "--quiet", url, str(dest)], env=NO_HOOK_ENV)


def pull(ctx: Ctx, store: Path) -> Result:
    return _git(ctx, store, "pull", "--rebase", "--autostash", "--quiet")


def push(ctx: Ctx, store: Path) -> Result:
    return _git(ctx, store, "push", "--quiet", "--set-upstream", "origin", "HEAD")


def conflicted(ctx: Ctx, store: Path) -> list[str]:
    return _lines(_git(ctx, store, "diff", "--name-only", "--diff-filter=U"))


def abort_rebase(ctx: Ctx, store: Path) -> None:
    _git(ctx, store, "rebase", "--abort")


def commit(ctx: Ctx, store: Path, message: str) -> bool:
    _git(ctx, store, "add", "-A")
    if _git(ctx, store, "diff", "--cached", "--quiet").ok:
        return False
    res = _git(ctx, store, "commit", "--quiet", "-m", message)
    if not res.ok:
        raise InstallError("pass-store", f"git commit -m {message!r}", res.code)
    return True


def ahead(ctx: Ctx, store: Path) -> int:
    out = _lines(_git(ctx, store, "rev-list", "--count", "@{u}..HEAD"))
    return int(out[0]) if out and out[0].isdigit() else 0


def head(ctx: Ctx, store: Path) -> str:
    out = _lines(_git(ctx, store, "rev-parse", "HEAD"))
    return out[0] if out else ""


def subjects_touching(ctx: Ctx, store: Path, since: str, path: str) -> list[str]:
    """Subjects of commits after *since* (all of history when empty) touching *path*."""
    rng = f"{since}..HEAD" if since else "HEAD"
    return _lines(_git(ctx, store, "log", "--format=%s", rng, "--", path))


def first_commit_with(ctx: Ctx, store: Path, token: str) -> str | None:
    """Oldest commit that changed the number of occurrences of *token* in root .gpg-id."""
    out = _lines(_git(ctx, store, "log", "--reverse", "--format=%H", f"-S{token}", "--",
                      ".gpg-id"))
    return out[0] if out else None


def files_at(ctx: Ctx, store: Path, rev: str) -> list[str]:
    return _lines(_git(ctx, store, "ls-tree", "-r", "--name-only", rev))


def added_since(ctx: Ctx, store: Path, rev: str) -> list[str]:
    return _lines(_git(ctx, store, "log", f"{rev}..HEAD", "--diff-filter=A", "--name-only",
                       "--format="))


def all_history_files(ctx: Ctx, store: Path) -> list[str]:
    return sorted(set(_lines(_git(ctx, store, "log", "--name-only", "--format="))))
