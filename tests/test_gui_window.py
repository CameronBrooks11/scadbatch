"""The GUI window itself: its title, and the row that absorbs the window's slack.

The title is checkable anywhere, because it is a module-level constant rather than a
literal inside `__init__`. The layout is not: reading a grid weight needs a real Tk root,
so that test runs on the CI job with xvfb and skips everywhere else (#89).
"""

from scadbatch.gui import WINDOW_TITLE
from scadbatch.gui import OpenSCADBatchExporterGUI as Gui
from scadbatch.runner import _TOOL_NAME


def test_the_window_title_is_built_from_the_tool_name():
    """It was a second hardcoded string, left on the pre-rename name by #48 (#96).

    Asserting it is derived rather than asserting the exact words: what matters is that
    there is one name and a rename cannot leave this one behind.
    """
    assert _TOOL_NAME in WINDOW_TITLE
    assert "OpenSCAD Batch Export" not in WINDOW_TITLE


def test_the_log_row_is_the_one_that_grows(window):
    """The slack was reserved for row 10, which holds nothing, so the log got its
    requested height and no more and a taller window did not enlarge it (#61).

    Checked against where the children actually are, not against the number 4, so moving
    the log frame without moving the weight fails here.
    """
    app = Gui(window)

    log_row = int(app.log_text.master.grid_info()["row"])
    assert app.main_frame.grid_rowconfigure(log_row)["weight"] == 1

    # And no other row of that frame claims the slack, which would split it.
    weighted = [
        row
        for row in range(12)
        if app.main_frame.grid_rowconfigure(row)["weight"] and row != log_row
    ]
    assert weighted == []


def test_the_window_title_is_actually_set(window):
    """`master.title()` runs inside `__init__`, so only a real root sees the result."""
    Gui(window)

    assert window.title() == WINDOW_TITLE
