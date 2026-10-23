# ============================================================
# Cloud Run / API 用 ラッパー（最小修正）
#
# 目的:
# - Colab専用の pip / files.upload / getpass を排除し、非対話環境で動くようにする
# - 既存のプロンプト/判定ロジックは触らない（下の「セル3」以降）
# - 入力: stdin から JSON（API payload）
# - 出力: WORKDIR/check_result.json を生成し、その内容を stdout に JSON で出力
# ============================================================

import os
import sys
import json
import base64
import traceback
from pathlib import Path
import time
import builtins
def print(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    return builtins.print(*args, **kwargs)
# Anthropic APIキーは環境変数から取得（Cloud Run の環境変数で設定）
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
RETRY_WAIT_SECONDS = int(os.getenv("RETRY_WAIT_SECONDS", "10"))
RETRY_MAX = int(os.getenv("RETRY_MAX", "3"))
if not ANTHROPIC_API_KEY:
    sys.stdout.write(json.dumps({"status":"error","message":"ANTHROPIC_API_KEY (or CLAUDE_API_KEY) is not set"}, ensure_ascii=False))
    sys.exit(2)

# 作業ディレクトリ（runner.py から渡される）
WORKDIR = os.getenv("WORKDIR", "/tmp")
Path(WORKDIR).mkdir(parents=True, exist_ok=True)



def call_claude_with_json_retry(*, create_fn, extract_text_fn, parse_fn, validate_fn=None, label="claude"):
    """
    Claude API呼び出し→テキスト抽出→JSON抽出(parse)→(任意でvalidate)までを
    JSONが取れない/形式が違う場合に待ってリトライする。
    """
    last_err = None
    last_raw = None

    for attempt in range(1, RETRY_MAX + 1):
        try:
            msg = create_fn()
            raw = extract_text_fn(msg)
            last_raw = raw

            obj = parse_fn(raw)  # parse_json_response(raw)

            if validate_fn is not None:
                validate_fn(obj)  # 形式が違えば例外を投げる

            return msg, obj

        except Exception as e:
            last_err = e
            if attempt < RETRY_MAX:
                time.sleep(RETRY_WAIT_SECONDS)
                continue
            raise RuntimeError(
                f"[{label}] JSON parse/validate failed after {RETRY_MAX} attempts. "
                f"last_error={type(last_err).__name__}: {last_err}\n"
                f"raw_head={repr((last_raw or '')[:400])}"
            ) from last_err


def validate_agent1_json(obj):
    # {"items":[{"level":...,"title":...,"detail":...},...]}
    if not isinstance(obj, dict) or "items" not in obj or not isinstance(obj["items"], list):
        raise ValueError("Agent1 JSON schema mismatch: missing items[]")
    for it in obj["items"]:
        if not isinstance(it, dict):
            raise ValueError("Agent1 JSON schema mismatch: item not dict")
        if it.get("level") not in ("ok", "warn", "error"):
            raise ValueError("Agent1 JSON schema mismatch: invalid level")
        if not isinstance(it.get("title", ""), str) or not isinstance(it.get("detail", ""), str):
            raise ValueError("Agent1 JSON schema mismatch: title/detail must be string")


def validate_agent3_json(obj):
    # {"summary":{...}, "sections":[...]}
    if not isinstance(obj, dict):
        raise ValueError("Agent3 JSON schema mismatch: not dict")

    s = obj.get("summary")
    if not isinstance(s, dict):
        raise ValueError("Agent3 JSON schema mismatch: missing summary")

    for k in ("ok_count", "warn_count", "error_count"):
        if k not in s or not isinstance(s[k], int):
            raise ValueError(f"Agent3 JSON schema mismatch: summary.{k} must be int")

    if s.get("overall") not in ("ok", "warn", "error"):
        raise ValueError("Agent3 JSON schema mismatch: summary.overall invalid")

    sections = obj.get("sections")
    if not isinstance(sections, list):
        raise ValueError("Agent3 JSON schema mismatch: sections must be list")

    for sec in sections:
        if not isinstance(sec, dict):
            raise ValueError("Agent3 JSON schema mismatch: section not dict")
        if not isinstance(sec.get("id", ""), str) or not isinstance(sec.get("title", ""), str):
            raise ValueError("Agent3 JSON schema mismatch: section id/title must be string")
        items = sec.get("items")
        if not isinstance(items, list):
            raise ValueError("Agent3 JSON schema mismatch: section.items must be list")
        for it in items:
            if not isinstance(it, dict):
                raise ValueError("Agent3 JSON schema mismatch: item not dict")
            if it.get("level") not in ("ok", "warn", "error"):
                raise ValueError("Agent3 JSON schema mismatch: invalid item.level")
            if not isinstance(it.get("title", ""), str) or not isinstance(it.get("detail", ""), str):
                raise ValueError("Agent3 JSON schema mismatch: title/detail must be string")
            v = it.get("values", {})
            if v is not None and not isinstance(v, dict):
                raise ValueError("Agent3 JSON schema mismatch: values must be dict or omitted")

def _split_pdfurls(v):
    if not v:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if not s:
        return []
    return [p.strip() for p in s.split("|,|") if p.strip()]

def _parse_s3_uri(uri: str):
    if not uri.startswith("s3://"):
        raise ValueError(f"Unsupported uri (expected s3://...): {uri}")
    no_scheme = uri[len("s3://"):]
    parts = no_scheme.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid s3 uri: {uri}")
    return parts[0], parts[1]

def _s3_client():
    import boto3
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

def _download_s3(uri: str, out_dir: Path, index: int):
    bucket, key = _parse_s3_uri(uri)
    base = Path(key).name or f"input_{index}.pdf"
    stem = Path(base).stem
    suffix = Path(base).suffix or ".pdf"
    local = out_dir / f"{stem}_{index}{suffix}"
    n = 1
    while local.exists():
        local = out_dir / f"{stem}_{index}_{n}{suffix}"
        n += 1
    _s3_client().download_file(bucket, key, str(local))
    return str(local)

def _parse_gs_uri(uri: str):
    if not uri.startswith("gs://"):
        raise ValueError(f"Unsupported uri (expected gs://...): {uri}")
    no_scheme = uri[len("gs://"):]
    parts = no_scheme.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid gs uri: {uri}")
    return parts[0], parts[1]

def _download_gcs(uri: str, out_dir: Path, index: int):
    # GCS からPDFをダウンロード（Cloud Run のサービスアカウント=ADC を使用）。
    from google.cloud import storage  # 遅延import
    bucket_name, key = _parse_gs_uri(uri)
    base = Path(key).name or f"input_{index}.pdf"
    stem = Path(base).stem
    suffix = Path(base).suffix or ".pdf"
    local = out_dir / f"{stem}_{index}{suffix}"
    n = 1
    while local.exists():
        local = out_dir / f"{stem}_{index}_{n}{suffix}"
        n += 1
    project = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    client = storage.Client(project=project) if project else storage.Client()
    client.bucket(bucket_name).blob(key).download_to_filename(str(local))
    return str(local)


def _read_payload():
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)

