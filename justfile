# Python (uv) task runner

set dotenv-load := false

# Default: show available recipes
default:
    @just --list

# Install dependencies and set up environment
setup:
    uv sync

# Install the git pre-commit hooks (opt-in; CI enforces the same checks regardless)
#
# Deliberately not part of `setup`: pre-commit builds a hook environment per repo on first
# run, which needs network access a confined session may not have, and a hook that cannot
# build leaves that session unable to commit at all. CI runs the same hooks, so skipping
# this costs a round trip, not a missed check.
[doc("Install the git pre-commit hooks (opt-in)")]
hooks:
    uv run pre-commit install

# Format code (mutates working tree — use locally)
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Verify formatting (non-mutating — use in CI)
fmt-check:
    uv run ruff format --check .

# Run linters
lint:
    uv run ruff check .

# Format + lint (non-mutating — safe for CI)
check: fmt-check lint

# Run tests (integration tests skip when OpenSCAD is not on PATH)
test:
    uv run pytest

# Remove build artifacts
clean:
    rm -rf .venv dist .pytest_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
