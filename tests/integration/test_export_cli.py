"""End-to-end tests that drive the CLI against a real OpenSCAD executable.

Skipped as a whole when `openscad` is not on PATH.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which(os.environ.get("OPENSCAD", "openscad")) is None,
    reason="openscad not on PATH (or $OPENSCAD not resolvable)",
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SIMPLE_CUBE = EXAMPLES / "simpleCube"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "scadbatch.export", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def read_stl(path):
    """Return (triangle_count, max_coordinate) for a binary or ASCII STL."""
    data = path.read_bytes()
    if data.startswith(b"solid") and b"facet normal" in data[:512]:
        text = data.decode()
        coords = [
            float(v)
            for line in text.splitlines()
            if line.strip().startswith("vertex")
            for v in line.split()[1:]
        ]
        return text.count("facet normal"), max(coords)
    (count,) = struct.unpack_from("<I", data, 80)
    assert len(data) == 84 + 50 * count, f"binary STL length mismatch in {path.name}"
    max_coord = float("-inf")
    for i in range(count):
        values = struct.unpack_from("<12f", data, 84 + 50 * i)
        max_coord = max(max_coord, *values[3:])  # skip the normal
    return count, max_coord


CUBES = {"cube_small": 10, "cube_medium": 20, "cube_large": 30}


@pytest.mark.parametrize("parameter_file", ["simpleCube.csv", "simpleCube.json"])
def test_exports_every_parameter_set_as_valid_stl(parameter_file, tmp_path):
    result = run_cli(
        "export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / parameter_file, tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert sorted(p.stem for p in tmp_path.glob("*.stl")) == sorted(CUBES)
    for name, size in CUBES.items():
        triangles, max_coord = read_stl(tmp_path / f"{name}.stl")
        assert triangles == 12, name
        assert max_coord == pytest.approx(size), name


def test_sequential_matches_parallel(tmp_path):
    parallel, sequential = tmp_path / "par", tmp_path / "seq"
    run_cli("export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / "simpleCube.csv", parallel)
    run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        sequential,
        "--sequential",
    )

    for name in CUBES:
        assert (parallel / f"{name}.stl").read_bytes() == (sequential / f"{name}.stl").read_bytes()


def test_ascii_stl_format(tmp_path):
    run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        tmp_path,
        "--export_format",
        "asciistl",
    )

    out = tmp_path / "cube_small.stl"
    assert out.read_bytes().startswith(b"solid")
    assert read_stl(out) == (12, pytest.approx(10))


def test_select_limits_which_sets_are_exported(tmp_path):
    result = run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        tmp_path,
        "--select",
        "0,2",
    )

    assert result.returncode == 0, result.stderr
    assert sorted(p.stem for p in tmp_path.glob("*.stl")) == ["cube_large", "cube_small"]


def test_failing_case_does_not_stop_the_batch(tmp_path):
    scad = tmp_path / "guarded.scad"
    scad.write_text('size = 1;\nassert(size > 0, "size must be positive");\ncube(size);\n')
    params = tmp_path / "params.csv"
    params.write_text("exported_filename,size\ngood,5\nbad,-1\n")
    out = tmp_path / "out"

    result = run_cli("export", scad, params, out)

    assert result.returncode == 1
    assert (out / "good.stl").exists()
    assert not (out / "bad.stl").exists()
    assert "Successful exports: 1" in result.stdout
    assert "Failed exports: 1" in result.stdout
    assert "size must be positive" in result.stdout


def test_literal_serialization_survives_openscad(tmp_path):
    """Values with quotes, backslashes, nested vectors, exponents and undef reach the model
    intact; the model asserts on every one of them."""
    scad = tmp_path / "check.scad"
    scad.write_text(
        'label = "x"; pts = [0]; code = "0"; n = 0; tiny = 1; path = "p"; maybe = 1;\n'
        'assert(label == "say \\"hi\\"", str("label=", label));\n'
        'assert(pts == [1, [2, 3], "a b"], str("pts=", pts));\n'
        'assert(code == "007", str("code=", code));\n'
        'assert(n == 1000, str("n=", n));\n'
        'assert(tiny == 0.00001, str("tiny=", tiny));\n'
        'assert(path == "C:\\\\dir\\\\f", str("path=", path));\n'
        'assert(maybe == undef, str("maybe=", maybe));\n'
        "cube(1);\n"
    )
    params = tmp_path / "params.csv"
    params.write_text(
        "exported_filename,label,pts,code,n,tiny,path,maybe\n"
        'ok,"say ""hi""","[1,[2,3],""a b""]","""007""",1e3,1e-05,C:\\dir\\f,undef\n'
    )

    result = run_cli("export", scad, params, tmp_path / "out")

    assert result.returncode == 0, result.stdout
    assert (tmp_path / "out" / "ok.stl").exists()


