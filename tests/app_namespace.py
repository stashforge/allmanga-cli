import importlib

import allmanga_cli.app_core as app_core


def load_app_namespace(*, reload=False):
    module = importlib.reload(app_core) if reload else app_core
    return module.__dict__
