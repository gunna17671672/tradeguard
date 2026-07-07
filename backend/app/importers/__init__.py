"""Broker importers. Register new brokers here; one module per broker."""

from __future__ import annotations

from app.importers.base import BaseImporter, ImporterError
from app.importers.generic import GenericCsvImporter
from app.importers.webull import WebullImporter

_REGISTRY: dict[str, type[BaseImporter]] = {
    "webull": WebullImporter,
    "generic": GenericCsvImporter,
}


def available_brokers() -> list[str]:
    return sorted(_REGISTRY)


def get_importer(broker: str, **kwargs: object) -> BaseImporter:
    try:
        cls = _REGISTRY[broker]
    except KeyError:
        raise ImporterError(
            f"unknown broker {broker!r}; available: {', '.join(available_brokers())}"
        ) from None
    return cls(**kwargs)  # type: ignore[arg-type]
