"""Stand-ins for the GUI window.

The widgets need a display and most CI jobs have none, so the tests drive the worker
methods with these instead. A plain module rather than conftest, because conftest
shares fixtures and these are classes the tests construct themselves.
"""

from scadbatch.gui import OpenSCADBatchExporterGUI as Gui


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
        self.output_formats = Field("stl")
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
