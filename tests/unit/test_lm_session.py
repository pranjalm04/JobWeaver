from __future__ import annotations

import unittest

from physicianx.llm.session import LMSession


class TestLMSession(unittest.TestCase):
    def test_messages_for_completion_order(self) -> None:
        s = LMSession(session_id="abc")
        s.add_system("sys")
        s.add_user("u1")
        s.add_assistant("a1")
        msgs = s.messages_for_completion()
        self.assertEqual(
            msgs,
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "u1"},
                {"role": "assistant", "content": "a1"},
            ],
        )

    def test_reset_clears_history(self) -> None:
        s = LMSession(session_id="x")
        s.add_user("u")
        s.reset()
        self.assertEqual(s.messages_for_completion(), [])


if __name__ == "__main__":
    unittest.main()
