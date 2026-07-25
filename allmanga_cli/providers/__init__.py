"""Streaming provider registry."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable


_SKIPPED_MODULES = {"shared"}
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
            factories[provider_id] = provider_class
    return factories


PROVIDER_FACTORIES = discover_provider_factories()
if _DEFAULT_PROVIDER_ID not in PROVIDER_FACTORIES:
    from .allanime import AllAnimeProvider

    PROVIDER_FACTORIES[_DEFAULT_PROVIDER_ID] = AllAnimeProvider

PROVIDERS = {
    provider_id: factory()
    for provider_id, factory in PROVIDER_FACTORIES.items()
}

ALLANIME = PROVIDERS[_DEFAULT_PROVIDER_ID]


def available_providers():
    return dict(PROVIDERS)


def provider_key(provider_id=_DEFAULT_PROVIDER_ID):
    key = str(provider_id or "").casefold()
    return key if key in PROVIDERS else _DEFAULT_PROVIDER_ID


def get_provider(provider_id=_DEFAULT_PROVIDER_ID, request_json_fn=None):
    key = provider_key(provider_id)
    if request_json_fn is None:
        return PROVIDERS[key]
    return PROVIDER_FACTORIES[key](request_json_fn)
