# Python project (uv-managed)

This skeleton uses [uv](https://docs.astral.sh/uv/) for project + dependency management
and [ruff](https://docs.astral.sh/ruff/) for linting/formatting. Editor intelligence is
provided by `basedpyright` via the fresh editor (see `python-lsp`).

## Getting started

```sh
# Initialise a new project in the current directory (if starting fresh):
uv init

# Add a runtime dependency:
uv add requests

# Add a dev-only dependency:
uv add --dev pytest

# Run a command inside the project's virtual environment:
uv run python main.py
uv run pytest
```

`uv` creates and manages `.venv/` and `uv.lock` automatically; no manual virtualenv
activation is required.
