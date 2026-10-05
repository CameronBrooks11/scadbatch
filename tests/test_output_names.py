import logging

import pytest

from scadbatch import batch_export, output_name, sanitize_filename
from scadbatch.cli import main

SCAD = "model.scad"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("lid", "lid"),
        ("Medium Size", "Medium Size"),
        ("Größe 日本", "Größe 日本"),
        ("lid/large", "lid_large"),
        ("lid\\large", "lid_large"),
        ("a:b", "a_b"),
        ('say "hi"', "say _hi_"),
        ("<x>|?*", "_x____"),
        ("tab\there", "tab_here"),
        ("  padded  ", "padded"),
        ("..hidden", "hidden"),
        ("trailing.", "trailing"),
        ("CON", "CON_"),
        ("nul", "nul_"),
        ("COM1", "COM1_"),
        ("COM10", "COM10"),  # only COM1-9 are reserved
        ("con.txt", "con.txt_"),  # Windows treats NUL.txt as the device too
        ("L" * 300, "L" * 200),  # cut to leave room for .part and an extension
        ("é" * 150, "é" * 100),  # by UTF-8 bytes, at a character boundary
        ("", "fallback"),
        ("///", "___"),
        (" . ", "fallback"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw, "fallback") == expected


def test_default_name_is_exported_filename_or_model_index():
    assert output_name({"exported_filename": "lid", "d": 1}, 3) == "lid"
    assert output_name({"d": 1}, 3) == "model_3"
    assert output_name({"exported_filename": "lid/large"}, 0) == "lid_large"


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{name}", "lid"),
        ("{name}_d{d}", "lid_d12"),
        ("part_{index:03d}", "part_007"),
        ("{d}x{h}", "12x3.5"),
        ("{material}", "steel"),
        ("{name}/{d}", "lid_12"),  # template output is sanitised too
        ("fixed", "fixed"),
    ],
)
def test_name_template_fields(template, expected):
    params = {"exported_filename": "lid", "d": 12, "h": 3.5, "material": "steel"}
    assert output_name(params, 7, template) == expected


def test_name_template_uses_model_index_when_there_is_no_name():
    assert output_name({"d": 12}, 4, "{name}_d{d}") == "model_4_d12"


def test_name_template_with_unknown_field_names_it_and_lists_the_fields():
    with pytest.raises(ValueError, match=r"'diameter'.*available fields: d, h, index, name"):
        output_name({"exported_filename": "lid", "d": 1, "h": 2}, 0, "{name}_{diameter}")


@pytest.mark.parametrize(
    "template",
    ["{d:03d}", "{name[zz]}", "{d.__class__.__init__.__globals__}", "{0}", "{", "{name!x}"],
)
def test_template_mistakes_are_always_value_errors(template):
    with pytest.raises(ValueError, match="could not be filled"):
        output_name({"exported_filename": "lid", "d": "x"}, 0, template)


def test_template_attribute_access_cannot_call_anything():
    # str.format allows attribute and index reads but never calls; the worst case is a
    # long, odd, but harmless name
    name = output_name({"exported_filename": "lid"}, 0, "{name.__class__.__name__}")
    assert name == "str"


# --- through batch_export -----------------------------------------------------------


@pytest.fixture
def params_csv(tmp_path):
    p = tmp_path / "params.csv"
    p.write_text("exported_filename,d\nlid,10\nbase,12\n")
    return str(p)


def run(fake_openscad, params_csv, out, **kwargs):
    return batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, True, **kwargs)


def test_unsafe_set_name_is_sanitised_for_the_file_but_not_for_openscad(
    fake_openscad, tmp_path, caplog
):
    sets = tmp_path / "sets.json"
    sets.write_text('{"parameterSets": {"lid/large": {"d": "10"}, "CON": {"d": "12"}}}')
    out = tmp_path / "o"

    with caplog.at_level(logging.WARNING, logger="scadbatch"):
        result = run(fake_openscad, str(sets), out)

    assert sorted(p.name for p in out.iterdir()) == ["CON_.stl", "lid_large.stl"]
    assert [r.name for r in result.results] == ["lid_large", "CON_"]
    # the Customizer set name handed to -P must be the original, or OpenSCAD silently
    # exports the defaults
    assert (out / "lid_large.stl").read_text().splitlines()[-1] == "lid/large"
    assert "Output name 'lid/large' is not a safe file name; using 'lid_large'." in caplog.text


def test_name_template_through_batch_export(fake_openscad, params_csv, tmp_path):
    out = tmp_path / "o"

    result = run(
        fake_openscad, params_csv, out, name_template="{name}-d{d}", formats=["stl", "png"]
    )

    assert sorted(p.name for p in out.iterdir()) == [
        "base-d12.png",
        "base-d12.stl",
        "lid-d10.png",
        "lid-d10.stl",
    ]
    assert result.inputs["name_template"] == "{name}-d{d}"


def test_duplicate_names_are_refused_before_anything_runs(fake_openscad, tmp_path, monkeypatch):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,d\ndup,1\nother,2\ndup,3\n")
    out = tmp_path / "o"
    probe = tmp_path / "probe.log"
    monkeypatch.setenv("FAKE_OPENSCAD_LOG", str(probe))

    with pytest.raises(ValueError, match=r"Duplicate output names: 'dup' from parameter sets 0, 2"):
        run(fake_openscad, str(csv), out)

    assert not out.exists()
    assert list(tmp_path.glob("probe.log.*")) == []


