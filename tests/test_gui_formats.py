"""The GUI's output-format field.

The GUI could only ever write STL, not for want of a control but because `formats` was
never passed to `batch_export` at all, so it took its `("stl",)` default (#97).

The field collects text and nothing more. The runner already lowercases, strips a leading
dot and de-duplicates, and *warns* rather than refuses when the engine does not advertise a
format, because the advertised list understates what a build accepts. Validating here would
reject formats that work, so these tests pin that it does not.
"""

import pytest
from gui_stubs import FakeGui

from scadbatch.gui import OpenSCADBatchExporterGUI as Gui
from scadbatch.gui import parse_formats


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("stl", ["stl"]),
        ("stl, png", ["stl", "png"]),
        ("stl,png", ["stl", "png"]),
        ("  stl ,  png  ", ["stl", "png"]),
        ("stl, , png", ["stl", "png"]),  # a stray comma is not an empty format
        ("", []),  # cleared field: the runner's own refusal, not a silent fallback to stl
        ("   ", []),
        ("3mf", ["3mf"]),
        ("stl, stl", ["stl", "stl"]),  # de-duplicating is the runner's job, not the field's
    ],
)
def test_the_field_is_split_and_nothing_else(text, expected):
    assert parse_formats(text) == expected


@pytest.mark.parametrize("text", ["STL", ".stl", "nonesuch"])
def test_the_field_does_not_second_guess_the_runner(text):
    """Case and a leading dot are the runner's job, and an unadvertised format is a warning
    there rather than a refusal. A single entry is handed over exactly as typed."""
    assert parse_formats(text) == [text.strip()]


def test_the_formats_reach_batch_export(monkeypatch, no_dialogs):
    """The defect itself: before this, `formats` was never passed and every run wrote STL."""
    captured = {}

    def fake_batch_export(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here")  # nothing to summarise

    monkeypatch.setattr("scadbatch.gui.batch_export", fake_batch_export)

    Gui.run_export(
        FakeGui(), "m.scad", "p.csv", "out", None, "binstl", None, False, "utf-8", ["stl", "png"]
    )

    assert captured["formats"] == ["stl", "png"]


def test_an_export_sends_what_the_field_holds(tmp_path, monkeypatch, no_dialogs):
    """Through `start_export`, so the wiring from the field to the call is covered and not
    just `run_export`'s own argument."""
    scad = tmp_path / "m.scad"
    scad.write_text("cube(1);")
    param = tmp_path / "p.csv"
    param.write_text("exported_filename,d\na,1\n")
    captured = {}
    monkeypatch.setattr("scadbatch.gui.batch_export", lambda *a, **k: captured.update(k))
    window = FakeGui(scad=str(scad), param=str(param), output=str(tmp_path / "out"))
    window.output_formats.value = "off, 3mf"

    Gui.start_export(window)

    thread = getattr(window, "export_thread", None)
    if thread is not None:
        thread.join(timeout=5)
    assert captured["formats"] == ["off", "3mf"]
