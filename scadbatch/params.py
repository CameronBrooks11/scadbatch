"""Parameter-set handling: reading CSV and Customizer JSON files, selecting subsets,
serializing values as OpenSCAD -D flags, and converting between the two formats."""

import codecs
import csv
import io
import json
import logging
import math
import os
import re
from typing import NamedTuple

log = logging.getLogger("scadbatch")

DEFAULT_ENCODING = "utf-8-sig"
"""How parameter files are read: UTF-8, tolerating the byte-order mark Excel writes.

Customizer JSON is UTF-8 by specification, and a CSV of parameters is usually UTF-8 too.
Reading with the locale's encoding instead would decode a set name or a string value
differently on each machine — silently, on a Windows cp1252 locale. Files are always
written as UTF-8 without a mark.
"""


def normalize_encoding(name):
    """
    The canonical name of a codec, e.g. ``utf8`` -> ``utf-8``.

    Raises:
        ValueError: If Python has no such codec, rather than the LookupError that
            :func:`codecs.lookup` raises, so callers report it like any bad argument; or if
            the name is a byte transform rather than a text encoding, which
            :func:`codecs.lookup` accepts and no file can be read with.
    """
    try:
        info = codecs.lookup(name)
    except LookupError as e:
        raise ValueError(f"Unknown encoding {name!r}: Python has no such codec.") from e
    try:
        # codecs.lookup also answers for byte-to-byte codecs -- rot13, base64, hex, zlib --
        # which no file can be read with. str.encode refuses exactly those.
        "".encode(name)
    except LookupError as e:
        raise ValueError(f"Encoding {name!r} is a byte transform, not a text encoding.") from e
    return info.name


def is_utf8_encoding(name):
    """True if ``name`` is UTF-8, with or without a byte-order mark."""
    return normalize_encoding(name) in ("utf-8", "utf-8-sig")


def read_csv(csv_path, encoding=DEFAULT_ENCODING):
    """
    Read parameters from a CSV file.

    Every row must have one cell per header column. Blank lines are skipped, before the
    header as well as after it; a line of only whitespace is not blank, it is one cell.

    An empty cell leaves that parameter out of the row, so the model's own default applies
    rather than an empty string. To ask for the empty string, give a cell whose text is
    ``""`` -- which CSV spells with six quote characters, since ``""`` on its own is how an
    empty field is quoted and parses the same as a bare comma.

    Args:
        csv_path (str): Path to the CSV file.
        encoding (str): Text encoding of the file; UTF-8 with an optional byte-order mark
            by default.

    Returns:
        list of dict: List of parameter dictionaries.

    Raises:
        ValueError: If the file is not text in that encoding, or a row does not have one
            cell per header column.
    """
    # csv.DictReader is not used here because it absorbs a ragged row instead of
    # reporting one: extra cells land under restkey, which is None and reaches OpenSCAD
    # as a parameter of that name, and missing cells become restval, which serializes to
    # undef. Both silently change the model the user asked for.
    reader = csv.reader(io.StringIO(_read_text(csv_path, encoding), newline=""))
    header = next((row for row in reader if row), None)
    if header is None:
        return []
    rows = []
    line = reader.line_num
    for row in reader:
        start, line = line + 1, reader.line_num
        if not row:
            continue
        if len(row) != len(header):
            hint = (
                "check for a stray comma at the end of the row, and quote any cell that "
                "contains one"
                if len(row) > len(header)
                else "check for a stray comma at the end of the header, and leave a cell "
                "empty rather than omitting it"
            )
            raise ValueError(
                f"{csv_path} line {start}: this row has {len(row)} "
                f"cell{'' if len(row) == 1 else 's'} but the header has {len(header)} "
                f"column{'' if len(header) == 1 else 's'}, so it is not clear which value belongs "
                f"to which parameter. Give every row one cell per column; {hint}."
            )
        # An empty cell leaves the parameter out, so the model's default applies. CSV
        # cannot hold an absent cell, and sending the empty string instead is worse
        # than useless: OpenSCAD cannot read "" as a number, so it warns, falls back
        # and exits 0, building a model the row did not ask for. A cell whose text is
        # "" still means the empty string -- see coerce_cell.
        rows.append({k: v for k, v in zip(header, row, strict=True) if v != ""})
    return rows


