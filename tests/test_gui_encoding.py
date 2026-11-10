"""The GUI's parameter-file encoding field.

The widgets need a display and CI has none, so these drive the methods behind them with a
stand-in for the window. That covers the part with behaviour -- which encoding is resolved,
and whether it reaches the three calls -- and not the layout.
"""

import json

import pytest

from scadbatch import gui as gui_module
from scadbatch.gui import OpenSCADBatchExporterGUI as Gui
from scadbatch.params import DEFAULT_ENCODING


class Field:
    """Stands in for a tk.StringVar."""

    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


class FakeGui:
    """Stands in for the window: the attributes the worker methods touch, and nothing else."""

    def __init__(self, encoding="", **paths):
        self.parameter_encoding = Field(encoding)
        self.scad_file = Field(paths.get("scad", ""))
        self.parameter_file = Field(paths.get("param", ""))
        self.output_folder = Field(paths.get("output", ""))
        self.openscad_path = Field("")
        self.export_format = Field("binstl")
        self.selection = Field("")
        self.sequential = Field(False)
        self.progress = {}
        self.log = []
        self.status_label = self
        self.enabled = False
        self.threads = []

    # start_export disables the controls, starts a thread and schedules a poll; a stand-in
    # records the thread rather than running it, so the test sees what it would have run.
    def disable_controls(self):
        self.enabled = False

    def after(self, _delay, _callback):
        pass

    def update_progress(self):
        pass

    master = property(lambda self: self)

    def append_log(self, message):
        self.log.append(message)

    def enable_controls(self):
        self.enabled = True

    def config(self, **kwargs):
        pass

    # the real resolver and the real guard, so these tests exercise them rather than a copy
    chosen_encoding = Gui.chosen_encoding
    is_executable = Gui.is_executable
    run_export = Gui.run_export


class Summary:
    """Stands in for the BatchResult the GUI logs."""

    def summary(self):
        return "nothing to report"


@pytest.fixture
def no_dialogs(monkeypatch):
    """Collect what would have been shown, so nothing tries to open a window."""
    shown = []
    for kind in ("showerror", "showinfo"):
        monkeypatch.setattr(
            gui_module.messagebox,
            kind,
            lambda title, message, kind=kind: shown.append((kind, message)),
        )
    return shown


def test_a_blank_field_means_the_default_encoding(no_dialogs):
    """A user who never touches the field gets what the command line gives without
    --encoding."""
    assert Gui.chosen_encoding(FakeGui("")) == DEFAULT_ENCODING
    assert Gui.chosen_encoding(FakeGui("   ")) == DEFAULT_ENCODING
    assert no_dialogs == []


def test_a_named_encoding_is_used_as_written(no_dialogs):
    assert Gui.chosen_encoding(FakeGui("cp1252")) == "cp1252"
    assert no_dialogs == []


def test_an_unknown_encoding_is_refused_before_anything_runs(no_dialogs):
    """Returning None stops the caller, so the user sees the dialog rather than a traceback
    from a worker thread partway through a batch."""
    assert Gui.chosen_encoding(FakeGui("latin-9000")) is None

    (kind, message) = no_dialogs[0]
    assert kind == "showerror"
    assert "latin-9000" in message and "no such codec" in message


def test_an_unresolvable_encoding_stops_the_export_before_it_starts(
    tmp_path, monkeypatch, no_dialogs
):
    """The guard, not just the function behind it. Without it the run goes ahead: None means
    "use the default" to batch_export, so a user told their codec name was bad would get a
    full export read as UTF-8 anyway."""
    scad = tmp_path / "m.scad"
    scad.write_text("cube(1);")
    param = tmp_path / "p.csv"
    param.write_text("exported_filename,d\na,1\n")
    called = []
    monkeypatch.setattr(gui_module, "batch_export", lambda *a, **k: called.append(k))
    window = FakeGui("latin-9000", scad=str(scad), param=str(param), output=str(tmp_path / "out"))

    Gui.start_export(window)

    thread = getattr(window, "export_thread", None)
    if thread is not None:
        thread.join(timeout=5)
    assert called == [], "the export ran although the encoding was refused"
    assert no_dialogs[0][0] == "showerror"


@pytest.mark.parametrize(
    "action", [Gui.convert_csv_to_json, Gui.convert_json_to_csv], ids=["csv2json", "json2csv"]
)
def test_an_unresolvable_encoding_stops_a_conversion_before_the_file_dialog(
    action, monkeypatch, no_dialogs
):
    """Resolving it first is what makes a bad name cost zero dialogs instead of two."""
    opened = []
    monkeypatch.setattr(
        gui_module.filedialog, "askopenfilename", lambda **k: opened.append(k) or ""
    )
    monkeypatch.setattr(
        gui_module.filedialog, "asksaveasfilename", lambda **k: opened.append(k) or ""
    )

    action(FakeGui("latin-9000"))

    assert opened == [], "a file dialog opened although the encoding was refused"
    assert no_dialogs[0][0] == "showerror"


