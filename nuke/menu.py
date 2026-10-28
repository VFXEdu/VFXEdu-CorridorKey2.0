# CorridorKey 2.0 Nuke menu.py
import os
import subprocess
import sys
import nuke

import corridorkey_nuke

# 1. Main Menu Bar
m_bar = nuke.menu("Nuke")
vfx_menu = m_bar.addMenu("VFXEdu")
vfx_menu.addCommand(
    "CorridorKeyer (Gizmo)",
    "nuke.createNode('CorridorKeyer')",
    icon="Keyer.png"
)
vfx_menu.addCommand(
    "Create CorridorKeyer Group (Native)",
    "import corridorkey_nuke; corridorkey_nuke.create_corridorkeyer_node()",
    icon="Group.png"
)
vfx_menu.addSeparator()


def _launch_workbench():
    root = corridorkey_nuke.find_corridorkey_root()
    if not root:
        nuke.message("CorridorKeyer 2.0 root directory not found!")
        return

    launch_bat = root / "Launch_GUI.bat"
    if sys.platform == "win32" and launch_bat.is_file():
        subprocess.Popen([str(launch_bat)], cwd=str(root), shell=True)
    else:
        py_exe = corridorkey_nuke.find_python_executable(root)
        gui_py = root / "gui.py"
        if py_exe and gui_py.is_file():
            subprocess.Popen([str(py_exe), str(gui_py)], cwd=str(root))
        else:
            nuke.message(f"Could not find Python or gui.py in {root}")


vfx_menu.addCommand(
    "Open VFXEdu CorridorKeyer Workbench GUI...",
    _launch_workbench,
    icon="Viewer.png"
)

# 2. Nodes Toolbar (Keyer menu)
nodes_toolbar = nuke.menu("Nodes")
keyer_menu = nodes_toolbar.findItem("Keyer")
if keyer_menu:
    keyer_menu.addCommand(
        "CorridorKeyer 2.0",
        "nuke.createNode('CorridorKeyer')",
        icon="Keyer.png"
    )
else:
    nodes_toolbar.addCommand(
        "CorridorKeyer 2.0",
        "nuke.createNode('CorridorKeyer')",
        icon="Keyer.png"
    )