def test_parameter_sets_are_typed_by_the_model_not_by_us(tmp_path):
    """Through -p/-P, OpenSCAD types each value by the model's default: a string
    parameter whose value looks numeric stays a string, and keys absent from the set
    keep the model's defaults. Neither is expressible through -D."""
    scad = tmp_path / "typed.scad"
    scad.write_text(
        'label = "x"; width = 10; depth = 3;\n'
        'assert(label == "007", str("label=", label));\n'
        'assert(width == 20, str("width=", width));\n'
        'assert(depth == 3, str("depth=", depth));\n'
        "cube([width, depth, 1]);\n"
    )
    sets = tmp_path / "sets.json"
    sets.write_text('{"parameterSets": {"partial": {"label": "007", "width": "20"}}}')

    result = run_cli("-v", "export", scad, sets, tmp_path / "out")

    assert result.returncode == 0, result.stdout
    assert "Passing parameter sets natively with -p/-P." in result.stdout
    assert f"-p {sets} -P partial" in result.stdout
    assert "-Dlabel" not in result.stdout


def test_json_via_p_and_csv_via_d_produce_identical_geometry(tmp_path):
    via_sets, via_flags = tmp_path / "sets", tmp_path / "flags"
    run_cli("export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / "simpleCube.json", via_sets)
    run_cli("export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / "simpleCube.csv", via_flags)

    for name in CUBES:
        assert (via_sets / f"{name}.stl").read_bytes() == (via_flags / f"{name}.stl").read_bytes()


def test_other_output_formats_through_real_openscad(tmp_path):
    result = run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        tmp_path,
        "--select",
        "0",
        "--format",
        "off",
        "--format",
        "3mf",
        "--format",
        "png",
        "--imgsize",
        "64,48",
    )

    assert result.returncode == 0, result.stdout
    assert (tmp_path / "cube_small.off").read_text().startswith("OFF")
    assert (tmp_path / "cube_small.3mf").read_bytes().startswith(b"PK")  # 3MF is a zip container
    png = (tmp_path / "cube_small.png").read_bytes()
    assert png.startswith(b"\x89PNG")
    assert struct.unpack(">II", png[16:24]) == (64, 48)  # IHDR width, height
    assert not (tmp_path / "cube_small.stl").exists()


def test_unwritable_format_fails_per_case_with_openscads_own_message(tmp_path):
    result = run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        tmp_path / "out",
        "--select",
        "0",
        "--format",
        "xyz",
        "--format",
        "off",
    )

    assert result.returncode == 1
    assert "xyz not listed by OpenSCAD" in result.stdout
    assert "Failed exports: 1" in result.stdout and "Successful exports: 1" in result.stdout
    assert (tmp_path / "out" / "cube_small.off").exists()
    assert not (tmp_path / "out" / "cube_small.xyz").exists()