def read_json(json_path, encoding=DEFAULT_ENCODING):
    """
    Read parameters from a JSON file.

    Args:
        json_path (str): Path to the JSON file.
        encoding (str): Text encoding of the file; UTF-8 with an optional byte-order mark
            by default.

    Returns:
        list of dict: List of parameter dictionaries with 'exported_filename' added.

    Raises:
        ValueError: If the file is not text in that encoding, or not valid JSON.
    """
    data = json.loads(_read_text(json_path, encoding))
    if not isinstance(data, dict):
        raise ValueError(
            f"{json_path}: JSON root must be a dict with a 'parameterSets' key, "
            f"but got {type(data).__name__}."
        )
    parameter_sets = data.get("parameterSets", {})
    parameters = []
    for name, params in parameter_sets.items():
        param_set = params.copy()
        param_set["exported_filename"] = name
        parameters.append(param_set)
    return parameters


def is_parameter_set_file(parameter_file):
    """True if the file is a Customizer JSON parameter-set file (by extension)."""
    return os.path.splitext(str(parameter_file))[1].lower() == ".json"


# Characters no common filesystem accepts in a name (the Windows set, which includes the
# POSIX separator), plus control characters.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{d}{n}" for d in ("COM", "LPT") for n in range(1, 10)
}


# Filesystems cap a name at 255 bytes; leave room for ".part", a dot and an extension.
MAX_NAME_BYTES = 200


def sanitize_filename(name, fallback):
    """
    Make ``name`` safe to use as a file name on any platform: unsafe characters become
    ``_``, surrounding whitespace and dots are dropped, Windows reserved device names
    (``CON``, ``NUL.txt``, ...) get a trailing ``_``, the name is cut to
    ``MAX_NAME_BYTES`` of UTF-8, and an empty result falls back to ``fallback``.
    """
    safe = _UNSAFE_CHARS.sub("_", str(name)).strip(" .")
    if safe.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        safe += "_"
    while len(safe.encode("utf-8")) > MAX_NAME_BYTES:
        safe = safe[:-1]
    return safe or fallback


def output_name(param_set, index, template=None):
    """
    The file name (without extension) for one parameter set.

    Without a template: the set's ``exported_filename`` (the Customizer set name for JSON
    input), or ``model_<index>``. With a template, ``str.format`` fields are filled from
    ``{name}`` (the same default), ``{index}`` and every parameter, e.g.
    ``"{name}_d{diameter}"`` or ``"part_{index:03d}"``.

    The result is passed through :func:`sanitize_filename`.

    Raises:
        ValueError: If the template names a field the parameter set does not have.
    """
    default = str(param_set.get("exported_filename", f"model_{index}"))
    if template is None:
        raw = default
    else:
        fields = {k: v for k, v in param_set.items() if k != "exported_filename"}
        fields.update(name=default, index=index)
        try:
            raw = template.format(**fields)
        except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
            raise ValueError(
                f"Name template {template!r} could not be filled for parameter set {index}"
                f" ({e.__class__.__name__}: {e}); available fields: "
                f"{', '.join(sorted(fields))}"
            ) from e
    return sanitize_filename(raw, f"model_{index}")


def read_parameters(parameter_file, encoding=DEFAULT_ENCODING):
    """
    Read parameter sets from a CSV or JSON file, chosen by extension.

    Args:
        parameter_file (str): Path to the CSV or JSON file.
        encoding (str): Text encoding of the file; UTF-8 with an optional byte-order mark
            by default.

    Returns:
        list of dict: List of parameter dictionaries.

    Raises:
        ValueError: If the file extension is not .csv or .json, the file is not text in
            that encoding, or a CSV row does not have one cell per header column.
    """
    ext = os.path.splitext(str(parameter_file))[1].lower()
    if ext == ".csv":
        return read_csv(parameter_file, encoding)
    if ext == ".json":
        return read_json(parameter_file, encoding)
    raise ValueError(f"Unsupported parameter file format: {ext}")


def _read_text(path, encoding):
    """Read a parameter file, reporting a wrong encoding in terms the user can act on
    rather than as a decoding error from deep in the stack."""
    normalize_encoding(encoding)
    try:
        with open(path, encoding=encoding, newline="") as handle:
            return handle.read()
    except UnicodeDecodeError as e:
        raise ValueError(
            f"{path} is not valid {encoding} text ({e.reason} at byte {e.start}). Re-save it "
            f"as UTF-8, or give the encoding it actually uses (--encoding on the command "
            f"line, the Parameter File Encoding field in the GUI, the encoding argument of "
            f"the API)."
        ) from e


