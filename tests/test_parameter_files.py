import csv
import json
from pathlib import Path

import pytest

from scadbatch.params import csv_to_json, json_to_csv, read_csv, read_json

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


def test_json_root_must_be_object(tmp_path):
    """A JSON file whose root is a list (e.g. []) must report a clear error."""
    src = tmp_path / "p.json"
    src.write_text("[]\n")

    with pytest.raises(ValueError) as excinfo:
        read_json(src)

    assert "JSON root must be a dict" in str(excinfo.value)
    assert "'parameterSets'" in str(excinfo.value)
