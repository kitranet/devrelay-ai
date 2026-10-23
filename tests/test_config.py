import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_and_secret(monkeypatch):
    for name in (
        "INFERENCE_PROVIDER", "NEBIUS_BASE_URL", "NEBIUS_MODEL", "NEBIUS_MAX_OUTPUT_TOKENS",
        "NEBIUS_MAX_PROMPT_TOKENS", "NEBIUS_MAX_IN_FLIGHT_REQUESTS", "NEBIUS_PLANNING_DISABLE_THINKING",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(nebius_api_key="test-secret", _env_file=None)
    assert settings.inference_provider == "mock"
    assert settings.nebius_base_url == "https://api.tokenfactory.nebius.com/v1"
    assert settings.nebius_model == "nvidia/Nemotron-3_5-Lightning"
    assert settings.nebius_max_output_tokens == 1024
    assert settings.nebius_max_prompt_tokens == 6000
    assert settings.nebius_max_in_flight_requests == 1
    assert settings.nebius_planning_disable_thinking is False
    assert settings.nebius_api_key.get_secret_value() == "test-secret"


def test_planning_thinking_control_is_configurable_and_opt_in(monkeypatch):
    monkeypatch.setenv("NEBIUS_PLANNING_DISABLE_THINKING", "true")
    assert Settings(_env_file=None).nebius_planning_disable_thinking is True


def test_invalid_paid_request_limits_are_rejected():
    with pytest.raises(ValidationError):
        Settings(nebius_max_output_tokens=0, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(nebius_max_prompt_tokens=100, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(nebius_max_in_flight_requests=0, _env_file=None)


def test_rejects_non_https_base_url():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nebius_base_url="http://example.com/v1")


def test_rejects_non_nebius_host_to_protect_api_key():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nebius_base_url="https://attacker.example/v1")


def test_accepts_regional_nebius_token_factory_host():
    settings = Settings(_env_file=None, nebius_base_url="https://api.tokenfactory.eu-north1.nebius.com/v1/")
    assert settings.nebius_base_url == "https://api.tokenfactory.eu-north1.nebius.com/v1"


def test_rejects_invalid_timeout():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nebius_timeout_seconds=0)
