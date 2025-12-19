import os
import unittest

from fastapi.testclient import TestClient

# Minimal env so app startup doesn't fail validation during tests
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DISABLE_AUTH_VERIFICATION", "true")

from api import app


class TestAuthRequired(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_chat_requires_auth(self) -> None:
        res = self.client.post("/api/chat", json={"message": "hello"})
        self.assertEqual(res.status_code, 401)

    def test_chat_with_files_requires_auth(self) -> None:
        res = self.client.post(
            "/api/chat/with-files",
            data={"message": "hello"},
            files={"files": ("test.txt", b"hello", "text/plain")},
        )
        self.assertEqual(res.status_code, 401)

    def test_chat_stream_requires_auth(self) -> None:
        res = self.client.post("/api/chat/stream", json={"message": "hello"})
        self.assertEqual(res.status_code, 401)