# payload -> (pdf_paths, json_data) を生成
try:
    payload = _read_payload()

    # PDF を WORKDIR にダウンロード
    pdf_paths = []
    for i, uri in enumerate(_split_pdfurls(payload.get("pdfurls")), start=1):
        if uri.startswith("s3://"):
            pdf_paths.append(_download_s3(uri, Path(WORKDIR), i))
        elif uri.startswith("gs://"):
            pdf_paths.append(_download_gcs(uri, Path(WORKDIR), i))
        else:
            raise ValueError(f"Unsupported pdf url scheme: {uri}")

    # OCR結果JSON（BS/PL/製造原価/販売費）を payload から構成
    json_data = {
        "BS": payload.get("BS", []) or [],
        "PL": payload.get("PL", []) or payload.get("pl", []) or [],
        "製造原価": payload.get("MFG", []) or payload.get("製造原価", []) or [],
        "販売費": payload.get("SGA", []) or payload.get("販売費", []) or [],
    }

except Exception as e:
    sys.stdout.write(json.dumps({
        "status": "error",
        "message": "input preparation failed",
        "detail": str(e),
        "trace": traceback.format_exc()[:4000],
    }, ensure_ascii=False))
    sys.exit(1)


# ============================================================
# セル3: チェック実行（3エージェント版）
#
# Agent1: PDF読取チェック    → Claude API（PDF画像を目視確認）
# Agent2: 数値検算           → Python（JSONを直接計算・確実）
# Agent3: 最終判定レビュアー → Claude API（矛盾・誤検出を除外）
# ============================================================
import anthropic
import re
import json
from pathlib import Path

