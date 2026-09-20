"""Per-User Isolated Storage Module (Phase 5).

Implements strictly isolated MongoDB persistence with mandatory dual-key query filtering:
{"user_id": user_id, "session_id": session_id}

Features:
- Enforces compound unique index [("user_id", 1), ("session_id", 1)]
- Secondary index on [("user_id", 1), ("created_at", -1)]
- Automatic graceful fallback to mongomock when live MongoDB is not configured
- Zero cross-user data leakage by architectural enforcement
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid
import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
import mongomock
from pydantic import BaseModel, Field, field_validator

from src.config import settings
from src.logger import get_logger

logger = get_logger(__name__)


def _sanitize_key(key: str, field_name: str) -> str:
    """Validate and sanitize key strings used in database queries."""
    if not isinstance(key, str):
        raise ValueError(f"{field_name} must be a string")
    clean = key.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty or only whitespace")
    if any(c in clean for c in ["\0", "$", "\n", "\r"]):
        raise ValueError(f"{field_name} contains prohibited characters")
    return clean


class ResearchSessionDocument(BaseModel):
    """Schema for a persisted research session document."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(...)
    query: str = Field(...)
    plan: Optional[List[str]] = Field(default=None)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    summaries: List[Dict[str, Any]] = Field(default_factory=list)
    fact_check: Optional[Dict[str, Any]] = Field(default=None)
    report: str = Field(default="")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("user_id")
    @classmethod
    def validate_user(cls, v: str) -> str:
        return _sanitize_key(v, "user_id")

    @field_validator("session_id")
    @classmethod
    def validate_session(cls, v: str) -> str:
        return _sanitize_key(v, "session_id")


class UserAccountDocument(BaseModel):
    """Schema for a persisted user account with hashed password."""
    user_id: str = Field(...)
    email: Optional[str] = Field(default=None)
    password_hash: str = Field(...)
    salt: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("user_id")
    @classmethod
    def validate_user(cls, v: str) -> str:
        return _sanitize_key(v, "user_id")


