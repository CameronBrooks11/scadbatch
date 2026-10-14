# Related tools

Batch-exporting from OpenSCAD is a problem many people have solved for themselves. This page
says what else exists, what each does, and when it is the better choice — including the cases
where it is.

scadbatch grew out of the first of these. It is not the first tool to do this, and the
contribution is the parts that come after "it runs the exports": refusing a parameter file it
cannot read faithfully, serialising values to OpenSCAD literals correctly, and recording a run in
a form you can assert against.

## Tools that do roughly this

### OutwardBuckle/OpenSCAD-Bulk-Export

PowerShell, Windows and Linux.
<https://github.com/OutwardBuckle/OpenSCAD-Bulk-Export>

The closest prior art and the direct inspiration for this project. It exports from a CSV or a
Customizer JSON, converts CSV to JSON, generates a CSV from a `.scad` file, handles STL, OFF,
AMF, 3MF, DXF, SVG and PNG, takes camera arguments for PNG, has an overwrite switch, and runs
exports in parallel on PowerShell 7+. It also uses the same `exported_filename` column
convention, which scadbatch kept for compatibility.

**Use it instead if** you are on Windows, in a PowerShell shop, and want a single script file
with no Python involved. For straightforward CSV-to-STL work it does the same job.

**What scadbatch adds** is mostly about what happens when something is wrong: a parameter file
whose values OpenSCAD would silently misread is refused rather than exported; a run summary
records the engine version and per-case status for CI; and there is a Python API rather than only
a command line. It also has per-case timeouts, index selection, name templates, and a documented
`-D` serialisation.

### pjaspinski/openscad-batch-exporter

Python.
<https://github.com/pjaspinski/openscad-batch-exporter>

Reads a CSV, builds `-D` flags from the columns, names the output from the joined values, and
runs exports in parallel with the count set by editing a constant in the source. STL only, and
about fifty lines, so it is quick to read and adapt.

One detail to know before adopting it: every value is wrapped in quotes, so a numeric column
reaches OpenSCAD as a string — `-Dwidth="10"` rather than `-Dwidth=10`. Which brings us to the
thing this problem keeps coming back to: serialising a `-D` value is the subtle part. A string
containing a space or a quote, a number, a list, a boolean — each has exactly one correct form,
and getting it wrong produces a command OpenSCAD accepts and misreads.

### mrdarip/OctoSCAD

<https://github.com/mrdarip/OctoSCAD>