from model_resolver import resolve_model
MODEL = resolve_model()   # CLAUDE_MODEL → claude-sonnet-4-6 → 使えるモデルへ自動フォールバック

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PERIODS = ["今期", "前期", "前々期"]


# ============================================================
# 共通ユーティリティ
# ============================================================
def load_pdf_as_base64(path):
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")

def parse_json_response(raw_text):
    idx_start = raw_text.find("```json")
    if idx_start != -1:
        idx_body = idx_start + len("```json")
        idx_end  = raw_text.rfind("```")
        if idx_end > idx_body:
            return json.loads(raw_text[idx_body:idx_end].strip())
    idx_open  = raw_text.find("{")
    idx_close = raw_text.rfind("}")
    if idx_open != -1 and idx_close > idx_open:
        return json.loads(raw_text[idx_open:idx_close+1].strip())
    raise ValueError(f"JSONを抽出できませんでした:\n{raw_text[:300]}")

def num(v):
    """JSON値を整数に変換（空文字・Noneは0）"""
    if v == "" or v is None:
        return 0
    return int(str(v).replace(",", ""))

import unicodedata

# 科目名の別の書き方（_norm() で表記をそろえたあとに比べる）
ALIASES = {
    "税引前当期純利益": ["税引前当期利益", "税金等調整前当期純利益", "税引前当期純損益"],
    "法人税及び住民税": ["法人税住民税及び事業税"],
    "当期純利益": ["当期利益", "当期純損益"],
    "経常利益": ["経常損益"],
    "営業利益": ["営業損益"],
}

def _norm(name):
    """科目名の表記ゆれをそろえる（全角半角・空白・【】・句読点・「(損失)」・末尾の「金額」）"""
    s = unicodedata.normalize("NFKC", str(name))
    s = re.sub(r"[(（][^)）]*損失[^)）]*[)）]", "", s)
    s = re.sub(r"[\s【】\[\]()（）、・,]", "", s)
    return re.sub(r"金額$", "", s)

def get(section_data, name, period):
    """指定科目・期のJSON金額を取得（科目名は _norm() でそろえて比べる。2026-10-23）
    「経常利益金額」「【特別損失】」「法人税、住民税及び事業税」のような書き方でも見つけられるようにした。
    これまでは完全一致のみで、見つからない科目の検算は黙って飛ばされていた。"""
    targets = {_norm(n) for n in [name] + ALIASES.get(name, [])}
    for row in section_data:
        if _norm(row["勘定科目"]) in targets:
            return num(row[period]["金額"])
    return None


# ============================================================
# ファイル読み込み
# ============================================================
print("=" * 60)
print("  ファイル読み込み")
print("=" * 60)
pdf_names    = [Path(p).name for p in pdf_paths]
pdf_b64_list = [load_pdf_as_base64(p) for p in pdf_paths]
# json_data はヘッダで payload から構成済み
bs  = json_data.get("BS", [])
pl  = json_data.get("PL", [])
mfg = json_data.get("製造原価", [])
print(f"PDF : {pdf_names}")
print(f"JSON: keys={list(json_data.keys())}")


