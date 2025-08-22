import os

from appdirs import user_config_dir

PACKAGE_ROOT = os.path.dirname(__file__)
SOURCE_ROOT = os.path.dirname(PACKAGE_ROOT)
PROJECT_ROOT = os.path.dirname(SOURCE_ROOT)
CONFIG_PATH = os.path.join(user_config_dir("hap", "yuanminhui"), "hap.yaml")
VERSION = "0.1.0"  # TODO: Remove hard-coded version and find a way to get version from project metadata
CTX_SETTINGS = dict(help_option_names=["-h", "--help"])
