# tests/test_provider.py
import os
import pytest
from unittest.mock import patch, MagicMock
from src.provider import load_config, create_client, get_model_name


def test_load_config():
    config = load_config("config.yaml")
    assert "providers" in config
    assert "primary" in config["providers"]
    assert "models" in config["providers"]["primary"]


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent.yaml")


def test_get_model_name():
    config = load_config("config.yaml")
    assert "Qwen3-235B" in get_model_name(config, "strong")
    # Research tier intentionally points at Qwen (same as strong) because
    # DeepSeek V3-0324 was removed from Nebius and V3.2 mis-emits tool calls.
    assert "Qwen" in get_model_name(config, "research")
    assert "Qwen3-30B" in get_model_name(config, "utility")


def test_get_model_name_invalid_tier():
    config = load_config("config.yaml")
    with pytest.raises(KeyError):
        get_model_name(config, "nonexistent")


@patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key-123"})
def test_create_client():
    config = load_config("config.yaml")
    client = create_client(config)
    assert client.api_key == "test-key-123"
    assert "tokenfactory.nebius.com" in str(client.base_url)


def test_create_client_missing_key():
    config = load_config("config.yaml")
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="API key"):
            create_client(config)