def test_dry_run_prints_the_real_command_and_touches_nothing(tmp_path):
    out = tmp_path / "out"
    result = run_cli(
        "export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / "simpleCube.csv", out, "--dry-run"
    )

    assert result.returncode == 0, result.stdout
    assert not out.exists()
    assert result.stdout.count("Would run: ") == 3
    assert f"-o {out / 'cube_small.stl'} --export-format=binstl -Ddepth=10" in result.stdout
    assert "Dry run: 3 export(s) would run." in result.stdout


def test_skip_existing_does_not_re_render(tmp_path):
    first = run_cli(
        "export", SIMPLE_CUBE / "simpleCube.scad", SIMPLE_CUBE / "simpleCube.csv", tmp_path
    )
    assert first.returncode == 0
    (tmp_path / "cube_medium.stl").unlink()
    before = {p.name: p.stat().st_mtime_ns for p in tmp_path.glob("*.stl")}

    second = run_cli(
        "export",
        SIMPLE_CUBE / "simpleCube.scad",
        SIMPLE_CUBE / "simpleCube.csv",
        tmp_path,
        "--skip-existing",
    )

    assert second.returncode == 0, second.stdout
    assert "Skipped (already present): 2" in second.stdout
    assert "Total exports attempted: 1" in second.stdout
    assert (tmp_path / "cube_medium.stl").exists()  # the missing one was rendered
    for name, mtime in before.items():
        assert (tmp_path / name).stat().st_mtime_ns == mtime, name  # the others were not


def test_warnings_and_echo_are_captured_into_the_json_summary(tmp_path):
    import json

    scad = tmp_path / "noisy.scad"
    scad.write_text('size = 5;\necho("size is", size);\nx = undefined_thing;\ncube(size);\n')
    params = tmp_path / "params.csv"
    params.write_text("exported_filename,size\na,5\n")
    summary = tmp_path / "run.json"

    result = run_cli("export", scad, params, tmp_path / "out", "--summary", summary)

    assert result.returncode == 0, result.stdout
    doc = json.loads(summary.read_text())
    (case,) = doc["results"]
    assert case["status"] == "ok" and case["returncode"] == 0
    assert any(w.startswith("ECHO:") and '"size is", 5' in w for w in case["warnings"]), case
    assert any(w.startswith("WARNING:") and "undefined_thing" in w for w in case["warnings"]), case
    assert doc["openscad"]["version"] and doc["openscad"]["path"]
    # Our own version resolves through importlib.metadata, so it is None whenever the
    # distribution name it looks up stops matching the installed one. These tests run
    # against a real install, which is the only place that mismatch is visible.
    assert doc["tool"]["version"], doc["tool"]
    assert doc["inputs"]["scad_file"] == str(scad)
    assert case["command"][0] == doc["openscad"]["path"]
    assert "OpenSCAD warnings from 1 successful case(s):" in result.stdout
    assert "ECHO:" in result.stdout  # re-logged per case as it happened


def test_timeout_kills_a_slow_render_and_leaves_nothing_behind(tmp_path):
    scad = tmp_path / "slow.scad"
    scad.write_text(
        "n = 1;\n"
        "if (n < 0) cube(1);  // the cheap case, for any engine\n"
        "else for (i = [0:n]) for (j = [0:n]) translate([i * 5, j * 5, 0])\n"
        "    difference() { sphere(2, $fn = 96); sphere(1.5, $fn = 96); }\n"
    )
    params = tmp_path / "params.csv"
    params.write_text("exported_filename,n\nbig,12\nsmall,-1\n")
    out = tmp_path / "out"

    result = run_cli("export", scad, params, out, "--timeout", "1", "-j", "1")

    assert result.returncode == 1
    assert "big.stl: Timed out after 1 s" in result.stdout
    assert "Successful exports: 1" in result.stdout  # the batch continued to the small case
    assert sorted(p.name for p in out.iterdir()) == ["small.stl"]  # no partial, no .part


