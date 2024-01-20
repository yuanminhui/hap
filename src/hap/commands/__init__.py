from pathlib import Path
import importlib


# import modules as functions
curdir = Path(__file__).parent.iterdir()
for modfp in curdir:
    if modfp.suffix == ".py" and not modfp.name.startswith("__"):
        modname = modfp.stem
        mod = importlib.import_module("." + modname, package=__name__)

        funcname = "cli"
        if funcname in dir(mod):
            globals()[modname] = getattr(mod, funcname)
