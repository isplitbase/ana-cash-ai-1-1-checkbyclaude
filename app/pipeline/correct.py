# -*- coding: utf-8 -*-
"""
読取結果を PDF と見比べて直す（/v1/correct・2026-10-23）

流れ:
  1. Claude（既定は claude-opus-5-5）に PDF と読取結果を渡し、読み違い・読取漏れ・行ずれの修正案を出させる
  2. 修正案を当てはめる前と後で、合計の検算（分類ごとの内訳の合計・BS の貸借・PL の利益の流れ・販管費の合計）をする
  3. 検算で裏付けが取れた修正（失敗していた検算が合うようになり、新しく合わなくなる検算が無いもの）だけを反映する
  4. 裏付けが取れない修正は反映せず、unverified として返す（画面での確認用）

入力: {"ai_case_id", "pdfurls": ["gs://..."], "response": {"BS": [...], "PL": [...], "販売費": [...], "製造原価": [...]}}
出力: {"status": "ok", "response": 直した読取結果, "applied": [...], "rejected": [...], "unverified": [...],
       "checks_before": [...], "checks_after": [...], "model": "..."}
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PERIODS = ["今期", "前期", "前々期"]
SECTIONS = ["BS", "PL", "販売費", "製造原価"]
DEFAULT_MODEL = "claude-opus-5-5"


# ------------------------------------------------------------
# 値の読み書き
# ------------------------------------------------------------
def _norm(name: Any) -> str:
    """科目名の表記ゆれをそろえる（全角半角・空白・【】・句読点・「(損失)」・末尾の「金額」）"""
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = re.sub(r"[(（][^)）]*損失[^)）]*[)）]", "", s)
    s = re.sub(r"[\s【】\[\]()（）、・,]", "", s)
    s = re.sub(r"金額$", "", s)
    return s


def _num(v: Any) -> Optional[int]:
    """金額を整数にする。空欄・None は None。△・▲ はマイナス。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = unicodedata.normalize("NFKC", str(v)).strip().replace(",", "")
    if s == "":
        return None
    neg = s.startswith(("△", "▲", "-"))
    s = s.lstrip("△▲-")
    try:
        n = int(float(s))
    except ValueError:
        return None
    return -n if neg else n


def _get(row: dict, period: str) -> Optional[int]:
    v = row.get(period)
    return _num(v.get("金額") if isinstance(v, dict) else v)


def _set(row: dict, period: str, value: Optional[int]) -> None:
    v = row.get(period)
    if not isinstance(v, dict):
        v = {"金額": "", "page_no": ""}
        row[period] = v
    v["金額"] = "" if value is None else int(value)


def _find(section: List[dict], *names: str) -> Optional[dict]:
    targets = {_norm(n) for n in names}
    for row in section:
        if _norm(row.get("勘定科目")) in targets:
            return row
    return None


# ------------------------------------------------------------
# 検算
# ------------------------------------------------------------
def _period_has_data(resp: dict, p: str) -> bool:
    for sec in ("BS", "PL"):
        for row in resp.get(sec) or []:
            if _get(row, p) not in (None, 0):
                return True
    return False


