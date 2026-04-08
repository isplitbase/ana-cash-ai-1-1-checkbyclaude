from __future__ import annotations
from typing import Any, Dict, List


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if s == "":
        return 0
    s = s.replace(",", "")
    return int(s)


def _normalize_rows(rows: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in (rows or []):
        nr = dict(r)
        for period in ["前々期", "前期", "今期"]:
            nr.setdefault(period, {})
            nr[period] = dict(nr[period] or {})
            nr[period]["金額"] = _to_int(nr[period].get("金額", 0))
        out.append(nr)
    return out


def adapter_in(api_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    あなたのAPI入力(JSON) → cloab001が期待する legacy入力へ変換
    - BS はそのまま
    - SGA → 販売費
    - MFG → 製造原価
    - 金額は int に統一（""/Noneは0）
    """
    legacy: Dict[str, Any] = {}
    legacy["BS"] = _normalize_rows(api_payload.get("BS"))
    legacy["PL"] = _normalize_rows(api_payload.get("PL"))
    legacy["販売費"] = _normalize_rows(api_payload.get("SGA"))
    legacy["製造原価"] = _normalize_rows(api_payload.get("MFG"))

    legacy["_meta"] = {
        "ai_case_id": api_payload.get("ai_case_id"),
        "postingPeriod": api_payload.get("postingPeriod"),
        "csvdownloadfilename": api_payload.get("csvdownloadfilename"),
        "nodoai": api_payload.get("nodoai"),
        "loginkey": api_payload.get("loginkey"),
    }
    return legacy


def adapter_out(api_payload: Dict[str, Any], legacy_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    いったん安全のため、legacy出力をそのまま返す + メタ情報を付与
    """
    return {
        "ai_case_id": api_payload.get("ai_case_id"),
        "postingPeriod": api_payload.get("postingPeriod"),
        "csvdownloadfilename": api_payload.get("csvdownloadfilename"),
        "result": legacy_output,
    }
