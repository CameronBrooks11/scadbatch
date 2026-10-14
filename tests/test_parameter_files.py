import csv
import json
import math
import re
from pathlib import Path

import pytest

from scadbatch.params import (
    _path_to_non_finite,
    csv_to_json,
    json_to_csv,
    read_csv,
    read_json,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
EXAMPLE_NAMES = sorted(p.name for p in EXAMPLES.iterdir() if (p / f"{p.name}.csv").exists())


def rows_by_name(csv_path):
    with open(csv_path, newline="") as f:
        return {row["exported_filename"]: row for row in csv.DictReader(f)}


def test_read_json_names_each_set_from_its_key(tmp_path):
    src = tmp_path / "p.json"
    src.write_text(
        json.dumps(
            {
                "fileFormatVersion": "1",
                "parameterSets": {"lid": {"d": 10, "open": True}, "base": {"d": 12}},
            }
        )
    )
    sets = read_json(src)
    assert [s["exported_filename"] for s in sets] == ["lid", "base"]
    assert sets[0] == {"d": 10, "open": True, "exported_filename": "lid"}


def test_csv_to_json_types_values_and_writes_customizer_format(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text(
        "exported_filename,n,x,flag,label\nsmall,3,2.5,true,ab c\nbig,10,4.0,FALSE,7up\n"
    )
    out = tmp_path / "p.json"

    csv_to_json(src, out)
    data = json.loads(out.read_text())

    assert data["fileFormatVersion"] == "1"
    assert data["parameterSets"] == {
        "small": {"n": 3, "x": 2.5, "flag": True, "label": "ab c"},
        "big": {"n": 10, "x": 4.0, "flag": False, "label": "7up"},
    }


def test_json_to_csv_puts_name_first_and_lowercases_booleans(tmp_path):
    src = tmp_path / "p.json"
    src.write_text(
        json.dumps(
            {"parameterSets": {"a": {"bore": 1, "flag": True}, "b": {"bore": 2, "flag": False}}}
        )
    )
    out = tmp_path / "p.csv"

    json_to_csv(src, out)

    with open(out, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["exported_filename", "bore", "flag"]
        rows = list(reader)
    assert rows == [
        {"exported_filename": "a", "bore": "1", "flag": "true"},
        {"exported_filename": "b", "bore": "2", "flag": "false"},
    ]


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_example_csv_survives_round_trip(name, tmp_path):
    src = EXAMPLES / name / f"{name}.csv"
    mid = tmp_path / "mid.json"
    back = tmp_path / "back.csv"

    csv_to_json(src, mid)
    json_to_csv(mid, back)

    original = rows_by_name(src)
    restored = rows_by_name(back)
    assert restored.keys() == original.keys()
    for key in original:
        assert set(restored[key]) == set(original[key])
        for column, value in original[key].items():
            # Booleans are normalised to lowercase; everything else must survive verbatim.
            expected = value.lower() if value.lower() in ("true", "false") else value
            assert restored[key][column] == expected, (key, column)


def test_a_newline_inside_a_quoted_cell_is_preserved(tmp_path):
    """The reader must not translate line endings, or a multi-line cell loses its \r."""
    src = tmp_path / "p.csv"
    src.write_bytes(b'exported_filename,note\r\nrow,"first\r\nsecond"\r\n')

    (row,) = read_csv(src)

    assert row["note"] == "first\r\nsecond"


def test_a_row_with_more_cells_than_the_header_is_rejected(tmp_path):
    """Absorbing the extra cell invents a parameter named for csv.DictReader's restkey."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d\nr,1,2\n")

    with pytest.raises(ValueError) as excinfo:
        read_csv(src)

    message = str(excinfo.value)
    assert "line 2" in message
    assert "3 cells" in message and "2 columns" in message


def test_a_row_with_fewer_cells_than_the_header_is_rejected(tmp_path):
    """Filling the gap makes the parameter undef, which is a value the user did not write."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d,h\nu\n")

    with pytest.raises(ValueError) as excinfo:
        read_csv(src)

    assert "1 cell but the header has 3 columns" in str(excinfo.value)


def test_blank_lines_before_the_header_are_skipped(tmp_path):
    """Taking a blank first line as the header reports every row against zero columns."""
    src = tmp_path / "p.csv"
    src.write_text("\n\nexported_filename,d\na,1\n")

    assert read_csv(src) == [{"exported_filename": "a", "d": "1"}]


def test_the_reported_line_counts_blank_lines_and_multi_line_cells(tmp_path):
    """The number has to send the user to the right line of their file, not the right row."""
    src = tmp_path / "p.csv"
    src.write_text('exported_filename,note\n\nok,"first\nsecond"\nbad,x,y\n')

    with pytest.raises(ValueError, match="line 5"):
        read_csv(src)


def test_a_file_of_only_a_header_reads_as_no_parameter_sets(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d\n")

    assert read_csv(src) == []


def test_an_empty_file_reads_as_no_parameter_sets(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text("")

    assert read_csv(src) == []


# --- a Customizer file that is not shaped like one ----------------------------------

# Every shape read_json cannot read, and the JSON name of what was found there. A
# Customizer file is {"parameterSets": {"<set>": {"<param>": <value>}}}, so there are three
# places to get wrong and the message has to say which one.
BAD_SHAPES = [
    ("[]", "root", "array"),
    ('"hello"', "root", "string"),
    ("42", "root", "number"),
    ("true", "root", "boolean"),
    ("null", "root", "null"),
    ('{"parameterSets": []}', "parameterSets", "array"),
    ('{"parameterSets": "nope"}', "parameterSets", "string"),
    ('{"parameterSets": 1}', "parameterSets", "number"),
    ('{"parameterSets": {"lid": "nope"}}', "parameter set 'lid'", "string"),
    ('{"parameterSets": {"lid": [1, 2]}}', "parameter set 'lid'", "array"),
    ('{"parameterSets": {"lid": 7}}', "parameter set 'lid'", "number"),
    ('{"parameterSets": {"lid": null}}', "parameter set 'lid'", "null"),
]


@pytest.mark.parametrize("text,where,found", BAD_SHAPES, ids=[c[0][:28] for c in BAD_SHAPES])
def test_a_file_not_shaped_like_a_parameter_set_file_names_the_place(tmp_path, text, where, found):
    """These reached the user as a traceback: read_json raised AttributeError, and the export
    handler catches only (OpenSCADError, ValueError) while the conversion handler adds
    TypeError. The message has to say which of the three levels was wrong and what was there
    instead.

    `where` is the phrase that names the level, not a bare name: the parameterSets message
    embeds the example {"parameterSets": {"lid": {"d": 10}}}, so a bare "lid" appears in that
    message too and a set-level row would pass against the wrong one."""
    src = tmp_path / "p.json"
    src.write_text(text)

    with pytest.raises(ValueError) as excinfo:
        read_json(src)

    message = str(excinfo.value)
    assert "p.json" in message
    assert where in message
    assert found in message


@pytest.mark.parametrize(
    "text",
    [
        "{}",
        '{"fileFormatVersion": "1"}',
        '{"parameterSets": {}}',
        '{"parameterSets": {"a": {}}}',
    ],
)
def test_a_file_with_no_sets_to_read_is_not_an_error(tmp_path, text):
    """These four say nothing about what to export, so there is no instruction to misread: an
    absent parameterSets key reads as no sets, and an empty set as a set that changes nothing.
    The shapes rejected above differ in kind -- each states an intent and states it wrongly,
    and defaulting silently would build something the file did not ask for.

    Matching the engine is not what separates them: OpenSCAD accepts all sixteen shapes,
    rejected and accepted alike, silently keeping the model's defaults (measured against
    2026.08.01 with -p/-P, reading the .csg)."""
    src = tmp_path / "p.json"
    src.write_text(text)

    assert read_json(src) == ([{"exported_filename": "a"}] if '"a"' in text else [])


@pytest.mark.parametrize(
    "text",
    ['{"parameterSets": []}', '{"parameterSets": {"lid": "nope"}}'],
    ids=["parameterSets-not-an-object", "set-not-an-object"],
)
@pytest.mark.parametrize("command", ["json2csv", "export"])
def test_the_cli_reports_a_bad_shape_without_a_traceback(
    tmp_path, capsys, text, command, fake_openscad
):
    """What #65 asked for. These two raised AttributeError, which neither CLI handler
    catches -- export catches (OpenSCADError, ValueError), the conversions add TypeError -- so
    they reached the user as a traceback on both routes that read a parameter file.

    The export route is given an engine explicitly: batch_export resolves one before it reads
    the parameter file, so without --openscad-path this asserts against "OpenSCAD executable
    not found" wherever none is installed. That is how it reddened the Windows job, which runs
    the unit tests with no OpenSCAD present."""
    from scadbatch.cli import main

    src = tmp_path / "p.json"
    src.write_text(text)
    if command == "json2csv":
        argv = ["json2csv", str(src), str(tmp_path / "out.csv")]
    else:
        scad = tmp_path / "m.scad"
        scad.write_text("cube(1);\n")
        argv = [
            "export",
            str(scad),
            str(src),
            str(tmp_path / "out"),
            "--openscad-path",
            fake_openscad,
            "--dry-run",
        ]

    code = main(argv)

    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err
    assert "p.json" in captured.err and "must be a JSON object" in captured.err


# --- a number OpenSCAD cannot use --------------------------------------------------

# A literal NaN/Infinity/-Infinity is not JSON, and OpenSCAD's reader refuses the whole file
# over one of them, wherever in the document it sits. A number literal that overflows is valid
# JSON: the engine parses the file and drops only that value. Two faults, two messages.


def write_json(tmp_path, text):
    src = tmp_path / "p.json"
    src.write_text(text)
    return src


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_token_json_does_not_define_refuses_the_file(tmp_path, token):
    """Measured against 2026.08.01: one of these makes the engine refuse the file, so a set
    that is itself well formed exports at the model's defaults too."""
    src = write_json(tmp_path, '{"parameterSets": {"big": {"d": 20}, "bad": {"d": ' + token + "}}}")

    with pytest.raises(ValueError) as excinfo:
        read_json(src)

    message = str(excinfo.value)
    assert "p.json" in message
    assert "parameterSets -> bad -> d" in message
    assert token in message
    assert "every set" in message  # the surprising part: the good set is spoiled too


def test_a_token_outside_parameterSets_refuses_the_file_too(tmp_path):
    """The engine's reader refuses the document, not the set, so scanning only the sets
    misses the shape users actually write -- fileFormatVersion sits beside parameterSets."""
    src = write_json(tmp_path, '{"parameterSets": {"big": {"d": 20}}, "fileFormatVersion": NaN}')

    with pytest.raises(ValueError, match=r"fileFormatVersion is NaN"):
        read_json(src)


@pytest.mark.parametrize(
    "value,path",
    [
        ("[1, NaN]", "v[1]"),
        ("[[1], [NaN]]", "v[1][0]"),
        ('{"x": NaN}', "v -> x"),
    ],
    ids=["in-a-list", "nested-lists", "in-an-object"],
)
def test_a_token_in_a_container_is_named_by_its_path(tmp_path, value, path):
    """Naming the parameter alone would say 'v is NaN' when v is a list holding one."""
    src = write_json(tmp_path, '{"parameterSets": {"s": {"v": ' + value + "}}}")

    with pytest.raises(ValueError, match=re.escape(path)):
        read_json(src)


def test_the_path_walk_finds_a_non_finite_without_json_involved():
    """The walk on its own, over a structure built in Python rather than parsed.

    This exists to split one failure into two. The tests above go through json.loads, so if
    they fail while this passes, the document reaching the walk has no non-finite in it and
    the parse is at fault; if this fails too, the walk is. They disagreed between this machine
    and CI once, and nothing distinguished the two causes.
    """
    document = {"parameterSets": {"big": {"d": 20.0}, "bad": {"d": float("nan")}}}

    assert _path_to_non_finite(document) == "parameterSets -> bad -> d"
    assert _path_to_non_finite({"fileFormatVersion": float("inf")}) == "fileFormatVersion"
    assert _path_to_non_finite({"a": {"v": [1, float("-inf")]}}) == "a -> v[1]"
    assert _path_to_non_finite({"a": {"v": [[1], [float("nan")]]}}) == "a -> v[1][0]"
    assert _path_to_non_finite({"a": {"d": 1.0}}) is None


def test_json_loads_puts_the_token_into_the_document_as_a_non_finite_float():
    """The other half: that this interpreter's json.loads really does hand the walk a
    non-finite float for each token, through whichever scanner it uses."""
    for token, check in (
        ("NaN", math.isnan),
        ("Infinity", lambda v: v > 0),
        ("-Infinity", lambda v: v < 0),
    ):
        document = json.loads('{"d": ' + token + "}")
        value = document["d"]
        assert isinstance(value, float), (token, type(value))
        assert not math.isfinite(value), (token, value)
        assert check(value), (token, value)


def test_an_overflowing_number_is_refused_as_out_of_range(tmp_path):
    """1e999 is well-formed JSON, so the engine parses the file and drops only that value --
    measured: d echoes as 5, the model's default, with no ERROR: line, where 1e308 echoes as
    1e+308. Saying the file is refused would be false, and coerce_cell already calls this out
    of range on the CSV route."""
    src = write_json(tmp_path, '{"parameterSets": {"s": {"d": 1e999}}}')

    with pytest.raises(ValueError) as excinfo:
        read_json(src)

    message = str(excinfo.value)
    assert "out of range" in message
    assert "this parameter alone" in message
    assert "every set" not in message  # that claim belongs to the token case only


def test_a_modestly_nested_file_reads_everywhere(tmp_path):
    """Shallow enough for every supported interpreter, so this says nothing about limits --
    it is here so the two tests below cannot both pass by refusing everything."""
    src = write_json(
        tmp_path, '{"parameterSets": {"s": {"v": ' + "[" * 100 + "1" + "]" * 100 + "}}}"
    )

    (read,) = read_json(src)

    assert read["exported_filename"] == "s"


def test_a_file_too_deep_for_this_interpreter_reports_rather_than_tracebacks(tmp_path):
    """json.loads recurses per level and how far it gets depends on the version: 3.13 parses
    2000 levels where 3.10 raises. RecursionError is not a ValueError, so the depth decided
    whether the user got a message or a traceback. Asserting a depth parses is therefore an
    assertion about the interpreter; what matters is that either way it is a message."""
    src = write_json(
        tmp_path, '{"parameterSets": {"s": {"v": ' + "[" * 100_000 + "1" + "]" * 100_000 + "}}}"
    )

    with pytest.raises(ValueError, match="nests too deeply"):
        read_json(src)


def test_the_walk_itself_handles_nesting_no_recursive_one_could(tmp_path):
    """The walk, directly, past any plausible recursion limit -- built in Python because
    json.loads cannot deliver a structure this deep on every version."""
    document = {"parameterSets": {"s": {"v": None}}}
    deep = [float("nan")]
    for _ in range(10_000):
        deep = [deep]
    document["parameterSets"]["s"]["v"] = deep

    found = _path_to_non_finite(document)

    assert found is not None and found.startswith("parameterSets -> s -> v[0]")


@pytest.mark.parametrize("value", ["0", "-1", "1e308", "1.5", '"NaN"', "true", "null"])
def test_a_usable_value_is_untouched(tmp_path, value):
    """Only 1e308 and 1.5 reach the overflow check; the rest are ints, a string, a bool and
    null, which it never sees. They are here as boundary cases, not as coverage of it."""
    src = write_json(tmp_path, '{"parameterSets": {"s": {"v": ' + value + "}}}")

    (read,) = read_json(src)

    assert read["exported_filename"] == "s" and "v" in read


def test_the_message_speaks_json_rather_than_python(tmp_path):
    """The file is JSON and its format is OpenSCAD's Customizer; 'dict' and 'list' are
    Python's words for things the user never wrote."""
    src = tmp_path / "p.json"
    src.write_text("[]\n")

    message = str(pytest.raises(ValueError, read_json, src).value)

    assert "dict" not in message and "list" not in message