def run_checks(resp: dict) -> Dict[str, bool]:
    """検算の結果を {"検算名": 合っているか} で返す。値が足りない検算は含めない。"""
    out: Dict[str, bool] = {}

    def add(name: str, calc: Optional[int], read: Optional[int]) -> None:
        if calc is not None and read is not None:
            out[name] = (calc == read)

    for p in PERIODS:
        if not _period_has_data(resp, p):
            continue

        # 1) 分類ごとに「分類と同じ名前の行（合計）＝その他の行の合計」
        for sec in SECTIONS:
            rows = resp.get(sec) or []
            groups: Dict[str, List[dict]] = {}
            for row in rows:
                groups.setdefault(_norm(row.get("分類")), []).append(row)
            for g, members in groups.items():
                if not g:
                    continue
                totals = [r for r in members if _norm(r.get("勘定科目")) == g]
                details = [r for r in members if _norm(r.get("勘定科目")) != g]
                if len(totals) != 1 or not details:
                    continue
                vals = [_get(r, p) for r in details]
                if all(v is None for v in vals):
                    continue
                add(f"【{p}】{sec}:{g}の内訳の合計", sum(v or 0 for v in vals), _get(totals[0], p))

        bs, pl = resp.get("BS") or [], resp.get("PL") or []
        sga, mfg = resp.get("販売費") or [], resp.get("製造原価") or []
        g = lambda sec, *n: (_get(_find(sec, *n), p) if _find(sec, *n) else None)

        # 2) BS の貸借
        assets = g(bs, "資産合計", "資産の部合計")
        liab = g(bs, "負債合計", "負債の部合計")
        equity = g(bs, "純資産合計", "純資産の部合計")
        if None not in (assets, liab, equity):
            add(f"【{p}】BS:資産＝負債＋純資産", liab + equity, assets)
        cur, fixed, defer = g(bs, "流動資産"), g(bs, "固定資産"), g(bs, "繰延資産")
        if None not in (assets, cur, fixed):
            add(f"【{p}】BS:資産＝流動＋固定＋繰延", cur + fixed + (defer or 0), assets)
        tang, intang, inv = g(bs, "有形固定資産"), g(bs, "無形固定資産"), g(bs, "投資その他の資産")
        if None not in (fixed, tang, intang, inv):
            add(f"【{p}】BS:固定資産＝有形＋無形＋投資", tang + intang + inv, fixed)

        # 3) PL の利益の流れ
        sales, cogs, gross = g(pl, "売上高"), g(pl, "売上原価"), g(pl, "売上総利益")
        sgna, op = g(pl, "販売費及び一般管理費"), g(pl, "営業利益")
        ninc, nexp, ordi = g(pl, "営業外収益"), g(pl, "営業外費用"), g(pl, "経常利益")
        sinc, sloss = g(pl, "特別利益"), g(pl, "特別損失")
        pre = g(pl, "税引前当期純利益", "税引前当期利益", "税金等調整前当期純利益")
        tax = g(pl, "法人税等", "法人税住民税及び事業税", "法人税及び住民税")
        adj = g(pl, "法人税等調整額")
        net = g(pl, "当期純利益", "当期利益")
        if None not in (sales, cogs, gross):
            add(f"【{p}】PL:売上総利益", sales - cogs, gross)
        if None not in (gross, sgna, op):
            add(f"【{p}】PL:営業利益", gross - sgna, op)
        if None not in (op, ninc, nexp, ordi):
            add(f"【{p}】PL:経常利益", op + ninc - nexp, ordi)
        if None not in (ordi, pre):
            add(f"【{p}】PL:税引前当期純利益", ordi + (sinc or 0) - (sloss or 0), pre)
        if None not in (pre, tax, net):
            add(f"【{p}】PL:当期純利益", pre - tax - (adj or 0), net)

        # 4) 販管費の内訳の合計（合計行の名前がそろっていない場合に備え、分類の検算とは別に見る）
        total_row = _find(sga, "販売費及び一般管理費", "販売費及び一般管理費合計", "合計")
        if total_row is not None:
            vals = [_get(r, p) for r in sga if r is not total_row]
            if any(v is not None for v in vals):
                add(f"【{p}】販売費:内訳の合計", sum(v or 0 for v in vals), _get(total_row, p))
            if sgna is not None:
                add(f"【{p}】販売費の合計＝PLの販管費", _get(total_row, p), sgna)

        # 5) 製造原価の流れ
        labor = g(mfg, "当期労務費")
        lab_items = [g(mfg, n) for n in ("賃金", "雑給", "法定福利費", "厚生費")]
        if labor is not None and any(v is not None for v in lab_items):
            add(f"【{p}】製造原価:労務費", sum(v or 0 for v in lab_items), labor)
        mat, exp, total_mfg = g(mfg, "当期材料費"), g(mfg, "当期経費"), g(mfg, "当期総製造費用")
        if None not in (labor, exp, total_mfg):
            add(f"【{p}】製造原価:総製造費用", (mat or 0) + labor + exp, total_mfg)
        prod_m, prod_p = g(mfg, "当期製品製造原価"), g(pl, "当期製品製造原価")
        if None not in (prod_m, prod_p):
            add(f"【{p}】製造原価＝PLの当期製品製造原価", prod_m, prod_p)
    return out


def _failing(checks: Dict[str, bool]) -> set:
    return {k for k, ok in checks.items() if not ok}


# ------------------------------------------------------------
# PDF の取得
# ------------------------------------------------------------
def _download_pdfs(urls: List[str], workdir: Path) -> List[Tuple[str, bytes]]:
    pdfs = []
    for i, uri in enumerate(urls, start=1):
        if not uri.startswith("gs://"):
            raise ValueError(f"gs:// 以外の PDF には対応していません: {uri}")
        from google.cloud import storage
        bucket, key = uri[len("gs://"):].split("/", 1)
        local = workdir / f"input_{i}.pdf"
        project = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        client = storage.Client(project=project) if project else storage.Client()
        client.bucket(bucket).blob(key).download_to_filename(str(local))
        pdfs.append((Path(key).name, local.read_bytes()))
    return pdfs