# ============================================================
# Agent1: PDF読取チェック（Claude API）
# ============================================================
print("\n" + "=" * 60)
print("  Agent1: PDF読取チェック（Claude API）")
print("=" * 60)

# 読取データ（OCR結果）を、照合しやすい形（科目名と各期の金額だけ）にして Agent1 に渡す（2026-10-23）
def _compact_rows(section_data):
    rows = []
    for row in section_data:
        item = {"勘定科目": row.get("勘定科目", "")}
        for p in PERIODS:
            v = row.get(p, "")
            item[p] = v.get("金額", "") if isinstance(v, dict) else v
        rows.append(item)
    return rows

read_data_for_agent1 = json.dumps(
    {k: _compact_rows(v) for k, v in json_data.items() if v},
    ensure_ascii=False, indent=1
)

AGENT1_PROMPT = f"""あなたは決算書の読取結果の検査員です。
添付された決算書PDFと、下の「読取データ」（PDFをOCRで読み取った結果）を見て、次の2つをチェックしてください。

## チェック1：PDFの読取品質（kind: "quality"）
- PDF画像の鮮明度・傾き・ノイズ
- 文字の潰れ・かすれ・影による読みにくさ
- 墨消し（黒塗り）の範囲と読取への影響
- スキャン品質として問題のある箇所

## チェック2：PDFと読取データの照合（kind: "transcription"）
貸借対照表・損益計算書・販売費及び一般管理費・製造原価報告書のページについて、PDFに書かれている金額と読取データを科目ごと・期ごとに見比べ、次のものを挙げてください。
- 読取漏れ：PDFに金額が書かれているのに、読取データでは空欄・0・科目そのものが無いもの
- 読み違い：PDFと読取データで金額が違うもの（桁・符号（△・▲）を含む）
照合のルール:
- 期は決算日で判断する。「今期」が最も新しい決算期、「前期」がその1つ前、「前々期」がさらに1つ前。PDFが複数あるときは、どのPDFがどの期かを決算日で見分ける。
- 【特別損失】のような見出しの行に金額が書かれておらず、明細の行（固定資産廃棄損など）の右の列に金額がある場合は、その金額を見出しの合計として扱う。読取データの見出しの行が空欄なら読取漏れとする。
- 「1,000」と「1000」、全角・半角、科目名の書き方（「売上総利益金額」と「売上総利益」など）だけの違いは挙げない。
- 株主資本等変動計算書・個別注記表など、上の4種類以外のページは照合しない。
- PDFが読めず判断できない箇所は level:"warn" にし、推測で金額を書かない。
- PDFが1つも添付されていない場合は、チェック1・2とも行わず items を空の配列にする。
- 読取漏れ・読み違いは level:"error"、title は「【前期】特別損失の読取漏れ」のように期と科目を入れ、detail に「PDF：4／読取データ：空欄」のように両方の値を書く。
- 照合して問題が無かった場合は、level:"ok"・kind:"transcription" の項目を1つだけ出す（title「PDFと読取データの照合」）。

## 絶対に含めないこと
- 前期比・増減率などのコメント
- 財務内容に関する意見
- 合計の検算（別の担当が計算で確認する）

## 読取データ
```json
{read_data_for_agent1}
```

## 出力形式（JSON形式のみ・他のテキスト不可）
```json
{{
  "items": [
    {{
      "kind": "quality" or "transcription",
      "level": "ok" or "warn" or "error",
      "title": "チェック項目名",
      "detail": "1文で簡潔に"
    }}
  ]
}}
```
"""

agent1_blocks = []
for b64, name in zip(pdf_b64_list, pdf_names):
    agent1_blocks.append({
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        "title": name,
    })
agent1_blocks.append({"type": "text", "text": AGENT1_PROMPT})