def parse_selection(selection_str, total_params):
    """
    Parse a selection string and return a sorted list of unique indices.

    Args:
        selection_str (str): Selection string
            (e.g., "0-5,7,10-12, every:2 in 0-10, from:15, up_to:20").
        total_params (int): Total number of parameter sets.

    Returns:
        list of int: Sorted list of unique selected indices.

    Raises:
        ValueError: If the selection string is invalid.
    """
    selected_indices = set()
    parts = selection_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("every:"):
            try:
                _, rest = part.split(":", 1)
                step, range_part = rest.split(" in ")
                step = int(step)
                start, end = map(int, range_part.split("-"))
                if start > end:
                    raise ValueError(f"Invalid range '{range_part}': start > end.")
                for i in range(start, end + 1, step):
                    if i < 0 or i >= total_params:
                        raise ValueError(f"Index {i} out of range (0-{total_params - 1}).")
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid step selection '{part}': {ve}") from ve
        elif part.startswith("from:"):
            try:
                _, start_str = part.split(":", 1)
                start = int(start_str)
                if start < 0 or start >= total_params:
                    raise ValueError(f"Start index {start} out of range (0-{total_params - 1}).")
                for i in range(start, total_params):
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid 'from' selection '{part}': {ve}") from ve
        elif part.startswith("up_to:"):
            try:
                _, end_str = part.split(":", 1)
                end = int(end_str)
                if end < 0 or end >= total_params:
                    raise ValueError(f"End index {end} out of range (0-{total_params - 1}).")
                for i in range(0, end + 1):
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid 'up_to' selection '{part}': {ve}") from ve
        elif "-" in part:
            try:
                start, end = map(int, part.split("-"))
                if start > end:
                    raise ValueError(f"Invalid range '{part}': start > end.")
                for i in range(start, end + 1):
                    if i < 0 or i >= total_params:
                        raise ValueError(f"Index {i} out of range (0-{total_params - 1}).")
                    selected_indices.add(i)
            except ValueError as ve:
                raise ValueError(f"Invalid range '{part}': {ve}") from ve
        else:
            try:
                index = int(part)
                if index < 0 or index >= total_params:
                    raise ValueError(f"Index {index} out of range (0-{total_params - 1}).")
                selected_indices.add(index)
            except ValueError as ve:
                raise ValueError(f"Invalid index '{part}': {ve}") from ve
    return sorted(selected_indices)


_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_INTEGER = re.compile(r"[+-]?\d+")


class ScadRange(NamedTuple):
    """An OpenSCAD range literal, ``[start : end]`` or ``[start : step : end]``."""

    start: float
    end: float
    step: float | None = None


_STRING_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r"}


