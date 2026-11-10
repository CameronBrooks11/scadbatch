import os
import stat
import sys
import textwrap

import pytest

FAKE_OPENSCAD = textwrap.dedent(
    """\
    import sys

    # Minimal stand-in for `openscad --version` and
    # `openscad -o OUT --export-format=F (-Dk=v ... | -p FILE -P SET) FILE`.
    # Writes the parameter arguments to OUT, one per line; exits 1 with a message if a
    # -D flag or a parameter set asks for fail=true. FAKE_OPENSCAD_VERSION overrides
    # the reported version.
    import json
    import os

    args = sys.argv[1:]
    if args == ["--version"]:
        version = os.environ.get("FAKE_OPENSCAD_VERSION", "2021.01")
        sys.stderr.write(f"OpenSCAD version {version}\\n")  # the real one prints to stderr
        sys.exit(0)
    # "none" means "print no format list" (Windows drops empty environment variables).
    formats = os.environ.get("FAKE_OPENSCAD_FORMATS", "stl, off, 3mf, csg, png")
    formats = "" if formats.lower() == "none" else formats
    if args == ["--help"]:
        if formats:
            sys.stdout.write("  -o [ --o ] arg  output specified file instead of running the\\n")
            sys.stdout.write("                  GUI, the file extension specifies the type: ")
            sys.stdout.write(f"{formats}\\n")
            sys.stdout.write("                  (May be used multiple time).\\n")
        sys.exit(0)
    out = args[args.index("-o") + 1]
    ext = out.rsplit(".", 1)[-1]
    # Concurrency probes: write start/end timestamps to FAKE_OPENSCAD_LOG.<pid> (one file
    # per process; concurrent appends to one file lose lines on Windows) and hold for
    # FAKE_OPENSCAD_SLEEP seconds.
    import time

    log_path = os.environ.get("FAKE_OPENSCAD_LOG")
    if log_path:
        log_path = f"{log_path}.{os.getpid()}"
    if log_path:
        with open(log_path, "a") as f:
            f.write(f"start {time.monotonic():.4f} {os.getpid()}\\n")
        if os.name != "nt":
            import signal

            def on_term(signum, frame):
                with open(log_path, "a") as f:
                    f.write(f"term {time.monotonic():.4f} {os.getpid()}\\n")
                sys.exit(143)

            signal.signal(signal.SIGTERM, on_term)
    if os.environ.get("FAKE_OPENSCAD_PARTIAL"):
        # Like the real engine, start writing the output before we know we will finish.
        with open(out, "w") as f:
            f.write("partial")
    time.sleep(float(os.environ.get("FAKE_OPENSCAD_SLEEP", "0")))
    # FAKE_OPENSCAD_STDERR: | separated diagnostics, emitted before any failure like the
    # real engine's, e.g. "ECHO: x = 5|WARNING: unused variable|Compiling design".
    for line in filter(None, os.environ.get("FAKE_OPENSCAD_STDERR", "").split("|")):
        sys.stderr.write(line + "\\n")
    if log_path:
        with open(log_path, "a") as f:
            f.write(f"end {time.monotonic():.4f} {os.getpid()}\\n")
    if formats and ext not in [f.strip() for f in formats.split(",")]:
        sys.stderr.write(f"Unknown suffix for output file {out}\\n")
        sys.exit(1)
    recorded = ("-D", "--export-format", "--camera", "--imgsize", "--colorscheme")
    param_args = [a for a in args if a.startswith(recorded)]
    if "-p" in args:
        sets_file, set_name = args[args.index("-p") + 1], args[args.index("-P") + 1]
        param_args += ["-p", sets_file, "-P", set_name]
        with open(sets_file, encoding="utf-8") as f:
            values = json.load(f)["parameterSets"][set_name]
        if str(values.get("fail", "")).lower() == "true":
            sys.stderr.write("boom: fail requested\\n")
            sys.exit(1)
    if "-Dfail=true" in param_args:
        sys.stderr.write("boom: fail requested\\n")
        sys.exit(1)
    if os.environ.get("FAKE_OPENSCAD_NO_OUTPUT"):
        sys.stderr.write(f"Can't open file \\"{out}\\" for export\\n")
        sys.exit(0)  # the real engine exits 0 here
    with open(out, "w", encoding="utf-8") as f:
        f.write("\\n".join(param_args))
    """
)


@pytest.fixture
def fake_openscad(tmp_path):
    """Path to an executable that mimics OpenSCAD's CLI contract for the runner."""
    script = tmp_path / "fake_openscad.py"
    script.write_text(FAKE_OPENSCAD)
    if os.name == "nt":
        exe = tmp_path / "openscad.cmd"
        exe.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n')
    else:
        exe = tmp_path / "openscad"
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


@pytest.fixture
def window():
    """A real Tk root, where one can be had. Only the tests that build real widgets need
    this; it lives here because more than one GUI module wants it."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    root.withdraw()
    yield root
    root.destroy()