def _create_agent1():
    return client.messages.create(
        model=MODEL, max_tokens=8192,   # 照合結果が増えるため 2048 → 8192（2026-10-23）
        messages=[{"role": "user", "content": agent1_blocks}]
    )

def _extract_text(msg):
    return "".join(b.text for b in msg.content if hasattr(b, "text"))

msg1, agent1_result = call_claude_with_json_retry(
    create_fn=_create_agent1,
    extract_text_fn=_extract_text,
    parse_fn=parse_json_response,
    validate_fn=validate_agent1_json,
    label="agent1"
)
print(f"完了 — トークン input:{msg1.usage.input_tokens:,} / output:{msg1.usage.output_tokens:,}")
print(f"検出件数: {len(agent1_result.get('items', []))} 件")


# ============================================================
# Agent2: 数値検算（Python — API不使用）
# ============================================================
print("\n" + "=" * 60)
print("  Agent2: 数値検算（Python）")
print("=" * 60)

agent2_items = []

def check(title, calc_val, json_val, period, detail_ok="", detail_ng=""):
    """計算値とJSON値を比較してアイテムを返す"""
    if calc_val == json_val:
        return {"level": "ok", "title": f"【{period}】{title}", "detail": detail_ok or "一致確認済み"}
    else:
        diff = calc_val - json_val
        return {
            "level": "error",
            "title": f"【{period}】{title}",
            "detail": detail_ng or f"計算値{calc_val:,} ≠ 読取値{json_val:,}（差額{diff:+,}）",
            "values": {"計算値": f"{calc_val:,}", "読取値": f"{json_val:,}"}
        }

# データが1つも無い期（1期分だけの決算書の前期・前々期など）は検算しない（2026-10-23）
# これまでは全部0どうしで「一致確認済み」と出ていた
def _period_has_data(p):
    for row in list(bs) + list(pl):
        try:
            v = row[p]["金額"] if isinstance(row.get(p), dict) else row.get(p)
            if num(v) != 0:
                return True
        except (ValueError, TypeError):
            return True   # 数値にできない値がある期は、データありとして扱う（データ型チェックで拾う）
    return False

# --- BS検算 ---
for p in PERIODS:
    if not _period_has_data(p):
        continue
    # 資産合計 = 負債合計 + 純資産合計
    sisan   = get(bs, "資産合計", p)
    fusai   = get(bs, "負債合計", p)
    junsisan= get(bs, "純資産合計", p)
    if all(v is not None for v in [sisan, fusai, junsisan]):
        agent2_items.append(check(
            "BS貸借バランス（資産 = 負債+純資産）",
            fusai + junsisan, sisan, p
        ))

    # 流動資産 = 当座資産 + 棚卸資産 + その他流動資産
    ryudo   = get(bs, "流動資産", p)
    touza   = get(bs, "当座資産", p)
    tana    = get(bs, "棚卸資産", p)
    other_r = get(bs, "その他流動資産", p)
    if all(v is not None for v in [ryudo, touza, tana, other_r]):
        agent2_items.append(check(
            "BS流動資産（当座+棚卸+その他）",
            touza + tana + other_r, ryudo, p
        ))

    # 固定資産 = 有形 + 無形 + 投資その他
    kotei   = get(bs, "固定資産", p)
    yukei   = get(bs, "有形固定資産", p)
    mukei   = get(bs, "無形固定資産", p)
    toushi  = get(bs, "投資その他の資産", p)
    if all(v is not None for v in [kotei, yukei, mukei, toushi]):
        agent2_items.append(check(
            "BS固定資産（有形+無形+投資）",
            yukei + mukei + toushi, kotei, p
        ))

