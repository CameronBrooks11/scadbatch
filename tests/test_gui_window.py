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


def test_the_settings_rows_moved_down_rather_than_onto_each_other(window):
    """The output-format field took row 0, so the flavour, selection and sequential rows
    each moved down one. A widget left behind would land on top of another (#97).

    Every cell the frame hands out must be distinct, whoever asked for it -- naming three
    widgets would miss a collision with a label, which is a local in __init__.
    """
    app = Gui(window)
    frame = app.formats_entry.master

    cells = []
    for child in frame.grid_slaves():
        placed = child.grid_info()
        row, column = int(placed["row"]), int(placed["column"])
        cells.extend((row, column + offset) for offset in range(int(placed["columnspan"])))

    assert len(cells) == len(set(cells)), sorted(c for c in cells if cells.count(c) > 1)
    assert int(app.formats_entry.grid_info()["row"]) == 0
    assert int(app.selection_entry.grid_info()["row"]) == 2
    assert int(app.seq_check.grid_info()["row"]) == 3


def test_only_the_column_holding_the_content_takes_the_width(window):
    """The horizontal twin of the row above. The window gave column 1 three times the
    weight of column 0 while placing its only child in column 0, so widening the window
    handed three quarters of the new space to a column holding nothing (#114).

    Found against the column the frame actually occupies, so moving the frame without
    moving the weight fails here.
    """
    app = Gui(window)

    content_column = int(app.main_frame.grid_info()["column"])
    assert window.grid_columnconfigure(content_column)["weight"] == 1

    # And no other column claims a share, which is what stranded the content.
    weighted = [
        column
        for column in range(6)
        if window.grid_columnconfigure(column)["weight"] and column != content_column
    ]
    assert weighted == []
