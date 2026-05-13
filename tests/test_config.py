"""Tests for the YAML config loader."""

from __future__ import annotations

from pathlib import Path

from lld.config import AppConfig


def test_load_default_config_files():
    cfg = AppConfig.load(Path(__file__).resolve().parents[1] / "config")
    assert cfg.workflow.name == "full_pipeline"
    assert cfg.models.provider in {"ollama", "llamacpp"}
    assert "implementation" in cfg.models.roles
    assert cfg.workflow.quality.min_review_score >= 1


def test_role_params_override_defaults():
    cfg = AppConfig.load(Path(__file__).resolve().parents[1] / "config")
    impl = cfg.models.for_role("implementation")
    assert impl["model"]
    # Implementation role pins low temperature.
    assert impl["temperature"] <= cfg.models.defaults.temperature
    assert impl["num_ctx"] >= cfg.models.defaults.num_ctx