# ------------------------------------------------------------
# Claude に修正案を出させる
# ------------------------------------------------------------
PROMPT = """あなたは決算書の読取結果を直す担当者です。
添付の決算書PDFと、下の「読取結果」（PDFをOCRで読み取ったもの）を見比べ、読取結果の誤りの直し方を出してください。

## 探すもの
- 読み違い：PDFと金額が違う（桁・数字の読み違い、△▲のマイナスの付け忘れ・付け過ぎ）
- 読取漏れ：PDFに金額があるのに空欄
- 行ずれ：ある期の列だけ、値が1行ずつ上下にずれている（例：預け金の値が棚卸資産に入り、以下も順にずれる）
- 隣の列の取り違え：PDFが金額を2〜3列に分けて書く様式で、同じ行の別の列（小計・合計）の値を入れている
- 余分な値：PDFに無い値が入っている行（行ずれで押し出された値など）

## ルール
- 直せるのは「読取結果にある行の、ある期の金額」だけ。行の追加・削除・科目名の変更はしない（余分な値は value を null にして空欄にする）。
- 期は決算日で判断する。「今期」が最も新しい決算期、「前期」がその1つ前、「前々期」がさらに1つ前。
  各行の page_no はアップロードされたページの通し番号で、PDFは添付の順に並んでいる。どのPDFがどの期かは決算日で確かめる。
- value は読取結果と同じ単位の整数（カンマなし）。マイナスは -123 のように書く。
- 1つの原因で複数の値を直すとき（行ずれなど）は、同じ group を付ける。
- PDFで確かめられない値は直さない。推測で直さない。合っている値は挙げない。
- 科目名の書き方の違い（「売上総利益金額」と「売上総利益」など）は直さない。

## 読取結果（id は行の番号）
```json
{read_data}
```

## 出力（JSONのみ。他の文章は書かない）
```json
{{
  "corrections": [
    {{"id": "BS-5", "period": "前々期", "value": 13049, "group": "g1", "pdf": "前々期のBS 預け金 13,049", "reason": "前々期の流動資産が1行ずれている"}}
  ]
}}
```
誤りが無ければ {{"corrections": []}} を返す。
"""


def _compact(resp: dict) -> Tuple[str, Dict[str, Tuple[str, int]]]:
    """Claude に渡す読取結果（行に id を付ける）と、id → (セクション, 行番号) の表を作る"""
    data, index = {}, {}
    for sec in SECTIONS:
        rows = []
        for i, row in enumerate(resp.get(sec) or []):
            rid = f"{sec}-{i}"
            index[rid] = (sec, i)
            item = {"id": rid, "勘定科目": row.get("勘定科目", ""), "分類": row.get("分類", "")}
            for p in PERIODS:
                v = row.get(p)
                item[p] = v.get("金額", "") if isinstance(v, dict) else (v or "")
                if isinstance(v, dict) and v.get("page_no") not in (None, ""):
                    item[f"{p}_page_no"] = v.get("page_no")
            rows.append(item)
        if rows:
            data[sec] = rows
    return json.dumps(data, ensure_ascii=False, indent=1), index


def _parse_json(text: str) -> dict:
    m = re.search(r"```json\s*(.*?)```", text, re.S)
    body = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(body)


def ask_claude(pdfs: List[Tuple[str, bytes]], read_data: str) -> Tuple[List[dict], str]:
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY が設定されていません")
    wanted = os.getenv("CORRECT_MODEL", DEFAULT_MODEL)
    try:
        from app.pipeline.originals.model_resolver import resolve_model
        model = resolve_model(api_key=api_key, override=wanted)
    except Exception:
        model = wanted
    client = anthropic.Anthropic(api_key=api_key)
    content = [{"type": "document", "title": name,
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(b).decode("ascii")}}
               for name, b in pdfs]
    content.append({"type": "text", "text": PROMPT.format(read_data=read_data)})
    last_err = None
    for _ in range(2):
        msg = client.messages.create(model=model, max_tokens=8192,
                                     messages=[{"role": "user", "content": content}])
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        try:
            obj = _parse_json(text)
            corr = obj.get("corrections", [])
            if isinstance(corr, list):
                return corr, model
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Claude の修正案を JSON として読めませんでした: {last_err}")


