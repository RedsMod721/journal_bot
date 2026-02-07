"""
Tests for FastAPI main application endpoints.

These tests cover:
- Root endpoint (/)
- Health check endpoint (/health)
- check_ollama_connection function (with various scenarios)
"""
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, check_ollama_connection


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestRootEndpoint:
    """Tests for the root (/) endpoint."""

    def test_root_returns_welcome_message(self, client):
        """Root endpoint should return welcome message."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Status Window API" in data["message"]

    def test_root_contains_expected_keys(self, client):
        """Root endpoint should contain expected keys."""
        response = client.get("/")
        data = response.json()
        expected_keys = {"message", "tagline", "docs", "redoc", "health", "status"}
        assert set(data.keys()) == expected_keys

    def test_root_status_is_operational(self, client):
        """Root endpoint should indicate operational status."""
        response = client.get("/")
        data = response.json()
        assert data["status"] == "operational"


class TestHealthEndpoint:
    """Tests for the health check (/health) endpoint."""

    @patch("app.main.check_ollama_connection")
    def test_health_healthy_when_ollama_connected(self, mock_ollama, client):
        """Health endpoint should return healthy when Ollama is connected."""
        mock_ollama.return_value = {
            "connected": True,
            "host": "http://localhost:11434",
            "models_available": 1,
            "preferred_model": "llama3.2",
            "preferred_model_available": True,
            "available_models": ["llama3.2"],
        }
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "ollama" in data
        assert data["ollama"]["connected"] is True

    @patch("app.main.check_ollama_connection")
    def test_health_degraded_when_ollama_not_connected(self, mock_ollama, client):
        """Health endpoint should return degraded when Ollama is not connected."""
        mock_ollama.return_value = {
            "connected": False,
            "error": "Connection refused",
            "solution": "Make sure Ollama is running",
        }
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["ollama"]["connected"] is False

    @patch("app.main.check_ollama_connection")
    def test_health_includes_api_version(self, mock_ollama, client):
        """Health endpoint should include API version."""
        mock_ollama.return_value = {"connected": True}
        response = client.get("/health")
        data = response.json()
        assert "api_version" in data

    @patch("app.main.check_ollama_connection")
    def test_health_includes_database_status(self, mock_ollama, client):
        """Health endpoint should include database status."""
        mock_ollama.return_value = {"connected": True}
        response = client.get("/health")
        data = response.json()
        assert "database" in data
        assert "status" in data["database"]


class TestCheckOllamaConnection:
    """Tests for the check_ollama_connection function."""

    def test_ollama_connected_successfully(self):
        """Should return connected status when Ollama is accessible."""
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"model": "codellama:7b"},
            ]
        }

        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = check_ollama_connection()

        assert result["connected"] is True
        assert result["models_available"] == 2
        assert "llama3.2:latest" in result["available_models"]
        assert "codellama:7b" in result["available_models"]

    def test_ollama_preferred_model_available(self):
        """Should indicate when preferred model is available."""
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {
            "models": [{"name": "llama3.2:latest"}]
        }

        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = check_ollama_connection()

        assert result["connected"] is True
        assert result["preferred_model_available"] is True

    def test_ollama_preferred_model_not_available(self):
        """Should indicate when preferred model is not available."""
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {
            "models": [{"name": "codellama:7b"}]
        }

        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = check_ollama_connection()

        assert result["connected"] is True
        assert result["preferred_model_available"] is False

    def test_ollama_empty_models_list(self):
        """Should handle empty models list."""
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = check_ollama_connection()

        assert result["connected"] is True
        assert result["models_available"] == 0
        assert result["available_models"] == []

    def test_ollama_import_error(self):
        """Should handle ImportError when ollama is not installed."""
        # Remove ollama from sys.modules if present and make import fail
        with patch.dict(sys.modules, {"ollama": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'ollama'")):
                result = check_ollama_connection()

        assert result["connected"] is False
        assert "error" in result
        assert "not installed" in result["error"]
        assert "solution" in result

    def test_ollama_connection_exception(self):
        """Should handle connection exceptions."""
        mock_ollama = MagicMock()
        mock_ollama.list.side_effect = Exception("Connection refused")

        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = check_ollama_connection()

        assert result["connected"] is False
        assert "error" in result
        assert "Connection refused" in result["error"]
        assert "solution" in result

    def test_ollama_handles_missing_model_key(self):
        """Should handle models with neither 'name' nor 'model' key."""
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {
            "models": [{"size": 1000}]  # Missing both 'name' and 'model'
        }

        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            result = check_ollama_connection()

        assert result["connected"] is True
        assert "unknown" in result["available_models"]


class TestAppConfiguration:
    """Tests for FastAPI app configuration."""

    def test_app_has_correct_title(self):
        """App should have the correct title."""
        assert app.title == "Status Window API"

    def test_app_has_docs_url(self):
        """App should have docs URL configured."""
        assert app.docs_url == "/docs"

    def test_app_has_redoc_url(self):
        """App should have redoc URL configured."""
        assert app.redoc_url == "/redoc"

    def test_cors_middleware_configured(self):
        """App should have CORS middleware configured."""
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes
