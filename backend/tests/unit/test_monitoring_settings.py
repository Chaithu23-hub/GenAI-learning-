import pytest
from pydantic import ValidationError

from legal_rag.infrastructure.settings import Settings


def test_monitoring_is_disabled_and_content_is_excluded_by_default():
    settings = Settings(_env_file=None)
    assert settings.langfuse_enabled is False
    assert settings.langfuse_capture_content is False


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"langfuse_public_key": "public"},
        {"langfuse_public_key": "public", "langfuse_secret_key": "secret"},
        {"langfuse_public_key": " ", "langfuse_secret_key": "secret"},
    ],
)
def test_enabled_monitoring_requires_explicit_destination_and_credentials(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, langfuse_enabled=True, **overrides)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/traces",
        "https://user:password@example.test",
        "https://example.test?token=secret",
        "https://example.test#secret",
        "not-a-url",
    ],
)
def test_monitoring_destination_rejects_credentials_and_non_http_urls(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, langfuse_base_url=url)


def test_enabled_monitoring_preserves_secret_types_and_private_representation():
    settings = Settings(
        _env_file=None,
        langfuse_enabled=True,
        langfuse_public_key="synthetic-public",
        langfuse_secret_key="synthetic-private",
        langfuse_base_url="https://langfuse.example.test",
    )
    assert settings.langfuse_secret_key.get_secret_value() == "synthetic-private"
    assert "synthetic-private" not in repr(settings)


@pytest.mark.parametrize(
    "overrides",
    [
        {"langfuse_max_content_chars": 0},
        {"langfuse_shutdown_timeout_seconds": 0},
        {"langfuse_timeout_seconds": 0},
        {"langfuse_environment": "a" * 65},
    ],
)
def test_monitoring_limits_are_validated(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)