def to_scad_literal(value):
    """
    Serialize a Python value as an OpenSCAD literal for use in a -D flag.

    bool -> true/false, int/float -> number, str -> quoted and escaped string,
    list/tuple -> vector (recursively), ScadRange -> range, None -> undef.

    Raises:
        ValueError: For non-finite floats, which OpenSCAD has no literal for.
        TypeError: For any other type.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Cannot serialize non-finite number {value!r} as an OpenSCAD literal")
        return repr(value)
    if isinstance(value, str):
        escaped = "".join(_STRING_ESCAPES.get(ch, ch) for ch in value)
        return f'"{escaped}"'
    if isinstance(value, ScadRange):
        parts = (
            [value.start, value.end] if value.step is None else [value.start, value.step, value.end]
        )
        return "[" + " : ".join(to_scad_literal(v) for v in parts) + "]"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(to_scad_literal(v) for v in value) + "]"
    if value is None:
        return "undef"
    raise TypeError(f"Cannot serialize {type(value).__name__} as an OpenSCAD literal")


def coerce_cell(text):
    """
    Decide what a parameter value written as text means, using OpenSCAD's own syntax.
    This applies to CSV cells, and to Customizer JSON strings only when they are passed
    as -D flags (engines older than 2019.05); through -p/-P OpenSCAD interprets JSON
    values itself, typed by the model's defaults, and these conventions do not apply.

    - ``true`` / ``false`` (any case) -> bool; ``undef`` -> None
    - a number in OpenSCAD's grammar (``12``, ``-2.5``, ``.5``, ``1e3``) -> int or float
    - text wrapped in double quotes (``"007"``) -> that string, verbatim. This is how to
      keep a numeric-looking value as a string.
    - text starting with ``[`` -> a vector or range literal, parsed and validated.
      Strings inside follow OpenSCAD escape rules (``\\n``, ``\\"``, ``\\u00e9``...).
      Only literals are accepted: expressions such as ``[1+2, a]`` are rejected.
    - anything else -> the string as written

    Raises:
        ValueError: If a vector is malformed or a number is out of range.
    """
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered == "undef":
        return None
    if _NUMBER.fullmatch(stripped):
        if _INTEGER.fullmatch(stripped):
            return int(stripped)
        number = float(stripped)
        if not math.isfinite(number):
            raise ValueError(f"Number {stripped!r} is out of range")
        return number
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        return stripped[1:-1]
    if stripped.startswith("["):
        return _parse_vector(stripped)
    return text


_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
_HEX_ESCAPE_WIDTH = {"x": 2, "u": 4, "U": 6}


def _parse_vector(text):
    """Parse an OpenSCAD vector or range literal: numbers, strings, bools, undef, nested
    vectors and ``[a : b]`` / ``[a : b : c]`` ranges. Expressions are not accepted."""
    pos = 0

    def error(message):
        return ValueError(f"Invalid vector {text!r}: {message} at position {pos}")

    def skip_ws():
        nonlocal pos
        while pos < len(text) and text[pos].isspace():
            pos += 1

    def parse_value():
        nonlocal pos
        skip_ws()
        if pos >= len(text):
            raise error("unexpected end")
        ch = text[pos]
        if ch == "[":
            pos += 1
            items = []
            skip_ws()
            if pos < len(text) and text[pos] == "]":
                pos += 1
                return items
            separator = None
            while True:
                items.append(parse_value())
                skip_ws()
                if pos >= len(text):
                    raise error("missing ']'")
                if text[pos] in ",:" and separator in (None, text[pos]):
                    separator = text[pos]
                    pos += 1
                    skip_ws()
                    if separator == "," and pos < len(text) and text[pos] == "]":
                        pos += 1  # trailing comma, as OpenSCAD allows
                        return items
                    continue
                if text[pos] == "]":
                    pos += 1
                    if separator != ":":
                        return items
                    if len(items) == 2:
                        return ScadRange(items[0], items[1])
                    if len(items) == 3:
                        return ScadRange(items[0], items[2], items[1])
                    raise error("a range has two or three parts")
                raise error(f"unexpected {text[pos]!r}")
        if ch == '"':
            pos += 1
            chars = []
            while pos < len(text) and text[pos] != '"':
                if text[pos] == "\\":
                    pos += 1
                    if pos >= len(text):
                        break
                    esc = text[pos]
                    if esc in _SIMPLE_ESCAPES:
                        chars.append(_SIMPLE_ESCAPES[esc])
                    elif esc in _HEX_ESCAPE_WIDTH:
                        width = _HEX_ESCAPE_WIDTH[esc]
                        digits = text[pos + 1 : pos + 1 + width]
                        if len(digits) != width or not all(
                            c in "0123456789abcdefABCDEF" for c in digits
                        ):
                            raise error(f"bad \\{esc} escape")
                        chars.append(chr(int(digits, 16)))
                        pos += width
                    else:
                        chars.append("\\" + esc)  # unknown escape: keep as written
                else:
                    chars.append(text[pos])
                pos += 1
            if pos >= len(text):
                raise error("unterminated string")
            pos += 1
            return "".join(chars)
        match = _NUMBER.match(text, pos)
        if match:
            pos = match.end()
            token = match.group(0)
            return int(token) if _INTEGER.fullmatch(token) else float(token)
        for word, value in (("true", True), ("false", False), ("undef", None)):
            if text.startswith(word, pos):
                pos += len(word)
                return value
        raise error(f"unexpected {ch!r}")

    try:
        result = parse_value()
    except RecursionError:
        raise error("nesting too deep") from None
    skip_ws()
    if pos != len(text):
        raise error("trailing characters")
    return result


def construct_d_flags(params):
    """
    Construct a list of -D flags for OpenSCAD based on parameters.

    String values are interpreted with :func:`coerce_cell`; other values are serialized
    directly with :func:`to_scad_literal`.

    Args:
        params (dict): Dictionary of parameters.

    Returns:
        list of str: List of -D flags.
    """
    d_flags = []
    for key, value in params.items():
        if key == "exported_filename":
            continue
        try:
            if isinstance(value, str):
                value = coerce_cell(value)
            d_flags.append(f"-D{key}={to_scad_literal(value)}")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Parameter '{key}': {e}") from e
    return d_flags


def csv_to_json(csv_file, json_file, encoding=DEFAULT_ENCODING):
    """
    Convert a CSV parameter file to JSON format.

    Args:
        csv_file (str): Path to the input CSV file.
        json_file (str): Path to the output JSON file.
        encoding (str): Text encoding of the CSV file; the JSON file is written as UTF-8.
    """
    sets = {}
    for index, param_set in enumerate(read_csv(csv_file, encoding)):
        name = str(param_set.get("exported_filename") or f"model_{index}")
        if name in sets:
            raise ValueError(
                f"Duplicate parameter set name {name!r} in {csv_file}: rows cannot share a "
                "name, because a parameter-set file holds one set per name."
            )
        params = {k: v for k, v in param_set.items() if k != "exported_filename"}
        sets[name] = {k: _json_value(_cell_value(v, k, index), k) for k, v in params.items()}
    json_data = {"parameterSets": sets}
    json_data["fileFormatVersion"] = "1"
    with open(json_file, "w", encoding="utf-8") as jf:
        # Written as real UTF-8 rather than \uXXXX escapes, so a set name reads as itself;
        # OpenSCAD accepts either form (checked on 2026.09.05).
        json.dump(json_data, jf, indent=4, ensure_ascii=False)
    log.info("Converted %s to %s.", csv_file, json_file)


def _json_value(value, key):
    """
    How a parameter value is stored in a Customizer JSON file.

    Scalars keep their JSON type, which OpenSCAD reads. Everything else is written as the
    OpenSCAD literal in a string, because OpenSCAD ignores a JSON array outright.

    Only a flat vector of numbers survives that encoding on every engine. Through
    ``-p/-P``, OpenSCAD keeps the model's default for a nested vector or ``undef`` on both
    2021.01 and 2026.09.05, and current builds also ignore a range and a vector of strings
    that 2021.01 applies. All of those are warned about; exporting the CSV file directly
    applies them.
    """
    if isinstance(value, (bool, int, float, str)):
        return value
    literal = to_scad_literal(value)
    if not _survives_parameter_sets(value):
        log.warning(
            "Parameter %r is %s, which current OpenSCAD builds ignore in a parameter-set "
            "file, keeping the model's default (2021.01 applies ranges and vectors of "
            "strings; no build applies a nested vector or undef). Export from the CSV file "
            "to apply it.",
            key,
            literal,
        )
    return literal


def _cell_value(value, key, index):
    """Interpret one CSV cell, naming the row and column if it cannot be read."""
    if not isinstance(value, str):
        return value
    try:
        return coerce_cell(value)
    except ValueError as e:
        raise ValueError(f"Row {index}, column {key!r}: {e}") from e


def _survives_parameter_sets(value):
    """True if OpenSCAD honours this value through ``-p FILE -P SET``."""
    return isinstance(value, list) and all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
    )


def json_to_csv(json_file, csv_file, encoding=DEFAULT_ENCODING):
    """
    Convert a JSON parameter file to CSV format.

    Args:
        json_file (str): Path to the input JSON file.
        csv_file (str): Path to the output CSV file.
        encoding (str): Text encoding of the JSON file; the CSV file is written as UTF-8.
    """
    parameter_sets = read_json(json_file, encoding)
    # Collect all unique keys
    all_keys = set()
    for params in parameter_sets:
        all_keys.update(params.keys())
    # Ensure 'exported_filename' is first column
    fieldnames = ["exported_filename"] + sorted(all_keys - {"exported_filename"})
    with open(csv_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for param_set in parameter_sets:
            row = {"exported_filename": param_set.get("exported_filename", "model")}
            for key in all_keys - {"exported_filename"}:
                # A key this set does not have becomes an empty cell, which read_csv reads
                # back as absent. A key whose value is the empty string goes through
                # _csv_cell, which spells it so the distinction survives.
                row[key] = _csv_cell(param_set[key]) if key in param_set else ""
            writer.writerow(row)
    log.info("Converted %s to %s.", json_file, csv_file)


def _csv_cell(value):
    """
    How a parameter value is written to a CSV cell: bools lowercased, vectors, ranges and
    undef as OpenSCAD literals, numbers and strings as themselves.

    Strings are written verbatim, not quote-wrapped, so a JSON string whose text reads as
    something else (``"10"``, ``"true"``, ``"[1, 2]"``) becomes that other type when the
    cell is read back. That is deliberate: the Customizer writes *every* value as a string,
    so quoting them would turn every number in a real parameter-set file into a string.
    Which of the two a JSON string means is the model's default to decide, and the file
    does not record it.
    """
    if isinstance(value, str):
        # An empty cell means "not set" to read_csv, so the empty string is written as the
        # two characters "" -- the spelling coerce_cell reads back as the empty string. The
        # csv writer escapes them, so the file holds six quotes.
        return '""' if value == "" else value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return value
    return to_scad_literal(value)
