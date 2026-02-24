"""
Tests: Requirements & environment verification
"""
import importlib
import sys


class TestDependencies:
    """Verify all critical imports are resolvable."""

    def test_fastapi_importable(self):
        assert importlib.util.find_spec("fastapi") is not None

    def test_pydantic_importable(self):
        assert importlib.util.find_spec("pydantic") is not None

    def test_httpx_importable(self):
        assert importlib.util.find_spec("httpx") is not None

    def test_supabase_importable(self):
        assert importlib.util.find_spec("supabase") is not None

    def test_python_version(self):
        """Ensure Python 3.10+."""
        assert sys.version_info >= (3, 10), f"Need Python 3.10+, got {sys.version}"


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_ok_structure(self):
        """Health endpoint returns expected keys."""
        from unittest.mock import MagicMock, patch
        from fastapi.testclient import TestClient

        mock_result = MagicMock()
        mock_result.data = [{"now": "2024-01-01"}]

        with patch("db.supabase.get_supabase_client") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_result
            mock_sb.return_value = mock_client

            from main import app
            client = TestClient(app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
