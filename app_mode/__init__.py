
import logging

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .models import EFAppModels
from .run_node import EFAppRun

NODE_CLASS_MAPPINGS = {**NODE_CLASS_MAPPINGS, "EFAppRun": EFAppRun, "EFAppModels": EFAppModels}
NODE_DISPLAY_NAME_MAPPINGS = {**NODE_DISPLAY_NAME_MAPPINGS, "EFAppRun": "Element Forge · Run", "EFAppModels": "Element Forge · Models"}

WEB_DIRECTORY = "./web"

try:
    from server import PromptServer
    from .prompt_rewrite import on_prompt

    _srv = getattr(PromptServer, "instance", None)
    if _srv is not None and not getattr(_srv, "_efa_on_prompt", False):
        _srv.add_on_prompt_handler(on_prompt)
        _srv._efa_on_prompt = True
        logging.info("[Element Forge] prompt rewrite for EFAppValues registered")
except Exception:
    pass

try:
    from .models import register as _register_models

    _register_models()
except Exception:
    pass

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