# --- PL検算 ---
for p in PERIODS:
    if not _period_has_data(p):
        continue
    uritage  = get(pl, "売上高", p)
    genka    = get(pl, "売上原価", p)
    souri    = get(pl, "売上総利益", p)
    hankan   = get(pl, "販売費及び一般管理費", p)
    eigyo    = get(pl, "営業利益", p)
    gaishuu  = get(pl, "営業外収益", p)
    gaihi    = get(pl, "営業外費用", p)
    keijo    = get(pl, "経常利益", p)
    tokuri   = get(pl, "特別利益", p)
    tokuson  = get(pl, "特別損失", p)
    zeimai   = get(pl, "税引前当期純利益", p)
    zeikin   = get(pl, "法人税及び住民税", p)
    junri    = get(pl, "当期純利益", p)

    # 特別利益・特別損失の行が無い会社もあるので、経常利益と税引前利益があれば 0 として検算する（2026-10-23）
    if keijo is not None and zeimai is not None:
        tokuri = tokuri if tokuri is not None else 0
        tokuson = tokuson if tokuson is not None else 0
    # 「法人税等」（合計）があればそれを使い、無ければ「法人税、住民税及び事業税」に法人税等調整額を足す
    # （当期純利益 = 税引前 − 法人税、住民税及び事業税 − 法人税等調整額）
    zeikin_total = get(pl, "法人税等", p)
    chousei = get(pl, "法人税等調整額", p)
    if zeikin_total is not None:
        zeikin = zeikin_total
    elif zeikin is not None and chousei is not None:
        zeikin = zeikin + chousei

    if all(v is not None for v in [uritage, genka, souri]):
        agent2_items.append(check("PL売上総利益（売上高-売上原価）",
            uritage - genka, souri, p))

    if all(v is not None for v in [souri, hankan, eigyo]):
        agent2_items.append(check("PL営業利益（売上総利益-販管費）",
            souri - hankan, eigyo, p))

    if all(v is not None for v in [eigyo, gaishuu, gaihi, keijo]):
        agent2_items.append(check("PL経常利益（営業利益+営業外収益-営業外費用）",
            eigyo + gaishuu - gaihi, keijo, p))

    if all(v is not None for v in [keijo, tokuri, tokuson, zeimai]):
        agent2_items.append(check("PL税引前当期純利益（経常±特別損益）",
            keijo + tokuri - tokuson, zeimai, p))

    if all(v is not None for v in [zeimai, zeikin, junri]):
        agent2_items.append(check("PL当期純利益（税引前-法人税等）",
            zeimai - zeikin, junri, p))

# --- 製造原価検算 ---
for p in PERIODS:
    # 労務費内訳合計
    chin    = get(mfg, "賃金", p)
    zakkyu  = get(mfg, "雑給", p)
    houtei  = get(mfg, "法定福利費", p)
    kousei  = get(mfg, "厚生費", p)
    roumu   = get(mfg, "当期労務費", p)
    if all(v is not None for v in [chin, zakkyu, houtei, kousei, roumu]):
        agent2_items.append(check("製造原価：労務費内訳合計（賃金+雑給+法定福利+厚生）",
            chin + zakkyu + houtei + kousei, roumu, p))

    # 当期総製造費用 = 労務費 + 経費
    keihiTotal = get(mfg, "当期経費", p)
    sousei     = get(mfg, "当期総製造費用", p)
    if all(v is not None for v in [roumu, keihiTotal, sousei]):
        agent2_items.append(check("製造原価：労務費+経費=当期総製造費用",
            roumu + keihiTotal, sousei, p))

# --- 期間整合性（期末→期首）---
for cur, prev in [("今期", "前期"), ("前期", "前々期")]:
    kimatsu_prev = get(pl, "期末商品材料高", prev)
    kisho_cur    = get(pl, "期首商品材料高", cur)
    if kimatsu_prev is not None and kisho_cur is not None:
        agent2_items.append(check(
            f"期間整合性：{prev}末棚卸={cur}首棚卸",
            kimatsu_prev, kisho_cur, "",
            f"{prev}末{kimatsu_prev:,} = {cur}首{kisho_cur:,} 一致",
            f"{prev}末{kimatsu_prev:,} ≠ {cur}首{kisho_cur:,}（差額{kisho_cur-kimatsu_prev:+,}）"
        ))

