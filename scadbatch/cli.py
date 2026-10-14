"""Command-line interface.

Available subcommands:
- export: Batch export models from CSV or Customizer JSON parameter sets.
- csv2json: Convert CSV parameter files to JSON.
- json2csv: Convert JSON parameter files to CSV.
- gui: Launch the graphical user interface."""

import argparse
import importlib.util
import logging
import os
import sys

from scadbatch.engine import OpenSCADError
from scadbatch.params import DEFAULT_ENCODING, csv_to_json, json_to_csv
from scadbatch.runner import batch_export


def parse_arguments(argv=None):
    """
    Parse and return the command-line arguments.

    Args:
        argv (list of str or None): Arguments to parse; defaults to sys.argv[1:].

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Batch export models from OpenSCAD using CSV or JSON parameters, "
            "and convert between CSV and JSON."
        )
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show the OpenSCAD command line for each export.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-commands")

    # Export subcommand
    export_parser = subparsers.add_parser(
        "export",
        help="Export each parameter set, in any format OpenSCAD can write.",
    )
    export_parser.add_argument("scad_file", help="Path to the OpenSCAD (.scad) file.")
    export_parser.add_argument(
        "parameter_file", help="Path to the CSV or JSON file containing parameters."
    )
    export_parser.add_argument(
        "output_folder", help="Directory where the exported files will be saved."
    )
    export_parser.add_argument(
        "--openscad-path",
        "--openscad_path",
        dest="openscad_path",
        default=None,
        help=(
            "Path to the OpenSCAD executable. By default: $OPENSCAD, then 'openscad' on "
            "PATH, then the platform's default install location."
        ),
    )
    export_parser.add_argument(
        "--format",
        action="append",
        metavar="EXT",
        help=(
            "Output format by extension (stl, off, 3mf, png, csg, ...), as accepted by the "
            "detected OpenSCAD's -o. Repeat to export every case in several formats. "
            "Defaults to stl. A format the build does not advertise is warned about, "
            "not refused."
        ),
    )
    export_parser.add_argument(
        "--export-format",
        "--export_format",
        dest="export_format",
        choices=["asciistl", "binstl"],
        default="binstl",
        help="STL flavour: asciistl or binstl. Defaults to binstl. Only applies to stl.",
    )
    image_group = export_parser.add_argument_group("image output (png)")
    image_group.add_argument("--camera", help="OpenSCAD --camera, e.g. 0,0,0,55,0,25,140")
    image_group.add_argument("--imgsize", help="OpenSCAD --imgsize, e.g. 1024,768")
    image_group.add_argument("--colorscheme", help="OpenSCAD --colorscheme, e.g. Tomorrow")
    export_parser.add_argument(
        "--select",
        type=str,
        default=None,
        help=(
            "Select specific parameter sets to export using indices and ranges. "
            "Supported formats: "
            "'0-5' (range), '1-3,7,10-12' (multiple ranges and indices), "
            "'2,4' (specific indices), "
            "'every:2 in 0-10' (every 2nd index in range), "
            "'from:5' (from index 5 onward), "
            "'up_to:4' (up to index 4 inclusive). "
            "You can combine multiple selections separated by commas. "
            "Indices are zero-based."
        ),
    )
    export_parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        metavar="N",
        help="Run up to N OpenSCAD processes at once. Defaults to the number of CPUs.",
    )
    export_parser.add_argument(
        "--sequential",
        action="store_true",
        help="Deprecated: same as --jobs 1.",
    )
    existing = export_parser.add_mutually_exclusive_group()
    existing.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-export a case even if its output file already exists (the default).",
    )
    existing.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a case whose output file already exists.",
    )
    export_parser.add_argument(
        "--encoding",
        metavar="NAME",
        help=(
            "Text encoding of the parameter file. Defaults to UTF-8, tolerating the "
            "byte-order mark Excel writes; pass e.g. cp1252 for a spreadsheet export that "
            "is not UTF-8."
        ),
    )
    export_parser.add_argument(
        "--name-template",
        metavar="TEMPLATE",
        help=(
            "How to name output files (without extension). Fields: {name} (the set name or "
            "exported_filename, else model_<index>), {index}, and any parameter, e.g. "
            "'{name}_d{diameter}' or 'part_{index:03d}'. Names are made filesystem-safe."
        ),
    )
    export_parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print the OpenSCAD command for each case and run nothing.",
    )
    export_parser.add_argument(
        "--timeout",
        type=float,
        metavar="SECONDS",
        help="Kill a case that runs longer than this and record it as timed out.",
    )
    export_parser.add_argument(
        "--summary",
        metavar="PATH.json",
        help=(
            "Write a JSON record of the run: OpenSCAD version, inputs, and per-case "
            "status, duration, return code, warnings, errors and command line. counts.errors "
            "is the number of cases OpenSCAD printed an error for, including cases it "
            "exited 0 on."
        ),
    )

    # csv2json subcommand
    csv2json_parser = subparsers.add_parser("csv2json", help="Convert CSV parameter file to JSON.")
    csv2json_parser.add_argument("csv_file", help="Path to the CSV file.")
    csv2json_parser.add_argument("json_file", help="Path to the output JSON file.")
    csv2json_parser.add_argument(
        "--encoding", metavar="NAME", help="Text encoding of the CSV file. Defaults to UTF-8."
    )

    # json2csv subcommand
    json2csv_parser = subparsers.add_parser("json2csv", help="Convert JSON parameter file to CSV.")
    json2csv_parser.add_argument("json_file", help="Path to the JSON file.")
    json2csv_parser.add_argument("csv_file", help="Path to the output CSV file.")
    json2csv_parser.add_argument(
        "--encoding", metavar="NAME", help="Text encoding of the JSON file. Defaults to UTF-8."
    )

    # GUI subcommand
    subparsers.add_parser("gui", help="Launch the graphical user interface.")

    return parser.parse_args(argv)


def main(argv=None):
    """
    Entry point of the module. Parses arguments and executes the corresponding subcommand.

    Returns:
        int: Process exit code. Non-zero if any export failed or the input was invalid.
    """
    args = parse_arguments(argv)
    logger = logging.getLogger("scadbatch")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    try:
        return _run(args)
    finally:
        logger.removeHandler(handler)


def _run(args):
    if args.command == "export":
        if args.sequential:
            print("Warning: --sequential is deprecated; use --jobs 1.", file=sys.stderr)
        if args.jobs is not None and args.jobs < 1:
            print("Error: --jobs must be at least 1.", file=sys.stderr)
            return 1
        if args.summary:
            # Fail now, not after a long batch, if the summary cannot be written there.
            try:
                os.makedirs(os.path.dirname(os.path.abspath(args.summary)), exist_ok=True)
                with open(args.summary, "a", encoding="utf-8"):
                    pass
            except OSError as e:
                print(f"Error: cannot write summary to {args.summary}: {e}", file=sys.stderr)
                return 1
        try:
            result = batch_export(
                args.scad_file,
                args.parameter_file,
                args.output_folder,
                args.openscad_path,
                args.export_format,
                args.select,
                args.sequential,
                formats=args.format or ["stl"],
                image_options={k: getattr(args, k) for k in ("camera", "imgsize", "colorscheme")},
                jobs=args.jobs,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
                timeout=args.timeout,
                name_template=args.name_template,
                encoding=args.encoding,
            )
        except (OpenSCADError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("Interrupted.", file=sys.stderr)
            return 130
        print()
        print(result.summary())
        if args.summary:
            result.write_summary(args.summary)
            print(f"Summary written to {args.summary}")
        return 1 if result.failures else 0
    if args.command in ("csv2json", "json2csv"):
        try:
            encoding = args.encoding or DEFAULT_ENCODING
            if args.command == "csv2json":
                csv_to_json(args.csv_file, args.json_file, encoding)
            else:
                json_to_csv(args.json_file, args.csv_file, encoding)
        except (ValueError, TypeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    elif args.command == "gui":
        try:
            # Absolute, not `from . import gui`: in a frozen one-file build this module is
            # __main__ and has no parent package, so a relative import cannot resolve.
            from scadbatch import gui
        except ImportError as e:
            if importlib.util.find_spec("scadbatch.gui") is None:
                # The module is not in this build at all, which is a packaging fault in a
                # frozen binary rather than anything the user can install.
                print(f"This build does not include the graphical interface: {e}", file=sys.stderr)
            else:
                print(
                    f"The graphical interface is unavailable: {e}. It needs tkinter, which some "
                    "Linux distributions package separately (try installing python3-tk).",
                    file=sys.stderr,
                )
            return 1
        gui.main()  # outside the try, so a failure inside the GUI is not reported as this
    return 0


if __name__ == "__main__":
    sys.exit(main())
