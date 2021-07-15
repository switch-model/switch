"""
This file ensures that all python files in this folder are imported so that
their @register_post_process function handlers are noticed.
"""
from pathlib import Path

# Import all the files in this directory that end in .py and don't start with an underscore
__all__ = [f.stem for f in Path(__file__).parent.glob("[!_]*.py")]
