# scadbatch/gui.py

"""
Graphical User Interface (GUI) for the OpenSCAD Batch Exporter.

This GUI allows users to configure batch exports from OpenSCAD using CSV or JSON
parameters.
It also provides functionalities to convert parameter files between CSV and JSON formats.

Features:
- Browse and select OpenSCAD files, parameter files, and output directories.
- Choose export formats and specify selection criteria.
- Monitor export progress and view logs.
- Convert between CSV and JSON parameter files.
- Access comprehensive help documentation.
"""

import contextlib
import logging
import os
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from scadbatch import batch_export, csv_to_json, json_to_csv
from scadbatch.params import DEFAULT_ENCODING, normalize_encoding


class OpenSCADBatchExporterGUI:
    """
    Main GUI class for the OpenSCAD Batch Exporter.

    Handles the creation and management of all GUI components and user interactions.
    """

    def __init__(self, master):
        """
        Initialize the GUI components.

        Args:
            master (tk.Tk): The root Tkinter window.
        """
        self.master = master
        master.title("OpenSCAD Batch Exporter")
        master.geometry("1000x750")
        master.resizable(True, True)

        # Configure grid for the main window
        master.columnconfigure(0, weight=1)
        master.columnconfigure(1, weight=3)
        master.rowconfigure(0, weight=1)

        # Main Frame
        main_frame = ttk.Frame(master, padding="10 10 10 10")
        main_frame.grid(row=0, column=0, sticky=tk.NSEW)

        # Configure grid within the main frame
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(10, weight=1)

        # Variables
        self.scad_file = tk.StringVar()
        self.parameter_file = tk.StringVar()
        self.parameter_encoding = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.openscad_path = tk.StringVar(value="")
        self.export_format = tk.StringVar(value="binstl")
        self.selection = tk.StringVar()
        self.sequential = tk.BooleanVar()
        self.export_thread = None
        self.stop_event = threading.Event()

        # Lists to keep track of widgets that support 'state'
        self.state_widgets = []

        # === Input Section Frame ===
        input_frame = ttk.LabelFrame(main_frame, text="Input Configuration", padding="10 10 10 10")
        input_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Configure grid within input_frame
        for i in range(4):
            input_frame.columnconfigure(i, weight=1)

        # SCAD File
        ttk.Label(input_frame, text="OpenSCAD File:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.scad_entry = ttk.Entry(input_frame, textvariable=self.scad_file)
        self.scad_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.state_widgets.append(self.scad_entry)
        scad_browse_btn = ttk.Button(input_frame, text="Browse", command=self.browse_scad)
        scad_browse_btn.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(scad_browse_btn)

        # Parameter File
        ttk.Label(input_frame, text="Parameter File (CSV/JSON):").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.param_entry = ttk.Entry(input_frame, textvariable=self.parameter_file)
        self.param_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.state_widgets.append(self.param_entry)
        param_browse_btn = ttk.Button(input_frame, text="Browse", command=self.browse_parameter)
        param_browse_btn.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(param_browse_btn)

        # Parameter File Encoding
        ttk.Label(input_frame, text="Parameter File Encoding:").grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.encoding_entry = ttk.Entry(input_frame, textvariable=self.parameter_encoding)
        self.encoding_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        self.state_widgets.append(self.encoding_entry)
        ttk.Label(
            input_frame,
            text=f"blank = {DEFAULT_ENCODING}; e.g. cp1252 for an Excel export. "
            f"Applies to the conversions too.",
            foreground="gray",
        ).grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=5, pady=5)

        # Output Folder
        ttk.Label(input_frame, text="Output Folder:").grid(
            row=3, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.output_entry = ttk.Entry(input_frame, textvariable=self.output_folder)
        self.output_entry.grid(row=3, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.state_widgets.append(self.output_entry)
        output_browse_btn = ttk.Button(input_frame, text="Browse", command=self.browse_output)
        output_browse_btn.grid(row=3, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(output_browse_btn)

        # OpenSCAD Path
        ttk.Label(input_frame, text="OpenSCAD Path:").grid(
            row=4, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.openscad_entry = ttk.Entry(input_frame, textvariable=self.openscad_path)
        self.openscad_entry.grid(row=4, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.state_widgets.append(self.openscad_entry)
        openscad_browse_btn = ttk.Button(input_frame, text="Browse", command=self.browse_openscad)
        openscad_browse_btn.grid(row=4, column=3, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(openscad_browse_btn)

        # === Settings Section Frame ===
        settings_frame = ttk.LabelFrame(main_frame, text="Export Settings", padding="10 10 10 10")
        settings_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Configure grid within settings_frame
        settings_frame.columnconfigure(1, weight=1)

        # Export Format
        ttk.Label(settings_frame, text="Export Format:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5
        )
        export_format_menu = ttk.Combobox(
            settings_frame,
            textvariable=self.export_format,
            values=["asciistl", "binstl"],
            state="readonly",
        )
        export_format_menu.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        export_format_menu.current(1)  # Default to binstl
        self.state_widgets.append(export_format_menu)

        # Selection
        ttk.Label(settings_frame, text="Selection:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.selection_entry = ttk.Entry(settings_frame, textvariable=self.selection)
        self.selection_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.state_widgets.append(self.selection_entry)
        selection_info = "e.g., '0-5', '1-3,7,10-12', 'every:2 in 0-10', 'from:5', 'up_to:4'"
        ttk.Label(settings_frame, text=selection_info, foreground="gray").grid(
            row=1, column=3, sticky=tk.W, padx=5, pady=5
        )

        # Sequential Processing
        self.seq_check = ttk.Checkbutton(
            settings_frame, text="Sequential Processing", variable=self.sequential
        )
        self.seq_check.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        self.state_widgets.append(self.seq_check)

        # === Progress and Status Frame ===
        progress_frame = ttk.Frame(main_frame, padding="10 10 10 10")
        progress_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Progress Bar
        self.progress = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate")
        self.progress.grid(row=0, column=0, sticky=tk.EW, padx=5, pady=5)
        progress_frame.columnconfigure(0, weight=1)

        # Status Label
        self.status_label = ttk.Label(progress_frame, text="Status: Idle", foreground="blue")
        self.status_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)

        # === Buttons Frame ===
        buttons_frame = ttk.Frame(main_frame, padding="10 10 10 10")
        buttons_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        # Configure grid within buttons_frame
        for col in range(5):
            buttons_frame.columnconfigure(col, weight=1)

        # Export Button
        export_btn = ttk.Button(buttons_frame, text="Export", command=self.start_export)
        export_btn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(export_btn)

        # Convert CSV to JSON Button
        convert_csv_json_btn = ttk.Button(
            buttons_frame, text="Convert CSV to JSON", command=self.convert_csv_to_json
        )
        convert_csv_json_btn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(convert_csv_json_btn)

        # Convert JSON to CSV Button
        convert_json_csv_btn = ttk.Button(
            buttons_frame, text="Convert JSON to CSV", command=self.convert_json_to_csv
        )
        convert_json_csv_btn.grid(row=0, column=2, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(convert_json_csv_btn)

        # Clear Log Button
        clear_log_btn = ttk.Button(buttons_frame, text="Clear Log", command=self.clear_log)
        clear_log_btn.grid(row=0, column=3, padx=5, pady=5, sticky=tk.EW)
        self.state_widgets.append(clear_log_btn)

        # Help Button
        help_btn = ttk.Button(buttons_frame, text="Help", command=self.show_help)
        help_btn.grid(row=0, column=4, padx=5, pady=5, sticky=tk.EW)
        # Do NOT append help_btn to self.state_widgets to keep it enabled during processing

        # === Log Output Frame ===
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10 10 10 10")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=tk.NSEW, padx=5, pady=5)

        # Configure grid within log_frame
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Log Text Widget
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 5), pady=5)

        # Log Scrollbar
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS, pady=5)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def browse_scad(self):
        """
        Open a file dialog to browse and select an OpenSCAD (.scad) file.
        """
        file_path = filedialog.askopenfilename(filetypes=[("OpenSCAD Files", "*.scad")])
        if file_path:
            self.scad_file.set(file_path)

    def browse_parameter(self):
        """
        Open a file dialog to browse and select a parameter file (CSV or JSON).
        """
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("JSON Files", "*.json")]
        )
        if file_path:
            self.parameter_file.set(file_path)

    def browse_output(self):
        """
        Open a directory dialog to browse and select an output folder.
        """
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder.set(folder)

    def browse_openscad(self):
        """
        Open a file dialog to browse and select the OpenSCAD executable.
        """
        file_path = filedialog.askopenfilename(
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")]
        )
        if file_path:
            self.openscad_path.set(file_path)

    def append_log(self, message):
        """
        Append a timestamped message to the log display.

        Args:
            message (str): The message to append.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, full_message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def clear_log(self):
        """
        Clear all messages from the log display.
        """
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def disable_controls(self):
        """
        Disable all input and action widgets to prevent user interaction during processing.
        """
        for widget in self.state_widgets:
            try:
                widget.state(["disabled"])
            except AttributeError:
                with contextlib.suppress(tk.TclError):  # widget does not support 'state'
                    widget.config(state=tk.DISABLED)

    def enable_controls(self):
        """
        Enable all input and action widgets after processing is complete.
        """
        for widget in self.state_widgets:
            try:
                if isinstance(widget, ttk.Combobox):
                    widget.state(["!disabled"])
                else:
                    widget.state(["!disabled"])
            except AttributeError:
                try:
                    if isinstance(widget, ttk.Combobox):
                        widget.config(state="readonly")
                    else:
                        widget.config(state=tk.NORMAL)
                except tk.TclError:
                    pass  # Widget does not support 'state'

    def is_executable(self, path):
        """
        Check if the provided path is an executable file.

        Args:
            path (str): Path to the file.

        Returns:
            bool: True if the path is executable, False otherwise.
        """
        return os.path.isfile(path) and os.access(path, os.X_OK)

    def chosen_encoding(self):
        """
        The encoding to read parameter files with, or None if the field does not name a
        codec Python has -- in which case the user has already been told why.

        Blank means the default, so a user who never touches the field gets UTF-8, the same
        as the command line without --encoding.

        One field serves the export and both conversions, which act on files chosen
        separately, so every action names the encoding it used as it starts and as it
        finishes. Read as the wrong encoding, most files do not fail -- cp1252 has five
        undefined bytes and decodes almost anything -- so a value left over from an earlier
        file would otherwise be invisible.
        """
        name = self.parameter_encoding.get().strip()
        if not name:
            return DEFAULT_ENCODING
        try:
            normalize_encoding(name)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return None
        return name

    def start_export(self):
        """
        Validate inputs and initiate the batch export process in a separate thread.
        """
        # Retrieve input values
        scad = self.scad_file.get()
        param = self.parameter_file.get()
        output = self.output_folder.get()
        openscad = self.openscad_path.get()
        fmt = self.export_format.get()
        sel = self.selection.get()
        seq = self.sequential.get()

        # Input validation
        if not scad or not os.path.isfile(scad):
            messagebox.showerror("Error", "Please select a valid OpenSCAD (.scad) file.")
            return
        if not param or not os.path.isfile(param):
            messagebox.showerror("Error", "Please select a valid parameter file (CSV or JSON).")
            return
        if not output:
            messagebox.showerror("Error", "Please select an output folder.")
            return

        # Validate OpenSCAD Path (empty means auto-detect)
        openscad = openscad.strip() or None
        if openscad and os.path.dirname(openscad):
            if not os.path.isfile(openscad):
                messagebox.showerror("Error", "Please select a valid OpenSCAD executable.")
                return
            if not self.is_executable(openscad):
                messagebox.showerror("Error", "The selected OpenSCAD path is not executable.")
                return

        encoding = self.chosen_encoding()
        if encoding is None:
            return

        # Disable controls and reset progress
        self.disable_controls()
        self.progress["value"] = 0
        self.status_label.config(text="Status: Exporting...", foreground="green")
        self.append_log(f"Starting batch export, reading {param} as {encoding}...")

        # Start export in a separate thread to keep GUI responsive
        self.export_thread = threading.Thread(
            target=self.run_export,
            args=(scad, param, output, openscad, fmt, sel, seq, encoding),
            daemon=True,
        )
        self.export_thread.start()
        self.master.after(100, self.update_progress)

    def run_export(self, scad, param, output, openscad, fmt, sel, seq, encoding):
        """
        Execute the batch export process and handle exceptions.

        Args:
            scad (str): Path to the OpenSCAD (.scad) file.
            param (str): Path to the parameter file (CSV or JSON).
            output (str): Output directory for the exported files.
            openscad (str): Path to the OpenSCAD executable.
            fmt (str): Export format ('asciistl' or 'binstl').
            sel (str): Selection string for parameter sets.
            seq (bool): Whether to process exports sequentially.
            encoding (str): Text encoding of the parameter file.
        """
        handler = GuiLogHandler(self)
        logger = logging.getLogger("scadbatch")
        logger.addHandler(handler)
        if logger.level == logging.NOTSET or logger.level > logging.INFO:
            logger.setLevel(logging.INFO)
        try:
            result = batch_export(scad, param, output, openscad, fmt, sel, seq, encoding=encoding)
            self.append_log(result.summary())
        except Exception as e:
            self.append_log(f"An error occurred: {str(e)}")
            messagebox.showerror("Error", f"An error occurred during export:\n{str(e)}")
        finally:
            logger.removeHandler(handler)
            self.enable_controls()
            self.status_label.config(text="Status: Idle", foreground="blue")

    def update_progress(self):
        """
        Update the progress bar based on the status of the export thread.
        """
        if self.export_thread.is_alive():
            # Update the progress bar to indeterminate mode
            self.progress.config(mode="indeterminate")
            if not self.progress["value"]:
                self.progress.start(10)
            self.master.after(100, self.update_progress)
        else:
            # Stop the progress bar and set it to complete
            self.progress.stop()
            self.progress.config(mode="determinate")
            self.progress["value"] = 100

    def convert_csv_to_json(self):
        """
        Initiate the CSV to JSON conversion process.
        """
        # Prompt user to select CSV file
        encoding = self.chosen_encoding()
        if encoding is None:
            return
        csv_file = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not csv_file:
            return
        # Prompt user to select JSON output file
        json_file = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON Files", "*.json")]
        )
        if not json_file:
            return

        # Disable controls during conversion
        self.disable_controls()
        self.append_log(
            f"Converting CSV to JSON: {csv_file} -> {json_file} (reading as {encoding})"
        )
        self.status_label.config(text="Status: Converting CSV to JSON...", foreground="orange")

        # Start conversion in a separate thread
        threading.Thread(
            target=self.run_csv_to_json, args=(csv_file, json_file, encoding), daemon=True
        ).start()

    def run_csv_to_json(self, csv_file, json_file, encoding):
        """
        Perform the CSV to JSON conversion and handle exceptions.

        Args:
            csv_file (str): Path to the input CSV file.
            json_file (str): Path to the output JSON file.
            encoding (str): Text encoding of the CSV file. The JSON is written as UTF-8.
        """
        try:
            csv_to_json(csv_file, json_file, encoding)
            done = f"CSV to JSON conversion completed successfully, reading as {encoding}."
            self.append_log(done)
            messagebox.showinfo("Success", done)
        except Exception as e:
            self.append_log(f"Conversion failed: {str(e)}")
            messagebox.showerror("Error", f"CSV to JSON conversion failed:\n{str(e)}")
        finally:
            # Re-enable controls and update status
            self.enable_controls()
            self.status_label.config(text="Status: Idle", foreground="blue")

    def convert_json_to_csv(self):
        """
        Initiate the JSON to CSV conversion process.
        """
        # Prompt user to select JSON file
        encoding = self.chosen_encoding()
        if encoding is None:
            return
        json_file = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not json_file:
            return
        # Prompt user to select CSV output file
        csv_file = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV Files", "*.csv")]
        )
        if not csv_file:
            return

        # Disable controls during conversion
        self.disable_controls()
        self.append_log(
            f"Converting JSON to CSV: {json_file} -> {csv_file} (reading as {encoding})"
        )
        self.status_label.config(text="Status: Converting JSON to CSV...", foreground="orange")

        # Start conversion in a separate thread
        threading.Thread(
            target=self.run_json_to_csv, args=(json_file, csv_file, encoding), daemon=True
        ).start()

    def run_json_to_csv(self, json_file, csv_file, encoding):
        """
        Perform the JSON to CSV conversion and handle exceptions.

        Args:
            json_file (str): Path to the input JSON file.
            csv_file (str): Path to the output CSV file.
            encoding (str): Text encoding of the JSON file. The CSV is written as UTF-8.
        """
        try:
            json_to_csv(json_file, csv_file, encoding)
            done = f"JSON to CSV conversion completed successfully, reading as {encoding}."
            self.append_log(done)
            messagebox.showinfo("Success", done)
        except Exception as e:
            self.append_log(f"Conversion failed: {str(e)}")
            messagebox.showerror("Error", f"JSON to CSV conversion failed:\n{str(e)}")
        finally:
            # Re-enable controls and update status
            self.enable_controls()
            self.status_label.config(text="Status: Idle", foreground="blue")

    def show_help(self):
        """
        Open the Help window displaying detailed help messages.
        """
        # Start a thread to fetch help text to avoid blocking the GUI
        threading.Thread(target=self.fetch_and_display_help, daemon=True).start()

    def fetch_and_display_help(self):
        """
        Fetch help messages for all subcommands and display them in the Help window.
        """
        help_text = ""
        commands = [
            ["scadbatch", "--help"],
            ["scadbatch", "export", "--help"],
            ["scadbatch", "csv2json", "--help"],
            ["scadbatch", "json2csv", "--help"],
            ["scadbatch", "gui", "--help"],
        ]

        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                help_text += f"{' '.join(cmd)}:\n{result.stdout}\n"
            except subprocess.CalledProcessError as e:
                help_text += f"{' '.join(cmd)} Error:\n{e.stderr}\n"
            except FileNotFoundError:
                help_text += (
                    f"Error: {' '.join(cmd)} command not found. "
                    "Please ensure it is installed and in your system's PATH.\n"
                )

        # Schedule the GUI update in the main thread
        self.master.after(0, self.display_help_window, help_text)

    def display_help_window(self, help_text):
        """
        Create and display the Help window with the provided help text.

        Args:
            help_text (str): The comprehensive help message to display.
        """
        help_window = tk.Toplevel(self.master)
        help_window.title("Help")
        help_window.geometry("800x600")
        help_window.resizable(True, True)

        # Configure grid
        help_window.columnconfigure(0, weight=1)
        help_window.rowconfigure(0, weight=1)

        # Text widget with scrollbar
        text = tk.Text(help_window, wrap=tk.WORD, state=tk.NORMAL, font=("Consolas", 10))
        text.insert(tk.END, help_text)
        text.configure(state=tk.DISABLED)
        text.grid(row=0, column=0, sticky=tk.NSEW, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(help_window, command=text.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS, pady=10)
        text.configure(yscrollcommand=scrollbar.set)


class GuiLogHandler(logging.Handler):
    """Forward log records from the export core to the GUI log panel."""

    def __init__(self, gui):
        super().__init__()
        self.gui = gui

    def emit(self, record):
        self.gui.append_log(self.format(record))


def main():
    """
    Entry point of the GUI module. Initializes and runs the GUI.
    """
    root = tk.Tk()
    # Apply a modern theme using ttk (optional)
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    elif "clam" in style.theme_names():
        style.theme_use("clam")
    else:
        style.theme_use(style.theme_names()[0])  # Default to the first available theme
    _gui = OpenSCADBatchExporterGUI(root)  # keep a reference for the lifetime of mainloop
    root.mainloop()


if __name__ == "__main__":
    main()
