"""CSV <-> JSON conversion must use the same value interpretation as the exporter."""

import csv
import json
import logging

import pytest

from scadbatch.params import (
    coerce_cell,
    construct_d_flags,
    csv_to_json,
    json_to_csv,
    read_csv,
)


def convert(tmp_path, cells):
    """Write one CSV row, convert it to JSON, and return the parameter set."""
    src = tmp_path / "p.csv"
    with open(src, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["exported_filename", *cells])
        writer.writeheader()
        writer.writerow({"exported_filename": "row", **cells})
    out = tmp_path / "p.json"
    csv_to_json(src, out)
    return json.loads(out.read_text())["parameterSets"]["row"]


@pytest.mark.parametrize(
    ("cell", "stored"),
    [
        ("12", 12),
        ("-2.5", -2.5),
        (".5", 0.5),
        ("1e3", 1000.0),
        ("true", True),
        ("FALSE", False),
        ("hello", "hello"),
        ('"007"', "007"),  # the quote hatch keeps it a string
        ("undef", "undef"),  # written as the OpenSCAD literal
        ("[1, 2, 3]", "[1, 2, 3]"),  # a vector, as a literal in a string
        ("[[0,0],[1,1]]", "[[0, 0], [1, 1]]"),
        ("1_000", "1_000"),  # not a number in OpenSCAD's grammar, so a string
        ("1.2.3", "1.2.3"),
        ("inf", "inf"),
    ],
)
def test_csv_to_json_stores_what_the_exporter_would_read(tmp_path, cell, stored):
    assert convert(tmp_path, {"v": cell})["v"] == stored


def test_underscore_number_means_the_same_either_way(tmp_path):
    """CSV -> export and CSV -> JSON -> export must agree; Python's int() accepts
    underscores and OpenSCAD's grammar does not."""
    direct = construct_d_flags({"a": "1_000"})
    via_json = construct_d_flags({"a": convert(tmp_path, {"a": "1_000"})["a"]})

    assert direct == ['-Da="1_000"']
    assert via_json == direct


def test_vectors_are_stored_as_strings_not_json_arrays(tmp_path):
    """OpenSCAD's -p ignores a JSON array and keeps the model default, so the literal
    has to reach it as text."""
    stored = convert(tmp_path, {"pts": "[1, 2]"})["pts"]

    assert isinstance(stored, str)
    assert coerce_cell(stored) == [1, 2]


@pytest.mark.parametrize(
    "cell",
    ["[[1, 2]]", "[0:2:10]", "undef", '["a", "b"]', "[true, false]"],
    ids=["nested", "range", "undef", "string-vector", "bool-vector"],
)
def test_value_kinds_openscad_ignores_in_a_parameter_set_are_warned_about(tmp_path, cell, caplog):
    """Only a flat numeric vector survives the literal-in-a-string encoding; for the rest
    OpenSCAD silently keeps the model's default, so the conversion must say so."""
    with caplog.at_level(logging.WARNING, logger="scadbatch"):
        stored = convert(tmp_path, {"v": cell})["v"]

    assert isinstance(stored, str)
    # the warning must name the parameter, show the value, and point at the CSV route;
    # the exact sentence is not pinned
    (record,) = [r for r in caplog.records if r.levelname == "WARNING"]
    message = record.getMessage()
    assert "'v'" in message and stored in message
    assert "model's default" in message and "CSV" in message


@pytest.mark.parametrize("cell", ["[1, 2]", "[3]", "[1.5, -2, 0]"])
def test_flat_numeric_vectors_are_not_warned_about(tmp_path, cell, caplog):
    with caplog.at_level(logging.WARNING, logger="scadbatch"):
        convert(tmp_path, {"v": cell})

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []


