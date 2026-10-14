import json
import logging
import os
import time

import pytest

from scadbatch import batch_export
from scadbatch.cli import main

SCAD = "model.scad"


@pytest.fixture
def params_csv(tmp_path):
    p = tmp_path / "params.csv"
    p.write_text("exported_filename,size,fail\nfirst,5,false\nsecond,7,true\n")
    return str(p)


def run(fake_openscad, params_csv, out, **kwargs):
    return batch_export(SCAD, params_csv, str(out), fake_openscad, "binstl", None, True, **kwargs)


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


# --- timeout -------------------------------------------------------------------------


def test_timed_out_case_is_a_failure_and_the_batch_continues(fake_openscad, tmp_path, monkeypatch):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\nquick,2\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "5")
    monkeypatch.setenv("FAKE_OPENSCAD_PARTIAL", "1")
    started = time.monotonic()

    result = batch_export(
        SCAD, str(csv), str(tmp_path / "o"), fake_openscad, "binstl", "0", True, timeout=0.5
    )

    assert time.monotonic() - started < 4, "the timeout did not kill the process"
    (slow,) = result.results
    assert slow.timed_out is True and slow.ok is False and slow.status == "timeout"
    assert slow.stderr == "Timed out after 0.5 s"
    assert slow.returncode not in (None, 0)  # the process was killed
    assert list((tmp_path / "o").iterdir()) == []  # no partial output left behind
    assert result.failures == [slow]


def test_timeout_leaves_fast_cases_alone(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o", timeout=30)

    assert [r.status for r in result.results] == ["ok", "failed"]
    assert not any(r.timed_out for r in result.results)


@pytest.mark.parametrize("timeout", [0, -1, "5", True])
def test_invalid_timeout_is_rejected_before_anything_runs(
    fake_openscad, params_csv, tmp_path, timeout
):
    with pytest.raises(ValueError, match="timeout must be a positive number"):
        run(fake_openscad, params_csv, tmp_path / "o", timeout=timeout)
    assert not (tmp_path / "o").exists()


def test_timed_out_case_is_reported_in_the_summary_text(fake_openscad, tmp_path, monkeypatch):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "5")

    result = batch_export(
        SCAD, str(csv), str(tmp_path / "o"), fake_openscad, "binstl", None, True, timeout=0.3
    )

    assert "slow.stl: Timed out after 0.3 s" in result.summary()


# --- warnings ------------------------------------------------------------------------


def test_diagnostic_lines_are_captured_on_success(fake_openscad, params_csv, tmp_path, monkeypatch):
    monkeypatch.setenv(
        "FAKE_OPENSCAD_STDERR",
        "Compiling design (CSG Tree generation)...|ECHO: size = 5|WARNING: variable x is unused"
        "|DEPRECATED: old thing|Geometries in cache: 1",
    )

    result = run(fake_openscad, params_csv, tmp_path / "o")

    first = result.results[0]
    assert first.ok and first.stderr == ""  # success still blanks raw stderr
    assert first.warnings == [
        "ECHO: size = 5",
        "WARNING: variable x is unused",
        "DEPRECATED: old thing",
    ]
    # the text summary lists warning-class lines of successful cases only: no ECHO chatter,
    # and the failed case's stderr is already printed in full above it
    text = result.summary()
    assert "OpenSCAD warnings from 1 successful case(s):" in text
    section = text.split("OpenSCAD warnings from", 1)[1]
    assert "      WARNING: variable x is unused" in section
    assert "      DEPRECATED: old thing" in section
    assert "ECHO:" not in section


