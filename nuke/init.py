# CorridorKey 2.0 Nuke init.py
# Add current directory to Nuke plugin path
import os
import nuke

this_dir = os.path.dirname(__file__)
if this_dir not in nuke.pluginPath():
    nuke.pluginAddPath(this_dir)
