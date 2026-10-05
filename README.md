# scadbatch

This repository provides a tool to automate the export of STL models from OpenSCAD using CSV or JSON files of parameters. It offers a simple and user-friendly solution for batch exporting models with different parameter sets and includes a graphical user interface (GUI) for ease of use. Inspired by:

[18107/OpenSCAD-batch-export-stl](https://github.com/18107/OpenSCAD-batch-export-stl)

[OutwardBuckle/OpenSCAD-Bulk-Export](https://github.com/OutwardBuckle/OpenSCAD-Bulk-Export)

## Features

- Batch export STL, 3MF, OFF, PNG and any other format OpenSCAD can write, with parameters defined in CSV or JSON files.
- Convert between CSV and JSON parameter files.
- Easy-to-use command-line interface and GUI.
- Handles boolean, numeric, and string parameter types correctly.
- Supports advanced selection options for parameter sets.
- Includes multiple example projects to get started.
- Tested and validated on a number of test cases.

## Quick Start

For easy usage, simply click on the **Releases** section on the right-hand side of the GitHub page and download the appropriate binary for your operating system (e.g., `.exe` for Windows, or equivalent for macOS and Linux). Install and start using the tool right away!

## Requirements

- Python 3.10 or later.
- OpenSCAD installed and added to your system PATH.

## Installation

### From Source

1. **Clone the repository:**

    ```
    git clone https://github.com/CameronBrooks11/scadbatch.git
    ```

    ```
    cd scadbatch
    ```

2. **Install the Python library:**

    ```
    pip install .
    ```

3. **Ensure OpenSCAD is installed and accessible from the command line. Add it to your PATH if necessary.**

4. **If you encounter the following warning:**

    ```
    WARNING: The script scadbatch.exe is installed in 'C:\Users\<YourUserName>\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_<somenumbers>\LocalCache\local-packages\Python311\Scripts' which is not on PATH.
    Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
    ```

    **You can resolve it by adding the directory returned by:**

    ```
    python -m site --user-base
    ```

    **Append the Scripts subdirectory of the output path to your system's PATH. For example:**

    ```
    C:\Users\<YourUserName>\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_<somenumbers>\LocalCache\local-packages\Python311\Scripts
    ```

5. **To modify the tool, reinstall it after making changes:**

    ```
    pip install --upgrade .
    ```

## Usage

Once installed, the tool can be called from anywhere using the `scadbatch` command. (It was called `openscad-export` before; that name still works and will be removed after v2.0.) The tool provides three primary modes:

1. **Export STL Files**
2. **Convert CSV to JSON**
3. **Convert JSON to CSV**

### Using the GUI

Launch the graphical interface for an intuitive way to configure and perform batch exports. Run the following command:

```
scadbatch gui
```

From the GUI, you can:

- Select your `.scad` file, parameter file (CSV or JSON), and output folder.
- Set the parameter file's encoding when it is not UTF-8 — leave the field blank for the default, or give a codec name such as `cp1252` for a spreadsheet export. One field serves the export and both conversions, which read different files, so each action names the encoding it used in the log. Files the tool writes are always UTF-8, whatever the field says.
- Configure export settings like format, selection range, and sequential processing.
- Monitor progress and view logs of the operation.
- Convert between CSV and JSON parameter files.

### Using the CLI

#### 1. Export STL Files

Export STL files using either a CSV or JSON parameter file.

**Command Structure:**

```
scadbatch export <scad_file> <parameter_file> <output_folder> [--openscad-path PATH] [--format EXT ...] [--export-format asciistl|binstl] [--select SELECTION] [-j N] [--skip-existing | --overwrite] [--dry-run] [--timeout SECONDS] [--summary PATH.json] [--name-template TEMPLATE] [--encoding NAME]
```

**Parameters:**

- `<scad_file>`: Path to the OpenSCAD `.scad` file.
- `<parameter_file>`: Path to the CSV or JSON file containing parameters. A JSON file is an OpenSCAD Customizer parameter-set file and is handed to OpenSCAD natively (`-p FILE -P SET`, OpenSCAD 2019.05+), so each value is typed by the model's own default and keys missing from a set keep the model's defaults; the CSV conventions below (quote-wrapping to force a string, `undef`) do not apply, OpenSCAD reads the values itself. CSV rows are passed as `-D` flags. A case never gets both.
- `<output_folder>`: Directory where STL files will be saved.

**Options:**

- `--openscad-path`: Path to the OpenSCAD executable. If omitted, `$OPENSCAD` is used, then `openscad` on PATH, then the platform's default install location (`C:\Program Files\OpenSCAD` on Windows, `/Applications/OpenSCAD.app` on macOS).
- `--format EXT`: Output format by file extension, as OpenSCAD's `-o` accepts it (`stl`, `off`, `3mf`, `png`, `csg`, ... — a format the detected OpenSCAD does not advertise in its `--help` is warned about; one it really cannot write fails per case with OpenSCAD's own message). Repeat the flag to export every case in several formats. Defaults to `stl`.
- `--export-format`: STL flavour, `asciistl` or `binstl`. Defaults to `binstl`. Only applies to `stl`.
- `--camera`, `--imgsize`, `--colorscheme`: passed straight to OpenSCAD for `png` output, e.g. `--format png --imgsize 1024,768 --camera 0,0,0,55,0,25,140`. OpenSCAD 2021.01 needs a display to render PNG (`xvfb-run scadbatch ...` on a headless Linux box); current builds render offscreen.
- `-j N`, `--jobs N`: run up to N OpenSCAD processes at once. Defaults to the number of CPUs. Ctrl-C stops the running renders and abandons the rest. (`--sequential` is a deprecated alias for `--jobs 1`.)
- `--skip-existing`: leave a case alone when its output file already exists, and say so in the summary. The default (`--overwrite`) re-exports everything.
- `-n`, `--dry-run`: print the OpenSCAD command for every case and run nothing; no files or folders are created.
- `--timeout SECONDS`: kill a case that runs longer than this; it is recorded as timed out and the batch continues.
- `--summary PATH.json`: write a machine-readable record of the run — OpenSCAD path and version, the inputs, and for every case its status (`ok`, `failed`, `timeout`, `skipped`, `dry-run`), return code, duration, OpenSCAD message lines (`WARNING:`, `ECHO:`, `ERROR:`, `EXPORT-WARNING:`, ...) and the exact command line, plus the tool version and a UTC timestamp. Written for failed and dry runs too, so CI can check it in; the directory is created if needed.
  - *Gating on OpenSCAD's errors.* `counts.errors` is how many cases produced a stderr line beginning with one of OpenSCAD's error groups (`ERROR:`, `PARSER-ERROR:`, `UI-ERROR:`, `EXPORT-ERROR:`), whatever their status; each case also carries its own `errors` list. It exists because OpenSCAD exits 0 on several of them — a parameter set it could not open (every set then falls back to the model's defaults), a font it could not read — so a case can be reported `ok` with its geometry wrong. Which errors invalidate a model is not decided here, so the exit code still reflects failures only; gate on `counts.errors == 0` to refuse them.
  - *What that gate does not cover.* It follows OpenSCAD's own taxonomy, which does not track whether the geometry is right. A missing `include` file, a missing `import()` and an unreadable `surface()` are all `WARNING:`, and each silently drops geometry — check `warnings` too if that matters. In the other direction, an `echo()` whose string contains a newline followed by `ERROR:` is counted, because groups are matched per stderr line. And `--skip-existing` leaves a kept file uninspected, so a re-run reports no errors for one that was produced with an error.
- `--name-template TEMPLATE`: how to name output files (without extension). Fields: `{name}` (the Customizer set name or `exported_filename`, else `model_<index>`), `{index}`, and any parameter, e.g. `{name}_d{diameter}` or `part_{index:03d}`. Names are always made filesystem-safe (`lid/large` becomes `lid_large`; the original set name still goes to OpenSCAD), and two cases producing the same file name are refused before anything runs.
- `--encoding NAME`: text encoding of the parameter file. Defaults to UTF-8, tolerating the byte-order mark Excel writes; pass e.g. `cp1252` for a spreadsheet export that is not UTF-8. Files this tool writes are always UTF-8.
- `--select SELECTION`: Select specific parameter sets to export using indices and ranges. Format examples: `'0-5'`, `'1-3,7,10-12'`, `'2,4'`. Indices are zero-based.

**Examples:**

- **Export with CSV:**

    ```
    scadbatch export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.csv output
    ```

- **Selective Export:**

    Export parameter sets from index 0 to 5:

    ```
    scadbatch export examples/candleStand/candleStand.scad examples/candleStand/candleStand.csv output --select "0-5"
    ```

- **Export from JSON:**

    Convert CSV to JSON first:

    ```
    scadbatch csv2json examples/simpleCube/simpleCube.csv examples/simpleCube/simpleCube.json
    ```

    Then, export using the JSON file:

    ```
    scadbatch export examples/simpleCube/simpleCube.scad examples/simpleCube/simpleCube.json output
    ```

#### 2. Convert CSV to JSON

Convert a CSV parameter file to JSON format compatible with OpenSCAD's customizer.

**Command Structure:**

```
scadbatch csv2json <csv_file> <json_file> [--encoding NAME]
```

Values are read with the same rules the exporter uses, so a cell means the same thing either way. A vector is stored as an OpenSCAD literal in a string, because OpenSCAD ignores a JSON array; nested vectors, ranges and `undef` are warned about, since current OpenSCAD builds ignore those in a parameter-set file and keep the model's default (export the CSV directly to apply them).

**Example:**

```
scadbatch csv2json examples/candleStand/candleStand.csv examples/candleStand/candleStand.json
```

#### 3. Convert JSON to CSV

Convert a JSON parameter file back to CSV format.

**Command Structure:**

```
scadbatch json2csv <json_file> <csv_file> [--encoding NAME]
```

**Example:**

```
scadbatch json2csv examples/sign/sign.json examples/sign/sign_converted.csv
```

## CSV File Structure

- The CSV file should have a header row with parameter names.
- Each subsequent row defines a set of parameters for the OpenSCAD model, with one cell per header column. A row with more or fewer cells is rejected by line number, rather than guessed at.
- An empty cell leaves that parameter out of the row, so the model's own default applies. This is how one row sets a parameter and another does not. An empty cell is *not* the empty string: OpenSCAD cannot read `""` as a number, so it warns, falls back and still exits 0, which would build a model the row never asked for. To ask for the empty string, give a cell whose text is `""` — type `""` into a spreadsheet cell, or write six quote characters in raw CSV, since `""` on its own is just how CSV quotes an empty field.
- An `exported_filename` column names the output files; without it files are named `model_<index>`, or use `--name-template`. Names are made filesystem-safe automatically, and two rows may not share a name.
- Files are read as UTF-8 (a byte-order mark is tolerated) and written as UTF-8. For a spreadsheet export in another encoding, pass `--encoding` or fill in the GUI's Parameter File Encoding field; note that Excel's "Unicode text" export is UTF-16 **and tab-separated**, which this tool does not read — save as "CSV UTF-8" instead.

**Example CSV file (`simpleCube.csv`):**

| exported_filename | depth | height | width |
|-------------------|-------|--------|-------|
| cube_small        | 10    | 10     | 10    |
| cube_medium       | 20    | 20     | 20    |
| cube_large        | 30    | 30     | 30    |

## JSON File Structure

The JSON file should follow the structure used by OpenSCAD's customizer profiles. It should contain a `parameterSets` object, where each key is the `exported_filename` and its value is a dictionary of parameters.

**Example JSON file (`simpleCube.json`):**

```
{
    "parameterSets": {
        "cube_small": {
            "width": "10",
            "height": "10",
            "depth": "10"
        },
        "cube_medium": {
            "width": "20",
            "height": "20",
            "depth": "20"
        },
        "cube_large": {
            "width": "30",
            "height": "30",
            "depth": "30"
        }
    },
    "fileFormatVersion": "1"
}
```

## OpenSCAD File Structure

The OpenSCAD file must define a model that uses parameters from the parameter file. For example:

**Example OpenSCAD file (`simpleCube.scad`):**

```
module model() { cube([width, height, depth]); }
```

## Example Files

The `examples/` directory contains multiple projects demonstrating how to use the exporter with different OpenSCAD models.

### 1. Simple Cube

A basic example of a customizable cube with varying dimensions.

**Files:**

- `examples/simpleCube/simpleCube.scad`
- `examples/simpleCube/simpleCube.csv`
- `examples/simpleCube/simpleCube.json`

### 2. Candle Stand

A more complex model featuring a candle stand with options for customization from the [OpenSCAD Parametric Examples](https://github.com/openscad/openscad/tree/master/examples/Parametric).

**Files:**

- `examples/candleStand/candleStand.scad`
- `examples/candleStand/candleStand.csv`
- `examples/candleStand/candleStand.json`

### 3. Sign

A customizable sign with adjustable message, size, and resolution parameters from the [OpenSCAD Parametric Examples](https://github.com/openscad/openscad/tree/master/examples/Parametric).

**Files:**

- `examples/sign/sign.scad`
- `examples/sign/sign.csv`
- `examples/sign/sign.json`

## Contributing

Contributions are welcome! Please open an issue or submit a pull request with improvements or suggestions.

## License

This project is licensed under the AGPL v3 License. See the LICENSE file for details.
