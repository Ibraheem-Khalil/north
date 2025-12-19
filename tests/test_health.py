import os
import unittest

from fastapi.testclient import TestClient

# Minimal env so app startup doesn't fail validation
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DISABLE_AUTH_VERIFICATION", "true")

from api import app


class TestHealthAndRoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_root_ok(self) -> None:
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("status", res.json())

    def test_health_ok(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "healthy")


if __name__ == "__main__":
    unittest.main()
