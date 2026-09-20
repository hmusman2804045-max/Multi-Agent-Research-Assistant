"""Research history routes.

Every operation delegates to `src.storage`, whose dual-key {user_id, session_id} filtering
is what actually enforces per-user isolation. The route supplies the user_id from the
verified JWT only - it is never taken from the request body or path.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_storage, require_identity
from src.api.schemas import (
    DeleteSessionResponse,
    HistoryDetailResponse,
    HistoryListItem,
    HistoryListResponse,
)
from src.auth import UserIdentity
from src.storage import ResearchStorage

router = APIRouter(prefix="/history", tags=["history"])


def _contradiction_count(fact_check) -> int:
    if not fact_check:
        return 0
    return len(fact_check.get("contradictions") or [])


@router.get("", response_model=HistoryListResponse)
def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    identity: UserIdentity = Depends(require_identity),
    storage: ResearchStorage = Depends(get_storage),
) -> HistoryListResponse:
    """List the authenticated user's saved research sessions, newest first."""
    sessions = storage.list_user_sessions(user_id=identity.user_id, limit=limit, skip=skip)
    return HistoryListResponse(
        sessions=[
            HistoryListItem(
                session_id=s.session_id,
                query=s.query,
                created_at=s.created_at.isoformat(),
                source_count=len(s.sources),
                contradiction_count=_contradiction_count(s.fact_check),
                is_fallback=bool((s.metadata or {}).get("is_fallback", False)),
            )
            for s in sessions
        ],
        total=storage.count_user_sessions(identity.user_id),
    )


@router.get("/{session_id}", response_model=HistoryDetailResponse)
def get_history_item(
    session_id: str,
    identity: UserIdentity = Depends(require_identity),
    storage: ResearchStorage = Depends(get_storage),
) -> HistoryDetailResponse:
    """Load one saved session.

    A session belonging to another user is indistinguishable from one that does not exist:
    the dual-key lookup simply returns nothing, and the caller gets 404 either way.
    """
    session = storage.get_session(user_id=identity.user_id, session_id=session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return HistoryDetailResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        query=session.query,
        plan=session.plan or [],
        report=session.report,
        sources=session.sources,
        summaries=session.summaries,
        fact_check=session.fact_check,
        metadata=session.metadata,
        created_at=session.created_at.isoformat(),
    )


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
def delete_history_item(
    session_id: str,
    identity: UserIdentity = Depends(require_identity),
    storage: ResearchStorage = Depends(get_storage),
) -> DeleteSessionResponse:
    """Delete one saved session belonging to the authenticated user."""
    deleted = storage.delete_session(user_id=identity.user_id, session_id=session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return DeleteSessionResponse(session_id=session_id, deleted=True)
