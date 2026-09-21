"""Bounded, thread-safe conversation history for the Databricks test app."""

import time
from threading import Lock

from .models import ConversationHistory, ConversationTurn


class InMemoryConversationStore:
    def __init__(self, *, history_limit: int, ttl_seconds: int, clock=time.time):
        self._history_limit = history_limit
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._records: dict[tuple[str, str], dict] = {}
        self._lock = Lock()

    def load_history(self, user_id: str, conversation_id: str) -> ConversationHistory:
        key = (user_id, conversation_id)
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return ConversationHistory()
            if record["expires_at"] <= int(self._clock()):
                del self._records[key]
                return ConversationHistory()
            return record["history"]

    def save_turn(
        self,
        turn: ConversationTurn,
        prior_history: ConversationHistory,
    ) -> ConversationHistory:
        key = (turn.user_id, turn.conversation_id)
        with self._lock:
            current = self._records.get(key)
            history = current["history"] if current else prior_history
            turns_by_request = {item.request_id: item for item in history.turns}
            turns_by_request[turn.request_id] = turn
            turns = sorted(turns_by_request.values(), key=lambda item: item.created_at)
            updated = ConversationHistory(
                turns=tuple(turns[-self._history_limit :]),
                version=history.version + 1,
            )
            self._records[key] = {
                "history": updated,
                "expires_at": int(self._clock()) + self._ttl_seconds,
            }
            return updated


class ConversationPersistence:
    def __init__(self, store: InMemoryConversationStore):
        self._store = store

    def load_history(self, user_id: str, conversation_id: str) -> ConversationHistory:
        return self._store.load_history(user_id, conversation_id)

    def record_turn(
        self,
        turn: ConversationTurn,
        prior_history: ConversationHistory,
    ) -> ConversationHistory:
        return self._store.save_turn(turn, prior_history)
