from os.path import dirname, basename, isfile, join
import glob

# Get all the modules in this folder
modules = glob.glob(join(dirname(__file__), "*.py"))
# Only keep the files and exclude this file
modules = filter(lambda f: isfile(f) and not f.endswith("__init__.py"), modules)
# Change the file path to a basename
modules = map(lambda f: basename(f)[:-3], modules)
# Specify in __all__
__all__ = list(modules)
