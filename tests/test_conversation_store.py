import unittest
from datetime import datetime, timezone

from mariner_genai_dbx.conversation_store import InMemoryConversationStore
from mariner_genai_dbx.models import ConversationHistory, ConversationTurn


def turn(user_id, conversation_id, request_id):
    return ConversationTurn(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        created_at=datetime.now(timezone.utc),
        question="question",
        answer="answer",
    )


class ConversationStoreTests(unittest.TestCase):
    def test_history_is_bounded_isolated_and_expires(self):
        now = [100]
        store = InMemoryConversationStore(
            history_limit=1, ttl_seconds=60, clock=lambda: now[0]
        )
        history = ConversationHistory()
        history = store.save_turn(turn("user-a", "chat", "one"), history)
        store.save_turn(turn("user-a", "chat", "two"), history)

        self.assertEqual(store.load_history("user-a", "chat").turns[0].request_id, "two")
        self.assertEqual(store.load_history("user-b", "chat").turns, ())

        now[0] = 161
        self.assertEqual(store.load_history("user-a", "chat").turns, ())


if __name__ == "__main__":
    unittest.main()
