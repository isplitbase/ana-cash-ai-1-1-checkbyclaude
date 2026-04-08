from __future__ import annotations
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # ~/cash-ai-01
ORIGINALS_DIR = PROJECT_ROOT / "app" / "pipeline" / "originals"

def _run(cmd: list[str], cwd: Path, env: Dict[str, str]) -> None:
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n--- output ---\n{p.stdout}")

def run_001_002_003(payload: Dict[str, Any]) -> Dict[str, Any]:
    data_json = {
        "BS": payload.get("BS", []),
        "PL": payload.get("PL", []),
        "販売費": payload.get("SGA", []),
        "製造原価": payload.get("MFG", []),
    }

    run_dir = Path(tempfile.mkdtemp(prefix="cashai_", dir="/tmp"))
    (run_dir / "data.json").write_text(json.dumps(data_json, ensure_ascii=False), encoding="utf-8")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    env = dict(os.environ)
    if api_key:
        env["OPENAI_API_KEY2"] = api_key

    # ★ここが重要：cash-ai-01 直下をPYTHONPATHに入れる（google/colabスタブを拾える）
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    _run(["python3", str(ORIGINALS_DIR / "cloab001.py")], cwd=run_dir, env=env)
    _run(["python3", str(ORIGINALS_DIR / "cloab002.py")], cwd=run_dir, env=env)
    _run(["python3", str(ORIGINALS_DIR / "cloab003.py")], cwd=run_dir, env=env)

    out_path = run_dir / "output_updated.json"
    if not out_path.exists():
        out_path = run_dir / "output.json"
    if not out_path.exists():
        raise RuntimeError("output_updated.json / output.json が生成されませんでした。")

    return json.loads(out_path.read_text(encoding="utf-8"))


# ============================================================
# Cloud Run 用: colab1-1-checkByClaude.py 相当の処理（Anthropic）
# ============================================================
import base64
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import boto3

try:
    import anthropic  # type: ignore
except Exception:  # pragma: no cover
    anthropic = None  # 依存が無い場合にエラーメッセージを出すため


def _parse_s3_uri(uri: str) -> Tuple[str, str]:
    # s3://bucket/key
    if not uri.startswith("s3://"):
        raise ValueError(f"Unsupported uri (expected s3://...): {uri}")
    no_scheme = uri[len("s3://") :]
    parts = no_scheme.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid s3 uri: {uri}")
    return parts[0], parts[1]


def _s3_client():
    # runner101.py と同じ環境変数名に合わせる
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    region = os.getenv("S3_REGION")
    if not access_key or not secret_key or not region:
        raise RuntimeError("S3_ACCESS_KEY / S3_SECRET_KEY / S3_REGION が未設定です。")
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def _download_s3_to_tmp(s3_uri: str, run_dir: Path, index: int | None = None) -> Path:
    bucket, key = _parse_s3_uri(s3_uri)
    base = Path(key).name or "input.pdf"
    # 1リクエスト内で同名ファイルが複数あるケースや、意図せず上書きしないようにユニーク化
    stem = Path(base).stem
    suffix = Path(base).suffix or ".pdf"
    if index is not None:
        candidate = f"{stem}_{index}{suffix}"
    else:
        candidate = base
    local = run_dir / candidate
    n = 1
    while local.exists():
        local = run_dir / f"{stem}_{index or 0}_{n}{suffix}"
        n += 1
    s3 = _s3_client()
    s3.download_file(bucket, key, str(local))
    return local



def _split_pdfurls(pdfurls: Any) -> List[str]:
    if not pdfurls:
        return []
    if isinstance(pdfurls, list):
        return [str(x).strip() for x in pdfurls if str(x).strip()]
    s = str(pdfurls).strip()
    if not s:
        return []
    # 例: "s3://...pdf|,|s3://...pdf"
    parts = [p.strip() for p in s.split("|,|")]
    return [p for p in parts if p]


def _anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY（または CLAUDE_API_KEY）が未設定です。")
    if anthropic is None:
        raise RuntimeError("anthropic ライブラリがインストールされていません。requirements.txt を確認してください。")
    return anthropic.Anthropic(api_key=api_key)


