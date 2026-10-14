# Running a batch

One OpenSCAD process is started per parameter set per output format. This page covers how many
run at once, what happens when one misbehaves, and what the run records about itself.

## Parallelism

```
scadbatch export model.scad params.csv out/ --jobs 4
```

`--jobs` bounds how many OpenSCAD processes run at once, defaulting to the number of CPUs.
OpenSCAD renders single-threaded for most work, so the useful setting is usually the core count;
the reason to go lower is memory, since each process holds its own geometry.

`--sequential` is deprecated and means `--jobs 1`.

## Output formats

```
scadbatch export model.scad params.csv out/ --format 3mf
scadbatch export model.scad params.csv out/ --format stl --format png
```

`--format` takes an extension, as the detected OpenSCAD's `-o` accepts it: `stl`, `off`, `3mf`,
`csg`, `png` and whatever else the build supports. Repeat it to export every case in several
formats — each becomes its own output file and its own OpenSCAD run.

A format the detected build does not advertise is **warned about, not refused**, because the
list of advertised formats is itself version-dependent and a wrong refusal is worse than a
failed export with OpenSCAD's own message.

`--export-format` chooses the STL flavour, `binstl` (default) or `asciistl`, and applies only to
`stl`. For `png` there are `--camera`, `--imgsize` and `--colorscheme`, passed straight through.

## Not repeating work

```
scadbatch export model.scad params.csv out/ --skip-existing
```

`--skip-existing` leaves a case alone when its output file is already there, which makes an
interrupted batch resumable. `--overwrite` is the default and states the same thing explicitly.

Neither looks at content or timestamps: existence is the whole test. A parameter file that
changed since the last run needs `--overwrite`, or the stale file stays.

## Seeing the commands without running them

```
scadbatch export model.scad params.csv out/ --dry-run
scadbatch -v export model.scad params.csv out/
```

`--dry-run` prints the OpenSCAD command line for each case and runs nothing. `-v` prints the
same commands while actually running.

This is the fastest way to answer "why did that come out wrong" — the command line shows exactly
what OpenSCAD was told, including how each value was serialised.

## Timeouts

```
scadbatch export model.scad params.csv out/ --timeout 300
```

A case that runs longer is killed and recorded as timed out, distinct from a failure. Without
it, one pathological parameter set can hang a batch indefinitely; with it, the batch finishes
and the summary says which case did not.

## The run summary

```
scadbatch export model.scad params.csv out/ --summary run.json
```

A machine-readable record of the whole run — what it was told, which OpenSCAD answered, and what
happened to every case. This is the output to assert against in CI, rather than parsing log
lines.

```json
{
  "openscad_batch_export": "2.0.0rc1",
  "started_at": "2026-10-14T03:35:01+00:00",
  "openscad": {
    "path": "/usr/bin/openscad",
    "version": "2026.08.01"
  },
  "inputs": {
    "scad_file": "examples/simpleCube/simpleCube.scad",
    "parameter_file": "examples/simpleCube/simpleCube.csv",
    "output_folder": "out",
    "formats": ["stl"],
    "export_format": "binstl",
    "selection": "0-1",
    "jobs": 12,
    "skip_existing": false,
    "timeout": null,
    "name_template": null,
    "encoding": "utf-8-sig",
    "image_options": {}
  },
  "dry_run": false,
  "total_duration": 0.0313,
  "counts": { "ok": 2, "failed": 0, "timeout": 0, "skipped": 0, "errors": 0 },
  "results": [
    {
      "index": 0,
      "set_name": "cube_small",
      "name": "cube_small",
      "output_path": "out/cube_small.stl",
      "format": "stl",
      "status": "ok",
      "returncode": 0,
      "duration": 0.03,
      "stderr": "",
      "warnings": [],
      "errors": [],
      "command": ["openscad", "-o", "out/.cube_small.part.stl", "--export-format=binstl",
                  "-Ddepth=10", "-Dheight=10", "-Dwidth=10", "simpleCube.scad"]
    }
  ]
}
```

That is a real summary, with the long absolute paths shortened, the durations rounded and the
second case removed for length.

The `-o` in `command` is a `.part` sibling of the output, not the output itself: each case writes
to `.<name>.part.<ext>` and is renamed on success, so an interrupted or failed run never leaves a
truncated file where a finished one should be. A dry-run summary records the final path, since
nothing is written.

Recording the OpenSCAD path and version is the point of the `openscad` block: the same parameter
file and the same model produce different geometry across OpenSCAD releases, so a result without
the engine version is not reproducible.

### counts.errors is not counts.failed

`status` is one of `ok`, `failed`, `timeout`, `skipped`, or `dry-run` under `--dry-run`, and
`counts` tallies the first four.
`counts.errors` is **separate**, and counts something the others cannot see: cases where
OpenSCAD printed an error line **whatever its exit status**.

OpenSCAD exits 0 on several `ERROR:` conditions — a parameter file it could not open, a font
file it could not read. Before this existed, such a run reported every case `ok` while the
geometry was wrong, and there was nothing to gate on.

A missing font *family* is worse still, and this does not catch it: OpenSCAD substitutes one
silently, with no message at all.

So in CI, gate on `counts.errors` as well as `counts.failed`:

```python
import json

s = json.load(open("run.json"))
assert s["counts"]["failed"] == 0, "an export failed"
assert s["counts"]["errors"] == 0, "OpenSCAD printed an error"
```

Per case, `errors` holds those lines and `warnings` holds **every** message line OpenSCAD
printed — `WARNING:`, `ECHO:`, `DEPRECATED:` and `ERROR:` alike — with `errors` being the subset
whose prefix marks it an error. The name is narrower than the content.

One consequence worth knowing: because the classification is by line prefix, a model that
`echo()`s a string beginning with `ERROR:` is counted as having printed an error, and a
multi-line echoed payload continues on a line with no prefix at all. See issue #59.

## Which OpenSCAD is used

In order: `--openscad-path`, then `$OPENSCAD`, then `openscad` on `PATH`, then the platform's
usual install location. The choice and the version are resolved once per run and recorded in the
summary.

Only the last two are a fallback chain. `--openscad-path` and `$OPENSCAD` name a specific
executable, so one that does not resolve is an error rather than a reason to look elsewhere:

```
$ scadbatch export … --openscad-path /nope/openscad
Error: OpenSCAD executable not found (tried --openscad-path '/nope/openscad'). …
$ echo $?
1
```

```
scadbatch export model.scad params.csv out/ --openscad-path /opt/openscad/bin/openscad
OPENSCAD=/opt/openscad/bin/openscad scadbatch export model.scad params.csv out/
```

The detected version decides whether parameter sets can be passed natively with `-p`/`-P`, so an
old build changes how a JSON file is handled — see
[How values reach OpenSCAD](parameters.md#how-values-reach-openscad).

## Exit codes

`0` when every case that ran succeeded, and `1` when any case failed or timed out, or when the
parameter file was refused.

A refusal happens before any export runs, so a malformed parameter file costs nothing but the
`--version` and `--help` that detection already needed — the second is how the advertised output
formats are read:

```
$ scadbatch export model.scad ragged.csv out/
Error: ragged.csv line 2: this row has 3 cells but the header has 2 columns, so it is
not clear which value belongs to which parameter. ...
$ echo $?
1
```

A failing export reports itself both ways — `counts.failed` for the non-zero exit and
`counts.errors` for the printed error line:

```
counts: {'ok': 0, 'failed': 1, 'timeout': 0, 'skipped': 0, 'errors': 1}
```
