# Parameter files

A parameter file says which models to build. Each **parameter set** is one row of a CSV or one
entry in a Customizer JSON file, and becomes one output file per requested format.

Both formats describe the same thing, and `scadbatch csv2json` / `scadbatch json2csv` convert
between them. They are not equivalent in how they reach OpenSCAD, which is the subject of
[How values reach OpenSCAD](#how-values-reach-openscad) below.

## CSV

The first row is the header: one column per parameter, named exactly as the variable is named in
the `.scad` file. Each later row is one parameter set.

```csv
exported_filename,width,height,depth
cube_small,10,10,10
cube_medium,20,20,20
cube_large,30,30,30
```

`exported_filename` is optional and is not a parameter. When present it names the output file;
see [Output names](#output-names).

A parameter the file does not mention keeps the default from the `.scad` file. That is the point
of the format: list only what varies.

### A blank cell leaves the parameter unset

An empty or whitespace-only cell is not the empty string. The parameter is left out of the set
entirely, so the model's own default applies:

```csv
exported_filename,w,h
blank_w,,20
```

reads as `{'exported_filename': 'blank_w', 'h': '20'}` — no `w` at all.

This is deliberate, because the alternative is worse. OpenSCAD types each parameter by the
default the model declares, and silently ignores a value it cannot convert: against `w = 10`,
passing `""` leaves `w` at `10` and exits 0 with no warning. A blank cell that meant "empty
string" would therefore build a model the row never asked for, and nothing in the output would
say so.

To pass an actual empty string, write a cell whose text is two quote characters. In CSV that
needs escaping, so the file contains `""""""`:

```csv
exported_filename,w,h
quoted_empty,"""""",20
```

which reads `w` as `""` and passes the empty string. This only does what you want where the
model's default for that parameter is itself a string.

`read_csv` logs which parameters each row leaves unset, since OpenSCAD will not.

### A row must match the header

A row with more or fewer cells than the header is refused, naming the file, the row and both
counts. Python's CSV reader pads a short row with `None` and collects a long row's overflow
under a `None` key, either of which previously became a `-D` flag like `-DNone=["2"]` — which
OpenSCAD accepts, ignores, and exits 0 on.

## Customizer JSON

The format OpenSCAD's own Customizer saves, so a `.json` saved from the GUI works unchanged:

```json
{
    "parameterSets": {
        "cube_small":  { "width": "10", "height": "10", "depth": "10" },
        "cube_medium": { "width": "20", "height": "20", "depth": "20" }
    },
    "fileFormatVersion": "1"
}
```

The key of each entry in `parameterSets` is the set name, used for the output file name and for
`-P`. Values are strings, as OpenSCAD writes them.

### What is refused

A parameter file is refused rather than partially understood when it cannot be read faithfully.
Each message names the file and the place in it.

| the file has | why it is refused |
| --- | --- |
| a root, `parameterSets`, or a set that is not an object | there is nothing to read as parameter sets; this previously raised `AttributeError` from inside the reader and reached you as a traceback |
| `NaN`, `Infinity` or `-Infinity` anywhere | OpenSCAD's JSON reader rejects the whole document, so **every** set exported at the model's defaults, exit code 0 — loud but not fatal: `ERROR: Cannot open Parameter Set 'p.json': <unspecified file>(1): expected value`, which `set -e` will not catch |
| a number too large for a double | it parses, then cannot be used |
| the same name twice at any level | for a duplicated *set* name, this tool kept the last and OpenSCAD selects the first, so the run reported values it did not build |

`NaN` and `Infinity` are not valid JSON, but Python's `json` module accepts them by default,
which is how they got this far.

## How values reach OpenSCAD

This differs by format, and it is the one place the two are not interchangeable.

**JSON goes to OpenSCAD natively**, with the file and the set name:

```
openscad -o out/cube_small.stl --export-format=binstl \
  -p examples/simpleCube/simpleCube.json -P cube_small \
  examples/simpleCube/simpleCube.scad
```

OpenSCAD reads the set itself, so **the model's declared default fixes each parameter's type**.
A value that cannot convert to that type is ignored and the default stands.

**CSV becomes `-D` flags**, one per parameter, in the order the columns appear:

```
openscad -o out/cube_small.stl --export-format=binstl \
  -Ddepth=10 -Dheight=10 -Dwidth=10 \
  examples/simpleCube/simpleCube.scad
```

`-D` takes an OpenSCAD *expression*, so each value has to be serialised as an OpenSCAD literal —
which is where quoting goes wrong if it is done by string concatenation. A string containing a
quote, a list of lists, a boolean spelled the Python way: each has exactly one correct form, and
the serialisation is a single function with one rule per type.

### Cell text to value

| cell | value | as a `-D` literal |
| --- | --- | --- |
| `10` | int `10` | `10` |
| `-2.5` | float `-2.5` | `-2.5` |
| `1e3` | float `1000.0` | `1000.0` |
| `true` / `false` | bool | `true` / `false` |
| `undef` | none | `undef` |
| `abc` | str `'abc'` | `"abc"` |
| `"quoted"` | str `'quoted'` | `"quoted"` |
| `[1,2,3]` | list | `[1, 2, 3]` |
| `[0:2:10]` | range | OpenSCAD range |
| `0x10` | str `'0x10'` | `"0x10"` |
| `1_000` | str `'1_000'` | `"1_000"` |

The last two matter: Python's `int()` accepts `0x10` and `1_000`, OpenSCAD does not read either
as a number, so they stay strings rather than becoming a number OpenSCAD would reject.

Quoted text is unquoted once, so `"quoted"` is the string `quoted`. Embedded quotes and
backslashes are escaped on the way out: `say "hi"` serialises as `"say \"hi\""`.

`[0:2:10]` is an OpenSCAD range, not a list. `[1:5]` is a range with no step.

## Output names

The name of each output file, without extension, is chosen in this order:

1. `--name-template`, if given
2. the set name — the JSON key, or the `exported_filename` column
3. `model_<index>`, zero-based

A template may use `{name}`, `{index}`, and any parameter in the set:

```
--name-template '{name}_d{diameter}'
--name-template 'part_{index:03d}'
```

A parameter the row leaves unset renders empty rather than failing the batch.

Every name is made filesystem-safe — `a/b c:d*` becomes `a_b c_d_`, and `../escape` becomes
`_escape`, so a set name cannot direct output outside the folder you chose. Spaces are left
alone. If two cases would produce the same file, the run is refused rather than letting one
silently overwrite the other.

## Selecting a subset

`--select` takes zero-based indices into the parameter file:

| form | meaning |
| --- | --- |
| `2,4` | those indices |
| `0-5` | a range, inclusive |
| `1-3,7,10-12` | combined |
| `every:2 in 0-10` | every second index in the range → `0 2 4 6 8 10` |
| `from:5` | index 5 onward |
| `up_to:4` | up to index 4, inclusive |
