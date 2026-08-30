"""Streaming provider registry."""

from __future__ import annotations

import importlib
import pkgutil
import json
import os
from typing import Iterable, Dict, Any

# Load the JSON registry
_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "registry.json")
try:
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as _f:
        PROVIDER_REGISTRY = json.load(_f).get("providers", {})
except Exception:
    PROVIDER_REGISTRY = {}


_SKIPPED_MODULES = {"shared"}
_DISABLED_PROVIDERS = {"senshi", "allanime"}
_DEFAULT_PROVIDER_ID = "miruro"


def _provider_classes_from_module(module) -> list[type]:
    classes = []
    provider_class = getattr(module, "PROVIDER_CLASS", None)
    if provider_class is not None:
        if isinstance(provider_class, (list, tuple)):
            classes.extend(provider_class)
        else:
            classes.append(provider_class)
    provider_classes = getattr(module, "PROVIDER_CLASSES", None)
    if provider_classes:
        classes.extend(provider_classes)
    return [
        cls for cls in classes
        if getattr(cls, "id", None) and callable(cls)
    ]


def discover_provider_factories(
    package_path: Iterable[str] | None = None,
    package_name: str | None = None,
) -> dict[str, type]:
    """Discover provider classes from provider modules.

    A built-in provider module only needs to expose ``PROVIDER_CLASS`` or
    ``PROVIDER_CLASSES``.  The registry handles the rest.
    """
    package_path = __path__ if package_path is None else package_path
    package_name = __name__ if package_name is None else package_name

    factories: dict[str, type] = {}
    for module_info in pkgutil.iter_modules(package_path):
        name = module_info.name
        if name.startswith("_") or name in _SKIPPED_MODULES:
            continue
        module = importlib.import_module(f"{package_name}.{name}")
        for provider_class in _provider_classes_from_module(module):
            provider_id = str(provider_class.id).casefold()
            if provider_id in _DISABLED_PROVIDERS:
                continue
            factories[provider_id] = provider_class
    return factories


PROVIDER_FACTORIES = discover_provider_factories()
if _DEFAULT_PROVIDER_ID not in PROVIDER_FACTORIES:
    from .miruro import MiruroProvider

    PROVIDER_FACTORIES[_DEFAULT_PROVIDER_ID] = MiruroProvider

PROVIDERS = {
    provider_id: factory()
    for provider_id, factory in PROVIDER_FACTORIES.items()
}

# Attach metadata directly to instances for backward compatibility,
# and so providers can self-reference their JSON domains.
for p_id, p_inst in PROVIDERS.items():
    if p_id in PROVIDER_REGISTRY:
        p_inst.metadata = PROVIDER_REGISTRY[p_id]
        if hasattr(p_inst, 'domains') or not hasattr(p_inst, 'domains'):
            p_inst.domains = PROVIDER_REGISTRY[p_id].get("domains", [])
    else:
        p_inst.metadata = {}
        p_inst.domains = []

ALLANIME = PROVIDERS[_DEFAULT_PROVIDER_ID]


def available_providers():
    return dict(PROVIDERS)

def get_provider_registry() -> Dict[str, Any]:
    return PROVIDER_REGISTRY


def is_provider_active(provider_id: str) -> bool:
    if not provider_id:
        return False
    key = str(provider_id).casefold()
    if key in _DISABLED_PROVIDERS or key not in PROVIDERS:
        return False
    status = PROVIDER_REGISTRY.get(key, {}).get("status", "active")
    if status in ("broken", "disabled", "deprecated"):
        return False
    return True


def provider_key(provider_id=_DEFAULT_PROVIDER_ID):
    key = str(provider_id or "").casefold()
    if is_provider_active(key):
        return key
    return _DEFAULT_PROVIDER_ID


def get_provider(provider_id=_DEFAULT_PROVIDER_ID, request_json_fn=None):
    key = provider_key(provider_id)
    if request_json_fn is None:
        return PROVIDERS[key]
    
    inst = PROVIDER_FACTORIES[key](request_json_fn)
    if key in PROVIDER_REGISTRY:
        inst.metadata = PROVIDER_REGISTRY[key]
        inst.domains = PROVIDER_REGISTRY[key].get("domains", [])
    else:
        inst.metadata = {}
        inst.domains = []
    return inst


def provider_translation_capability(
    provider_id: str,
    show: dict[str, Any] | None = None,
    current_ttype: str = "sub",
    target_ttype: str = "dub",
) -> tuple[bool, str | None]:
    prov = get_provider(provider_id)
    if hasattr(prov, "translation_switch_capability") and callable(prov.translation_switch_capability):
        return prov.translation_switch_capability(show, current_ttype, target_ttype)

    audio_mode = getattr(prov, "audio_mode", "separate_catalogs")
    p_name = getattr(prov, "name", str(provider_id).title())
    if audio_mode == "embedded_multi_audio":
        return False, "Multi-audio embedded in stream. Switch audio inside player (# in mpv)."
    if audio_mode == "sub_only":
        return False, f"Releases are sub-only on {p_name}."
    return True, None