def test_a_cell_that_cannot_be_read_names_the_row_and_column(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,label\nfirst,ok\nsecond,[draft]\n")

    with pytest.raises(ValueError, match=r"Row 1, column 'label': Invalid vector"):
        csv_to_json(src, tmp_path / "p.json")


def test_duplicate_row_names_are_refused_instead_of_dropping_a_row(tmp_path):
    """A parameter-set file holds one set per name, so two rows called the same thing
    would silently become one; the exporter refuses them too."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d\nsame,10\nsame,20\nother,30\n")

    with pytest.raises(ValueError, match=r"Duplicate parameter set name 'same'"):
        csv_to_json(src, tmp_path / "p.json")


def test_blank_names_fall_back_to_the_index_like_the_exporter(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,d\n,1\n,2\n")
    out = tmp_path / "p.json"

    csv_to_json(src, out)

    assert list(json.loads(out.read_text())["parameterSets"]) == ["model_0", "model_1"]


def test_json_to_csv_writes_cells_the_exporter_can_read_back(tmp_path):
    src = tmp_path / "p.json"
    src.write_text(
        json.dumps(
            {
                "parameterSets": {
                    "row": {
                        "n": 12,
                        "x": 2.5,
                        "flag": True,
                        "off": False,
                        "label": "hello",
                        "pts": ["a", "b"],
                        "nested": [1, [2, 3]],
                        "nothing": None,
                    }
                }
            }
        )
    )
    out = tmp_path / "p.csv"

    json_to_csv(src, out)

    with open(out, newline="") as f:
        (row,) = list(csv.DictReader(f))
    assert row["n"] == "12" and row["x"] == "2.5"
    assert row["flag"] == "true" and row["off"] == "false"
    assert row["label"] == "hello"
    assert row["pts"] == '["a", "b"]'  # not Python's ['a', 'b']
    assert row["nested"] == "[1, [2, 3]]"
    assert row["nothing"] == "undef"
    # every cell round-trips through the exporter's own reader
    assert coerce_cell(row["pts"]) == ["a", "b"]
    assert coerce_cell(row["nested"]) == [1, [2, 3]]
    assert coerce_cell(row["nothing"]) is None
    assert construct_d_flags(row)  # no ValueError from a malformed cell


def test_list_values_round_trip_csv_to_json_to_csv(tmp_path):
    src = tmp_path / "a.csv"
    src.write_text('exported_filename,pts\nrow,"[1, 2, 3]"\n')
    mid, back = tmp_path / "b.json", tmp_path / "c.csv"

    csv_to_json(src, mid)
    json_to_csv(mid, back)

    with open(back, newline="") as f:
        (row,) = list(csv.DictReader(f))
    assert row["pts"] == "[1, 2, 3]"
    assert coerce_cell(row["pts"]) == [1, 2, 3]


def test_unnamed_rows_get_the_index_the_exporter_uses(tmp_path):
    """Without an exported_filename column the exporter names cases model_<index>,
    zero-based; the converter used to number from 1 and to resolve the index by
    equality, so identical rows collapsed onto the first one."""
    src = tmp_path / "p.csv"
    src.write_text("d\n5\n5\n7\n")
    out = tmp_path / "p.json"

    csv_to_json(src, out)

    assert list(json.loads(out.read_text())["parameterSets"]) == ["model_0", "model_1", "model_2"]


def test_cli_reports_a_bad_cell_without_a_traceback(tmp_path, capsys):
    from scadbatch.cli import main

    src = tmp_path / "p.csv"
    src.write_text("exported_filename,label\nrow,[draft]\n")

    code = main(["csv2json", str(src), str(tmp_path / "p.json")])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error: Row 0, column 'label'")
    assert "Traceback" not in captured.err


def test_cli_reports_an_unserialisable_json_value_without_a_traceback(tmp_path, capsys):
    from scadbatch.cli import main

    src = tmp_path / "p.json"
    src.write_text('{"parameterSets": {"row": {"nested": {"a": 1}}}}')

    code = main(["json2csv", str(src), str(tmp_path / "p.csv")])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error: Cannot serialize dict")
    assert "Traceback" not in captured.err


# --- an empty cell is a parameter that was not set -----------------------------------


def test_an_empty_cell_leaves_the_parameter_out(tmp_path):
    """CSV cannot hold an absent cell, so an empty one has to mean it: a parameter the row
    does not set, left to the model's default."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,x,y\na,1,2\nb,3,\n")

    a, b = read_csv(src)

    assert a == {"exported_filename": "a", "x": "1", "y": "2"}
    assert b == {"exported_filename": "b", "x": "3"}  # no 'y' at all


def test_a_cell_holding_two_quote_characters_is_still_the_empty_string(tmp_path):
    """So nothing becomes inexpressible. The cell's *text* has to be "" for coerce_cell to
    read it as the empty string, and CSV spells that with six quotes: `""` in the file is
    the quoting of an empty field, which the parser yields as '' exactly like a bare comma
    does, so it cannot carry the distinction."""
    src = tmp_path / "p.csv"
    src.write_text('exported_filename,y\nb,""""""\n')

    (b,) = read_csv(src)

    # read_csv hands back the cell's text; coerce_cell is what turns it into a value.
    assert b == {"exported_filename": "b", "y": '""'}
    assert coerce_cell(b["y"]) == ""


def test_a_two_quote_cell_is_not_confused_with_an_empty_one(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text('exported_filename,y\nquoted,""""""\nbare,\n')

    quoted, bare = read_csv(src)

    assert quoted == {"exported_filename": "quoted", "y": '""'}
    assert bare == {"exported_filename": "bare"}  # the key is gone, not empty


def test_an_empty_cell_sends_no_flag_rather_than_an_empty_string(tmp_path):
    """The defect in #63. OpenSCAD cannot read "" as a number: it warns, falls back and
    exits 0, so the wrong model is built and no gate sees it."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,x,y\nb,3,\n")

    (b,) = read_csv(src)

    assert construct_d_flags(b) == ["-Dx=3"]


def test_a_two_quote_cell_does_send_an_empty_string(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text('exported_filename,x,y\nb,3,""""""\n')

    (b,) = read_csv(src)

    assert construct_d_flags(b) == ["-Dx=3", '-Dy=""']


def test_csv_to_json_leaves_out_a_parameter_whose_cell_is_empty(tmp_path):
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,x,y\na,1,2\nb,3,\n")
    out = tmp_path / "p.json"

    csv_to_json(src, out)

    assert json.loads(out.read_text())["parameterSets"] == {
        "a": {"x": 1, "y": 2},
        "b": {"x": 3},
    }


def test_a_set_missing_a_parameter_survives_the_json_csv_json_round_trip(tmp_path):
    """#63's case end to end: `b` has no `y` in the JSON, and must still have none after a
    trip through CSV, or the round trip changes what gets built."""
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"parameterSets": {"a": {"x": "1", "y": "2"}, "b": {"x": "3"}}}))
    csv_file = tmp_path / "mid.csv"
    back = tmp_path / "out.json"

    json_to_csv(src, csv_file)
    csv_to_json(csv_file, back)

    assert json.loads(back.read_text())["parameterSets"] == {
        "a": {"x": 1, "y": 2},
        "b": {"x": 3},
    }


def test_a_json_empty_string_converts_to_unset_like_openscad_treats_it(tmp_path):
    """OpenSCAD ignores "" for any parameter whose default is not a string and keeps the
    default -- measured through -p/-P on 2026.08.01. Carrying it through as an empty string
    would make the CSV route build a model the JSON route does not, which is #63 again."""
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"parameterSets": {"a": {"label": ""}}}))
    csv_file = tmp_path / "mid.csv"
    back = tmp_path / "out.json"

    json_to_csv(src, csv_file)
    csv_to_json(csv_file, back)

    assert csv_file.read_text().splitlines()[1] == "a,"  # a blank cell, not six quotes
    assert json.loads(back.read_text())["parameterSets"] == {"a": {}}


