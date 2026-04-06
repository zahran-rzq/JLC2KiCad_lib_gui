#!/usr/bin/env python
import json
import logging
import os
import re
import sys
import tempfile

import pcbnew
import requests
import wx

from .core_library_installer import (
    REPO_URL,
    get_core_version,
    get_latest_core_version,
    install_or_upgrade_core,
)


OUTPUT_FOLDER = "kicad_libs"
FOOTPRINT_LIB  = "footprint"
FOOTPRINT_LIB_NICK  = "footprint"  #set the same as FOOTPRINT_LIB, or to nickname choosen in Footprint libraries manager
# Leave empty so JLC2KiCadLib creates one symbol library file per product name.
SYMBOL_LIB = ""
SYMBOL_LIB_DIR = "symbols"


helper = None
create_footprint = None
create_symbol = None


def _core_version_text():
    version = get_core_version()
    return (
        f"JLC2KiCad library v{version}"
        if version
        else "JLC2KiCad library not installed"
    )


def _load_gui_core_library():
    global helper, create_footprint, create_symbol

    if helper and create_footprint and create_symbol:
        return

    from JLC2KiCadLib import helper as _helper
    from JLC2KiCadLib.footprint.footprint import create_footprint as _create_footprint
    from JLC2KiCadLib.symbol.symbol import create_symbol as _create_symbol

    helper = _helper
    create_footprint = _create_footprint
    create_symbol = _create_symbol


def _check_gui_core_library(parent=None):
    global helper, create_footprint, create_symbol

    try:
        _load_gui_core_library()
        return True
    except ModuleNotFoundError:
        answer = wx.MessageBox(
            "JLC2KiCad library is missing.\n\nInstall it now?",
            "JLC2KiCad Missing Dependency",
            wx.YES_NO | wx.ICON_QUESTION,
            parent=parent,
        )
        if answer == wx.YES:
            if install_or_upgrade_core(prompt_reason="missing", prompt_user=False):
                helper = None
                create_footprint = None
                create_symbol = None
                try:
                    _load_gui_core_library()
                    return True
                except Exception:
                    pass

        wx.MessageBox(
            "JLC2KiCad library is required to run this plugin.\n"
            "See README.md for installation steps.\n"
            f"Repository: {REPO_URL}",
            "JLC2KiCad Missing Dependency",
            wx.OK | wx.ICON_ERROR,
            parent=parent,
        )
        return False
    except Exception as exc:
        wx.MessageBox(
            "Failed to load JLC2KiCad library.\n"
            f"Error: {type(exc).__name__}: {exc}",
            "JLC2KiCad Error",
            wx.OK | wx.ICON_ERROR,
            parent=parent,
        )
        return False


