"""Canonical Section 13 entry-processing routes."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from src.ai.pipeline import JournalEntryPipeline, PIPELINE_VERSION, RULESET_VERSION
from src.db.models.journal_entry import JournalEntry
from src.db.models.processing import EntryIdempotencyClaim, ProcessingJob
from src.db.models.processing_distributed import ProcessingJobClaim
from src.db.models.user import User
from src.db.session import SessionLocal, get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["entries"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso8601z(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _request_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _poll_path(job_id: str) -> str:
    return f"/api/v1/entry-jobs/{job_id}"


def _ack_payload(
    *,
    idempotency_key: str,
    job: ProcessingJob,
    status: str = "pending",
) -> dict[str, Any]:
    return {
        "result_type": "ack",
        "status": status,
        "idempotency_key": idempotency_key,
        "job_id": job.id,
        "processing_run_id": job.processing_run_id,
        "entry_id": job.entry_id,
        "poll_path": _poll_path(job.id),
        "retryable": True,
        "created_at_utc": _iso8601z(job.created_at),
        "updated_at_utc": _iso8601z(job.updated_at),
        "attempt_count": int(job.attempt_count or 0),
        "last_error_code": job.final_error_code,
    }


def _job_terminal_pointer(job: ProcessingJob, status: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "job_id": job.id,
        "entry_id": job.entry_id,
        "status": status,
        "poll_path": _poll_path(job.id),
        "terminal_result_hash": job.final_payload_hash,
    }


def _job_status_payload(job: ProcessingJob) -> dict[str, Any]:
    if job.status == "in_progress":
        return {
            "status": "in_progress",
            "job_id": job.id,
            "processing_run_id": job.processing_run_id,
            "entry_id": job.entry_id,
            "created_at_utc": _iso8601z(job.created_at),
            "updated_at_utc": _iso8601z(job.updated_at),
            "attempt_count": job.attempt_count,
            "last_error_code": job.final_error_code,
            "terminal_result": None,
            "terminal_result_pointer": _job_terminal_pointer(job, "pending"),
        }

    terminal_result = json.loads(job.result_json) if job.result_json else None
    if job.status == "succeeded":
        return {
            "status": "completed",
            "job_id": job.id,
            "processing_run_id": job.processing_run_id,
            "entry_id": job.entry_id,
            "created_at_utc": _iso8601z(job.created_at),
            "updated_at_utc": _iso8601z(job.updated_at),
            "attempt_count": job.attempt_count,
            "last_error_code": None,
            "terminal_result": terminal_result,
            "terminal_result_pointer": _job_terminal_pointer(job, "completed"),
        }

    if terminal_result is None:
        terminal_result = {
            "status": "failed",
            "errors": [
                {
                    "code": job.final_error_code or "ENTRY_PIPELINE_FAILED",
                    "retryable": False,
                }
            ],
        }
    return {
        "status": "failed_terminal",
        "job_id": job.id,
        "processing_run_id": job.processing_run_id,
        "entry_id": job.entry_id,
        "created_at_utc": _iso8601z(job.created_at),
        "updated_at_utc": _iso8601z(job.updated_at),
        "attempt_count": job.attempt_count,
        "last_error_code": job.final_error_code,
        "terminal_result": terminal_result,
        "terminal_result_pointer": _job_terminal_pointer(job, "failed_terminal"),
    }


class ProcessEntryRequest(BaseModel):
    user_id: str
    content: str = Field(..., min_length=1, max_length=50_000)
    content_type: Literal["text", "audio_transcript"] = "text"
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    processing_mode: Literal["auto", "sync", "async"] = "auto"
    attachment_refs: Optional[list[str]] = None
    question_state: Optional[dict[str, Any]] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("content must not be empty")
        return trimmed

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("idempotency_key must not be empty")
        return trimmed


class EntryProcessingAckResult(BaseModel):
    result_type: Literal["ack"] = "ack"
    status: str
    idempotency_key: str
    job_id: str
    processing_run_id: str
    entry_id: str
    poll_path: str
    retryable: bool
    created_at_utc: Optional[str]
    updated_at_utc: Optional[str]
    attempt_count: int
    last_error_code: Optional[str]


class EntryJobStatusResponse(BaseModel):
    status: str
    job_id: str
    processing_run_id: str
    entry_id: str
    created_at_utc: Optional[str]
    updated_at_utc: Optional[str]
    attempt_count: int
    last_error_code: Optional[str]
    terminal_result: Optional[dict[str, Any]]
    terminal_result_pointer: dict[str, Any]


def _resolve_processing_mode(payload: ProcessEntryRequest) -> Literal["sync", "async"]:
    if payload.processing_mode in ("sync", "async"):
        return payload.processing_mode
    if payload.content_type != "text":
        return "async"
    return "sync" if len(payload.content) <= 4_000 else "async"


async def _process_reserved_entry_background(
    entry_id: str,
    user_id: str,
    idempotency_key: str,
    job_id: str,
    processing_run_id: str,
    request_payload_hash: str,
) -> None:
    db: Session = SessionLocal()
    try:
        pipeline = JournalEntryPipeline(db_session=db)
        result = await pipeline.process_entry(
            entry_id,
            user_id,
            idempotency_key=idempotency_key,
            job_id=job_id,
            processing_run_id=processing_run_id,
            reserved_claim=True,
            request_payload_hash=request_payload_hash,
        )
        logger.info(
            "Canonical entry pipeline completed job=%s entry=%s status=%s",
            job_id,
            entry_id,
            result.get("status"),
        )
    except Exception:
        logger.exception(
            "Canonical entry pipeline failed job=%s entry=%s", job_id, entry_id
        )
    finally:
        db.close()


def _reserve_entry_job(
    payload: ProcessEntryRequest,
    db: Session,
) -> tuple[ProcessingJob, str]:
    user_exists = db.query(User.id).filter(User.id == payload.user_id).first()
    if user_exists is None:
        raise HTTPException(status_code=404, detail=f"User {payload.user_id!r} not found")

    now = _now_utc()
    processing_run_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    entry_id = str(uuid.uuid4())
    normalized_request = {
        "user_id": payload.user_id,
        "content": payload.content,
        "content_type": payload.content_type,
        "idempotency_key": payload.idempotency_key,
        "processing_mode": payload.processing_mode,
        "attachment_refs": payload.attachment_refs or [],
        "question_state": payload.question_state or {},
    }
    request_hash = _request_payload_hash(normalized_request)

    entry_type = "audio" if payload.content_type == "audio_transcript" else payload.content_type

    entry = JournalEntry(
        id=entry_id,
        user_id=payload.user_id,
        content=payload.content,
        entry_type=entry_type,
        status="processing",
        question_state="none",
    )
    job = ProcessingJob(
        id=job_id,
        user_id=payload.user_id,
        entry_id=entry_id,
        step_name="entry_pipeline",
        processing_run_id=processing_run_id,
        status="in_progress",
        attempt_count=0,
        request_payload_hash=request_hash,
        pipeline_version=PIPELINE_VERSION,
        ruleset_version=RULESET_VERSION,
        ai_version_snapshot=json.dumps({}),
        prompt_version_snapshot=json.dumps({}),
    )
    ack = _ack_payload(idempotency_key=payload.idempotency_key, job=job)

    db.add(entry)
    db.add(job)
    db.flush()
    db.add(
        ProcessingJobClaim(
            user_id=payload.user_id,
            entry_id=entry_id,
            step_name="entry_pipeline",
            owner_kind="server_worker",
            owner_id="api",
            lease_token=str(uuid.uuid4()),
            claimed_at=now,
            lease_expires_at=now + timedelta(minutes=5),
            heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        EntryIdempotencyClaim(
            user_id=payload.user_id,
            idempotency_key=payload.idempotency_key,
            request_payload_hash=request_hash,
            entry_id=entry_id,
            processing_job_id=job_id,
            processing_run_id=processing_run_id,
            result_pointer_json=json.dumps(ack, sort_keys=True),
            status="in_progress",
            claimed_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return job, request_hash


@router.post("/entries", response_model=None)
async def process_entry(
    payload: ProcessEntryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    claim = (
        db.query(EntryIdempotencyClaim)
        .filter(
            EntryIdempotencyClaim.user_id == payload.user_id,
            EntryIdempotencyClaim.idempotency_key == payload.idempotency_key,
        )
        .one_or_none()
    )
    if claim is not None:
        job = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.id == claim.processing_job_id,
                ProcessingJob.user_id == payload.user_id,
            )
            .one_or_none()
        )
        if job is None:
            raise HTTPException(status_code=409, detail="Idempotency claim has no job")
        if job.status == "succeeded" and job.result_json:
            replay = json.loads(job.result_json)
            replay["replayed"] = True
            replay["idempotency_key"] = payload.idempotency_key
            return JSONResponse(status_code=200, content=replay)
        if job.status == "failed" and job.result_json:
            replay = json.loads(job.result_json)
            replay["replayed"] = True
            replay["idempotency_key"] = payload.idempotency_key
            return JSONResponse(status_code=200, content=replay)
        replay = _ack_payload(
            idempotency_key=payload.idempotency_key,
            job=job,
            status="pending",
        )
        replay["replayed"] = True
        return JSONResponse(status_code=202, content=replay)

    resolved_mode = _resolve_processing_mode(payload)
    job, request_hash = _reserve_entry_job(payload, db)

    if resolved_mode == "sync":
        pipeline = JournalEntryPipeline(db_session=db)
        try:
            result = await pipeline.process_entry(
                job.entry_id,
                payload.user_id,
                idempotency_key=payload.idempotency_key,
                job_id=job.id,
                processing_run_id=job.processing_run_id,
                reserved_claim=True,
                request_payload_hash=request_hash,
            )
            return JSONResponse(status_code=200, content=result)
        except Exception:
            db.expire_all()
            refreshed_job = (
                db.query(ProcessingJob)
                .filter(
                    ProcessingJob.id == job.id,
                    ProcessingJob.user_id == payload.user_id,
                )
                .one_or_none()
            )
            if refreshed_job is not None and refreshed_job.result_json:
                return JSONResponse(
                    status_code=200,
                    content=json.loads(refreshed_job.result_json),
                )
            raise

    background_tasks.add_task(
        _process_reserved_entry_background,
        job.entry_id,
        payload.user_id,
        payload.idempotency_key,
        job.id,
        job.processing_run_id,
        request_hash,
    )
    return JSONResponse(
        status_code=202,
        content=_ack_payload(idempotency_key=payload.idempotency_key, job=job),
    )


@router.get("/entry-jobs/{job_id}", response_model=EntryJobStatusResponse)
def get_entry_job(
    job_id: str,
    user_id: str = Query(..., description="User UUID"),
    db: Session = Depends(get_db),
) -> EntryJobStatusResponse:
    job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == user_id,
        )
        .one_or_none()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return EntryJobStatusResponse(**_job_status_payload(job))