def test_unsafe_set_name_is_sanitised_but_still_selects_the_right_set(tmp_path):
    """A Customizer set called "lid/large" must not become a subdirectory, and the
    original name must still reach -P: OpenSCAD silently exports the defaults for an
    unknown set name, so the geometry proves the parameters applied."""
    scad = tmp_path / "m.scad"
    scad.write_text("size = 1;\ncube(size);\n")
    sets = tmp_path / "sets.json"
    sets.write_text('{"parameterSets": {"lid/large": {"size": "30"}}}')

    result = run_cli("export", scad, sets, tmp_path / "out")

    assert result.returncode == 0, result.stdout
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["lid_large.stl"]
    assert read_stl(tmp_path / "out" / "lid_large.stl") == (12, pytest.approx(30))
    assert "not a safe file name" in result.stdout


def test_converted_flat_numeric_vectors_reach_openscad_as_literals(tmp_path):
    """csv2json stores a vector as an OpenSCAD literal in a string, because -p/-P
    ignores a JSON array outright. Only a flat numeric vector survives even that; the
    kinds that do not are warned about at conversion time (see test_conversion_types)."""
    scad = tmp_path / "m.scad"
    scad.write_text('pts = [0, 0];\nassert(pts == [3, 4], str("pts=", pts));\ncube(1);\n')
    params = tmp_path / "p.csv"
    params.write_text('exported_filename,pts\nrow,"[3, 4]"\n')
    sets = tmp_path / "sets.json"
    assert run_cli("csv2json", params, sets).returncode == 0

    result = run_cli("export", scad, sets, tmp_path / "out")

    assert result.returncode == 0, result.stdout
    assert (tmp_path / "out" / "row.stl").exists()

    # the same set written as a JSON array is ignored by OpenSCAD, which is why it is not
    arr = tmp_path / "arr.json"
    arr.write_text('{"parameterSets": {"row": {"pts": [3, 4]}}}')

    ignored = run_cli("export", scad, arr, tmp_path / "out2")

    assert ignored.returncode == 1
    assert "pts=[0, 0]" in ignored.stdout


def test_parameter_set_files_ignore_the_value_kinds_the_converter_warns_about(tmp_path):
    """Pins the engine behaviour the csv2json warning rests on. A nested vector and undef
    are ignored by every engine measured; ranges and vectors of strings are applied by
    2021.01 and ignored by current builds."""
    scad = tmp_path / "m.scad"
    scad.write_text(
        'nested = [[0, 0]];\nrng = [0:1];\nmaybe = 1;\nstrvec = ["x"];\nflat = [0, 0];\n'
        "echo(nested = nested, rng = rng, maybe = maybe, strvec = strvec, flat = flat);\ncube(1);\n"
    )
    sets = tmp_path / "sets.json"
    sets.write_text(
        json.dumps(
            {
                "parameterSets": {
                    "row": {
                        "nested": "[[1, 2]]",
                        "rng": "[0 : 2 : 10]",
                        "maybe": "undef",
                        "strvec": '["a", "b"]',
                        "flat": "[3, 4]",
                    }
                }
            }
        )
    )

    result = run_cli("export", scad, sets, tmp_path / "out")

    assert result.returncode == 0, result.stdout
    echo = next(line for line in result.stdout.splitlines() if "ECHO:" in line)
    version = next(
        line.split("version ")[1].split()[0]
        for line in result.stdout.splitlines()
        if "Using OpenSCAD version" in line
    )

    # true of every engine measured: a flat numeric vector applies, a nested vector and
    # undef do not
    assert "flat = [3, 4]" in echo
    assert "nested = [[0, 0]]" in echo
    assert "maybe = 1" in echo

    # ranges and vectors of strings changed somewhere between 2021.01 and 2026.09: the
    # older engine applies them, current builds keep the model's default
    if int(version.split(".")[0]) <= 2021:
        assert "rng = [0 : 2 : 10]" in echo
        assert 'strvec = ["a", "b"]' in echo
    else:
        assert "rng = [0 : 1 : 1]" in echo
        assert 'strvec = ["x"]' in echo