def test_names_differing_only_by_case_are_duplicates(fake_openscad, tmp_path):
    """Windows and macOS file systems are case-insensitive; Lid and lid are one file."""
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,d\nLid,1\nlid,2\n")

    with pytest.raises(
        ValueError, match="Duplicate output names: 'Lid' / 'lid' from parameter sets 0, 1"
    ):
        run(fake_openscad, str(csv), tmp_path / "o")


def test_names_that_collide_only_after_sanitising_are_duplicates_too(fake_openscad, tmp_path):
    sets = tmp_path / "sets.json"
    sets.write_text('{"parameterSets": {"a/b": {"d": "1"}, "a:b": {"d": "2"}}}')

    with pytest.raises(ValueError, match="Duplicate output names: 'a_b'"):
        run(fake_openscad, str(sets), tmp_path / "o")


def test_duplicates_outside_the_selection_do_not_matter(fake_openscad, tmp_path):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,d\ndup,1\nother,2\ndup,3\n")

    result = batch_export(SCAD, str(csv), str(tmp_path / "o"), fake_openscad, "binstl", "0-1", True)

    assert [r.name for r in result.results] == ["dup", "other"]


def test_template_can_resolve_duplicates(fake_openscad, tmp_path):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,d\ndup,1\ndup,3\n")

    result = run(fake_openscad, str(csv), tmp_path / "o", name_template="{name}_{index}")

    assert [r.name for r in result.results] == ["dup_0", "dup_1"]


def test_a_blank_cell_does_not_stop_a_templated_batch(fake_openscad, tmp_path):
    """Names are computed for every case before anything exports, so without the file's
    columns reaching output_name one blank cell refuses the whole run."""
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,w,label\na,10,hi\nb,20,\nc,30,yo\n")

    result = run(fake_openscad, str(csv), tmp_path / "o", name_template="{name}_{label}")

    assert [r.name for r in result.results] == ["a_hi", "b_", "c_yo"]


def test_bad_template_is_refused_before_anything_runs(fake_openscad, params_csv, tmp_path):
    with pytest.raises(ValueError, match="could not be filled"):
        run(fake_openscad, params_csv, tmp_path / "o", name_template="{nope}")
    assert not (tmp_path / "o").exists()


# --- CLI -----------------------------------------------------------------------------


def cli_args(params_csv, tmp_path, fake_openscad, *extra):
    return [
        "export",
        SCAD,
        params_csv,
        str(tmp_path / "out"),
        "--openscad-path",
        fake_openscad,
        *extra,
    ]


def test_cli_name_template(fake_openscad, params_csv, tmp_path):
    code = main(
        cli_args(params_csv, tmp_path, fake_openscad, "--name-template", "part_{index:02d}")
    )

    assert code == 0
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["part_00.stl", "part_01.stl"]


def test_cli_duplicate_names_are_a_clean_error(fake_openscad, tmp_path, capsys):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,d\ndup,1\ndup,3\n")

    code = main(cli_args(str(csv), tmp_path, fake_openscad))

    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: Duplicate output names") and "{name}_{index}" in err


def test_json_record_keeps_index_and_original_set_name(fake_openscad, tmp_path):
    sets = tmp_path / "sets.json"
    sets.write_text('{"parameterSets": {"lid/large": {"d": "10"}}}')

    doc = run(fake_openscad, str(sets), tmp_path / "o", formats=["stl", "png"]).to_dict()

    assert [(r["index"], r["set_name"], r["name"]) for r in doc["results"]] == [
        (0, "lid/large", "lid_large"),
        (0, "lid/large", "lid_large"),
    ]
    csv = tmp_path / "p.csv"
    csv.write_text("d\n1\n")
    (case,) = run(fake_openscad, str(csv), tmp_path / "o2").to_dict()["results"]
    assert (case["index"], case["set_name"], case["name"]) == (0, None, "model_0")


def test_exit_zero_without_an_output_file_is_a_failure(fake_openscad, tmp_path, monkeypatch):
    """OpenSCAD exits 0 for "Can't open file" on a path it cannot write."""
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,d\nghost,1\n")
    monkeypatch.setenv("FAKE_OPENSCAD_NO_OUTPUT", "1")

    result = run(fake_openscad, str(csv), tmp_path / "o")

    (case,) = result.results
    assert case.ok is False and case.returncode == 0
    assert case.stderr.startswith("Can't open file")  # OpenSCAD's own message is kept
    assert list((tmp_path / "o").iterdir()) == []


def test_a_template_may_name_a_parameter_this_set_leaves_unset():
    """An unset parameter is absent from the row, so without the columns the template could
    not be filled and one blank cell would stop the whole batch before anything exported."""
    assert (
        output_name({"exported_filename": "b", "w": 20}, 1, "{name}_{label}", {"w", "label"})
        == "b_"
    )


def test_a_template_naming_no_parameter_at_all_is_still_an_error():
    """The safety net the columns must not dissolve: a typo stays a typo."""
    with pytest.raises(ValueError, match=r"'labl'.*available fields:"):
        output_name({"exported_filename": "b", "w": 20}, 1, "{name}_{labl}", {"w", "label"})
