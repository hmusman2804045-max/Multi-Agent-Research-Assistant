"""Server-Sent Events route for a live research run.

`ResearchPipeline.run()` is a synchronous, multi-second call. It is executed on a worker
thread while its observability hooks push progress onto an asyncio queue that this
endpoint drains into an SSE stream. The pipeline itself is untouched by the streaming:
the hooks are read-only observers and the returned result is exactly what the CLI gets.

Works identically for authenticated users and for guests. Guests are still rate limited,
under their own scoped guest bucket, and simply do not persist to history.
"""

import asyncio
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.api.deps import get_guest_id, get_optional_identity, get_pipeline
from src.api.errors import describe_exception
from src.auth import UserIdentity
from src.logger import get_logger
from src.pipeline import PIPELINE_STEPS, ResearchPipeline, ResearchResult
from src.rate_limiter import QuotaStatus

logger = get_logger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

# Emitted as an SSE comment while a long step is still running, so intermediaries do not
# treat an idle connection as dead.
_HEARTBEAT_INTERVAL_SECONDS = 15.0


def _sse(event: str, data: Dict[str, Any]) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _serialize_result(result: ResearchResult, saved: bool) -> Dict[str, Any]:
    """Shape a completed ResearchResult for the web client.

    The token usage breakdown is forwarded without the `model` field: the UI reports time
    and tokens, but does not surface the underlying model's brand name.
    """
    usage = {k: v for k, v in (result.usage or {}).items() if k != "model"}

    return {
        "query": result.query,
        "session_id": result.session_id,
        "saved_to_history": saved,
        "is_fallback": result.is_fallback,
        "report": result.report,
        "sub_queries": result.sub_queries,
        "plan_rationale": result.plan_rationale,
        "sources": [
            {
                "index": idx,
                "title": src.get("title", "Untitled Source"),
                "url": src.get("url", ""),
                "excerpt": (src.get("content", "") or "")[:320],
                "matched_sub_query": src.get("matched_sub_query", ""),
            }
            for idx, src in enumerate(result.search_results, 1)
        ],
        "summaries": (
            [s.model_dump() for s in result.summary_output.sources]
            if result.summary_output else []
        ),
        "fact_check": (
            result.fact_check_output.model_dump() if result.fact_check_output else None
        ),
        "telemetry": {
            "planning_time_sec": result.planning_time_sec,
            "search_time_sec": result.search_time_sec,
            "summarization_time_sec": result.summarization_time_sec,
            "fact_check_time_sec": result.fact_check_time_sec,
            "synthesis_time_sec": result.synthesis_time_sec,
            "total_time_sec": result.total_time_sec,
            "usage": usage,
        },
        "quota": result.quota_status.model_dump() if result.quota_status else None,
    }


@router.get("/stream")
async def stream_research(
    request: Request,
    query: str = Query(..., description="The research question."),
    identity: Optional[UserIdentity] = Depends(get_optional_identity),
    guest_id: Optional[str] = Depends(get_guest_id),
    pipeline: ResearchPipeline = Depends(get_pipeline),
) -> StreamingResponse:
    """Run the 5-agent pipeline, emitting one SSE event as each step completes.

    Event sequence:
      accepted -> step(planning) -> step(searching) -> step(summarizing)
               -> step(fact_checking) -> step(writing) -> complete

    Failures that occur before any agent work (invalid query, personal daily cap, shared
    service-wide cap, burst limit) are raised as real HTTP status codes before the stream
    opens. A failure mid-run is delivered as a terminal `error` event carrying the same
    payload the equivalent HTTP error would have carried.
    """
    user_id = identity.user_id if identity else None
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def publish(item) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def on_accepted(quota: QuotaStatus) -> None:
        publish(("accepted", quota.model_dump()))

    def on_step_complete(step: str, index: int, elapsed: float, payload: Dict[str, Any]) -> None:
        publish(("step", {
            "step": step,
            "index": index,
            "total_steps": len(PIPELINE_STEPS),
            "status": "completed",
            "elapsed_sec": elapsed,
            "payload": payload,
        }))

    def worker() -> None:
        try:
            result = pipeline.run(
                query=query,
                user_id=user_id,
                session_id=None if user_id else guest_id,
                on_step_complete=on_step_complete,
                on_accepted=on_accepted,
            )
        except Exception as exc:  # translated below into HTTP status or SSE error event
            publish(("error", exc))
        else:
            publish(("complete", result))

    run_task = loop.run_in_executor(None, worker)

    # The rate-limit gate runs before any agent work, so the first queued item tells us
    # immediately whether the request was admitted. Rejections become real HTTP errors.
    first_kind, first_value = await queue.get()
    if first_kind == "error":
        http_status, payload = describe_exception(first_value)
        headers = {}
        if payload.get("retry_after_seconds"):
            headers["Retry-After"] = str(int(payload["retry_after_seconds"]))
        raise HTTPException(status_code=http_status, detail=payload, headers=headers or None)

    async def event_stream():
        yield _sse("accepted", {
            "steps": list(PIPELINE_STEPS),
            "authenticated": bool(user_id),
            "persisted": bool(user_id),
            "quota": first_value,
        })

        try:
            while True:
                if await request.is_disconnected():
                    logger.info("Client disconnected from research stream; run continues to completion.")
                    return
                try:
                    kind, value = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                if kind == "step":
                    yield _sse("step", value)
                elif kind == "complete":
                    yield _sse("complete", _serialize_result(value, saved=bool(user_id)))
                    return
                elif kind == "error":
                    _, payload = describe_exception(value)
                    yield _sse("error", payload)
                    return
        finally:
            await run_task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
