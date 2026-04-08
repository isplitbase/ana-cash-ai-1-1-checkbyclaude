import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../cash-ai-02
ORIGINAL_SCRIPT = PROJECT_ROOT / "app" / "pipeline" / "originals" / "colab101.py"


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


def run_colab101(payload: Any) -> Any:
    """
    payload を output.json として /tmp に配置し、
    colab101.py を実行して output_updated.json を返す。
    """
    run_dir = Path(tempfile.mkdtemp(prefix="cashai02_", dir="/tmp"))

    # 1) 入力を output.json として保存
    # colab101.py は output.json を読む仕様
    (run_dir / "output.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) 環境変数
    env = dict(os.environ)

    # colab101.py 側で HTML を作らない
    env["NO_HTML"] = "1"

    # もし OpenAI キーを使う処理がある場合に備えて（不要なら無視される）
    if "OPENAI_API_KEY" in env and "OPENAI_API_KEY2" not in env:
        env["OPENAI_API_KEY2"] = env["OPENAI_API_KEY"]

    # 3) 実行（python3 colab101.py）
    _run(["python3", str(ORIGINAL_SCRIPT)], cwd=run_dir, env=env)

    # 4) 結果を読む
    out_path = run_dir / "output_updated.json"
    if not out_path.exists():
        raise RuntimeError("output_updated.json が生成されませんでした（colab101.py の処理を確認してください）")

    return json.loads(out_path.read_text(encoding="utf-8"))
