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
