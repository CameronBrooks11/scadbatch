# scadbatch

Batch export models from parametric OpenSCAD designs using CSV or Customizer JSON parameter
sets.

One `.scad` model plus a list of parameter sets gives you one output file per set — in any format
OpenSCAD can write, several at a time, with a machine-readable record of what happened.

```
scadbatch export model.scad params.csv out/
```

No runtime dependencies beyond Python 3.10 and OpenSCAD.

## Install

```
pip install scadbatch
```

Or download a standalone binary for Windows, macOS or Linux from
[Releases](https://github.com/CameronBrooks11/scadbatch/releases) — no Python needed.

OpenSCAD itself is not bundled. Install it from [openscad.org](https://openscad.org/downloads.html)
and either put it on `PATH`, set `$OPENSCAD`, or pass `--openscad-path`.

## Quick start

A parameter file, one row per model:

```csv
exported_filename,width,height,depth
cube_small,10,10,10
cube_medium,20,20,20
cube_large,30,30,30
```

Export every row:

```
scadbatch export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.csv out/
```

Three STLs in `out/`, named from the first column. A parameter the file does not mention keeps
the default from the `.scad` file, so list only what varies.

To see the OpenSCAD command line for each case without running anything, add `--dry-run`.

### From Python

```python
from scadbatch import batch_export, detect_engine

engine = detect_engine()

result = batch_export(
    scad_file="examples/simpleCube/simpleCube.scad",
    parameter_file="examples/simpleCube/simpleCube.csv",
    output_folder="out",
    openscad_path=engine.path,
    export_format="binstl",
    selection="0-1",
    sequential=False,
    formats=("stl",),
    jobs=2,
)

for r in result.results:
    print(f"{r.name:14} {r.format}  ok={r.ok}  {r.duration:.2f}s  {r.output_path}")

print(f"failures={len(result.failures)} with_errors={len(result.with_errors)}")
```

```
cube_small     stl  ok=True  0.03s  out/cube_small.stl
cube_medium    stl  ok=True  0.03s  out/cube_medium.stl
failures=0 with_errors=0
```

The library configures no logging handlers of its own, so add `logging.basicConfig()` to see the
progress messages the CLI prints.

### The GUI

```
scadbatch gui
```

Select the `.scad` file, the parameter file and an output folder; set the format, a selection
range and the parameter file's encoding; watch the log; and convert between CSV and JSON.

## Documentation

- **[docs/parameters.md](docs/parameters.md)** — the CSV and JSON formats, what a blank cell
  means, how a cell becomes an OpenSCAD literal, how output files are named, and what is refused
- **[docs/execution.md](docs/execution.md)** — parallelism, formats, timeouts, skipping existing
  output, and the run summary JSON
- **[docs/related-tools.md](docs/related-tools.md)** — the other tools that do this, what each is
  good at, and when a shell loop is the right answer

## Commands

| command | what it does |
| --- | --- |
| `scadbatch export <scad> <params> <out/>` | export one file per parameter set |
| `scadbatch csv2json <csv> <json>` | CSV to a Customizer parameter-set file |
| `scadbatch json2csv <json> <csv>` | and back |
| `scadbatch gui` | the graphical interface |

`scadbatch <command> --help` lists every flag. The ones worth knowing early:

| flag | |
| --- | --- |
| `--format EXT` | `stl`, `off`, `3mf`, `png`, `csg`, … Repeat for several at once |
| `--select` | which sets to export: `0-5`, `1-3,7`, `every:2 in 0-10`, `from:5` |
| `-j N`, `--jobs N` | how many OpenSCAD processes at once |
| `--dry-run`, `-n` | print the commands, run nothing |
| `--timeout SECONDS` | kill a case that hangs, keep the batch going |
| `--summary run.json` | record the run for CI to assert against |
| `--name-template` | e.g. `'{name}_d{diameter}'`, `'part_{index:03d}'` |

The conversions read values with the same rules the exporter uses, so a cell means the same
thing either way. Converting to JSON is lossy for a few types that current OpenSCAD builds
ignore in a parameter-set file — nested vectors, ranges and `undef` — and each is warned about;
export the CSV directly to apply those.

## Why this rather than a shell loop

For a few numeric parameters, a shell loop is fine, and
[docs/related-tools.md](docs/related-tools.md) shows one. The reasons to reach for a tool are all
the same reason: **OpenSCAD exits 0 when it does the wrong thing.**

- A value it cannot convert to the parameter's declared type is ignored, leaving the default, with
  no warning. A typo in a column name gives you a full set of outputs built at the defaults.
- `-D` takes an OpenSCAD expression, not a value, so `-D msg=hello` sets `msg` to undef.
- Several `ERROR:` conditions — an unreadable parameter file, a missing font — print an error and
  still exit 0.

So parameter files that OpenSCAD would misread are refused up front, with a message naming the
file and the place in it; values are serialised through one documented set of rules; and
`--summary` records per-case status plus `counts.errors`, which counts cases that printed an
error **whatever the exit status**, so CI has something to gate on.

## Examples

`examples/` has three projects, each with a `.scad`, a `.csv` and a `.json`:

| | |
| --- | --- |
| `simpleCube` | a cube in three sizes — the smallest thing that shows the idea |
| `candleStand` | from the [OpenSCAD parametric examples](https://github.com/openscad/openscad/tree/master/examples/Parametric) |
| `sign` | adjustable message, size and resolution, same source |

## Used by

Models and projects this has been used on:

- **[SnapTessSCAD](https://github.com/uwo-fast/SnapTessSCAD)**
- **[Open Source Nasopharyngeal Swab and UV Curing System](https://github.com/uwo-fast/OpenNasopharyngealSwab)** —
  [HardwareX paper](https://www.hardware-x.com/article/S2468-0672(20)30044-4/fulltext)
- **[Customizable Christmas Name Ornament](https://github.com/CameronBrooks11/ChristmasNameOrnament/)** —
  after [the original by Lyl3](https://www.thingiverse.com/thing:4681765)
- the `candleStand` and `sign` parametric examples above

## Contributing and support

Contributions are welcome, and a bug report with a reproduction is as useful as a patch.

- [CONTRIBUTING.md](CONTRIBUTING.md) — setting up, the checks to run, and how changes are organised: one issue, one branch, one pull request
- [SUPPORT.md](SUPPORT.md) — where to ask, what to include, and what response to expect
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant 2.1
- [CHANGELOG.md](CHANGELOG.md) — what changed in each release, with the pull request behind each entry
- [docs/releasing.md](docs/releasing.md) — how a release is cut

## Citing

[CITATION.cff](CITATION.cff) carries the metadata GitHub's "Cite this repository" button reads.
A DOI will be added once a release is archived on Zenodo.

## Prior art

This started as a Python port of
[OutwardBuckle/OpenSCAD-Bulk-Export](https://github.com/OutwardBuckle/OpenSCAD-Bulk-Export), and
also took ideas from
[18107/OpenSCAD-batch-export-stl](https://github.com/18107/OpenSCAD-batch-export-stl).
[docs/related-tools.md](docs/related-tools.md) says what each does and when to prefer it.

## License

AGPL v3. See [LICENSE](LICENSE).