def test_a_blank_name_column_is_kept_because_it_is_not_a_parameter(tmp_path):
    """exported_filename names the output rather than setting anything on the model, so the
    unset rule does not apply: dropping it loses the warning that a blank name fell back to
    model_<index>, and writes null where the summary said ""."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,n\n,3\n")

    (row,) = read_csv(src)

    assert row == {"exported_filename": "", "n": "3"}


def test_each_row_says_which_parameters_it_leaves_unset(tmp_path, caplog):
    """OpenSCAD is silent when it ignores a value. A column nobody filled would otherwise
    export a whole batch at the defaults with nothing anywhere to say so."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,x,height\na,1,5\nb,2,\nc,3,\n")

    with caplog.at_level("INFO", logger="scadbatch"):
        read_csv(src)

    said = [r.getMessage() for r in caplog.records if "unset" in r.getMessage()]
    assert len(said) == 2, said  # rows b and c, not row a
    assert "line 3 leaves height unset" in said[0]
    assert "line 4 leaves height unset" in said[1]


def test_a_whitespace_only_cell_is_as_unset_as_an_empty_one(tmp_path):
    """OpenSCAD cannot convert " " to a number either, so it keeps the default. Leaving the
    flag in sends -Dn=" " and builds something else -- the same defect through a spelling a
    spreadsheet shows as blank."""
    src = tmp_path / "p.csv"
    src.write_text("exported_filename,x,y,z\nb,3, ,\t\n")

    (b,) = read_csv(src)

    assert b == {"exported_filename": "b", "x": "3"}
    assert construct_d_flags(b) == ["-Dx=3"]