def test_csv_to_json_reads_the_chosen_encoding(tmp_path, no_dialogs):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\na,café\n".encode("cp1252"))
    out = tmp_path / "p.json"

    Gui.run_csv_to_json(FakeGui(), str(src), str(out), "cp1252")

    assert json.loads(out.read_text(encoding="utf-8"))["parameterSets"]["a"]["label"] == "café"


def test_json_to_csv_reads_the_chosen_encoding(tmp_path, no_dialogs):
    src = tmp_path / "p.json"
    # ensure_ascii, the default, would escape the accent and leave a pure-ASCII file, where
    # reading as cp1252 and as UTF-8 are the same thing and this would prove nothing.
    src.write_bytes(
        json.dumps({"parameterSets": {"a": {"label": "café"}}}, ensure_ascii=False).encode("cp1252")
    )
    out = tmp_path / "p.csv"

    Gui.run_json_to_csv(FakeGui(), str(src), str(out), "cp1252")

    assert "café" in out.read_text(encoding="utf-8")


def test_a_conversion_in_the_wrong_encoding_is_reported_not_raised(tmp_path, no_dialogs):
    src = tmp_path / "p.csv"
    src.write_bytes("exported_filename,label\na,café\n".encode("cp1252"))
    window = FakeGui()

    Gui.run_csv_to_json(window, str(src), str(tmp_path / "p.json"), DEFAULT_ENCODING)

    assert no_dialogs[0][0] == "showerror"
    assert "not valid utf-8-sig text" in no_dialogs[0][1]
    assert window.enabled, "the controls must come back after a failed conversion"


def test_export_passes_the_encoding_to_batch_export(monkeypatch, no_dialogs):
    captured = {}

    def fake_batch_export(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here")  # nothing to summarise

    monkeypatch.setattr(gui_module, "batch_export", fake_batch_export)

    Gui.run_export(FakeGui(), "m.scad", "p.csv", "out", None, "binstl", None, False, "cp1252")

    assert captured["encoding"] == "cp1252"


def test_the_export_log_names_the_encoding_it_used(tmp_path, monkeypatch, no_dialogs):
    """One field drives three buttons acting on three files, and nothing resets it. Read as
    the wrong encoding most files do not fail -- cp1252 has five undefined bytes -- so a
    value left over from an earlier file is invisible unless each action says what it used.
    """
    scad = tmp_path / "m.scad"
    scad.write_text("cube(1);")
    param = tmp_path / "p.csv"
    param.write_text("exported_filename,d\na,1\n")
    monkeypatch.setattr(gui_module, "batch_export", lambda *a, **k: Summary())
    window = FakeGui("cp1252", scad=str(scad), param=str(param), output=str(tmp_path / "out"))

    Gui.start_export(window)
    thread = getattr(window, "export_thread", None)
    if thread is not None:
        thread.join(timeout=5)

    assert any("cp1252" in line and str(param) in line for line in window.log), window.log


@pytest.mark.parametrize("direction", ["csv2json", "json2csv"])
def test_a_conversion_says_which_encoding_it_read(direction, tmp_path, no_dialogs):
    """Including in the dialog, which is the part a user actually reads."""
    window = FakeGui()
    if direction == "csv2json":
        src = tmp_path / "p.csv"
        src.write_bytes("exported_filename,label\na,café\n".encode("cp1252"))
        Gui.run_csv_to_json(window, str(src), str(tmp_path / "p.json"), "cp1252")
    else:
        src = tmp_path / "p.json"
        src.write_bytes(
            json.dumps({"parameterSets": {"a": {"label": "café"}}}, ensure_ascii=False).encode(
                "cp1252"
            )
        )
        Gui.run_json_to_csv(window, str(src), str(tmp_path / "p.csv"), "cp1252")

    (kind, message) = no_dialogs[0]
    assert kind == "showinfo" and "cp1252" in message


def test_the_window_builds_with_the_encoding_field(window):
    """The stand-in above cannot see a layout mistake -- a duplicated grid cell, a widget
    left out of state_widgets. CI runs the suite under xvfb on one job, which is where this
    one runs; everywhere else it skips."""
    app = Gui(window)

    assert app.parameter_encoding.get() == ""  # blank by default, so UTF-8 by default
    assert app.encoding_entry in app.state_widgets  # greyed out with the rest during a run
    placed = app.encoding_entry.grid_info()
    assert (int(placed["row"]), int(placed["column"])) == (2, 1)
    # the rows below it moved down rather than landing on top of it
    assert int(app.output_entry.grid_info()["row"]) == 3
    assert int(app.openscad_entry.grid_info()["row"]) == 4

    # Naming three widgets would miss a collision with the Browse buttons, which are local
    # variables in __init__ and unreachable from here. Every cell the frame hands out must
    # be distinct, whoever asked for it.
    frame = app.encoding_entry.master
    cells = []
    for child in frame.grid_slaves():
        placed = child.grid_info()
        row, column = int(placed["row"]), int(placed["column"])
        cells.extend((row, column + offset) for offset in range(int(placed["columnspan"])))
    assert len(cells) == len(set(cells)), sorted(c for c in cells if cells.count(c) > 1)
