import json
import re
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


def _extract_port(payload: Any) -> str | None:
    """payload から port を抽出（無ければ None）。"""
    try:
        if isinstance(payload, dict) and "port" in payload and payload["port"] is not None:
            v = str(payload["port"]).strip()
            return v if v else None
    except Exception:
        pass
    return None


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
    return p

def _patch_report_html_for_cloudrun(html_path: Path, port_value: str | None = None) -> None:
    """
    report.html 内の「保存」処理を、Google Colab ではなく EC2 上の PHP API に向けるためのパッチ。
    originals 配下を変更せず、生成後HTMLをアップロード直前に書き換える。
    """
    html = html_path.read_text(encoding="utf-8")

    # var payload = {...} に port を追加（Cloud Run の Python 側 payload.port をHTMLに埋め込む）
    if port_value is not None:
        js_port_literal = json.dumps(str(port_value))  # => "1234"
        # 1行形式: var payload = { data: ..., period_numbers: ... };
        html, n_payload = re.subn(
            r"var\s+payload\s*=\s*\{\s*data:\s*window\.reportData\s*\|\|\s*\[\]\s*,\s*period_numbers:\s*window\._periodNumbers\s*\|\|\s*\{\}\s*\}\s*;",
            lambda _m: f"var payload = {{ data: window.reportData || [], period_numbers: window._periodNumbers || {{}}, port: {js_port_literal} }};",
            html,
            count=1,
        )
        # もし改行・インデント形式なら、period_numbers 行の後ろに port 行を差し込む
        if n_payload == 0:
            html, _ = re.subn(
                r"(var\s+payload\s*=\s*\{[^\}]*period_numbers\s*:\s*window\._periodNumbers\s*\|\|\s*\{\}\s*)(\}\s*;)",
                lambda _m: _m.group(1) + f",\n                port: {js_port_literal}\n            " + _m.group(2),
                html,
                count=1,
                flags=re.DOTALL,
            )


    # safeInvokeSave(payload){...} の実装を差し替える
    pattern = re.compile(
        r"function\s+safeInvokeSave\s*\(\s*payload\s*\)\s*\{.*?\n\}\n\nfunction\s+showSimpleModal",
        re.DOTALL,
    )

    replacement = """function safeInvokeSave(payload){
      try{
        const port = (payload && typeof payload === "object" && payload.port !== undefined && payload.port !== null && String(payload.port).trim() !== "")
          ? String(payload.port).trim()
          : ((window.CASH_AI_PORT !== undefined && window.CASH_AI_PORT !== null && String(window.CASH_AI_PORT).trim() !== "")
              ? String(window.CASH_AI_PORT).trim()
              : "[port]");
        if (port.indexOf("[port]") !== -1){
          showSimpleModal("保存先ポートが未設定です（CASH_AI_PORT を設定してください）");
          return Promise.resolve(null);
        }

        const url = "https://z-lite.aitask.biz:" + port + "/sapis/cash_ai_03.php";

        // payload は {data: [...], period_numbers: {...}} 形式だが、
        // API へは output_updated.json と同じ「配列だけ」を送る。
        const dataToSend = (payload && typeof payload === "object" && Array.isArray(payload.data))
          ? payload.data
          : payload;

        return fetch(url, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(dataToSend)
        }).then(async (r) => {
          let data = null;
          let text = "";
          try{
            data = await r.json();
          }catch(_e){
            try{ text = await r.text(); }catch(__e){}
          }

          if (!r.ok){
            showSimpleModal("保存できませんでした");
            return { ok: false, status: r.status, data, text };
          }

          const ok = (data && typeof data === "object" && ("ok" in data)) ? !!data.ok : true;
          const excelUpdated = (data && typeof data === "object" && ("excel_updated" in data)) ? !!data.excel_updated : null;
          const excelError = (data && typeof data === "object" && ("excel_error" in data)) ? String(data.excel_error || "") : "";

          if (!ok){
            showSimpleModal("保存できませんでした");
          }else{
            if (excelUpdated === true){
              if (excelError && excelError.trim() !== ""){
                showSimpleModal("保存できました<br>（Excel転記：失敗）");
              }else{
                showSimpleModal("保存できました<br>（Excel転記：成功）");
              }
            }else if (excelUpdated === false){
              if (excelError && excelError.trim() !== ""){
                showSimpleModal("保存できました<br>（Excel転記：失敗）");
              }else{
                showSimpleModal("保存できました");
              }
            }else{
              showSimpleModal("保存できました");
            }
          }

          return data || { ok, text };
        }).catch(err => {
          console.error(err);
          showSimpleModal("保存できませんでした");
          return null;
        });

      }catch(e){
        console.error(e);
        showSimpleModal("保存できませんでした");
        return Promise.resolve(null);
      }
    }

    function showSimpleModal"""

    new_html, n = pattern.subn(replacement, html, count=1)
    if n == 0:
        # 想定した関数定義が見つからない場合は、末尾に override を差し込む
        override = """
<script>
// Override safeInvokeSave to call Cloud Run API instead of Colab kernel
(function(){
  if (typeof window.safeInvokeSave !== "function") return;
  window.safeInvokeSave = function(payload){
    try{
      const port = (payload && typeof payload === "object" && payload.port !== undefined && payload.port !== null && String(payload.port).trim() !== "")
          ? String(payload.port).trim()
          : ((window.CASH_AI_PORT !== undefined && window.CASH_AI_PORT !== null && String(window.CASH_AI_PORT).trim() !== "")
              ? String(window.CASH_AI_PORT).trim()
              : "[port]");
      if (port.indexOf("[port]") !== -1){
        window.showSimpleModal && window.showSimpleModal("保存先ポートが未設定です（CASH_AI_PORT を設定してください）");
        return Promise.resolve(null);
      }
      const url = "https://z-lite.aitask.biz:" + port + "/sapis/cash_ai_03.php";
      const dataToSend = (payload && typeof payload === "object" && Array.isArray(payload.data))
        ? payload.data
        : payload;
      return fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(dataToSend)})
        .then(r=>r.json().catch(()=>r.text().then(t=>({text:t}))))
        .catch(err=>{
          console.error(err);
          window.showSimpleModal && window.showSimpleModal("保存できませんでした");
          return null;
        });
    }catch(e){
      console.error(e);
      window.showSimpleModal && window.showSimpleModal("保存できませんでした");
      return Promise.resolve(null);
    }
  };
})();
</script>
"""
        if "</body>" in html:
            new_html = html.replace("</body>", override + "\n</body>")
        else:
            new_html = html + "\n" + override

    html_path.write_text(new_html, encoding="utf-8")


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

        _patch_report_html_for_cloudrun(html_path, port_value=_extract_port(payload))

        html_url = _upload_html_and_presign(html_path)

        return {"html": html_url, "data": data}

    finally:
        # 成功・失敗に関わらず /tmp 配下の作業ディレクトリを掃除

        # DEBUG_KEEP_TMP=1 のときは消さない（調査用）
        if os.getenv("DEBUG_KEEP_TMP", "0") != "1":
            shutil.rmtree(run_dir, ignore_errors=True)