# --- データ型チェック ---
for section_name, section_data in [("BS", bs), ("PL", pl), ("製造原価", mfg)]:
    for row in section_data:
        name = row["勘定科目"]
        for p in PERIODS:
            v = row[p]["金額"]
            if v != "" and not isinstance(v, (int, float)):
                try:
                    int(str(v).replace(",", ""))
                except ValueError:
                    agent2_items.append({
                        "level": "warn",
                        "title": f"データ型異常：{section_name}/{name}/{p}",
                        "detail": f"数値に変換できない値: {repr(v)}",
                        "values": {"読取値": repr(v)}
                    })

ok2   = sum(1 for i in agent2_items if i["level"] == "ok")
warn2 = sum(1 for i in agent2_items if i["level"] == "warn")
err2  = sum(1 for i in agent2_items if i["level"] == "error")
print(f"完了 — ✅ {ok2}件 / ⚠️ {warn2}件 / ❌ {err2}件")
for i in agent2_items:
    if i["level"] != "ok":
        print(f"  {'⚠️' if i['level']=='warn' else '❌'} {i['title']}: {i['detail']}")


# ============================================================
# Agent3: 最終判定レビュアー（Claude API）
# ============================================================
print("\n" + "=" * 60)
print("  Agent3: 最終判定レビュアー（Claude API）")
print("=" * 60)

agent2_summary = json.dumps(agent2_items, ensure_ascii=False, indent=2)
agent1_summary = json.dumps(agent1_result, ensure_ascii=False, indent=2)

AGENT3_PROMPT = f"""あなたは決算書チェックの最終判定者です。
以下の2つのエージェントの結果を統合し、最終チェック結果を作成してください。

## Agent1の結果（PDF読取品質チェック kind:"quality" と、PDFと読取データの照合 kind:"transcription"）
```json
{agent1_summary}
```

## Agent2の結果（Python数値検算・確実）
```json
{agent2_summary}
```

## 統合ルール（厳守）
1. Agent2が「error」と判定した項目は必ずerrorとして残すこと
2. Agent2の計算結果が「一致（ok）」の項目は ok のままにすること（Agent1の品質チェックの「計算が合わない」等の指摘で ok を覆さない）
3. Agent1の kind:"quality"（PDF品質）の指摘はそのまま採用してよい
4. Agent1の kind:"transcription"（PDFと読取データの照合）の指摘は、Agent2の検算結果と突き合わせて判断すること:
   a. Agent2のerrorと同じ期で、その差額をAgent1の読取漏れ・読み違いの金額で説明できる場合（例：差額 −545,449 ＝ 特別利益の読取漏れ 545,453 − 特別損失の読取漏れ 4）は、照合の指摘を error とし、Agent2のerrorの detail にも「原因：前期の特別利益 545,453 と特別損失 4 の読取漏れ（PDFとの照合）」のように原因を書き添えること
   b. Agent2の検算と矛盾しない（関係する検算が無い、または検算では見つからない種類の）読取漏れ・読み違いは error のまま残すこと
   c. 照合の指摘の金額を当てはめると、Agent2で ok だった検算が合わなくなる場合は、照合の指摘の方が誤りの可能性が高いので warn に下げ、detail に「検算は一致しているため要確認」と書くこと
   d. 根拠の金額（PDFの値と読取データの値）が書かれていない照合の指摘は warn にすること
5. 「計算は合っているが〜」「一致しているが〜」という理由の warn は全て ok に変更すること（4c を除く）
6. 前期比・増減率・経営判断コメントは一切含めないこと
7. warn/errorは「実際に数値が食い違っている、または読取漏れがある」場合のみ使用すること

## 出力形式（JSON形式のみ・他テキスト不可）
```json
{{
  "summary": {{
    "ok_count": 整数,
    "warn_count": 整数,
    "error_count": 整数,
    "overall": "ok" or "warn" or "error"
  }},
  "sections": [
    {{
      "id": "セクションID",
      "title": "セクション名",
      "items": [
        {{
          "level": "ok" or "warn" or "error",
          "title": "チェック項目名",
          "detail": "1〜2文で簡潔に",
          "values": {{"計算値": "（任意）", "読取値": "（任意）"}}
        }}
      ]
    }}
  ]
}}
```

セクション構成:
1. id:"pdf_quality"         PDF品質チェック（Agent1の kind:"quality" の結果）
1b. id:"transcription_check" PDFと読取データの照合（Agent1の kind:"transcription" の結果。統合ルール4で判断したもの。指摘が無い場合も ok の項目を1つ入れる。PDFが無く照合していない場合はこのセクションを出さない）
2. id:"bs_check"            貸借対照表の検算（Agent2の結果）
3. id:"pl_check"            損益計算書の検算（Agent2の結果）
4. id:"manufacturing_check" 製造原価報告書の検算（Agent2の結果）
5. id:"period_check"        期間整合性チェック（Agent2の結果）
6. id:"data_quality"        データ品質（Agent2のデータ型チェック結果）
"""