def test_no_warnings_means_no_warnings_section(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o")

    assert all(r.warnings == [] for r in result.results)
    assert "OpenSCAD warnings" not in result.summary()


def test_warnings_are_captured_on_failure_too(fake_openscad, params_csv, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "WARNING: about to fail")

    result = run(fake_openscad, params_csv, tmp_path / "o")

    # the fake writes its diagnostics before checking fail=true, so the failing case has both
    failed = result.failures[0]
    assert failed.warnings == ["WARNING: about to fail"]
    assert "boom" in failed.stderr


# --- JSON summary --------------------------------------------------------------------


def test_to_dict_records_engine_inputs_and_every_case(
    fake_openscad, params_csv, tmp_path, monkeypatch
):
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "ECHO: hi")
    out = tmp_path / "o"
    out.mkdir()
    (out / "first.png").write_text("present")

    result = run(
        fake_openscad, params_csv, out, formats=["stl", "png"], skip_existing=True, timeout=30
    )
    doc = result.to_dict()

    assert doc["openscad"] == {"path": fake_openscad, "version": "2021.01"}
    assert doc["inputs"]["scad_file"] == SCAD
    assert doc["inputs"]["parameter_file"] == params_csv
    assert doc["inputs"]["formats"] == ["stl", "png"]
    assert doc["inputs"]["jobs"] == 1 and doc["inputs"]["timeout"] == 30
    assert doc["inputs"]["skip_existing"] is True
    assert doc["dry_run"] is False
    assert doc["counts"] == {"ok": 1, "failed": 2, "timeout": 0, "skipped": 1, "errors": 0}
    assert doc["started_at"].endswith("+00:00")  # ISO 8601, UTC
    # Keyed by role, with the name in the record: a consumer reads which tool wrote the
    # summary rather than having to know the key. Version is None when not installed.
    assert doc["tool"]["name"] == "scadbatch"
    assert set(doc["tool"]) == {"name", "version"}
    assert "openscad_batch_export" not in doc  # the pre-rename key is gone, not aliased
    statuses = [(r["name"], r["format"], r["status"]) for r in doc["results"]]
    assert statuses == [
        ("first", "stl", "ok"),
        ("first", "png", "skipped"),
        ("second", "stl", "failed"),
        ("second", "png", "failed"),
    ]
    ok = doc["results"][0]
    assert ok["returncode"] == 0 and ok["warnings"] == ["ECHO: hi"] and ok["stderr"] == ""
    assert ok["command"][0] == fake_openscad and ok["command"][-1] == SCAD
    assert isinstance(ok["duration"], float)
    skipped = doc["results"][1]
    assert skipped["returncode"] is None and skipped["command"] is None
    failed = doc["results"][2]
    assert failed["returncode"] == 1 and "boom" in failed["stderr"]
    json.dumps(doc)  # serialisable


