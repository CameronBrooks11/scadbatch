# Contributing

Thanks for your interest in contributing. Bug reports with a reproduction are as welcome as
code.

## Getting set up

```sh
git clone https://github.com/CameronBrooks11/scadbatch.git
cd scadbatch
just setup
```

`just --list` shows every recipe. Python 3.10 or newer; dependencies are managed with
[uv](https://docs.astral.sh/uv/), which `just setup` drives.

You also need OpenSCAD to run the integration tests. Either put `openscad` on your `PATH` or
point `$OPENSCAD` at the binary:

```sh
OPENSCAD=/path/to/openscad just test
```

Without one, the integration tests skip and the rest of the suite still runs — `pytest -rs`
prints the reason, which `just test` does not. CI tests against both a stable and a nightly
OpenSCAD, because the two disagree about enough to matter.

## Before you open a pull request

```sh
just check && just test
```

`just check` is what CI runs: formatting and lint, non-mutating. `just fmt` fixes formatting
locally. Do not skip CI.

There is a `.pre-commit-config.yaml` in the repo, but nothing installs or runs it — it is not
in the dev dependencies, the justfile or any workflow, so a fresh clone has no hooks. `just
check && just test` is the gate that is actually enforced (#82).

## How changes are organised

- **One issue, one branch off `main`, one pull request.** Do not stack a pull request on an
  unmerged branch; open the next one once the previous has landed. Two pull requests that touch
  the same file go in sequence, not in parallel.
- **One logical change per commit.** Unrelated fixes belong in separate commits, and usually in
  separate pull requests.
- The commit history is meant to be the real one. No timestamp shaping, no spacing changes out
  to look organic, no filler commits.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): description`, with
`feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore` or `build` as the type.

```
fix(params): reject a CSV row that does not match the header
feat(runner): count and report the errors OpenSCAD exits 0 on
docs: say what counts.errors does not cover
```

Imperative mood, lowercase, no trailing period, subject under 72 characters. Put the reasoning
in the body, separated by a blank line, and reference issue numbers there rather than in the
subject. The `(#NN)` on every subject in `git log` is the pull request number, which GitHub
appends when it squashes; you do not write it.

## Tests

A change to behaviour needs a test that fails without it. The useful check is to break the
thing the test is named for and watch that test go red — a test that passes both before and
after is testing something else.

Where a message matters, test the behaviour rather than the wording. Pinning a sentence keeps a
wrong explanation alive and breaks on every rewording.

The suite leans on a stand-in OpenSCAD (see `tests/conftest.py`) so most of it runs anywhere.
Reach for the real engine when the question is what OpenSCAD actually does — several of this
project's rules exist because the engine's behaviour turned out not to be what the code assumed.

## Reporting a bug

Open an issue with the `.scad` file, the parameter file, the exact command, and what you
expected versus what happened. A reproduction is worth more than a description: a parameter file
small enough to paste is ideal. Include the OpenSCAD version — `openscad --version` — because
behaviour differs between releases.

## Licence

By contributing you agree that your contributions are licensed under the project's licence; see
[LICENSE](LICENSE).
