import json
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import boto3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COLAB_SCRIPT = PROJECT_ROOT / "app" / "pipeline" / "originals" / "colab101.py"

OUTPUT_JSON = "output.json"
OUTPUT_UPDATED_JSON = "output_updated.json"
HTML_FILE = "report.html"

# presigned URL の最大は 7日（SigV4）
PRESIGNED_EXPIRES_SECONDS = 7 * 24 * 60 * 60


def _run(cmd, cwd: Path, env: dict):
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            f"cmd={cmd}\n"
            f"returncode={p.returncode}\n"
            f"stdout:\n{p.stdout}\n"
            f"stderr:\n{p.stderr}\n"
        )
    return p.stdout


def _s3_client():
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    region = os.getenv("S3_REGION")
    if not access_key or not secret_key or not region:
        raise RuntimeError(
            "S3環境変数が不足しています。"
            "S3_ACCESS_KEY / S3_SECRET_KEY / S3_REGION を設定してください。"
        )

    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def _upload_html_and_presign(html_path: Path) -> str:
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise RuntimeError("S3_BUCKET が未設定です（例: zlite）")

    prefix = os.getenv("S3_PREFIX", "cash-ai-02/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    # 例: cash-ai-02/20260205T031245Z_<uuid>.html
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{prefix}{ts}_{uuid.uuid4().hex}.html"

    s3 = _s3_client()

    s3.upload_file(
        Filename=str(html_path),
        Bucket=bucket,
        Key=key,
        ExtraArgs={
            "ContentType": "text/html; charset=utf-8",
            "CacheControl": "no-store",
        },
    )

    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=PRESIGNED_EXPIRES_SECONDS,
    )


def run_colab101(payload: Any) -> Dict[str, Any]:
    """
    入力 payload を output.json として保存し colab101.py を実行。
    colab101.py が生成した report.html を S3 にアップして URL を返し、
    output_updated.json の中身を data として返す。

    返却:
      {"html": "<presigned_url>", "data": [...]}
    """
    run_dir = Path(tempfile.mkdtemp(prefix="cashai02_", dir="/tmp"))

    try:
        # 入力を output.json に保存（colab101.py は list でも dict でも対応）
        (run_dir / OUTPUT_JSON).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        env = dict(os.environ)

        # colab101.py に HTML をファイル出力させる（displayは不要でもOK）
        env["NO_HTML"] = "0"  # Notebook表示は不要（ファイルは出る）
        env["HTML_OUTPUT_PATH"] = HTML_FILE

        # OpenAIキー互換（不要なら無視される）
        if "OPENAI_API_KEY" in env and "OPENAI_API_KEY2" not in env:
            env["OPENAI_API_KEY2"] = env["OPENAI_API_KEY"]

        # 実行
        _run(["python3", str(COLAB_SCRIPT)], cwd=run_dir, env=env)

        # data（output_updated.json）
        out_path = run_dir / OUTPUT_UPDATED_JSON
        if not out_path.exists():
            raise RuntimeError("output_updated.json が生成されませんでした。")

        data = json.loads(out_path.read_text(encoding="utf-8"))

        # html（report.html）
        html_path = run_dir / HTML_FILE
        if not html_path.exists():
            raise RuntimeError(
                "report.html が生成されませんでした。"
                "colab101.py の #9 以降に html 書き出しを追加できているか確認してください。"
            )

        html_url = _upload_html_and_presign(html_path)

        return {"html": html_url, "data": data}

    finally:
        # 成功・失敗に関わらず /tmp 配下の作業ディレクトリを掃除

        # DEBUG_KEEP_TMP=1 のときは消さない（調査用）
        if os.getenv("DEBUG_KEEP_TMP", "0") != "1":
            shutil.rmtree(run_dir, ignore_errors=True)