class MyCustomDialog(wx.Dialog):
    def __init__(self, parent, title, message, caption):
        super(MyCustomDialog, self).__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        board: pcbnew.BOARD = pcbnew.GetBoard()
        board_file = board.GetFileName() if board else ""
        self.board_dir = os.path.dirname(board_file) if board_file else os.getcwd()
        self.project_dir = self._find_project_dir(self.board_dir)
        self.default_output_dir = os.path.join(self.board_dir, OUTPUT_FOLDER)

        # Create a sizer to manage the layout
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header row: part label on the left, update action on the right.
        header_row = wx.BoxSizer(wx.HORIZONTAL)
        header_row.Add(wx.StaticText(self, label=message), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        header_row.AddStretchSpacer(1)
        self.core_version_label = wx.StaticText(self, label=_core_version_text())
        header_row.Add(self.core_version_label, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        self.update_button = wx.Button(self, wx.ID_ANY, "Check for updates")
        header_row.Add(self.update_button, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        sizer.Add(header_row, 0, wx.EXPAND, 0)

        # Add a text entry field
        self.text_entry = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.text_entry, 0, wx.ALL | wx.EXPAND, 10)

        output_row = wx.BoxSizer(wx.HORIZONTAL)
        output_label = wx.StaticText(self, label="Output folder")
        self.output_entry = wx.TextCtrl(self, value=self.default_output_dir)
        browse_button = wx.Button(self, wx.ID_ANY, "Browse...")
        output_row.Add(output_label, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        output_row.Add(self.output_entry, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        output_row.Add(browse_button, 0, wx.ALIGN_CENTER_VERTICAL, 0)
        sizer.Add(output_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        # Add custom buttons, right-aligned.
        button_row = wx.BoxSizer(wx.HORIZONTAL)
        button_row.AddStretchSpacer(1)

        ok_button = wx.Button(self, wx.ID_OK, "Copy to clipboard")
        download_button = wx.Button(self, wx.ID_APPLY, "Download to project library")
        auto_import_button = wx.Button(self, wx.ID_ANY, "beta Download + Auto Import (need restart kicad)")
        import_symbols_button = wx.Button(self, wx.ID_ANY, "beta Import Symbols (Semi Auto) (need restart kicad)")
        cancel_button = wx.Button(self, wx.ID_CANCEL, "Cancel")
        help_button = wx.Button(self, wx.ID_HELP, "Help")

        button_row.Add(ok_button, 0, wx.LEFT, 6)
        button_row.Add(download_button, 0, wx.LEFT, 6)
        button_row.Add(auto_import_button, 0, wx.LEFT, 6)
        button_row.Add(import_symbols_button, 0, wx.LEFT, 6)
        button_row.Add(cancel_button, 0, wx.LEFT, 6)
        button_row.Add(help_button, 0, wx.LEFT, 6)

        sizer.Add(button_row, 0, wx.ALL | wx.EXPAND, 10)

        self.SetSizer(sizer)
        self.Fit()

        self.Bind(wx.EVT_BUTTON, self.OnDownload, id=wx.ID_APPLY)
        self.Bind(wx.EVT_BUTTON, self.OnDownloadAutoImport, id=auto_import_button.GetId())
        self.Bind(wx.EVT_BUTTON, self.OnImportSymbolsOnly, id=import_symbols_button.GetId())
        self.Bind(wx.EVT_BUTTON, self.OnUpdateCoreLibrary, id=self.update_button.GetId())
        self.Bind(wx.EVT_BUTTON, self.OnBrowseOutput, id=browse_button.GetId())
        self.Bind(wx.EVT_BUTTON, self.OnPlaceFootprint, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self.OnHelp, id=wx.ID_HELP)

        
        self.SetDefaultItem(ok_button)
        wx.CallAfter(self._prefill_part_number_from_clipboard)

    @staticmethod
    def _parse_part_number(text):
        if not text:
            return ""
        match = re.search(r"\bC\d+\b", text)
        return match.group(0) if match else ""

    @staticmethod
    def _read_clipboard_text():
        data = wx.TextDataObject()
        if not wx.TheClipboard.Open():
            return ""
        try:
            if wx.TheClipboard.GetData(data):
                return data.GetText()
        finally:
            wx.TheClipboard.Close()
        return ""

    def _prefill_part_number_from_clipboard(self):
        clipboard_text = self._read_clipboard_text()
        part_number = self._parse_part_number(clipboard_text)
        if part_number:
            self.text_entry.SetValue(part_number)
            self.text_entry.SelectAll()
        self.text_entry.SetFocus()

    def _get_output_dir(self):
        configured = self.output_entry.GetValue().strip()
        if not configured:
            return ""
        expanded = os.path.expanduser(os.path.expandvars(configured))
        if os.path.isabs(expanded):
            return expanded
        return os.path.abspath(os.path.join(self.board_dir, expanded))

    def OnBrowseOutput(self, event):
        current = self._get_output_dir() or self.default_output_dir
        if not os.path.isdir(current):
            current = self.board_dir
        with wx.DirDialog(
            self,
            "Choose output folder",
            defaultPath=current,
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.output_entry.SetValue(dlg.GetPath())

    def _prepare_download(self):
        component_id = self.text_entry.GetValue().strip()
        if not component_id:
            wx.MessageBox("Type part number, e.g. C326215")
            return "", ""

        out_dir = self._get_output_dir()
        if not out_dir:
            wx.MessageBox("Choose output folder first")
            return "", ""

        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            wx.MessageBox(f"Cannot create output folder:\n{out_dir}\n\n{type(exc).__name__}: {exc}")
            return "", ""

        return component_id, out_dir

    @staticmethod
    def _collect_symbol_library_files(out_dir):
        symbol_dir = os.path.join(out_dir, SYMBOL_LIB_DIR)
        if not os.path.isdir(symbol_dir):
            return []
        symbol_files = []
        for name in os.listdir(symbol_dir):
            if name.lower().endswith(".kicad_sym"):
                symbol_files.append(os.path.join(symbol_dir, name))
        symbol_files.sort()
        return symbol_files

    @staticmethod
    def _find_project_dir(start_dir):
        current = os.path.abspath(start_dir)
        while True:
            try:
                files = os.listdir(current)
            except OSError:
                files = []

            has_kicad_project = any(
                name.lower().endswith(".kicad_pro") or name.lower().endswith(".pro")
                for name in files
            )
            if has_kicad_project:
                return current

            parent = os.path.dirname(current)
            if not parent or parent == current:
                return os.path.abspath(start_dir)
            current = parent

    def _symbol_table_uri(self, symbol_file):
        symbol_file = os.path.abspath(symbol_file)
        project_dir = os.path.abspath(self.project_dir)
        try:
            rel_path = os.path.relpath(symbol_file, project_dir)
            if not rel_path.startswith("..") and not os.path.isabs(rel_path):
                return "${KIPRJMOD}/" + rel_path.replace("\\", "/")
        except ValueError:
            pass
        return symbol_file.replace("\\", "/")

    @staticmethod
    def _unique_library_name(base_name, table_text):
        candidate = base_name
        suffix = 2
        while f'(name "{candidate}")' in table_text:
            candidate = f"{base_name}_{suffix}"
            suffix += 1
        return candidate

    def _import_symbol_libraries_to_project(self, out_dir):
        symbol_files = self._collect_symbol_library_files(out_dir)
        if not symbol_files:
            return 0, 0, os.path.join(self.project_dir, "sym-lib-table")

        table_path = os.path.join(self.project_dir, "sym-lib-table")
        if os.path.isfile(table_path):
            with open(table_path, "r", encoding="utf-8") as table_file:
                table_text = table_file.read()
        else:
            table_text = "(sym_lib_table\n)\n"

        if "(sym_lib_table" not in table_text:
            raise RuntimeError("sym-lib-table format is not recognized")

        imported = 0
        skipped = 0
        entries_to_add = []
        table_index_text = table_text

        for symbol_file in symbol_files:
            uri = self._symbol_table_uri(symbol_file)
            if f'(uri "{uri}")' in table_text:
                skipped += 1
                continue

            base_name = os.path.splitext(os.path.basename(symbol_file))[0]
            lib_name = self._unique_library_name(base_name, table_index_text)
            entry = (
                f'  (lib (name "{lib_name}") (type "KiCad") '
                f'(uri "{uri}") (options "") (descr "Imported by JLC2KiCad GUI"))\n'
            )
            entries_to_add.append(entry)
            table_index_text += entry
            imported += 1

        if entries_to_add:
            insert_at = table_text.rfind(")")
            if insert_at < 0:
                raise RuntimeError("sym-lib-table footer not found")
            new_text = table_text[:insert_at] + "".join(entries_to_add) + table_text[insert_at:]
            with open(table_path, "w", encoding="utf-8") as table_file:
                table_file.write(new_text)

        return imported, skipped, table_path


    def OnDownload(self, event):
        component_id, out_dir = self._prepare_download()
        if not component_id:
            return

        self.libpath, self.component_name = download_part(component_id, out_dir, True, True)
        if not self.component_name:
            return

        wx.MessageBox(f"Footprint " + self.component_name + " downloaded to project library " + self.libpath)

    def OnDownloadAutoImport(self, event):
        component_id, out_dir = self._prepare_download()
        if not component_id:
            return

        self.libpath, self.component_name = download_part(component_id, out_dir, True, True)
        if not self.component_name:
            return

        try:
            imported, skipped, table_path = self._import_symbol_libraries_to_project(out_dir)
        except Exception as exc:
            wx.MessageBox(
                "Download succeeded but symbol auto-import failed.\n"
                f"{type(exc).__name__}: {exc}"
            )
            return

        wx.MessageBox(
            f"Footprint {self.component_name} downloaded to {self.libpath}\n"
            f"Symbol libraries imported: {imported}, skipped: {skipped}\n"
            f"Project dir: {self.project_dir}\n"
            f"Project table: {table_path}"
        )

    def OnImportSymbolsOnly(self, event):
        out_dir = self._get_output_dir()
        if not out_dir:
            wx.MessageBox("Choose output folder first")
            return
        if not os.path.isdir(out_dir):
            wx.MessageBox("Output folder does not exist yet")
            return

        try:
            imported, skipped, table_path = self._import_symbol_libraries_to_project(out_dir)
        except Exception as exc:
            wx.MessageBox(
                "Symbol import failed.\n"
                f"{type(exc).__name__}: {exc}"
            )
            return

        wx.MessageBox(
            f"Symbol libraries imported: {imported}, skipped: {skipped}\n"
            f"Project dir: {self.project_dir}\n"
            f"Project table: {table_path}"
        )

    def OnPlaceFootprint(self, event):
        component_id = self.text_entry.GetValue()
        if not component_id:
            wx.MessageBox("Type part number, e.g. C326215")
            return
        out_dir =  os.path.join(tempfile.mkdtemp())
        self.libpath, self.component_name = download_part(component_id, out_dir)
        self.EndModal(wx.ID_OK)

    def OnCancel(self, event):
        self.EndModal(wx.ID_CANCEL)

    def OnUpdateCoreLibrary(self, event):
        current_version = get_core_version()
        latest_version = get_latest_core_version()
        if current_version and latest_version and current_version == latest_version:
            wx.MessageBox(
                f"JLC2KiCad library is already up to date (v{current_version}).",
                "JLC2KiCad",
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        if install_or_upgrade_core(prompt_reason="update"):
            new_version = get_core_version()
            self.core_version_label.SetLabel(_core_version_text())
            self.Layout()

            global helper, create_footprint, create_symbol
            helper = None
            create_footprint = None
            create_symbol = None
            if current_version != new_version:
                self.EndModal(wx.ID_CANCEL)

    def OnHelp(self, event):
        wx.MessageBox(
            "Copy to clipboard downloads footprint to a temporary folder and copies it to clipboard (Ctrl+V to paste).\n"
            "Download to project library saves files to the selected output folder.\n"
            "Download + Auto Import also adds all .kicad_sym files to project sym-lib-table automatically.\n"
            "Import Symbols (Semi Auto) only updates project sym-lib-table from existing downloaded symbols.",
            "Help",
            wx.OK | wx.ICON_INFORMATION,
        )


def download_part(component_id, out_dir, get_symbol=False, skip_existing=False):
    logging.info(f"creating library for component {component_id}")
    data = json.loads(
        requests.get(
            f"https://easyeda.com/api/products/{component_id}/svgs",
            headers={"User-Agent": helper.get_user_agent()},
        ).content.decode()
    )

    if not data["success"]:
        wx.MessageBox(
            f"Failed to get component uuid for {component_id}\nThe component # is probably wrong. Check a possible typo and that the component exists on easyEDA"
        )
        return "", ""
    
    footprint_component_uuid = data["result"][-1]["component_uuid"]
    footprint_name, datasheet_link = create_footprint(
        footprint_component_uuid=footprint_component_uuid,
        component_id=component_id,
        footprint_lib=FOOTPRINT_LIB,
        output_dir=out_dir,
        model_base_variable="",
        model_dir="packages3d",
        skip_existing=skip_existing,
        models="STEP",
    )

    if get_symbol:
        symbol_component_uuid = [i["component_uuid"] for i in data["result"][:-1]]
        create_symbol(
            symbol_component_uuid=symbol_component_uuid,
            footprint_name=footprint_name.replace(FOOTPRINT_LIB, FOOTPRINT_LIB_NICK) #link footprint according to the nickname
                .replace(".pretty", ""),  # see https://github.com/TousstNicolas/JLC2KiCad_lib/issues/47
            datasheet_link=datasheet_link,
            library_name=SYMBOL_LIB,
            symbol_path=SYMBOL_LIB_DIR,
            output_dir=out_dir,
            component_id=component_id,
            skip_existing=skip_existing,
        )
    libpath = os.path.join(out_dir, FOOTPRINT_LIB)
    component_name = footprint_name.replace(FOOTPRINT_LIB + ":", "")
    
    return libpath, component_name

class JLC2KiCad_GUI(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Download JLC part"
        self.category = "Modify PCB"
        self.description = "A description of the plugin and what it does"
        self.show_toolbar_button = True
 
        self.pcbnew_icon_support = hasattr(self, "show_toolbar_button")
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")
        
        self._pcbnew_frame = None
        self.kicad_build_version = pcbnew.GetBuildVersion()

        self.InitLogger()
        self.logger = logging.getLogger(__name__)

    def IsVersion(self, version):
        for v in version:
            if v in self.kicad_build_version:
                return True
        return False

    def PasteFootprint(self):
        # Footprint string pasting based on KiBuzzard https://github.com/gregdavill/KiBuzzard/blob/main/KiBuzzard/plugin.py
        if self.IsVersion(['5.99','6.', '7.']):
            if self._pcbnew_frame is not None:
                # Set focus to main window and attempt to execute a Paste operation 
                wx.MilliSleep(100)
                try:
                    # Send ESC key before Ctrl+V to close other activities
                    esc_evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
                    esc_evt.SetKeyCode(wx.WXK_ESCAPE)
                    self.logger.log(logging.INFO, "Using wx.KeyEvent for ESC key")

                    wnd = [i for i in self._pcbnew_frame.Children if i.ClassName == 'wxWindow'][0]
                    self.logger.log(logging.INFO, "Injecting ESC event: {} into window: {}".format(esc_evt, wnd))
                    wx.PostEvent(wnd, esc_evt)

                    # Simulate pressing Ctrl+V to paste footprint
                    v_evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
                    v_evt.SetKeyCode(ord('V'))
                    v_evt.SetControlDown(True)
                    self.logger.log(logging.INFO, "Using wx.KeyEvent for Ctrl+V")

                    self.logger.log(logging.INFO, "Injecting Ctrl+V event: {} into window: {}".format(v_evt, wnd))
                    wx.PostEvent(wnd, v_evt)

                except:
                    # Likely on Linux with old wx python support :(
                    self.logger.log(logging.INFO, "Using wx.UIActionSimulator for paste")
                    keyinput = wx.UIActionSimulator()
                    self._pcbnew_frame.Raise()
                    self._pcbnew_frame.SetFocus()
                    wx.MilliSleep(100)
                    wx.Yield()
                    # Press and release CTRL + V
                    keyinput.Char(ord("V"), wx.MOD_CONTROL)
                    wx.MilliSleep(100)
            else:
                self.logger.log(logging.ERROR, "No pcbnew window found")
        else:
            self.logger.log(logging.ERROR, "Version check failed \"{}\" not in version list".format(self.kicad_build_version))

    def Run(self):
        board: pcbnew.BOARD = pcbnew.GetBoard()
        if not _check_gui_core_library():
            return

        if self._pcbnew_frame is None:
            try:
                self._pcbnew_frame = [x for x in wx.GetTopLevelWindows() if ('pcbnew' in x.GetTitle().lower() and not 'python' in x.GetTitle().lower()) or ('pcb editor' in x.GetTitle().lower())]
                if len(self._pcbnew_frame) == 1:
                    self._pcbnew_frame = self._pcbnew_frame[0]
                else:
                    self._pcbnew_frame = None
            except:
                pass

        part_download_dialog = MyCustomDialog(None, "Download JLCPCB part footprint and symbol", "JLCPCB part no:", "JLCPCB part download plugin")
        part_download_dialog.Center()
        
        dialog_answer = part_download_dialog.ShowModal()
        if dialog_answer == wx.ID_CANCEL:
            return
        if dialog_answer == wx.ID_OK:
            libpath = part_download_dialog.libpath
            component_name = part_download_dialog.component_name
            if component_name:
                self.logger.log(logging.DEBUG, "Loading footprint into the clipboard")
                clipboard = wx.Clipboard.Get()
                if clipboard.Open():
                    # read file
                    with open(os.path.join(libpath, component_name + ".kicad_mod"), 'r') as file:
                        footprint_string = file.read()
                    clipboard.SetData(wx.TextDataObject(footprint_string))
                    clipboard.Close()
                else:
                    self.logger.log(logging.DEBUG, "Clipboard error")
                    fp : pcbnew.FOOTPRINT = pcbnew.FootprintLoad(libpath, component_name)
                    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
                    board.Add(fp)
                    pcbnew.Refresh()
                    wx.MessageBox("Clipboard couldn't be opened. Footprint " + component_name + " was placed in top left corner of the canvas")

                self.PasteFootprint()



    def InitLogger(self):
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        # Log to stderr
        handler1 = logging.StreamHandler(sys.stderr)
        handler1.setLevel(logging.DEBUG)


        log_path = os.path.dirname(__file__)
        log_file = os.path.join(log_path, "JLC2KiCad_gui.log")

        # and to our error file
        # Check logging file permissions, if fails, move log file to tmp folder
        handler2 = None
        try:
            handler2 = logging.FileHandler(log_file)
        except PermissionError:
            log_path = os.path.join(tempfile.mkdtemp()) 
            try: # Use try/except here because python 2.7 doesn't support exist_ok
                os.makedirs(log_path)

            except:
                pass
            log_file = os.path.join(log_path, "JLC2KiCad_gui.log")
            handler2 = logging.FileHandler(log_file)

            # Also move config file
            self.config_file = os.path.join(log_path, 'config.json')
        
        handler2.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s %(name)s %(lineno)d:%(message)s", datefmt="%m-%d %H:%M:%S"
        )
        handler1.setFormatter(formatter)
        handler2.setFormatter(formatter)
        root.addHandler(handler1)
        root.addHandler(handler2)
