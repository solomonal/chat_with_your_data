from __future__ import annotations

from typing import Any


def model_to_dict(model: Any) -> dict[str, object]:
    """Convert the SDK ModelInfo object without assuming optional metadata exists."""
    data: dict[str, object] = {
        "id": model.id,
        "name": getattr(model, "name", None) or model.id,
    }
    description = getattr(model, "description", None)
    if description:
        data["description"] = description
    billing = getattr(model, "billing", None)
    multiplier = getattr(billing, "multiplier", None)
    if multiplier is not None:
        data["premium_multiplier"] = multiplier
    supports = getattr(model, "supports", None)
    if supports is not None:
        data["supports"] = (
            supports.model_dump()
            if hasattr(supports, "model_dump")
            else str(supports)
        )
    return data
