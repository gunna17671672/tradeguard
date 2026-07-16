"""Imports API: multipart CSV upload -> parse, ingest, audit, batch summary."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.api.deps import RulesConfigDep, SessionDep
from app.importers import (
    available_brokers,
    get_importer,
    mapping_kwargs_from_config,
)
from app.importers.base import ImporterError
from app.ingest import import_fills
from app.schemas import ImportResponse

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _importer_kwargs(broker: str, mapping: str | None) -> dict[str, object]:
    if mapping is None:
        return {}
    if broker != "generic":
        raise HTTPException(422, detail="a column mapping is only supported with broker=generic")
    try:
        config = json.loads(mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, detail=f"mapping is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise HTTPException(422, detail="mapping must be a JSON object of field -> column name")
    return config


def _validated_timezone(export_timezone: str) -> str:
    try:
        ZoneInfo(export_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(
            422,
            detail=f"unknown export_timezone {export_timezone!r}; "
            "use an IANA name like 'America/New_York'",
        ) from exc
    return export_timezone


@router.post("", status_code=201)
def create_import(
    session: SessionDep,
    rules_config: RulesConfigDep,
    file: UploadFile,
    broker: Annotated[str, Form()],
    mapping: Annotated[str | None, Form()] = None,
    export_timezone: Annotated[str | None, Form()] = None,
) -> ImportResponse:
    """`export_timezone`: IANA zone the export's zone-less timestamps are in.

    Webull writes timestamps in the exporting device's local timezone, so a
    trader outside Eastern time must pass their device's zone here. Omitted:
    the importer's own default applies (Webull assumes America/New_York;
    generic assumes UTC unless the mapping says otherwise).
    """
    if broker not in available_brokers():
        raise HTTPException(
            422, detail=f"unknown broker {broker!r}; available: {', '.join(available_brokers())}"
        )
    mapping_config = _importer_kwargs(broker, mapping)
    if export_timezone is not None:
        if "timezone" in mapping_config:
            raise HTTPException(
                422,
                detail="timezone given twice: drop export_timezone or the mapping's timezone key",
            )
        export_timezone = _validated_timezone(export_timezone)

    # Importers parse from a path; keep the client's filename so parse errors
    # ("orders.csv: missing expected column ...") name the file the user sent.
    filename = Path(file.filename or "upload.csv").name
    with tempfile.TemporaryDirectory(prefix="tradeguard_import_") as tmp_dir:
        target = Path(tmp_dir) / filename
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            kwargs = mapping_kwargs_from_config(mapping_config) if mapping_config else {}
            if export_timezone is not None:
                kwargs["timezone"] = export_timezone
            importer = get_importer(broker, **kwargs)
            fills = importer.parse(target)
        except ImporterError as exc:
            raise HTTPException(422, detail=str(exc)) from exc

    result = import_fills(
        session, fills, broker=broker, filename=filename, rules_config=rules_config
    )
    return ImportResponse(
        batch_id=result.batch_id,
        broker=broker,
        filename=filename,
        inserted=result.inserted,
        skipped_duplicates=result.skipped_duplicates,
        skipped_unfilled=importer.skipped_unfilled,
        trades_rebuilt=result.trades_rebuilt,
        violations_recorded=result.violations_recorded,
        audited=rules_config is not None,
    )
