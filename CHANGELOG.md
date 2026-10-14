# Changelog

Notable changes to scadbatch. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

Entries are reconstructed from the merged pull requests, which are linked so the reasoning and
the measurements behind each change stay reachable.

Not every commit appears here. `v1.1.0..main` is 81 commits, of which 36 are squashed pull
requests; the other 45 are direct pushes, almost all paper revisions, figures and examples from
November and December 2024, including the automated `(auto) Paper PDF Draft` commits. None of
them changes the tool.

Of the 36 pull requests, seven are left out because nothing about them is visible to someone
using the tool: dependency pin bumps (#1, #2, #47), the version bump that cut 2.0.0rc1 (#52),
the paper-draft workflow (#38), and the two fixes to the release workflow's own frozen-GUI
self-check (#53, #54). The release workflow itself is listed, under 2.0.0rc1, because what it
produces is something a user gets.

## [Unreleased]

Everything here landed after `2.0.0rc1` and will ship in `2.0.0`.

### Changed — breaking

- A blank or whitespace-only CSV cell now leaves that parameter unset, so the model's own
  default applies, instead of passing the empty string. OpenSCAD cannot read `""` as a number:
  it warns, falls back and still exits 0, so the previous behaviour built a model the row never
  asked for. To ask for the empty string, give a cell whose text is `""`. ([#67])
- Parameter files whose values OpenSCAD would silently misread are now refused, rather than
  exported with geometry the file never asked for. Each of these previously exited 0 with the
  wrong result, and each refusal now names the file and the place in it:
  - a `NaN`, `Infinity` or `-Infinity` token anywhere in the file, which OpenSCAD's reader
    refuses wholesale — so one of them made every set export at the model's defaults — and a
    number literal that overflows, which it parses and then cannot use ([#73])
  - the same name given twice at any level. For a repeated *set* name this tool kept the last
    and OpenSCAD selects the first, so a run reported values it did not build ([#77])
  - a CSV row whose cell count does not match the header ([#55])

### Added

- `counts.errors` in the `--summary` JSON, and an `errors` list per case: the number of cases
  OpenSCAD printed an error for, including cases it exited 0 on. OpenSCAD exits 0 on several
  `ERROR:` conditions, so a run could report every case `ok` with the geometry wrong and nothing
  to gate on. ([#57])
- A **Parameter File Encoding** field in the GUI, which had no way to override UTF-8 after the
  encoding change in 2.0.0rc1. ([#60])
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, issue forms and a pull request
  template. ([#81])

### Fixed

- A JSON root, `parameterSets`, or individual set that is not an object is refused with a message
  naming which level is wrong. Previously `read_json` raised `AttributeError` or `TypeError` from
  inside itself — `'list' object has no attribute 'items'` for `{"parameterSets": []}` — which
  reached the user as a traceback: `export` catches only `OpenSCADError` and `ValueError`
  (`cli.py:241`), and while the conversion subcommands also catch `TypeError` (`cli.py:260`),
  nothing catches `AttributeError`. ([#64], [#69])
- A `--name-template` may reference a parameter a given row leaves unset; it renders empty
  rather than refusing the whole batch. ([#67])
- `read_csv` reports which parameters each row leaves unset, because OpenSCAD is silent when it
  ignores a value. ([#67])

### Security

- The test and draft-paper workflows now run with `contents: read` rather than the default
  token scope. ([#76])

## [2.0.0rc1] — 2026-09-28

The first release of the rewritten tool. Published to PyPI as
[`scadbatch`](https://pypi.org/project/scadbatch/), with frozen binaries for Linux, macOS and
Windows attached to the GitHub release.

### Changed — breaking

- **Renamed** from `openscad-batch-export` to `scadbatch`: the distribution, the command and the
  importable module. ([#48])
- Packaging moved to `pyproject.toml`; Python 3.10 or newer is required. ([#25])
- `export.py` was split into `params`, `runner` and `cli` behind a documented public API, and
  the core returns structured results and logs instead of printing and exiting, so the CLI owns
  exit codes. ([#29], [#30])
- Parameter files are read and written as UTF-8 — tolerating the byte-order mark Excel writes —
  rather than with the machine's locale encoding, which decoded the same file differently on
  different machines. `--encoding` overrides it. ([#44])
- `--sequential` is deprecated in favour of `--jobs`. ([#37])

### Added

- Export to any format OpenSCAD supports, not only STL. ([#36])
- Customizer JSON is passed to OpenSCAD natively with `-p`/`-P` where the engine supports it,
  so the engine types each value by the model's own default; CSV rows still become `-D` flags.
  ([#34])
- Bounded parallelism with `--jobs`. ([#37])
- `--skip-existing`, `--overwrite` and `--dry-run`. ([#39])
- A per-case `--timeout`, captured OpenSCAD diagnostics, and a machine-readable
  `--summary PATH.json` recording the engine, the inputs and every case. ([#40])
- `--name-template` for output names, with filesystem-safe sanitising and a refusal when two
  cases would produce the same file. ([#41])
- The OpenSCAD executable and its version are detected once per run. ([#33])
- A release workflow: pushing a `v*.*.*` tag verifies the tree, builds the distribution and
  freezes the binaries, then publishes to PyPI with trusted publishing behind a required
  approval, and creates a GitHub release with the binaries attached. Only the PyPI step waits on
  the approval. ([#49])
- A test suite with unit and integration layers, the latter against a real OpenSCAD across a CI
  matrix. ([#26], [#28])
- `ruff`, a `justfile` and a pre-commit configuration. ([#27])

### Fixed

- `-D` values are serialised as deterministic OpenSCAD literals. ([#32])
- CSV and JSON are converted through one value interpretation, so a round trip no longer changes
  what a parameter means. ([#42])
- The `gui` subcommand works in a frozen binary, where the entry module has no parent package.
  ([#51])

## [1.1.0] — 2024-12-01 and [1.0.0] — 2024-11-23

The original `openscad-batch-export`: a single `export.py` with a Tkinter interface, released
before this project kept a changelog. The commit history and the
[release notes](https://github.com/CameronBrooks11/scadbatch/releases) are the record for these
two. They are not reconstructed here, because the intent behind individual commits of that era
is no longer recoverable with any confidence — `updated readme to reflect latest updates`, and
`Fix workflow issues` five times — and a changelog that guesses is worse than one that says it
does not know.

<!-- Contributions from outside the maintainer are credited on the pull requests linked above;
     #64 is from @Jah-yee. -->

[Unreleased]: https://github.com/CameronBrooks11/scadbatch/compare/v2.0.0rc1...HEAD
[2.0.0rc1]: https://github.com/CameronBrooks11/scadbatch/releases/tag/v2.0.0rc1
[1.1.0]: https://github.com/CameronBrooks11/scadbatch/releases/tag/v1.1.0
[1.0.0]: https://github.com/CameronBrooks11/scadbatch/releases/tag/v1.0.0
[#25]: https://github.com/CameronBrooks11/scadbatch/pull/25
[#26]: https://github.com/CameronBrooks11/scadbatch/pull/26
[#27]: https://github.com/CameronBrooks11/scadbatch/pull/27
[#28]: https://github.com/CameronBrooks11/scadbatch/pull/28
[#29]: https://github.com/CameronBrooks11/scadbatch/pull/29
[#30]: https://github.com/CameronBrooks11/scadbatch/pull/30
[#32]: https://github.com/CameronBrooks11/scadbatch/pull/32
[#33]: https://github.com/CameronBrooks11/scadbatch/pull/33
[#34]: https://github.com/CameronBrooks11/scadbatch/pull/34
[#36]: https://github.com/CameronBrooks11/scadbatch/pull/36
[#37]: https://github.com/CameronBrooks11/scadbatch/pull/37
[#39]: https://github.com/CameronBrooks11/scadbatch/pull/39
[#40]: https://github.com/CameronBrooks11/scadbatch/pull/40
[#41]: https://github.com/CameronBrooks11/scadbatch/pull/41
[#42]: https://github.com/CameronBrooks11/scadbatch/pull/42
[#44]: https://github.com/CameronBrooks11/scadbatch/pull/44
[#48]: https://github.com/CameronBrooks11/scadbatch/pull/48
[#49]: https://github.com/CameronBrooks11/scadbatch/pull/49
[#51]: https://github.com/CameronBrooks11/scadbatch/pull/51
[#55]: https://github.com/CameronBrooks11/scadbatch/pull/55
[#57]: https://github.com/CameronBrooks11/scadbatch/pull/57
[#60]: https://github.com/CameronBrooks11/scadbatch/pull/60
[#64]: https://github.com/CameronBrooks11/scadbatch/pull/64
[#67]: https://github.com/CameronBrooks11/scadbatch/pull/67
[#69]: https://github.com/CameronBrooks11/scadbatch/pull/69
[#73]: https://github.com/CameronBrooks11/scadbatch/pull/73
[#76]: https://github.com/CameronBrooks11/scadbatch/pull/76
[#77]: https://github.com/CameronBrooks11/scadbatch/pull/77
[#81]: https://github.com/CameronBrooks11/scadbatch/pull/81
