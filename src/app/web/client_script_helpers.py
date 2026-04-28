"""client-side script renderer 共用 helper。"""

from __future__ import annotations

import json


def replace_script_constants(script: str, replacements: dict[str, object]) -> str:
    """把 Python contract 常數安全注入 inline script。"""
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, json.dumps(value))
    return script
