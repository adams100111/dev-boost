"""Low-level, idempotent user operations. Every effect goes through ctx.ex.run."""

from __future__ import annotations

from devboost.model import Ctx


def exists(ctx: Ctx, user: str) -> bool:
    return ctx.ex.run(["getent", "passwd", user]).ok


def uid_of(ctx: Ctx, user: str) -> int:
    return int(ctx.ex.run(["id", "-u", user]).stdout.strip())


def admin_group(ctx: Ctx) -> str:
    return "wheel" if ctx.ex.run(["getent", "group", "wheel"]).ok else "sudo"


def ensure_user(ctx: Ctx, user: str, *, shell: str, home: str | None = None) -> None:
    if exists(ctx, user):
        return
    argv = ["useradd", "-m", "-s", shell]
    if home is not None:
        argv += ["-d", home]
    argv.append(user)
    ctx.ex.run(argv, sudo=True)


def set_authorized_keys(ctx: Ctx, user: str, home: str, keys: tuple[str, ...]) -> None:
    if not keys:
        return
    ssh = f"{home}/.ssh"
    ctx.ex.run(["install", "-d", "-m", "700", "-o", user, "-g", user, ssh], sudo=True)
    ctx.ex.run(["tee", f"{ssh}/authorized_keys"], sudo=True, stdin="\n".join(keys) + "\n")
    ctx.ex.run(["chown", f"{user}:{user}", f"{ssh}/authorized_keys"], sudo=True)
    ctx.ex.run(["chmod", "600", f"{ssh}/authorized_keys"], sudo=True)


def set_password(ctx: Ctx, user: str, password: str) -> None:
    ctx.ex.run(["chpasswd"], sudo=True, stdin=f"{user}:{password}\n")


def lock(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["usermod", "-L", "--expiredate", "1", user], sudo=True)


def unlock(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["usermod", "-U", user], sudo=True)
    ctx.ex.run(["usermod", "-e", "", user], sudo=True)


def terminate_sessions(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["loginctl", "terminate-user", user], sudo=True)
    ctx.ex.run(["pkill", "-u", user], sudo=True)


def delete(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["userdel", "-r", user], sudo=True)


def enable_linger(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["loginctl", "enable-linger", user], sudo=True)


def disable_linger(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["loginctl", "disable-linger", user], sudo=True)


# ---------------------------------------------------------------------------
# Privilege tiers: admin group + visudo-validated sudoers drop-in
# ---------------------------------------------------------------------------

from devboost.accounts.config import AccountsError, Privilege  # noqa: E402

_STAGE = "/etc/sudoers.d/.devboost-stage"


def in_admin_group(ctx: Ctx, user: str) -> bool:
    groups = ctx.ex.run(["id", "-nG", user]).stdout.split()
    return "wheel" in groups or "sudo" in groups


def add_admin_group(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["usermod", "-aG", admin_group(ctx), user], sudo=True)


def remove_admin_group(ctx: Ctx, user: str) -> None:
    # Best-effort: drop from whichever admin group exists; ignore "not a member".
    ctx.ex.run(["gpasswd", "-d", user, admin_group(ctx)], sudo=True)


def sudoers_path(user: str) -> str:
    return f"/etc/sudoers.d/devboost-{user}"


def sudoers_content(
    user: str, privilege: Privilege, sudo_commands: tuple[str, ...]
) -> str | None:
    if privilege in ("none", "full"):
        return None
    if privilege == "nopasswd":
        return f"{user} ALL=(ALL) NOPASSWD: ALL\n"
    # allowlist
    cmds = ", ".join(sudo_commands)
    return f"{user} ALL=(ALL) NOPASSWD: {cmds}\n"


def write_sudoers(ctx: Ctx, user: str, content: str) -> None:
    """Stage -> validate with visudo -> fix mode/owner -> atomic move. Raise on invalid."""
    ctx.ex.run(["tee", _STAGE], sudo=True, stdin=content)
    if not ctx.ex.run(["visudo", "-cf", _STAGE], sudo=True).ok:
        ctx.ex.run(["rm", "-f", _STAGE], sudo=True)
        raise AccountsError(f"sudoers content for {user!r} failed visudo validation")
    ctx.ex.run(["chown", "root:root", _STAGE], sudo=True)
    ctx.ex.run(["chmod", "0440", _STAGE], sudo=True)
    ctx.ex.run(["mv", "-f", _STAGE, sudoers_path(user)], sudo=True)


def remove_sudoers(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["rm", "-f", sudoers_path(user)], sudo=True)


# ---------------------------------------------------------------------------
# Resource caps: systemd slice + drop-in + daemon-reload + set-property
# ---------------------------------------------------------------------------

_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def _to_bytes(size: str) -> int:
    s = size.rstrip("iB")
    if s and s[-1] in _UNITS:
        return int(float(s[:-1]) * _UNITS[s[-1]])
    return int(s)


