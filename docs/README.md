# docs

- **[parameters.md](parameters.md)** — the CSV and Customizer JSON formats: what a blank cell
  means, how cell text becomes an OpenSCAD literal, how output files are named, which parameter
  files are refused and why.
- **[execution.md](execution.md)** — running a batch: parallelism, output formats, timeouts,
  skipping existing output, and the `--summary` JSON, including why `counts.errors` is not
  `counts.failed`.
- **[related-tools.md](related-tools.md)** — the other tools that batch-export from OpenSCAD,
  what each is good at, when a plain shell loop is the right answer, and why this exists
  separately.
- **[releasing.md](releasing.md)** — how a release is cut, and what the release workflow actually
  does.

The [README](../README.md) is the starting point; these go deeper on one thing each.
