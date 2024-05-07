import importlib
from pathlib import Path

MAIN_FUNC_NAME = "main"

# Import modules as functions
for file in Path(__file__).parent.iterdir():
    if file.suffix == ".py" and not file.name.startswith("__"):
        module_name = file.stem
        module = importlib.import_module("." + module_name, package=__name__)
        if MAIN_FUNC_NAME in dir(module):
            globals()[module_name] = getattr(module, MAIN_FUNC_NAME)