# ------------------------------------------------------------
# 修正案の検証と反映
# ------------------------------------------------------------
def _apply(resp: dict, items: List[dict], index: Dict[str, Tuple[str, int]]) -> dict:
    new = copy.deepcopy(resp)
    for c in items:
        sec, i = index[c["id"]]
        _set(new[sec][i], c["period"], c["value"])
    return new


def _is_rearrangement(resp: dict, items: List[dict], index) -> bool:
    """修正が「同じ表・同じ期の中で、今ある値を別の行へ移すだけ」かどうか（2件以上・値の集まりが変わらない）"""
    if len(items) < 2:
        return False
    keys = {(index[c["id"]][0], c["period"]) for c in items}
    if len(keys) != 1:
        return False
    before = sorted(v for v in (_get(resp[index[c["id"]][0]][index[c["id"]][1]], c["period"]) for c in items) if v is not None)
    after = sorted(c["value"] for c in items if c["value"] is not None)
    return before == after and len(after) > 0


def _describe(c: dict, resp: dict, index) -> dict:
    sec, i = index[c["id"]]
    row = resp[sec][i]
    return {"section": sec, "勘定科目": row.get("勘定科目", ""), "period": c["period"],
            "before": _get(row, c["period"]), "after": c["value"],
            "pdf": c.get("pdf", ""), "reason": c.get("reason", ""), "group": c.get("group", "")}


def correct_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = payload.get("response") or {}
    if not isinstance(resp, dict) or not any(resp.get(s) for s in SECTIONS):
        return {"status": "error", "message": "response（読取結果）がありません"}
    pdfurls = payload.get("pdfurls") or []
    if isinstance(pdfurls, str):
        pdfurls = [u for u in pdfurls.split("|,|") if u.strip()]
    if not pdfurls:
        return {"status": "error", "message": "pdfurls がありません"}

    with tempfile.TemporaryDirectory(prefix="correct_") as td:
        pdfs = _download_pdfs(pdfurls, Path(td))
    read_data, index = _compact(resp)
    raw, model = ask_claude(pdfs, read_data)

    # 形の正しい修正案だけ残す（存在する行・期、整数か null、今と違う値）
    cands = []
    for c in raw:
        if not isinstance(c, dict) or c.get("id") not in index or c.get("period") not in PERIODS:
            continue
        v = c.get("value")
        if v is not None:
            v = _num(v)
            if v is None:
                continue
        sec, i = index[c["id"]]
        if _get(resp[sec][i], c["period"]) == v:
            continue
        cands.append({**c, "value": v, "group": str(c.get("group") or c["id"] + c["period"])})

    before = run_checks(resp)
    fail_before = _failing(before)

    # group ごとに、検算で裏付けが取れるかを順に確かめる
    groups: Dict[str, List[dict]] = {}
    for c in cands:
        groups.setdefault(c["group"], []).append(c)

    current, fail_cur = resp, fail_before
    applied, rejected, unverified = [], [], []
    pending = list(groups.values())
    progress = True
    while pending and progress:          # ある group を直すと別の group の裏付けが取れることがあるので繰り返す
        progress = False
        rest = []
        for items in pending:
            trial = _apply(current, items, index)
            fail_trial = _failing(run_checks(trial))
            if fail_trial < fail_cur:    # 合わなかった検算が減り、新しく合わなくなる検算が無い
                applied += [_describe(c, current, index) for c in items]
                current, fail_cur, progress = trial, fail_trial, True
            elif fail_trial - fail_cur:  # 新しく合わなくなる検算がある＝修正案の方が誤り
                rejected += [{**_describe(c, current, index), "why": "検算が合わなくなる"} for c in items]
            elif _is_rearrangement(current, items, index):
                # 同じ表・同じ期の中で値を入れ替えるだけ（行ずれの直し）は合計が変わらないので検算では確かめられないが、
                # 合計を壊さないので反映する
                applied += [{**_describe(c, current, index), "note": "行ずれの直し（値の入れ替えのみ）"} for c in items]
                current, progress = trial, True
            else:
                rest.append(items)
        pending = rest
    for items in pending:                # 検算に関係しない修正は反映しない（画面での確認用に返す）
        unverified += [_describe(c, current, index) for c in items]

    after = run_checks(current)
    return {
        "status": "ok",
        "ai_case_id": payload.get("ai_case_id"),
        "model": model,
        "response": current,
        "applied": applied,
        "rejected": rejected,
        "unverified": unverified,
        "checks_before": sorted(fail_before),
        "checks_after": sorted(_failing(after)),
        "checks_total": len(after),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
