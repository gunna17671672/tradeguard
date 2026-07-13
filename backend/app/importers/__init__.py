"""Broker importers. Register new brokers here; one module per broker."""

from __future__ import annotations

from app.importers.base import BaseImporter, ColumnMapping, ImporterError
from app.importers.generic import GenericCsvImporter
from app.importers.webull import WebullImporter

MAPPING_FIELDS = frozenset(
    {"symbol", "side", "qty", "price", "executed_at", "fees", "account_label"}
)


def mapping_kwargs_from_config(config: dict[str, object]) -> dict[str, object]:
    """Generic-importer kwargs from a user mapping config (CLI JSON file or
    API form field): column names plus optional datetime_format/timezone."""
    try:
        mapping = ColumnMapping(**{k: v for k, v in config.items() if k in MAPPING_FIELDS})
    except TypeError as exc:
        raise ImporterError(f"invalid column mapping: {exc}") from exc
    kwargs: dict[str, object] = {"mapping": mapping}
    if "datetime_format" in config:
        kwargs["datetime_format"] = config["datetime_format"]
    if "timezone" in config:
        kwargs["timezone"] = config["timezone"]
    return kwargs


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
