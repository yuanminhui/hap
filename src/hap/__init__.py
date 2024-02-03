import os
from appdirs import user_config_dir


pkgroot = os.path.dirname(__file__)
prjroot = os.path.dirname(os.path.dirname(pkgroot))
confpath = os.path.join(user_config_dir("hap", "yuanminhui"), "hap.yaml")
version = "0.1.0"
ctx_settings = dict(help_option_names=["-h", "--help"])