def _to_int(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0


def _find_amount(rows: list, name: str, period: str) -> Optional[int]:
    for row in rows or []:
        if isinstance(row, dict) and row.get("勘定科目") == name:
            p = row.get(period) or {}
            if isinstance(p, dict):
                return _to_int(p.get("金額"))
    return None


def _agent2_numeric_checks(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Colabの Agent2 を Cloud Run で再現：JSONの数値だけで機械的に検算する"""
    bs = payload.get("BS") or []
    pl = payload.get("PL") or payload.get("pl") or []
    periods = ["今期", "前期", "前々期"]

    checks = []

    # BS: 資産合計 == 負債純資産合計
    for per in periods:
        assets = _find_amount(bs, "資産合計", per) or _find_amount(bs, "資産合計", per)
        liab_eq = _find_amount(bs, "負債純資産合計", per) or _find_amount(bs, "負債及び純資産合計", per)
        if assets is not None and liab_eq is not None:
            diff = assets - liab_eq
            checks.append(
                {
                    "type": "BS_balance",
                    "period": per,
                    "left": {"name": "資産合計", "amount": assets},
                    "right": {"name": "負債純資産合計", "amount": liab_eq},
                    "diff": diff,
                    "ok": diff == 0,
                }
            )

    # PL: 代表的な利益の式（存在する項目だけ）
    # 売上総利益 = 売上高 - 売上原価
    for per in periods:
        sales = _find_amount(pl, "売上高", per)
        cogs = _find_amount(pl, "売上原価", per)
        gp = _find_amount(pl, "売上総利益", per)
        if sales is not None and cogs is not None and gp is not None:
            diff = gp - (sales - cogs)
            checks.append(
                {
                    "type": "PL_gross_profit",
                    "period": per,
                    "expected": sales - cogs,
                    "actual": gp,
                    "diff": diff,
                    "ok": diff == 0,
                }
            )

    return {
        "periods": periods,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "ok": sum(1 for c in checks if c.get("ok")),
            "ng": sum(1 for c in checks if not c.get("ok")),
        },
    }


def run_check_by_claude(payload: Dict[str, Any]) -> Dict[str, Any]:
    """API から呼ばれるエントリポイント。

    方針: Colab 版の処理ロジック（プロンプト含む）を極力そのまま使うため、
    app/pipeline/originals/colab1-1-checkByClaude.py を subprocess で実行し、
    生成された check_result.json の中身を API の戻り値として返す。

    - 入力: payload（BS/PL/MFG/SGA, pdfurls など）
    - 出力: check_result.json の内容（dict）
    """

    # nodoai=true のときは互換的にスキップ
    if payload.get("nodoai") is True:
        return {
            "ai_case_id": payload.get("ai_case_id"),
            "postingPeriod": payload.get("postingPeriod"),
            "skipped": True,
            "reason": "nodoai=true のため AI チェックをスキップしました。",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    script_path = ORIGINALS_DIR / "colab1-1-checkByClaude.py"
    if not script_path.exists():
        return {
            "status": "error",
            "message": "colab1-1-checkByClaude.py が見つかりません",
            "path": str(script_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # リクエストごとに作業ディレクトリを分離（同時実行の衝突回避）
    run_dir = Path(tempfile.mkdtemp(prefix="checkbyclaude_", dir="/tmp"))
    out_path = run_dir / "check_result.json"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["WORKDIR"] = str(run_dir)

    # Colab版は MODEL を固定値で持っているため、Cloud Run 側の環境変数で上書きできるようにしている
    # (originals 側で CLAUDE_MODEL を参照)

    p = subprocess.run(
        ["python3", str(script_path)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        cwd=str(run_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if p.returncode != 0:
        return {
            "status": "error",
            "message": "colab1-1-checkByClaude.py の実行に失敗しました",
            "returncode": p.returncode,
            "output_head": (p.stdout or "")[:2000],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    if not out_path.exists():
        return {
            "status": "error",
            "message": "check_result.json が生成されませんでした",
            "output_head": (p.stdout or "")[:2000],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        result = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "status": "error",
            "message": "check_result.json のJSON解析に失敗しました",
            "detail": str(e),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # API互換用のメタ情報を付与（必要なら）
    if isinstance(result, dict):
        result.setdefault("ai_case_id", payload.get("ai_case_id"))
        result.setdefault("postingPeriod", payload.get("postingPeriod"))
        result.setdefault("csvdownloadfilename", payload.get("csvdownloadfilename"))
        result.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    return result