Aims at exporting the **cross product** of parameter values from a JSON description, including
range syntax. The README marks its usage "[To be determined]", so it is an idea with a shape
rather than a tool to depend on today — but the idea is a real gap, see
[What none of these do](#what-none-of-these-do).

## Tools that do something else

### 18107/OpenSCAD-batch-export-stl

Python.
<https://github.com/18107/OpenSCAD-batch-export-stl>

Despite the name, not a parameter sweep. It looks for a `module export()` in a `.scad` file and
renders **each statement inside it** to its own file, naming each from the trailing comment on
its line, or from the module call when there is no comment:

```openscad
module export() {
  cube(10);
  sphere(5); //Ball
}
```

produces `cube.stl` and `Ball.stl`.

**Use it instead if** your file contains several distinct models rather than one parametric
model. That is a genuinely different job, and scadbatch does not do it: scadbatch varies
parameters of one model.

### kintel/openscad-benchmark

Shell, OpenSCAD and Python, by OpenSCAD's own maintainer.
<https://github.com/kintel/openscad-benchmark>

A performance harness for OpenSCAD itself — geometry timing, VBO rendering, frame counts — with
scripts to run the benchmarks and analyse the results.

Its `gen_param_sets` is worth knowing about on its own: it takes variable declarations and emits
Customizer JSON for the **cross product** of their values.

```
./gen_param_sets 'N=[2,10]' '$fn=[20,100]' > scalemail.json
```

That composes with scadbatch, which consumes such a file but will not generate one.

**Use it instead if** you are measuring OpenSCAD's performance rather than producing models.

### BelfrySCAD/openscad_test

Python, from the organisation behind BOSL2.
<https://github.com/BelfrySCAD/openscad_test> · `pip install openscad-test`

A test framework that runs OpenSCAD scripts and asserts on what they print. Tests are `[[test]]`
sections in a TOML `.scadtest` file, each with an inline `script` or a `script_file`, variables
passed via `set_vars` (which become `-D` flags), and assertions: `expect_success`,
`assert_echoes`, `assert_warnings`, `assert_no_echoes`, `assert_no_warnings`, plus a per-test
`timeout`. It has a CLI with `-j` for parallelism and a Python API.

```toml
[[test]]
name = "Echo Integer Test"
script = "echo(42);"
expect_success = true
assert_echoes = ["ECHO: 42"]
```

**Use it instead if** you want to assert that a model behaves correctly, rather than to produce
files from it. It is the closest thing here to scadbatch in construction — Python, a CLI and an
API, bounded parallelism, per-case timeouts — and it answers a different question: it tests, and
does not export.

The overlap worth noting is that it classifies OpenSCAD's output lines into echoes, warnings and
errors, which is the same problem `counts.errors` solves here, approached from the other side.

### UnitTestSCAD, SpecSCAD

<https://github.com/HopefulLlama/UnitTestSCAD> · <https://github.com/matths/SpecSCAD>

Test frameworks for OpenSCAD code, unit-style and BDD-style respectively. UnitTestSCAD asserts
about both functions and modules; SpecSCAD's README is explicit that it "tests **only functions**
(not modules), encouraging you to place core logic into reusable functions". They test the
source; scadbatch builds artefacts from it.

### A plain shell loop

```sh
while IFS=, read -r name w h d; do
  openscad -o "out/$name.stl" -D "width=$w" -D "height=$h" -D "depth=$d" model.scad
done < <(tail -n +2 params.csv)
```

Honestly: for a handful of numeric parameters that you control, this is fine, and it is what most
people should start with. Reach for a tool when one of these starts to bite:

- **quoting** — `-D` takes an OpenSCAD *expression*, not a value, so the quotes have to be
  inside it. `-D msg=hello` makes `msg` undef, because `hello` is read as a variable name:

  ```
  $ openscad -o out.stl -D msg=hello d.scad
  WARNING: Ignoring unknown variable "hello" in file d.scad, line 7
  ECHO: msg = undef, n = 1

  $ openscad -o out.stl -D 'msg="hello"' d.scad
  ECHO: msg = "hello", n = 1
  ```

  The shell's own quoting is then a second layer on top of that one, and the loop above is
  already wrong for a CSV field containing a comma.
- **silent wrong results** — a misspelled variable is simply never used, so a typo in a column
  name gives you a full set of outputs built at the defaults, exit 0, no message:

  ```
  $ openscad -o out.stl -Dwdith=99 m.scad
  ECHO: w = 10, h = 20
  ```
- **errors that still exit 0** — an unreadable parameter file, or a font file it cannot read,
  prints `ERROR:` and exits 0, so `set -e` does not catch it.
- **parallelism** — easy to add with `xargs -P`, easy to get wrong in a way that interleaves
  output.
- **wanting to know what happened** — which case produced which file, how long each took, which
  printed warnings.

## What none of these do

Generating the parameter sets, with one partial exception. `gen_param_sets` above does build a
cross product, as part of a benchmarking harness. Otherwise every tool here, scadbatch included,
consumes a list someone else produced — by hand, from a spreadsheet, or from the OpenSCAD
Customizer — and no general cross-product sweep or design-of-experiments selection exists.

## Why a new tool rather than contributing to one of these

The honest answer is that it started as the Python port of a PowerShell script, for a lab that
did not want PowerShell on its machines, and the scope grew from there. A contribution to
OpenSCAD-Bulk-Export would have meant rewriting it in another language, which is not a
contribution so much as a replacement.

What justifies it continuing to exist separately is the part that is not the export loop: the
parameter-file validation, the value serialisation, and the run record. Those are testable in
isolation, and they are where the defects this project has fixed actually were — every one of
them a case where OpenSCAD exited 0 and produced the wrong geometry. A shell or PowerShell
script can do the export; it is a poor place to put that kind of checking.
