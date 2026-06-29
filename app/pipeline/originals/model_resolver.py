# -*- coding: utf-8 -*-
"""
model_resolver.py  (マルチプロバイダ対応版 / claude・openai・gemini)

目的:
  AI へリクエストする「前」に、その時点で実際に使えるモデル一覧を API から取得し、
  使おうとしているモデルが提供終了 (deprecated / 削除) で存在しない場合でも、
  一覧の中から比較的安定した近いモデルへ自動フォールバックして、
  「指定モデルが 404 でサービス停止」になるのを防ぐ。

考え方:
  1. 希望モデルを決める: 引数 override > 環境変数 (CLAUDE_MODEL / OPENAI_MODEL /
     GEMINI_MODEL) > 引数 desired > プロバイダ既定。
  2. プロバイダの models 一覧 API を叩いて「今使えるモデル」を取得する。
  3. 希望モデルが一覧にあればそれを使う。
  4. 無ければ "一覧の中から" 同系統・同ティアで最も近く安定したものを選ぶ
     (フォールバック先をコードに固定値で持たず、常に生きている一覧から選ぶ)。
  5. 一覧取得自体に失敗 (ネットワーク不調・SDK未導入など) したら、希望モデル
     (= 安全既定) をそのまま返して停止を避ける。

後方互換:
  旧 API である resolve_model() / resolve_model(api_key=..., override=...) は
  そのまま Claude 用として動作する (provider 既定が "claude")。

依存: 各プロバイダの SDK (anthropic / openai / google-genai)。すべて遅延 import。
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

# === 運用者が触る設定 =========================================================

# Claude の優先モデル (旧 model_resolver.py の挙動を踏襲)。先頭が最優先。
PREFERRED_MODELS: List[str] = [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]
# Claude 優先リストが全滅したとき「このティアの最新」を自動採用する接頭辞。
TIER_FALLBACK_PREFIX: str = "claude-sonnet-"

# プロバイダごとの: 環境変数名 / 既定モデル
_PROVIDER_CFG = {
    "claude":  {"env": "CLAUDE_MODEL",  "default": "claude-sonnet-4-6"},
    "anthropic": {"env": "CLAUDE_MODEL", "default": "claude-sonnet-4-6"},
    "openai":  {"env": "OPENAI_MODEL",  "default": "gpt-4.1-mini"},
    "gemini":  {"env": "GEMINI_MODEL",  "default": "gemini-2.0-flash"},
    "google":  {"env": "GEMINI_MODEL",  "default": "gemini-2.0-flash"},
}

# 「不安定」とみなすトークン (プレビュー版等は安定版があれば避ける)
_UNSTABLE_TOKENS = ("preview", "exp", "experimental", "nightly", "beta", "alpha", "rc")

# =============================================================================

# プロセス内キャッシュ: provider -> Tuple[str, ...]
_CACHE: dict = {}


def _normalize_provider(provider: str) -> str:
    p = (provider or "claude").lower()
    if p in ("anthropic",):
        return "claude"
    if p in ("google",):
        return "gemini"
    return p


def _norm_id(provider: str, model_id: str) -> str:
    """比較用にモデルIDを正規化する。"""
    mid = (model_id or "").strip().lower()
    if _normalize_provider(provider) == "gemini" and mid.startswith("models/"):
        mid = mid[len("models/"):]
    return mid


def list_available_models(provider: str = "claude",
                          api_key: Optional[str] = None,
                          client=None,
                          use_cache: bool = True) -> Tuple[str, ...]:
    """現在 API で利用可能なモデルIDの一覧を返す (プロセス内キャッシュ)。

    取得できない場合は例外を送出する (呼び出し側で握って既定にフォールバック)。
    """
    prov = _normalize_provider(provider)
    if use_cache and client is None and prov in _CACHE:
        return _CACHE[prov]

    if prov == "claude":
        if client is None:
            import anthropic  # 遅延 import
            client = anthropic.Anthropic(
                api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
            )
        ids = tuple(m.id for m in client.models.list(limit=1000))

    elif prov == "openai":
        if client is None:
            from openai import OpenAI  # 遅延 import
            client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        resp = client.models.list()
        data = getattr(resp, "data", None) or list(resp)
        ids = tuple(getattr(m, "id", None) or m["id"] for m in data)

    elif prov == "gemini":
        if client is None:
            from google import genai  # 遅延 import
            client = genai.Client(
                api_key=api_key
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
            )
        ids = tuple(
            getattr(m, "name", None) or getattr(m, "id", None) or str(m)
            for m in client.models.list()
        )
    else:
        raise ValueError(f"未知のプロバイダ: {provider}")

    ids = tuple(i for i in ids if i)
    if client is not None and use_cache:
        _CACHE[prov] = ids
    return ids


def _version_key(model_id: str) -> Tuple[int, ...]:
    """'claude-sonnet-4-6' -> (4, 6)。末尾の8桁日付スナップショット等は無視。"""
    nums = re.findall(r"(\d+)", model_id)
    return tuple(int(n) for n in nums if len(n) <= 2)  # 日付(長い数字)を除外


def _family(model_id: str) -> str:
    """先頭の英字連なりを「系統」とみなす。例: gpt-4.1-mini -> 'gpt'。"""
    m = re.match(r"[a-z]+", model_id.lower())
    return m.group(0) if m else ""


def _descriptors(model_id: str) -> set:
    """系統以外の英字トークン集合 (mini / pro / flash / sonnet ... )。"""
    fam = _family(model_id)
    toks = re.split(r"[^a-z0-9]+", model_id.lower())
    out = set()
    for t in toks:
        if not t or t == fam:
            continue
        alpha = re.sub(r"[0-9]+", "", t)  # '4o' -> 'o'
        if alpha and alpha not in _UNSTABLE_TOKENS:
            out.add(alpha)
    return out


def _is_stable(model_id: str) -> bool:
    low = model_id.lower()
    return not any(tok in low for tok in _UNSTABLE_TOKENS)


def _has_long_digits(model_id: str) -> bool:
    """日付スナップショット (例: -20251001) を持つか。"""
    return any(len(n) >= 6 for n in re.findall(r"\d+", model_id))


def _pick_similar(desired: str, available, provider: str) -> Optional[str]:
    """available の中から desired に最も近く安定したモデルを1つ選ぶ。

    系統が一致するものだけを候補とし、
    (記述子の一致数, 安定版か, バージョン, 非スナップショット, 短さ) で順位付け。
    """
    d_norm = _norm_id(provider, desired)
    d_fam = _family(d_norm)
    d_desc = _descriptors(d_norm)

    scored = []
    for native in available:
        n = _norm_id(provider, native)
        if _family(n) != d_fam or not d_fam:
            continue  # 別系統 (embedding 等) は除外
        overlap = len(d_desc & _descriptors(n))
        scored.append((
            overlap,                 # 記述子の一致が多いほど良い
            1 if _is_stable(n) else 0,
            _version_key(n),         # 新しいほど良い
            0 if _has_long_digits(n) else 1,  # 日付固定版より基底エイリアスを優先
            -len(n),                 # 短い(汎用的な)ID を優先
            native,
        ))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][-1]


def resolve_model(provider: str = "claude",
                  desired: Optional[str] = None,
                  *,
                  api_key: Optional[str] = None,
                  override: Optional[str] = None,
                  client=None) -> str:
    """今使えるモデルIDを1つ決めて返す。

    優先順位 (希望モデルの決定):
      override > 環境変数 > desired > プロバイダ既定
    その希望モデルが models 一覧に存在すればそれを採用。無ければ一覧から近い
    安定モデルへフォールバック。一覧取得に失敗したら希望モデルをそのまま返す。
    """
    prov = _normalize_provider(provider)
    cfg = _PROVIDER_CFG.get(prov, _PROVIDER_CFG["claude"])

    env_val = os.environ.get(cfg["env"]) if cfg.get("env") else None
    ov = override or env_val
    desired = ov or desired or cfg["default"]
    safe_default = desired  # 取得失敗時に返す安全既定

    try:
        available = list_available_models(prov, api_key=api_key, client=client)
    except Exception:
        return safe_default
    if not available:
        return safe_default

    norm_map = {}
    for native in available:
        norm_map.setdefault(_norm_id(prov, native), native)

    # 1) 希望モデルがそのまま使えるなら採用
    d = _norm_id(prov, desired)
    if d in norm_map:
        return norm_map[d]

    # 2) Claude は従来どおり優先リスト → 同ティア最新 を尊重
    if prov == "claude":
        for m in PREFERRED_MODELS:
            if _norm_id("claude", m) in norm_map:
                return norm_map[_norm_id("claude", m)]
        tier = [n for n in available
                if _norm_id("claude", n).startswith(TIER_FALLBACK_PREFIX)]
        if tier:
            return sorted(tier, key=_version_key)[-1]

    # 3) 一般: 一覧から同系統で最も近い安定モデルを選ぶ
    best = _pick_similar(desired, available, prov)
    return best or safe_default


if __name__ == "__main__":
    import sys
    prov = sys.argv[1] if len(sys.argv) > 1 else "claude"
    print(f"[{prov}] 利用可能なモデル:")
    try:
        for mid in list_available_models(prov):
            print("  -", mid)
    except Exception as e:  # noqa: BLE001
        print("  (一覧取得に失敗:", e, ")")
    print("採用モデル:", resolve_model(prov))
