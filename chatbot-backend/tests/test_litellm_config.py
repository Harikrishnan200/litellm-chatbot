"""Checks litellm/config.yaml: fallbacks point at real deployments and nothing is paid."""
from pathlib import Path

import yaml

CONFIG = yaml.safe_load((Path(__file__).parents[2] / "litellm" / "config.yaml").read_text())
NAMES = {m["model_name"] for m in CONFIG["model_list"]}


def test_every_fallback_exists():
    for rule in CONFIG["router_settings"]["fallbacks"]:
        for group, targets in rule.items():
            assert group in NAMES
            assert all(t in NAMES for t in targets)


def test_all_four_groups_and_three_providers_are_configured():
    assert {"coding-model", "research-model", "general-model", "reasoning-model"} <= NAMES
    providers = {m["litellm_params"]["model"].split("/")[0] for m in CONFIG["model_list"]} - {"auto_router"}
    assert providers == {"openrouter", "gemini", "groq"}


def test_openrouter_models_are_free_variants():
    for m in CONFIG["model_list"]:
        model = m["litellm_params"]["model"]
        if model.startswith("openrouter/"):
            assert model.endswith(":free"), f"{model} could be billed"


def test_guardrail_runs_on_every_request():
    guardrail = CONFIG["guardrails"][0]["litellm_params"]
    assert guardrail["mode"] == "pre_call" and guardrail["default_on"] is True
