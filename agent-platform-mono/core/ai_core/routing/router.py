from __future__ import annotations

from dataclasses import dataclass

from shared.config.settings import settings


@dataclass(frozen=True)
class ModelSpec:
    model: str
    task_type: str
    scene: str
    sensitive: bool = False


_CAPABILITY_SETTING_MAP: dict[str, str] = {
    "nano": "nano_model",
    "simple": "default_model",
    "medium": "medium_model",
    "complex": "strong_model",
    "local": "local_model",
}

_SCENE_ROUTING: dict[str, dict[str, str | bool]] = {
    "policy_query": {"capability": "simple", "sensitive": False},
    "policy_rag_rewrite": {"capability": "nano", "sensitive": False},
    "claim_reason": {"capability": "complex", "sensitive": False},
    "claim_doc_verify": {"capability": "medium", "sensitive": False},
    "claim_rag_rewrite": {"capability": "nano", "sensitive": False},
    "customer_faq": {"capability": "simple", "sensitive": False},
    "customer_intent": {"capability": "medium", "sensitive": False},
    "memory_summary": {"capability": "nano", "sensitive": False},
    "tool_select": {"capability": "medium", "sensitive": False},
    "plan_execute_step": {"capability": "complex", "sensitive": False},
    "plan_execute_summary": {"capability": "simple", "sensitive": False},
    "sensitive_reason": {"capability": "complex", "sensitive": True},
}

_TASK_TO_CAPABILITY: dict[str, str] = {
    "simple": "simple",
    "local": "local",
    "medium": "medium",
    "nano": "nano",
    "complex": "complex",
}


def _model_by_capability(capability: str) -> str:
    setting_name = _CAPABILITY_SETTING_MAP.get(capability, "strong_model")
    return str(getattr(settings.llm, setting_name, settings.llm.strong_model))


def select_model(
    task_type: str = "complex",
    *,
    scene: str | None = None,
    force_local: bool = False,
) -> ModelSpec:
    selected_scene = str(scene or task_type or "complex")
    rule = _SCENE_ROUTING.get(selected_scene)
    if rule is not None:
        capability = str(rule.get("capability", "complex"))
        sensitive = bool(rule.get("sensitive", False))
    else:
        capability = _TASK_TO_CAPABILITY.get(str(task_type), "complex")
        sensitive = capability == "local"
    if force_local or sensitive:
        model = _model_by_capability("local")
        return ModelSpec(model=model, task_type="local", scene=selected_scene, sensitive=True)
    model = _model_by_capability(capability)
    return ModelSpec(
        model=model,
        task_type=capability,
        scene=selected_scene,
        sensitive=sensitive,
    )
