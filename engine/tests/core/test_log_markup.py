"""Log messages are plain text: angle brackets and backslashes are never loguru markup."""

from __future__ import annotations

import pytest
from loguru import logger

from devboost.core import log


@pytest.mark.parametrize(
    "text",
    ["clone it by hand (`git clone <repo> ~/Vault`)", "<red>not a tag</red>", r"a\b \<x>", "</>"],
)
def test_messages_print_verbatim(text: str) -> None:
    seen: list[str] = []
    sink = logger.add(lambda m: seen.append(str(m).rstrip("\n")), format="{message}")
    try:
        for fn, prefix in ((log.info, ""), (log.warn, "warn "), (log.error, "error ")):
            seen.clear()
            fn(text)
            assert seen == [prefix + text]
    finally:
        logger.remove(sink)