def test_write_summary_round_trips_through_json(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o")
    path = tmp_path / "summary.json"

    result.write_summary(path)

    assert json.loads(path.read_text(encoding="utf-8")) == result.to_dict()
    assert path.read_text().endswith("}\n")


def test_write_summary_creates_missing_directories(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o")
    path = tmp_path / "deep" / "er" / "summary.json"

    result.write_summary(path)

    assert json.loads(path.read_text())["counts"]["ok"] == 1


def test_dry_run_summary_marks_cases_as_dry_run(fake_openscad, params_csv, tmp_path):
    result = run(fake_openscad, params_csv, tmp_path / "o", dry_run=True)
    doc = result.to_dict()

    assert doc["dry_run"] is True
    assert [r["status"] for r in doc["results"]] == ["dry-run", "dry-run"]
    assert all(r["command"] for r in doc["results"])


# --- CLI -----------------------------------------------------------------------------


def test_cli_timeout_flag(fake_openscad, tmp_path, monkeypatch, capsys):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "5")

    code = main(cli_args(str(csv), tmp_path, fake_openscad, "--timeout", "0.3"))

    assert code == 1
    assert "Timed out after 0.3 s" in capsys.readouterr().out


def test_cli_summary_flag_writes_the_json_record(fake_openscad, params_csv, tmp_path, capsys):
    summary = tmp_path / "run.json"

    code = main(cli_args(params_csv, tmp_path, fake_openscad, "--summary", str(summary)))

    assert code == 1  # one case fails; the summary is still written
    doc = json.loads(summary.read_text())
    assert doc["counts"] == {"ok": 1, "failed": 1, "timeout": 0, "skipped": 0, "errors": 0}
    assert doc["openscad"]["version"] == "2021.01"
    assert f"Summary written to {summary}" in capsys.readouterr().out


def test_cli_summary_is_written_for_a_dry_run_too(fake_openscad, params_csv, tmp_path):
    summary = tmp_path / "run.json"

    main(cli_args(params_csv, tmp_path, fake_openscad, "--dry-run", "--summary", str(summary)))

    doc = json.loads(summary.read_text())
    assert doc["dry_run"] is True and doc["counts"]["ok"] == 2


def test_warnings_are_logged_per_case(fake_openscad, params_csv, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "WARNING: careful")

    with caplog.at_level(logging.WARNING, logger="scadbatch"):
        run(fake_openscad, params_csv, tmp_path / "o")

    assert "first.stl: WARNING: careful" in caplog.text


def test_error_class_lines_are_captured_on_a_successful_export(
    fake_openscad, params_csv, tmp_path, monkeypatch
):
    """OpenSCAD exits 0 for a missing font yet prints ERROR:, and for a non-manifold STL
    prints EXPORT-WARNING:; those must not vanish with the blanked stderr."""
    monkeypatch.setenv(
        "FAKE_OPENSCAD_STDERR",
        "ERROR: Can't read font with path 'x.ttf'|EXPORT-WARNING: Exported object may not be"
        " a valid 2-manifold|UI-WARNING: something|Compiling design",
    )

    result = run(fake_openscad, params_csv, tmp_path / "o")

    first = result.results[0]
    assert first.ok and first.stderr == ""
    assert first.warnings == [
        "ERROR: Can't read font with path 'x.ttf'",
        "EXPORT-WARNING: Exported object may not be a valid 2-manifold",
        "UI-WARNING: something",
    ]
    assert "ERROR: Can't read font" in result.summary()


# --- errors reported with exit 0 -----------------------------------------------------


def one_row_csv(tmp_path):
    csv = tmp_path / "one.csv"
    csv.write_text("exported_filename,size,fail\nonly,5,false\n")
    return str(csv)


def test_an_error_printed_with_exit_0_is_counted_and_given_its_own_section(
    fake_openscad, tmp_path, monkeypatch
):
    """The case OpenSCAD drops a parameter set on: the geometry is wrong and it exits 0."""
    monkeypatch.setenv(
        "FAKE_OPENSCAD_STDERR",
        "ERROR: Cannot open Parameter Set 'p.json' for reading|WARNING: variable x is unused",
    )

    result = run(fake_openscad, one_row_csv(tmp_path), tmp_path / "o")

    (only,) = result.results
    assert only.status == "ok" and only.returncode == 0  # the whole point: OpenSCAD exited 0
    assert only.errors == ["ERROR: Cannot open Parameter Set 'p.json' for reading"]
    assert result.with_errors == [only] and result.failures == []
    assert result.to_dict()["counts"]["errors"] == 1

    text = result.summary()
    assert "OpenSCAD reported an error in 1 case(s):" in text
    assert "      ERROR: Cannot open Parameter Set 'p.json' for reading" in text


def test_an_error_line_is_not_also_left_in_the_warnings_section(
    fake_openscad, tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "FAKE_OPENSCAD_STDERR", "ERROR: Cannot open Parameter Set 'p.json'|WARNING: x is unused"
    )

    text = run(fake_openscad, one_row_csv(tmp_path), tmp_path / "o").summary()

    warnings_section = text.split("OpenSCAD warnings from", 1)[1]
    assert "WARNING: x is unused" in warnings_section
    assert "ERROR:" not in warnings_section


def test_every_error_group_counts_and_no_warning_group_does(fake_openscad, tmp_path, monkeypatch):
    """The groups OpenSCAD prints are its own taxonomy; a consumer should not have to know
    it to gate on an error."""
    monkeypatch.setenv(
        "FAKE_OPENSCAD_STDERR",
        "ERROR: a|PARSER-ERROR: b|UI-ERROR: c|EXPORT-ERROR: d"
        "|WARNING: e|UI-WARNING: f|EXPORT-WARNING: g|FONT-WARNING: h|DEPRECATED: i|ECHO: j",
    )

    (only,) = run(fake_openscad, one_row_csv(tmp_path), tmp_path / "o").results

    assert only.errors == ["ERROR: a", "PARSER-ERROR: b", "UI-ERROR: c", "EXPORT-ERROR: d"]


def test_a_failed_case_with_an_error_is_counted_too(
    fake_openscad, params_csv, tmp_path, monkeypatch
):
    """counts.errors is about what OpenSCAD reported, not about how the case was classified,
    so a failed case with an error line is counted too. It is not a superset of failures:
    most failures carry no error prefix at all, which is why the exit code still carries
    them."""
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "ERROR: Cannot open Parameter Set 'p.json'")

    result = run(fake_openscad, params_csv, tmp_path / "o")

    assert [r.status for r in result.with_errors] == ["ok", "failed"]
    assert result.to_dict()["counts"]["errors"] == 2
    text = result.summary()
    assert "OpenSCAD reported an error in 2 case(s):" in text
    assert "(ok):" in text and "(failed):" in text


def test_no_error_lines_means_no_error_section_and_a_zero_count(
    fake_openscad, params_csv, tmp_path, monkeypatch
):
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "WARNING: careful|ECHO: hi")

    result = run(fake_openscad, params_csv, tmp_path / "o")

    assert result.with_errors == []
    assert result.to_dict()["counts"]["errors"] == 0
    assert "OpenSCAD reported an error" not in result.summary()


def test_the_json_record_carries_each_case_errors(fake_openscad, tmp_path, monkeypatch):
    """So a consumer can find which case without re-implementing OpenSCAD's prefixes."""
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "ERROR: Cannot open Parameter Set 'p.json'|ECHO: hi")

    doc = run(fake_openscad, one_row_csv(tmp_path), tmp_path / "o").to_dict()

    assert doc["results"][0]["errors"] == ["ERROR: Cannot open Parameter Set 'p.json'"]
    json.dumps(doc)


