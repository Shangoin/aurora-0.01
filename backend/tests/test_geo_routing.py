"""
Tests: Geo-routing logic — _get_phone_number_id(), _detect_geo_region()
Aurora 1.0 — ensures correct Vapi phone number and region selected per country code.
"""
import os
import pytest
from unittest.mock import patch


class TestDetectGeoRegion:
    """Tests for _detect_geo_region() country code → region mapping."""

    def test_india_prefix_detected(self):
        from ai.improvement import _detect_geo_region
        assert _detect_geo_region("+919876543210") == "india"
        assert _detect_geo_region("+91 98765 43210") == "india"

    def test_us_prefix_detected(self):
        from ai.improvement import _detect_geo_region
        assert _detect_geo_region("+15551234567") == "us"
        assert _detect_geo_region("+1 555 123 4567") == "us"

    def test_uk_prefix_detected(self):
        from ai.improvement import _detect_geo_region
        assert _detect_geo_region("+447911123456") == "uk"
        assert _detect_geo_region("+44 7911 123456") == "uk"

    def test_australia_prefix_maps_to_global(self):
        from ai.improvement import _detect_geo_region
        assert _detect_geo_region("+61412345678") == "global"

    def test_singapore_prefix_maps_to_global(self):
        from ai.improvement import _detect_geo_region
        assert _detect_geo_region("+6591234567") == "global"

    def test_unknown_prefix_maps_to_global(self):
        from ai.improvement import _detect_geo_region
        assert _detect_geo_region("+33612345678") == "global"  # France
        assert _detect_geo_region("") == "global"
        assert _detect_geo_region(None) == "global"


class TestGetPhoneNumberId:
    """Tests for _get_phone_number_id() — returns correct Vapi phone number env var."""

    def test_india_returns_in_number(self):
        with patch.dict(os.environ, {
            "VAPI_PHONE_NUMBER_ID_IN": "vapi-in-123",
            "VAPI_PHONE_NUMBER_ID": "vapi-fallback",
        }):
            from ai.improvement import _get_phone_number_id
            result = _get_phone_number_id("+919876543210")
            assert result == "vapi-in-123"

    def test_us_returns_us_number(self):
        with patch.dict(os.environ, {
            "VAPI_PHONE_NUMBER_ID_US": "vapi-us-456",
            "VAPI_PHONE_NUMBER_ID": "vapi-fallback",
        }):
            from ai.improvement import _get_phone_number_id
            result = _get_phone_number_id("+15551234567")
            assert result == "vapi-us-456"

    def test_uk_returns_uk_number(self):
        with patch.dict(os.environ, {
            "VAPI_PHONE_NUMBER_ID_UK": "vapi-uk-789",
            "VAPI_PHONE_NUMBER_ID": "vapi-fallback",
        }):
            from ai.improvement import _get_phone_number_id
            result = _get_phone_number_id("+447911123456")
            assert result == "vapi-uk-789"

    def test_global_prefix_returns_global_number(self):
        with patch.dict(os.environ, {
            "VAPI_PHONE_NUMBER_ID_GLOBAL": "vapi-global-101",
            "VAPI_PHONE_NUMBER_ID": "vapi-fallback",
        }):
            from ai.improvement import _get_phone_number_id
            result = _get_phone_number_id("+61412345678")
            assert result == "vapi-global-101"

    def test_missing_geo_number_falls_back_to_default(self):
        """When geo-specific env var is absent, fall back to VAPI_PHONE_NUMBER_ID."""
        env = {"VAPI_PHONE_NUMBER_ID": "vapi-fallback-only"}
        # Ensure geo vars are NOT set
        env_without_geo = {k: v for k, v in os.environ.items()
                           if k not in ("VAPI_PHONE_NUMBER_ID_IN", "VAPI_PHONE_NUMBER_ID_US",
                                        "VAPI_PHONE_NUMBER_ID_UK", "VAPI_PHONE_NUMBER_ID_GLOBAL")}
        env_without_geo["VAPI_PHONE_NUMBER_ID"] = "vapi-fallback-only"
        with patch.dict(os.environ, env_without_geo, clear=True):
            from ai.improvement import _get_phone_number_id
            result = _get_phone_number_id("+919876543210")
            assert result == "vapi-fallback-only"

    def test_trigger_call_passes_geo_region_in_metadata(self):
        """trigger_call includes geo_region in Vapi payload metadata."""
        import httpx
        from unittest.mock import AsyncMock, MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "call-geo-test"}
        mock_response.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"VAPI_PHONE_NUMBER_ID_IN": "vapi-in-xxx",
                                     "VAPI_API_KEY": "test-key",
                                     "VAPI_ASSISTANT_ID": "test-assistant"}), \
             patch("ai.improvement.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            import asyncio
            from ai.improvement import trigger_call
            asyncio.get_event_loop().run_until_complete(
                trigger_call(
                    phone_number="+919876543210",
                    lead_name="Priya S",
                    lead_email="priya@acme.in",
                    lead_company="Acme India",
                )
            )

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert payload.get("phoneNumberId") == "vapi-in-xxx"
        assert payload["call"]["metadata"]["geo_region"] == "india"
