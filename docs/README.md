# scadbatch

One `.scad` model plus a list of parameter sets gives you one output file per set per output
format — in any format OpenSCAD can write, several at a time, with a machine-readable record of
what happened.

These pages go deeper on one thing each. For installation and a first run, start from the
[project README](https://github.com/CameronBrooks11/scadbatch#readme).

- **[Parameter files](parameters.md)** — the CSV and Customizer JSON formats: what a blank cell
  means, how cell text becomes an OpenSCAD literal, how output files are named, which parameter
  files are refused and why.
- **[Running a batch](execution.md)** — parallelism, output formats, timeouts, skipping existing
  output, which OpenSCAD is used, and the `--summary` JSON, including why `counts.errors` is not
  `counts.failed`.
- **[Related tools](related-tools.md)** — the other tools that batch-export from OpenSCAD, what
  each is good at, when a plain shell loop is the right answer, and why this exists separately.
- **[Cutting a release](releasing.md)** — how a release is cut, and what the release workflow
  actually does.
