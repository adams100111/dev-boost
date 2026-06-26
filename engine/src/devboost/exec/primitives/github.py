"""github primitive — GitHub REST via stdlib HTTP (not a bundled library, not the gh CLI).

The HTTP transport is injectable so tests are hermetic (no network).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import NamedTuple

from devboost.core.errors import GithubError

API = "https://api.github.com"


class HttpResponse(NamedTuple):
    status: int
    body: str


# (method, url, headers, body) -> HttpResponse
HttpFn = Callable[[str, str, Mapping[str, str], bytes | None], HttpResponse]


def _urllib_http(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> HttpResponse:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310 — fixed api.github.com host
            return HttpResponse(resp.status, resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read().decode("utf-8"))


def _headers(pat: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def upload_ssh_key(
    pat: str,
    pubkey_body: str,
    title: str,
    *,
    api: str = API,
    http: HttpFn = _urllib_http,
) -> bool:
    """Register a user SSH key. Idempotent: returns True if title/key already exist.

    Returns True on success or already-registered; raises GithubError on API failure.
    """
    key_body = pubkey_body.strip()
    resp = http("GET", f"{api}/user/keys", _headers(pat), None)
    if not (200 <= resp.status < 300):
        raise GithubError(f"GET /user/keys failed (HTTP {resp.status})")
    existing = json.loads(resp.body or "[]")
    for k in existing:
        if k.get("title") == title or k.get("key") == key_body:
            return True
    payload = json.dumps({"title": title, "key": key_body}).encode("utf-8")
    headers = {**_headers(pat), "Content-Type": "application/json"}
    resp = http("POST", f"{api}/user/keys", headers, payload)
    if not (200 <= resp.status < 300):
        raise GithubError(f"POST /user/keys failed (HTTP {resp.status})")
    return True


def add_deploy_key(
    pat: str,
    owner: str,
    repo: str,
    pubkey_body: str,
    title: str,
    *,
    read_only: bool = False,
    api: str = API,
    http: HttpFn = _urllib_http,
) -> bool:
    """Register a repo deploy key. Idempotent by title/key; raises GithubError on failure."""
    key_body = pubkey_body.strip()
    path = f"{api}/repos/{owner}/{repo}/keys"
    resp = http("GET", path, _headers(pat), None)
    if not (200 <= resp.status < 300):
        raise GithubError(f"GET deploy keys failed (HTTP {resp.status})")
    for k in json.loads(resp.body or "[]"):
        if k.get("title") == title or k.get("key") == key_body:
            return True
    payload = json.dumps({"title": title, "key": key_body, "read_only": read_only}).encode("utf-8")
    headers = {**_headers(pat), "Content-Type": "application/json"}
    resp = http("POST", path, headers, payload)
    if not (200 <= resp.status < 300):
        raise GithubError(f"POST deploy key failed (HTTP {resp.status})")
    return True
