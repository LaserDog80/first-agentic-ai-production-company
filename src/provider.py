# src/provider.py
"""Config-driven OpenAI-compatible client factory."""
import os
from pathlib import Path

import yaml
from openai import OpenAI


def load_config(config_path: str = "config.yaml") -> dict:
    """Load YAML config file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(path) as f:
        return yaml.safe_load(f)


def get_model_name(config: dict, tier: str) -> str:
    """Get model name for a given tier (strong/research/utility)."""
    models = config["providers"]["primary"]["models"]
    if tier not in models:
        raise KeyError(f"Unknown model tier: {tier}. Available: {list(models.keys())}")
    return models[tier]


def create_client(config: dict) -> OpenAI:
    """Create an OpenAI client from config."""
    provider = config["providers"]["primary"]
    api_key_env = provider["api_key_env"]
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(
            f"API key not found. Set the {api_key_env} environment variable."
        )
    return OpenAI(base_url=provider["base_url"], api_key=api_key)
