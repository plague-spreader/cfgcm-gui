#!/usr/bin/python3
import tkinter.messagebox as tkmsg
import tkinter as tk
import subprocess
import pathlib
import pygubu
import os

PROJECT_PATH = pathlib.Path(__file__).parent
PROJECT_UI = PROJECT_PATH / "cfgcm.ui"


def is_executable(path_obj):
    return path_obj.is_file() and os.access(str(path_obj), os.X_OK)

def is_terminal(path_obj):
    return path_obj.is_dir() and any(map(lambda t: t.name == "connect" and
                                         is_executable(t), path_obj.iterdir()))

def is_cycling(path_parent, path_child):
    parent_parts = path_parent.parts
    child_parts = path_child.parts
    if len(child_parts) > len(parent_parts):
        return False
    for pp, pc in zip(parent_parts, child_parts):
        if pp != pc:
            return False
    return True

class ConnectionView:
    def __init__(self, conn_path_obj):
        self.parts = pathlib.Path(conn_path_obj).parts
        self.description = None
        try:
            self.description = conn_path_obj.joinpath("description")
        except FileNotFoundError:
            pass

    def __eq__(self, value):
        if isinstance(value, ConnectionView):
            return self.parts == value.parts
        return False

def search_connections(path_obj, prefix, ret):
    for child_path_obj in path_obj.iterdir():
        resolved_child_path_obj = child_path_obj.resolve()
        if resolved_child_path_obj.name.startswith("."):
            continue

        if is_cycling(path_obj, resolved_child_path_obj):
            raise ValueError(f'Found cycle "{path_obj}" -> \
"{resolved_child_path_obj}"')

        if is_terminal(resolved_child_path_obj):
            no_prefix_path_obj = pathlib.Path("/")
            for part in resolved_child_path_obj.parts[len(prefix.parts):]:
                no_prefix_path_obj = no_prefix_path_obj.joinpath(part)
            ret.append(no_prefix_path_obj)
        elif resolved_child_path_obj.is_dir():
            search_connections(resolved_child_path_obj, prefix, ret)
    return ret

def get_cfgcm_dir():
    xdg_data_home = pathlib.Path.home().joinpath(".local/share")
    try:
        xdg_data_home = pathlib.Path(os.environ["XDG_DATA_HOME"])
    except KeyError:
        pass
    return xdg_data_home.joinpath("cfgcm")

def get_terminal_command():
    try:
        return os.environ["CFGCM_DEFAULT_TERMINAL"]
    except KeyError:
        return 'alacritty --hold -e {connection:}'

class CfgcmApp:
    def __init__(self, master=None):
        self.builder = builder = pygubu.Builder()
        builder.add_resource_path(PROJECT_PATH)
        builder.add_from_file(PROJECT_UI)

        # GUI object definitions
        self.window_main = builder.get_object("window_main", master)
        self.window_set_terminal = \
                builder.get_object("window_set_terminal", master)
        self.menu_main = builder.get_object("menu_main", self.window_main)

        # global variables
        self.CFGCM_PATH = get_cfgcm_dir()
        self.is_edit_visible = True
        self.is_description_visible = True
        self.terminal_command = get_terminal_command()

        # initialization
        self.window_main.configure(menu=self.menu_main)
        self.window_set_terminal.protocol("WM_DELETE_WINDOW",
                                          self.set_terminal)

        self.load_connections()
        self.toggle_edit_visibility()
        self.toggle_description_visibility()
        self.window_set_terminal.withdraw()

        builder.connect_callbacks(self)

    def run(self):
        self.window_main.mainloop()

    # CALLBACKS
    def load_connections(self, event=None):
        treeview_conns = self.builder.get_object("tree_conns", None)
        treeview_conns.delete(*treeview_conns.get_children())
        for conn in search_connections(pathlib.Path(self.CFGCM_PATH),
                                       pathlib.Path(self.CFGCM_PATH), []):
            parent = ""
            cumulative_parts = ""
            for part in conn.parts:
                cumulative_parts = str(pathlib.Path(cumulative_parts).
                        joinpath(part))
                if treeview_conns.exists(cumulative_parts):
                    parent = cumulative_parts
                    continue
                treeview_conns.insert(parent, "end", str(cumulative_parts),
                                      text=part)
                parent = cumulative_parts

    def update_selected_path(self, event=None):
        treeview_conns = self.builder.get_object("tree_conns", None)
        self.selected_path = treeview_conns.selection()[0]

        self.update_description()

    def toggle_edit_visibility(self, event=None):
        frame_edit_conns = self.builder.get_object("frame_edit_conns", None)
        btn_toggle_edit = self.builder.get_object("btn_toggle_edit", None)

        btn_new_text = ""
        if self.is_edit_visible:
            btn_new_text = "⮞"
            frame_edit_conns.pack_forget()
        else:
            btn_new_text = "⮟"
            frame_edit_conns.pack()

        self.is_edit_visible = not self.is_edit_visible
        btn_toggle_edit.config(text=btn_new_text)

    def toggle_description_visibility(self, event=None):
        frame_description = self.builder.get_object("frame_description", None)
        btn_toggle_description = self.builder.\
                get_object("btn_toggle_description", None)

        btn_new_text = ""
        if self.is_description_visible:
            btn_new_text = "⮜"
            frame_description.pack_forget()
        else:
            btn_new_text = "⮟"
            frame_description.pack()

        self.is_description_visible = not self.is_description_visible
        btn_toggle_description.config(text=btn_new_text)

    def show_set_terminal(self, event=None):
        self.window_set_terminal.deiconify()
        txt_terminal = self.builder.get_object("txt_terminal", None)
        txt_terminal.delete(0, tk.END)
        txt_terminal.insert(0, self.terminal_command)

    def set_terminal(self, event=None):
        terminal_command = self.builder.get_object("txt_terminal", None).\
                get()
        if "{connection:}" in terminal_command:
            self.terminal_command = terminal_command
        else:
            tkmsg.showerror(message='The terminal command must contain the \
"{connection:}" substring otherwise it will NOT work\n\
\n\
Example: \'alacritty --hold -e "{connection:}"\'')
        self.window_set_terminal.withdraw()

    def do_connect(self, event=None):
        connect_path = self.selected_path_to_absolute()
        if connect_path is None:
            tkmsg.showerror(message="No connection selected")
            return

        connect_path = connect_path.joinpath("connect")
        if not is_executable(connect_path):
            tkmsg.showerror(message="The selected path is not a connection")
            return

        exec_command = self.terminal_command.format(connection=connect_path)
        subprocess.Popen(exec_command.split())

    # METHODS
    def update_description(self):
        lbl_description = self.builder.get_object("lbl_description", None)
        description_text = self.selected_path

        description_path = self.selected_path_to_absolute()
        if description_path is not None:
            description_path = description_path.joinpath("description")
            if description_path.is_file():
                description_text += f" — {description_path.read_text()}"

        lbl_description.config(text=description_text)

    def selected_path_to_absolute(self):
        try:
            selected_path = self.selected_path
            if selected_path.startswith("/"):
                selected_path = selected_path[1:]
            return self.CFGCM_PATH.joinpath(selected_path)
        except AttributeError:
            return None

if __name__ == "__main__":
    app = CfgcmApp()
    app.run()
