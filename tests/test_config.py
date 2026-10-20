import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_and_secret():
    settings = Settings(nebius_api_key="test-secret")
    assert settings.nebius_base_url == "https://api.tokenfactory.us-central1.nebius.com/v1"
    assert settings.nebius_model == "nvidia/nemotron-3-super-120b-a12b"
    assert settings.nebius_api_key.get_secret_value() == "test-secret"


def test_rejects_non_https_base_url():
    with pytest.raises(ValidationError):
        Settings(nebius_base_url="http://example.com/v1")


def test_rejects_non_nebius_host_to_protect_api_key():
    with pytest.raises(ValidationError):
        Settings(nebius_base_url="https://attacker.example/v1")


def test_accepts_regional_nebius_token_factory_host():
    settings = Settings(nebius_base_url="https://api.tokenfactory.eu-north1.nebius.com/v1/")
    assert settings.nebius_base_url == "https://api.tokenfactory.eu-north1.nebius.com/v1"


def test_rejects_invalid_timeout():
    with pytest.raises(ValidationError):
        Settings(nebius_timeout_seconds=0)