def test_the_cli_still_exits_0_when_only_errors_were_reported(
    fake_openscad, tmp_path, monkeypatch, capsys
):
    """Option 2 of #46: report the error, do not reclassify the case. A consumer that wants
    to fail on it reads counts.errors; the exit code keeps its meaning."""
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "ERROR: Cannot open Parameter Set 'p.json'")
    summary = tmp_path / "s.json"

    code = main(cli_args(one_row_csv(tmp_path), tmp_path, fake_openscad, "--summary", str(summary)))

    assert code == 0
    assert "OpenSCAD reported an error in 1 case(s):" in capsys.readouterr().out
    assert json.loads(summary.read_text())["counts"] == {
        "ok": 1,
        "failed": 0,
        "timeout": 0,
        "skipped": 0,
        "errors": 1,
    }


def test_an_error_line_is_logged_at_error_level(fake_openscad, tmp_path, monkeypatch, caplog):
    """A live run shows it as an error too, not as one more warning in the stream."""
    monkeypatch.setenv("FAKE_OPENSCAD_STDERR", "ERROR: Cannot open Parameter Set 'p.json'")

    with caplog.at_level(logging.WARNING, logger="scadbatch"):
        run(fake_openscad, one_row_csv(tmp_path), tmp_path / "o")

    (record,) = [r for r in caplog.records if "Cannot open Parameter Set" in r.getMessage()]
    assert record.levelno == logging.ERROR


def test_timeout_counts_and_status_in_the_json_record(fake_openscad, tmp_path, monkeypatch):
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "5")

    doc = batch_export(
        SCAD, str(csv), str(tmp_path / "o"), fake_openscad, "binstl", None, True, timeout=0.3
    ).to_dict()

    assert doc["counts"] == {"ok": 0, "failed": 1, "timeout": 1, "skipped": 0, "errors": 0}
    assert doc["results"][0]["status"] == "timeout"


@pytest.mark.skipif(os.name == "nt", reason="shell wrapper is POSIX")
def test_timeout_reaches_a_render_behind_a_wrapper_script(fake_openscad, tmp_path, monkeypatch):
    """Like the Linux AppImage runtime, a wrapper that does not exec leaves the real
    process as a grandchild; killing only the direct child would leave it holding our
    pipes for the full render."""
    wrapper = tmp_path / "wrapped-openscad"
    wrapper.write_text(f'#!/bin/sh\n"{fake_openscad}" "$@"\nexit $?\n')
    wrapper.chmod(0o755)
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\n")
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "6")
    started = time.monotonic()

    result = batch_export(
        SCAD, str(csv), str(tmp_path / "o"), str(wrapper), "binstl", None, True, timeout=0.5
    )

    assert time.monotonic() - started < 4, "the grandchild survived and held the pipes"
    assert result.results[0].status == "timeout"


@pytest.mark.skipif(os.name == "nt", reason="SIGINT delivery to self is POSIX-specific")
def test_interrupt_reaches_a_render_behind_a_wrapper_script(fake_openscad, tmp_path, monkeypatch):
    import signal
    import threading

    wrapper = tmp_path / "wrapped-openscad"
    wrapper.write_text(f'#!/bin/sh\n"{fake_openscad}" "$@"\nexit $?\n')
    wrapper.chmod(0o755)
    csv = tmp_path / "p.csv"
    csv.write_text("exported_filename,size\nslow,1\n")
    log_path = tmp_path / "probe.log"
    monkeypatch.setenv("FAKE_OPENSCAD_LOG", str(log_path))
    monkeypatch.setenv("FAKE_OPENSCAD_SLEEP", "10")
    threading.Timer(0.5, os.kill, args=(os.getpid(), signal.SIGINT)).start()
    started = time.monotonic()

    with pytest.raises(KeyboardInterrupt):
        batch_export(SCAD, str(csv), str(tmp_path / "o"), str(wrapper), "binstl", None, True)

    assert time.monotonic() - started < 5
    time.sleep(0.5)
    lines = [
        line for part in tmp_path.glob("probe.log.*") for line in part.read_text().splitlines()
    ]
    assert any(line.startswith("term") for line in lines)  # the grandchild got SIGTERM


def test_cli_refuses_an_unwritable_summary_path_before_running(
    fake_openscad, params_csv, tmp_path, capsys
):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")

    code = main(
        cli_args(params_csv, tmp_path, fake_openscad, "--summary", str(blocker / "run.json"))
    )

    assert code == 1
    assert "cannot write summary" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()  # nothing ran


def test_cli_creates_the_summary_directory(fake_openscad, params_csv, tmp_path):
    summary = tmp_path / "build" / "reports" / "run.json"

    main(cli_args(params_csv, tmp_path, fake_openscad, "--summary", str(summary)))

    assert json.loads(summary.read_text())["counts"]["ok"] == 1