class ResearchStorage:
    """Database client wrapper ensuring strict per-user dual-key isolation."""

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        db_name: Optional[str] = None,
        force_mock: bool = False,
    ) -> None:
        self.uri = mongodb_uri if mongodb_uri is not None else settings.mongodb_uri
        self.db_name = db_name if db_name is not None else settings.mongodb_db_name
        self.is_mock = force_mock or not bool(self.uri.strip())

        if self.is_mock:
            logger.info("Initializing in-memory MongoMock storage client for Phase 5.")
            self.client: MongoClient = mongomock.MongoClient()
        else:
            logger.info(f"Connecting to live MongoDB database: '{self.db_name}'...")
            try:
                self.client = MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=3000,
                )
                # Quick ping to verify connectivity
                self.client.admin.command("ping")
                logger.info("Successfully connected to live MongoDB.")
            except Exception as e:
                logger.warning(
                    f"Could not connect to live MongoDB ({e}). Falling back to MongoMock."
                )
                self.is_mock = True
                self.client = mongomock.MongoClient()

        self.db: Database = self.client[self.db_name]
        self.sessions_col: Collection = self.db["research_sessions"]
        self.users_col: Collection = self.db["users"]
        self.rate_limits_col: Collection = self.db["rate_limits"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create required indexes for dual-key querying, user lookup, and performance."""
        try:
            # Compound unique index: user_id + session_id (PRD Lesson 5)
            self.sessions_col.create_index(
                [("user_id", pymongo.ASCENDING), ("session_id", pymongo.ASCENDING)],
                unique=True,
                name="idx_user_session_unique",
            )
            # Secondary index for chronological session history per user
            self.sessions_col.create_index(
                [("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
                name="idx_user_created_at",
            )
            # Unique index on user_id for users collection
            self.users_col.create_index(
                [("user_id", pymongo.ASCENDING)],
                unique=True,
                name="idx_users_user_id_unique",
            )
            # Unique index on user_id for rate limits collection
            self.rate_limits_col.create_index(
                [("user_id", pymongo.ASCENDING)],
                unique=True,
                name="idx_rate_limits_user_id_unique",
            )
            logger.debug("MongoDB indexes initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not create indexes on storage collection: {e}")

    def save_user(self, user: UserAccountDocument) -> str:
        """Persist a registered user account."""
        user_id = _sanitize_key(user.user_id, "user_id")
        doc = user.model_dump()
        self.users_col.update_one(
            {"user_id": user_id},
            {"$set": doc},
            upsert=True,
        )
        logger.info(f"Saved user account for '{user_id}'.")
        return user_id

    def get_user(self, user_id: str) -> Optional[UserAccountDocument]:
        """Retrieve a user account by user_id."""
        clean_user = _sanitize_key(user_id, "user_id")
        doc = self.users_col.find_one({"user_id": clean_user})
        if not doc:
            return None
        doc.pop("_id", None)
        return UserAccountDocument(**doc)

    def user_exists(self, user_id: str) -> bool:
        """Check if a user account already exists."""
        clean_user = _sanitize_key(user_id, "user_id")
        return self.users_col.count_documents({"user_id": clean_user}) > 0

    def get_rate_limit_record(self, user_id: str) -> Dict[str, Any]:
        """Retrieve or initialize rate limit document for a user."""
        clean_user = _sanitize_key(user_id, "user_id")
        doc = self.rate_limits_col.find_one({"user_id": clean_user})
        if not doc:
            return {
                "user_id": clean_user,
                "daily_date": "",
                "daily_count": 0,
                "minute_timestamps": [],
                "failed_login_attempts": 0,
                "lockout_until": None,
            }
        doc.pop("_id", None)
        return doc

    def save_rate_limit_record(self, user_id: str, record: Dict[str, Any]) -> None:
        """Persist updated rate limit document for a user."""
        clean_user = _sanitize_key(user_id, "user_id")
        record["user_id"] = clean_user
        record["updated_at"] = datetime.now(timezone.utc)
        self.rate_limits_col.update_one(
            {"user_id": clean_user},
            {"$set": record},
            upsert=True,
        )

    def atomic_check_and_consume_quota(
        self,
        user_id: str,
        daily_limit: int,
        rpm_limit: int,
        now_dt: datetime,
    ) -> Tuple[bool, Optional[str], Dict[str, Any], int]:
        """Atomically evaluate rate limits and consume one allocation using MongoDB atomic operators.

        Protects against race conditions across concurrent requests/threads/workers.

        Args:
            user_id: The target user identifier.
            daily_limit: Maximum allowed queries per day.
            rpm_limit: Maximum allowed requests per minute.
            now_dt: Current UTC datetime.

        Returns:
            Tuple of (success: bool, error_type: Optional[str], record: Dict[str, Any], retry_after: int)
            error_type is 'rpm', 'daily', or None.
        """
        clean_user = _sanitize_key(user_id, "user_id")
        now_ts = now_dt.timestamp()
        today_str = now_dt.strftime("%Y-%m-%d")

        # 1. Ensure record document exists
        self.rate_limits_col.update_one(
            {"user_id": clean_user},
            {
                "$setOnInsert": {
                    "user_id": clean_user,
                    "daily_date": today_str,
                    "daily_count": 0,
                    "minute_timestamps": [],
                    "failed_login_attempts": 0,
                    "lockout_until": None,
                }
            },
            upsert=True,
        )

        # 2. Reset daily counter if a new UTC day has started
        self.rate_limits_col.update_one(
            {"user_id": clean_user, "daily_date": {"$ne": today_str}},
            {
                "$set": {
                    "daily_date": today_str,
                    "daily_count": 0,
                    "minute_timestamps": [],
                    "updated_at": now_dt,
                }
            },
        )

        # 3. Retrieve current record to inspect RPM timestamps window
        rec = self.rate_limits_col.find_one({"user_id": clean_user})
        raw_ts: List[float] = rec.get("minute_timestamps", []) if rec else []
        recent_ts = [t for t in raw_ts if (now_ts - t) < 60.0]

        # 4. Check RPM burst limit
        if len(recent_ts) >= rpm_limit:
            oldest = min(recent_ts) if recent_ts else now_ts
            retry_after = max(1, int(60.0 - (now_ts - oldest)))
            return False, "rpm", rec or {}, retry_after

        # 5. Check Daily quota limit
        current_daily = int(rec.get("daily_count", 0)) if rec and rec.get("daily_date") == today_str else 0
        if current_daily >= daily_limit:
            tomorrow = (now_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            secs_to_reset = max(1, int((tomorrow - now_dt).total_seconds()))
            return False, "daily", rec or {}, secs_to_reset

        # 6. Atomic increment and timestamp append with concurrency guard filter
        updated_doc = self.rate_limits_col.find_one_and_update(
            {
                "user_id": clean_user,
                "daily_date": today_str,
                "daily_count": {"$lt": daily_limit},
            },
            {
                "$inc": {"daily_count": 1},
                "$set": {
                    "minute_timestamps": recent_ts + [now_ts],
                    "updated_at": now_dt,
                },
            },
            return_document=pymongo.ReturnDocument.AFTER,
        )

        if not updated_doc:
            # Concurrency race: another thread consumed the final available slot
            rec = self.rate_limits_col.find_one({"user_id": clean_user})
            tomorrow = (now_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            secs_to_reset = max(1, int((tomorrow - now_dt).total_seconds()))
            return False, "daily", rec or {}, secs_to_reset

        updated_doc.pop("_id", None)
        return True, None, updated_doc, 0

    def save_session(self, session: ResearchSessionDocument) -> str:
        """Persist or update a research session document using dual-key filtering.

        Args:
            session: The ResearchSessionDocument to store.

        Returns:
            The session_id string.
        """
        user_id = _sanitize_key(session.user_id, "user_id")
        session_id = _sanitize_key(session.session_id, "session_id")

        doc = session.model_dump()
        doc["updated_at"] = datetime.now(timezone.utc)

        # Dual-key query filter
        filter_query = {"user_id": user_id, "session_id": session_id}

        self.sessions_col.update_one(
            filter_query,
            {"$set": doc},
            upsert=True,
        )
        logger.info(f"Saved research session '{session_id}' for user '{user_id}'.")
        return session_id

    def get_session(self, user_id: str, session_id: str) -> Optional[ResearchSessionDocument]:
        """Retrieve a session strictly filtered by both user_id and session_id.

        Args:
            user_id: The authenticated user's ID.
            session_id: The target session ID.

        Returns:
            ResearchSessionDocument if found, None otherwise.
        """
        clean_user = _sanitize_key(user_id, "user_id")
        clean_session = _sanitize_key(session_id, "session_id")

        # Strict dual-key filter
        filter_query = {"user_id": clean_user, "session_id": clean_session}
        doc = self.sessions_col.find_one(filter_query)

        if not doc:
            logger.debug(f"No session found for user '{clean_user}' with session_id '{clean_session}'.")
            return None

        doc.pop("_id", None)
        return ResearchSessionDocument(**doc)

    def list_user_sessions(
        self,
        user_id: str,
        limit: int = 20,
        skip: int = 0,
    ) -> List[ResearchSessionDocument]:
        """List all research sessions belonging to a specific user.

        Args:
            user_id: The authenticated user's ID.
            limit: Maximum number of sessions to return.
            skip: Number of sessions to skip (for pagination).

        Returns:
            List of ResearchSessionDocument objects ordered by created_at DESC.
        """
        clean_user = _sanitize_key(user_id, "user_id")
        filter_query = {"user_id": clean_user}

        cursor = (
            self.sessions_col.find(filter_query)
            .sort("created_at", pymongo.DESCENDING)
            .skip(max(0, skip))
            .limit(max(1, limit))
        )

        results: List[ResearchSessionDocument] = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(ResearchSessionDocument(**doc))

        return results

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """Delete a research session strictly filtered by both user_id and session_id.

        Args:
            user_id: The authenticated user's ID.
            session_id: The target session ID to delete.

        Returns:
            True if a document was deleted, False otherwise.
        """
        clean_user = _sanitize_key(user_id, "user_id")
        clean_session = _sanitize_key(session_id, "session_id")

        # Strict dual-key filter
        filter_query = {"user_id": clean_user, "session_id": clean_session}
        result = self.sessions_col.delete_one(filter_query)

        deleted = result.deleted_count > 0
        if deleted:
            logger.info(f"Deleted session '{clean_session}' for user '{clean_user}'.")
        else:
            logger.warning(
                f"Delete session failed: Session '{clean_session}' not found for user '{clean_user}'."
            )
        return deleted

    def count_user_sessions(self, user_id: str) -> int:
        """Count total sessions owned by a specific user.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Integer count of sessions.
        """
        clean_user = _sanitize_key(user_id, "user_id")
        return self.sessions_col.count_documents({"user_id": clean_user})
