"""Imports API: multipart CSV upload -> parse, ingest, audit, batch summary."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

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


@router.post("", status_code=201)
def create_import(
    session: SessionDep,
    rules_config: RulesConfigDep,
    file: UploadFile,
    broker: Annotated[str, Form()],
    mapping: Annotated[str | None, Form()] = None,
) -> ImportResponse:
    if broker not in available_brokers():
        raise HTTPException(
            422, detail=f"unknown broker {broker!r}; available: {', '.join(available_brokers())}"
        )
    mapping_config = _importer_kwargs(broker, mapping)

    # Importers parse from a path; keep the client's filename so parse errors
    # ("orders.csv: missing expected column ...") name the file the user sent.
    filename = Path(file.filename or "upload.csv").name
    with tempfile.TemporaryDirectory(prefix="tradeguard_import_") as tmp_dir:
        target = Path(tmp_dir) / filename
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            kwargs = mapping_kwargs_from_config(mapping_config) if mapping_config else {}
            fills = get_importer(broker, **kwargs).parse(target)
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
        trades_rebuilt=result.trades_rebuilt,
        violations_recorded=result.violations_recorded,
        audited=rules_config is not None,
    )
