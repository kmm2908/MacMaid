from typing import Literal

RiskLevel = Literal["safe", "review", "inform-only"]
ActionType = Literal["trash", "empty-trash", "none"]

# Alias for import compatibility
ModuleResult = dict


def make_item(path: str, size_bytes: int, label: str, meta: dict = None) -> dict:
    return {
        "path": path,
        "size_bytes": size_bytes,
        "label": label,
        "meta": meta or {},
    }


def make_result(
    category: str,
    risk: RiskLevel,
    action: ActionType = "trash",
    suggestion: str = "",
    items: list = None,
) -> dict:
    items = items or []
    return {
        "category": category,
        "risk": risk,
        "items": items,
        "total_size_bytes": sum(i["size_bytes"] for i in items),
        "suggestion": suggestion,
        "action": action,
    }