def _create_agent3():
    return client.messages.create(
        model=MODEL, max_tokens=8192,
        messages=[{"role": "user", "content": AGENT3_PROMPT}]
    )

msg3, final_result = call_claude_with_json_retry(
    create_fn=_create_agent3,
    extract_text_fn=_extract_text,   # Agent1で定義したものを流用可
    parse_fn=parse_json_response,
    validate_fn=validate_agent3_json,
    label="agent3"
)
print(f"完了 — トークン input:{msg3.usage.input_tokens:,} / output:{msg3.usage.output_tokens:,}")


# ============================================================
# 結果表示
# ============================================================
def display_results(result):
    EMOJI = {"ok": "✅", "warn": "⚠️ ", "error": "❌"}
    LABEL = {"ok": "OK    ", "warn": "要確認", "error": "エラー"}

    s = result.get("summary", {})
    overall = s.get("overall", "ok")
    print("\n" + "=" * 60)
    print(f"  {EMOJI.get(overall, '')} 最終チェック結果")
    print("=" * 60)
    print(f"  ✅ 正常   : {s.get('ok_count', 0)} 件")
    print(f"  ⚠️  要確認 : {s.get('warn_count', 0)} 件")
    print(f"  ❌ エラー : {s.get('error_count', 0)} 件")
    print("=" * 60)

    for section in result.get("sections", []):
        items = section.get("items", [])
        # warn/error のみのセクションはタイトル表示
        non_ok = [i for i in items if i.get("level") != "ok"]
        print(f"\n▌ {section.get('title', '')}")
        print("  " + "-" * 50)
        if not non_ok:
            print("  ✅ 全項目正常")
            continue
        for item in items:
            lv = item.get("level", "ok")
            if lv == "ok":
                continue   # ok は省略表示
            print(f"  {EMOJI[lv]} [{LABEL[lv]}] {item.get('title', '')}")
            if item.get("detail"):
                print(f"             {item['detail']}")
            v = item.get("values", {})
            if v:
                for k, val in v.items():
                    if val:
                        print(f"             {k}: {val}")


display_results(final_result)

# JSON保存
with open(str(Path(WORKDIR) / "check_result.json"), "w", encoding="utf-8") as f:
    json.dump(final_result, f, ensure_ascii=False, indent=2)
out_path = Path(WORKDIR) / "check_result.json"
print(f"結果を {out_path} に保存しました")

# トークン合計
total_in  = msg1.usage.input_tokens  + msg3.usage.input_tokens
total_out = msg1.usage.output_tokens + msg3.usage.output_tokens
print(f"APIトークン合計 — input:{total_in:,} / output:{total_out:,}")
# stdout に最終JSONを出力（APIレスポンス用）
sys.stdout.write(json.dumps(final_result, ensure_ascii=False) + "\n")