def mem_high(ram: str) -> str:
    """≈90% of *ram*, emitted in bytes (systemd accepts a bare byte count)."""
    return str(int(_to_bytes(ram) * 0.9))


def slice_dropin_text(ram: str | None, cpu: str | None, tasks: int | None) -> str | None:
    if ram is None and cpu is None and tasks is None:
        return None
    lines = ["[Slice]"]
    if ram is not None:
        lines.append(f"MemoryHigh={mem_high(ram)}")
        lines.append(f"MemoryMax={ram}")
    if cpu is not None:
        lines.append(f"CPUQuota={cpu}")
    if tasks is not None:
        lines.append(f"TasksMax={tasks}")
    return "\n".join(lines) + "\n"


def _slice_dir(uid: int) -> str:
    return f"/etc/systemd/system/user-{uid}.slice.d"


def _slice_props(ram: str | None, cpu: str | None, tasks: int | None) -> list[str]:
    props: list[str] = []
    if ram is not None:
        props += [f"MemoryHigh={mem_high(ram)}", f"MemoryMax={ram}"]
    if cpu is not None:
        props.append(f"CPUQuota={cpu}")
    if tasks is not None:
        props.append(f"TasksMax={tasks}")
    return props


def set_slice(ctx: Ctx, uid: int, *, ram: str | None, cpu: str | None, tasks: int | None) -> None:
    text = slice_dropin_text(ram, cpu, tasks)
    if text is None:
        return
    d = _slice_dir(uid)
    ctx.ex.run(["install", "-d", "-m", "755", d], sudo=True)
    ctx.ex.run(["tee", f"{d}/50-devboost.conf"], sudo=True, stdin=text)
    ctx.ex.run(["systemctl", "daemon-reload"], sudo=True)
    ctx.ex.run(["systemctl", "set-property", f"user-{uid}.slice", *_slice_props(ram, cpu, tasks)],
               sudo=True)


def clear_slice(ctx: Ctx, uid: int) -> None:
    ctx.ex.run(["rm", "-f", f"{_slice_dir(uid)}/50-devboost.conf"], sudo=True)
    ctx.ex.run(["systemctl", "daemon-reload"], sudo=True)
    ctx.ex.run(
        ["systemctl", "set-property", "--runtime", f"user-{uid}.slice",
         "MemoryHigh=", "MemoryMax=", "CPUQuota=", "TasksMax="],
        sudo=True,
    )


# ---------------------------------------------------------------------------
# Disk quota: tiered, best-effort per-user cap
# ---------------------------------------------------------------------------

from devboost.core.errors import InstallError, UnsupportedOS  # noqa: E402
from devboost.exec.primitives import pkg  # noqa: E402


def fstype_of(ctx: Ctx, path: str) -> str:
    return ctx.ex.run(["findmnt", "-no", "FSTYPE", "--target", path]).stdout.strip()


def _mountpoint_of(ctx: Ctx, path: str) -> str:
    return ctx.ex.run(["findmnt", "-no", "TARGET", "--target", path]).stdout.strip() or "/"


def ensure_subvolume(ctx: Ctx, path: str) -> None:
    if not ctx.ex.run(["btrfs", "subvolume", "show", path]).ok:
        ctx.ex.run(["btrfs", "subvolume", "create", path], sudo=True)


def set_quota(ctx: Ctx, user: str, home: str, size: str) -> str:
    """Best-effort per-user disk cap. Returns 'enforced' or 'skipped: <reason>'. Never raises."""
    fs = fstype_of(ctx, home)
    if fs == "btrfs":
        ctx.ex.run(["btrfs", "quota", "enable", "/"], sudo=True)
        ctx.ex.run(["btrfs", "qgroup", "limit", size, home], sudo=True)
        return "enforced"
    if fs in ("ext4", "xfs"):
        mnt = _mountpoint_of(ctx, home)
        if not ctx.ex.run(["quotaon", "-pu", mnt]).ok:
            return f"skipped: quota not enabled on {mnt} (needs usrquota mount + reboot)"
        if not ctx.ex.which("setquota"):
            try:
                pkg.install(ctx, "quota")
            except (InstallError, UnsupportedOS) as exc:
                return f"skipped: cannot install quota tools — {exc}"
        ctx.ex.run(["setquota", "-u", user, "0", size, "0", "0", mnt], sudo=True)
        return "enforced"
    return f"skipped: disk quota unsupported on {fs or 'unknown fs'}"


def clear_quota(ctx: Ctx, user: str, home: str) -> None:
    fs = fstype_of(ctx, home)
    if fs == "btrfs":
        ctx.ex.run(["btrfs", "qgroup", "limit", "none", home], sudo=True)
    elif fs in ("ext4", "xfs"):
        mnt = _mountpoint_of(ctx, home)
        ctx.ex.run(["setquota", "-u", user, "0", "0", "0", "0", mnt], sudo=True)
