import os

from appdirs import user_config_dir


PACKAGE_ROOT = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(os.path.dirname(PACKAGE_ROOT))
CONFIG_FILE = os.path.join(user_config_dir("hap", "yuanminhui"), "hap.yaml")
VERSION = "0.1.0"
CTX_SETTINGS = dict(help_option_names=["-h", "--help"])
