# -*- coding: utf-8 -*-
"""
model_resolver.py

Claude のモデルIDを「手動切り替え」せずに運用するためのヘルパー。

考え方:
  1. 環境変数 CLAUDE_MODEL があれば最優先で使う（運用者が明示指定したいケース）。
  2. それも含めた優先リスト PREFERRED_MODELS を上から順に見て、
     /v1/models で「今この瞬間に使えるモデル」に含まれる最初の1つを採用する。
  3. 優先リストが全滅（全部 deprecation 済み等）でも、同ティアの最新版を
     自動で拾うので、claude-sonnet-4-7 / 4-8 / 4-9 ... が出れば勝手に追従する。
  4. /v1/models の取得自体に失敗（ネットワーク不調など）したら、安全な既定
     （CLAUDE_MODEL もしくは PREFERRED_MODELS の先頭）を返して停止を避ける。

これにより「指定したモデルが提供終了で 404 になってサービス停止」を防ぐ。

依存: anthropic（各プロジェクトの requirements.txt に既にあるもの。遅延importする）
"""
from __future__ import annotations
import os
import re
from functools import lru_cache
from typing import List, Optional, Tuple

# --- 運用者が触る設定 ---------------------------------------------------------

# 上から順に「使えるなら使いたい」モデル。先頭が最優先。
PREFERRED_MODELS: List[str] = [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]

# 優先リストが全滅したときに「このティアの最新」を自動採用するための接頭辞。
# 例: "claude-sonnet-" にしておくと、将来 claude-sonnet-4-9 等が出れば自動追従。
TIER_FALLBACK_PREFIX: str = "claude-sonnet-"

# -----------------------------------------------------------------------------


@lru_cache(maxsize=2)
def list_available_models(api_key: Optional[str] = None) -> Tuple[str, ...]:
    """現在 API で利用可能なモデルIDの一覧を返す（プロセス内でキャッシュ）。"""
    import anthropic  # 遅延import（未インストール環境での import 失敗を避ける）
    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    return tuple(m.id for m in client.models.list(limit=1000))


def _version_key(model_id: str) -> Tuple[int, ...]:
    """'claude-sonnet-4-6' -> (4, 6)。末尾の8桁日付スナップショットは無視して比較。"""
    nums = re.findall(r"-(\d+)", model_id)
    return tuple(int(n) for n in nums if len(n) <= 2)  # 日付(8桁)を除外


def resolve_model(api_key: Optional[str] = None, override: Optional[str] = None) -> str:
    """今使えるモデルIDを1つ決めて返す。

    優先順位:
      override 引数 > 環境変数 CLAUDE_MODEL > PREFERRED_MODELS > 同ティア最新
    いずれも「実際に /v1/models に存在するもの」だけを採用する。
    一覧取得に失敗した場合は安全な既定を返して停止を避ける。
    """
    ov = override or os.environ.get("CLAUDE_MODEL")
    default = ov or PREFERRED_MODELS[0]

    try:
        available = set(list_available_models(api_key))
    except Exception:
        # ネットワーク不調などで一覧が取れない → 既定にフォールバック（停止回避）
        return default

    candidates: List[str] = []
    if ov:
        candidates.append(ov)
    candidates += PREFERRED_MODELS

    for m in candidates:
        if m in available:
            return m

    # 優先リスト全滅 → 同ティアの最新版を自動採用
    tier = [m for m in available if m.startswith(TIER_FALLBACK_PREFIX)]
    if tier:
        return sorted(tier, key=_version_key)[-1]

    # それも無ければ既定（少なくとも文字列は返す）
    return default


if __name__ == "__main__":
    print("利用可能なモデル:")
    for mid in list_available_models():
        print("  -", mid)
    print("\n採用モデル:", resolve_model())
