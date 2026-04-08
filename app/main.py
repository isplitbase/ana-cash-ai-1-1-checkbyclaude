from fastapi import FastAPI, Body
from typing import Any, Dict

from app.pipeline.runner import run_check_by_claude

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/v1/checkbyclaude")
def checkbyclaude(payload: Dict[str, Any] = Body(...)):
    # 想定入力: ai_case_id / postingPeriod / BS / PL / pdfurls / ... など
    return run_check_by_claude(payload)

# /v1/pipeline は本APIのメインエンドポイント（呼ばれたら checkByClaude を実行）
# 互換のため /v1/checkbyclaude も残しています（どちらも同じ処理）
@app.post("/v1/pipeline")
def pipeline(payload: Dict[str, Any] = Body(...)):
    return run_check_by_claude(payload)
