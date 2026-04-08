from __future__ import annotations
from typing import Any, Dict

from app.adapter import adapter_in, adapter_out


def run_pipeline(api_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    今は土台確認のため：
    - adapter_in の変換結果（legacy_input）を返すだけ
    次に 001→002→003 をここへ繋ぎます。
    """
    legacy_input = adapter_in(api_payload)

    legacy_output = {
        "stage": "adapter_only",
        "legacy_input_preview": legacy_input,  # まずは確認のためそのまま返す
    }
    return adapter_out(api_payload, legacy_output)
