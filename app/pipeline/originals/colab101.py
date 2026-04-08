# -*- coding: utf-8 -*-
"""TCF_create_html_v2 (cash-ai)

colab101.20260228.py を Cloud Run でも runner101.py から実行できるように
I/O（output_updated.json / report.html）を colab101.py と互換にした版。

- NO_HTML=1 なら HTML生成/表示/保存をしない（デフォルト）
- NO_HTML=0 なら report.html を HTML_OUTPUT_PATH に保存する（runner が使用）
- DISABLE_EXCEL=1 なら Excel 転記をしない（デフォルト）
"""

#create_html
#

import json
import os

# Cloud Run では HTML 生成が不要なのでデフォルトで無効
NO_HTML = os.getenv("NO_HTML", "1") == "1"
# Excel 出力は不要（要求によりデフォルト無効）
DISABLE_EXCEL = os.getenv("DISABLE_EXCEL", "1") == "1"

try:
    from IPython.display import HTML, display
except Exception:
    HTML = None
    display = None

# --- Colab専用：JS→Python コールバック登録 ---
try:
    from google.colab import output as colab_output
    _IS_COLAB = True
except Exception:
    colab_output = None
    _IS_COLAB = False

# 保存先（Colab実行ディレクトリ）
OUTPUT_PATH = "output_updated.json"


# HTML出力先（Cloud Run でS3アップロードするため）
HTML_OUTPUT_PATH = os.getenv("HTML_OUTPUT_PATH", "report.html")
# Excel転記先（決算期=第何期・決算年月日）
EXCEL_PATH = "/content/CF付財務分析表（経営指標あり）_ReadingData.xlsx"
EXCEL_SHEET_NAME = "財務諸表（入力）"
# 各期: (決算年月日セル, 第何期セル)
EXCEL_PERIOD_CELLS = {"前々期": ("E4","E5"), "前期": ("G4","G5"), "今期": ("J4","J5")}


# ------------------------------------------------------------------
# 追加：行番号→Excel行番号の精密マッピングを付与（シート名・セル）
# ------------------------------------------------------------------
def add_precise_cell_references_to_data(data):
    # ご提示いただいた対応表のマッピング (行番号: Excel行番号)
    # 連続していない箇所（76→77, 111→112など）を正確に反映しています
    row_mapping = {
        1:6, 2:7, 3:8, 4:9, 5:10, 6:11, 7:12, 8:13, 9:14, 10:15,
        11:16, 12:17, 13:18, 14:19, 15:20, 16:21, 17:22, 18:23, 19:24, 20:25,
        21:26, 22:27, 23:28, 24:29, 25:30, 26:31, 27:32, 28:33, 29:34, 30:35,
        31:36, 32:37, 33:38, 34:39, 35:40, 36:41, 37:42, 38:43, 39:44, 40:45,
        41:46, 42:47, 43:48, 44:49, 45:50, 46:51, 47:52, 48:53, 49:54, 50:55,
        51:56, 52:57, 53:58, 54:59, 55:60, 56:61, 57:62, 58:63, 59:64, 60:65,
        61:66, 62:67, 63:68, 64:69, 65:70, 66:71, 67:72, 68:73, 69:74, 70:75,
        71:76, 72:77, 73:78, 74:79, 75:80, 76:81,
        77:83, 78:84, 79:87, 80:88, 81:93, 82:94, 83:95, 84:96, 85:97, 86:98,
        87:99, 88:100, 89:101, 90:102, 91:103, 92:104, 93:105, 94:106, 95:107, 96:108,
        97:109, 98:110, 99:111, 100:112, 101:113, 102:114, 103:115, 104:116, 105:117, 106:118,
        107:119, 108:120, 109:121, 110:122, 111:123, 112:129, 113:130, 114:131, 115:132, 116:133,
        117:134, 118:135, 119:136, 120:137, 121:138, 122:139, 123:140, 124:141, 125:142, 126:143,
        127:144, 128:145, 129:146, 130:147, 131:148, 132:149, 133:150, 134:151, 135:152, 136:153,
        137:154, 138:155, 139:156, 140:157, 141:158, 142:159, 143:160, 144:161, 145:162, 146:163,
        147:164, 148:165, 149:166, 150:167, 151:168, 152:169, 153:170, 154:171, 155:173, 156:174,
        157:177, 158:178, 159:179, 160:181, 161:182, 162:183, 163:184, 164:185
    }

    sheet_name = "財務諸表（入力）"
    current_period_col = ""  # エクセルの行番号。列はE,G,J

    for entry in data:
        row_num = entry.get("行番号")
        if row_num in row_mapping:
            excel_row = row_mapping[row_num]
            entry["シート名"] = sheet_name
            entry["セル"] = f"{current_period_col}{excel_row}"

    return data

# ------------------------------------------------------------------
# 0. Colab callback: JSから渡されたJSONをサーバ側（Colab側）で保存
#    ※保存前に「シート名」「セル」を付与して output_updated.json を上書き
# ------------------------------------------------------------------
def _save_output_updated_json(payload):
    print("★★★ SAVE FUNCTION CALLED ★★★")
    """
    payload は JS から渡される dict を想定:
      {
        "data": [ {行番号:..., ...}, ... ],
        "period_numbers": {"前々期": 11, "前期": 12, "今期": 13}
      }
    """
    try:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "payload must be a dict."}
        if "data" not in payload:
            return {"ok": False, "error": "payload missing 'data'."}

        data = payload["data"]
        if not isinstance(data, list):
            return {"ok": False, "error": "'data' must be a list."}

        for i, item in enumerate(data):
            if not isinstance(item, dict):
                return {"ok": False, "error": f"Item {i} is not an object."}
            if "行番号" not in item:
                return {"ok": False, "error": f"Item {i} missing 行番号."}

        print(any(r.get("行番号") == 160 for r in data))

        abs_path = os.path.abspath(OUTPUT_PATH)
        tmp_path = abs_path + f".tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, abs_path)

        exists = os.path.exists(abs_path)
        size = os.path.getsize(abs_path) if exists else -1

        # -----------------------------
        # Excel へ転記（決算年月日: E4/G4/J4, 第何期: E5/G5/J5）
        # -----------------------------
        excel_updated = False
        excel_error = ""

        # Cloud Run 等の並列実行時に共有ファイル(EXCEL_PATH)を書き換えないため、デフォルトで無効
        if DISABLE_EXCEL:
            return {
                "ok": True,
                "path": abs_path,
                "exists": exists,
                "size": size,
                "excel_updated": False,
                "excel_error": None
            }

        try:
            period_numbers = payload.get("period_numbers", {}) or {}
            if not isinstance(period_numbers, dict):
                raise ValueError("payload['period_numbers'] must be a dict.")

            # 期数：1以上の整数のみ許可（"11" / "11期" / "第11期" などは数字抽出で許容）
            cleaned = {}
            import re as _re
            for k in ["前々期", "前期", "今期"]:
                v = period_numbers.get(k, None)
                if v is None or v == "":
                    continue
                if isinstance(v, bool):
                    raise ValueError(f"{k} must be a positive integer.")

                if isinstance(v, (int, float)):
                    iv = int(v)
                    if float(v) != float(iv):
                        raise ValueError(f"{k} must be an integer.")
                    if iv < 1:
                        raise ValueError(f"{k} must be >= 1.")
                    cleaned[k] = iv
                    continue

                s = str(v).strip()
                digits = "".join(_re.findall(r"\d+", s))
                if digits == "":
                    raise ValueError(f"{k} must be a positive integer.")
                iv = int(digits)
                if iv < 1:
                    raise ValueError(f"{k} must be >= 1.")
                cleaned[k] = iv

            # 決算年月日（output.json から読んだ closing_dates を転記）
            dates = {
                "前々期": closing_dates.get("前々期", "") or "",
                "前期": closing_dates.get("前期", "") or "",
                "今期": closing_dates.get("今期", "") or "",
            }

            # Excel 転記
            try:
                from openpyxl import load_workbook
            except Exception as e:
                raise RuntimeError("openpyxl is required to write Excel.") from e

            if not os.path.exists(EXCEL_PATH):
                raise FileNotFoundError(f"Excel file not found: {EXCEL_PATH}")

            wb = load_workbook(EXCEL_PATH)
            if EXCEL_SHEET_NAME not in wb.sheetnames:
                raise KeyError(f"Sheet not found: {EXCEL_SHEET_NAME}")

            ws = wb[EXCEL_SHEET_NAME]

            for k, (cell_date, cell_period) in EXCEL_PERIOD_CELLS.items():
                # 決算年月日（常に転記）
                ws[cell_date].value = dates.get(k, "")

                # 第何期（入力がある場合は「●●期」、未入力なら「前々期/前期/今期」のまま転記）
                ws[cell_period].number_format = "@"
                if k in cleaned:
                    ws[cell_period].value = f"{cleaned[k]}期"
                else:
                    ws[cell_period].value = k

            wb.save(EXCEL_PATH)
            excel_updated = True

        except Exception as e:
            excel_updated = False
            excel_error = str(e)

        return {
            "ok": True,
            "path": abs_path,
            "exists": exists,
            "size": size,
            "excel_updated": excel_updated,
            "excel_error": excel_error
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


# Colab上なら callback を登録
if _IS_COLAB:
    colab_output.register_callback("save_output_updated_json", _save_output_updated_json)

# ------------------------------------------------------------------
# 1. データの読み込み
# ------------------------------------------------------------------
# output.json は従来の「行データ配列」形式と、
# 「決算期年月日 + data」形式の両方を受け入れる。
closing_dates = {"前々期": "", "前期": "", "今期": ""}

def _load_output_json_any(path: str):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        return loaded
    except Exception:
        return None

json_data = None
loaded1 = _load_output_json_any('output.json')
if loaded1 is not None:
    json_data = loaded1
else:
    loaded2 = _load_output_json_any('output (11).json')
    if loaded2 is not None:
        json_data = loaded2
    else:
        json_data = []

# 新形式: {"決算期年月日": {...}, "data": [ ... ]}
if isinstance(json_data, dict):
    cd = json_data.get("決算期年月日", {})
    if isinstance(cd, dict):
        closing_dates = {
            "前々期": str(cd.get("前々期", "") or ""),
            "前期": str(cd.get("前期", "") or ""),
            "今期": str(cd.get("今期", "") or ""),
        }
    json_rows = json_data.get("data", [])
    if json_rows is None:
        json_rows = []
else:
    # 旧形式: [ ... ]
    json_rows = json_data

data_dict = {}
for item in (json_rows or []):
    try:
        rn = int(item.get('行番号'))
    except Exception:
        # 行番号が不正な行はスキップ
        continue
    item['行番号'] = rn
    data_dict[rn] = item

# 名称の定義・修正
mapping = {
    77: "受取手形割引高",
    78: "受取手形裏書譲渡高",
    79: "経営資本額",
    80: "経常運転資金額",
    118: "期首-期末製品差額(V)",
    155: "配当金",
    156: "役員賞与",
    157: "常用従業員数（ﾊﾟｰﾄも換算）①",
    158: "行金役員数②",
    159: "①＋②",
    160: "加工高",
    161: "減価償却費合計",
    162: "キャッシュフロー（当期利益＋減価償却費－配当金－役員賞与）",
    163: "借入金合計",
    164: "人件費合計",
}
for k, v in mapping.items():
    if k in data_dict:
        data_dict[k]["勘定科目"] = v

# ------------------------------------------------------------------
# 2. 計算用ヘルパー関数
# ------------------------------------------------------------------
PERIOD_KEYS = ["前々期", "前期", "今期"]

def _get_num(row_no, col):
    v = data_dict.get(row_no, {}).get(col, 0)
    return float(v) if v is not None else 0.0

def _calc_borrowings_excel(period_key: str) -> float:
    """
    借入金合計（Excel式完全準拠）
    = F53 + F62 + F63 + F83
    F53 → 48行目
    F62 → 57行目
    F63 → 58行目
    F83 → 77行目
    """
    return (_get_num(48, period_key) +
        _get_num(57, period_key) +
        _get_num(58, period_key) +
        _get_num(77, period_key) +
        _get_num(78, period_key))

def _sum_v(row_min, row_max, col):
    s = 0.0
    for r in range(row_min, row_max + 1):
        # 89行目（当期労務費 合計）はSUMIF対象から除外
        if r == 89:
            continue
        row = data_dict.get(r, {})
        kubun = str(row.get("区分", "") or "").strip().upper()
        if kubun in ["V", "Ｖ"]:
            s += float(row.get(col, 0) or 0)
    return s

def _set_row_data(row_no, name, vals):
    if row_no not in data_dict:
        data_dict[row_no] = {"行番号": row_no, "勘定科目": name}
    data_dict[row_no]["勘定科目"] = name

    if "集計方法" not in data_dict[row_no] or data_dict[row_no].get("集計方法") in (None, "", '""', '\"\"'):
        data_dict[row_no]["集計方法"] = "自動計算"

    for pk in PERIOD_KEYS:
        data_dict[row_no][pk] = int(round(vals.get(pk, 0)))

    vv, vp, vc = [float(data_dict[row_no][k]) for k in PERIOD_KEYS]

    # =========================
    # 前年比増加率
    # =========================
    data_dict[row_no]["前期増減額"] = int(vp - vv)
    data_dict[row_no]["今期増減額"] = int(vc - vp)
    data_dict[row_no]["前期前年比増加率"] = int(round((vp / vv - 1) * 100)) if vv else 0
    data_dict[row_no]["今期前年比増加率"] = int(round((vc / vp - 1) * 100)) if vp else 0

# ------------------------------------------------------------------
# 3. 解析・ログ出力用関数（160, 162, 163行用）
# ------------------------------------------------------------------
debug_logs = []

def calc_and_log_metrics(col):
    # --- 既存の取得処理 ---
    r112 = _get_num(112, col); r114 = _get_num(114, col)
    r84  = _get_num(84, col);  r110 = _get_num(110, col)
    r118 = _get_num(118, col); r109 = _get_num(109, col)

    # --- 105行目周辺の集計（変動費合計） ---
    sumV1 = _sum_v(90, 104, col)

    # --- 【修正箇所】138行目と139行目の整合性ロジック ---

    # 1. JSONから「販売費及び一般管理費」の総額を直接取得（139行目）
    total_ga_139 = data_dict[139].get(col, 0) if 139 in data_dict else 0

    # 2. 内訳（121〜137行目）の合計を算出
    # _sum_v を使わず、区分に関係なく純粋に数値を合計します
    sum_details_121_137 = 0.0
    for r in range(121, 138): # 121から137まで
        sum_details_121_137 += _get_num(r, col)

    # 3. 138行目（その他雑費）を「差額」として算出
    other_expenses_138 = total_ga_139 - sum_details_121_137

    # 4. 検証用変数に総額をセット
    sumV2 = total_ga_139

    # --- データの反映 ---
    if 105 in data_dict:
        data_dict[105][col] = sumV1
    if 138 in data_dict:
        data_dict[138][col] = other_expenses_138
    if 139 in data_dict:
        data_dict[139][col] = total_ga_139

    # --- 利益等の計算 ---
    kakou = r112 - r114 - (r84 + sumV1 + r110 + r118 + sumV2 - r109)

    # ==========================================
    # データの反映（上書き順序に注意）
    # ==========================================
    if 105 in data_dict:
        data_dict[105][col] = sumV1

    if 138 in data_dict:
        data_dict[138][col] = other_expenses_138

    if 139 in data_dict:
        # ここで確実に元の総額を再代入します
        data_dict[139][col] = total_ga_139

    # 加工高（または利益系）の計算
    kakou = r112 - r114 - (r84 + sumV1 + r110 + r118 + sumV2 - r109)

    # ==========================================
    # データの反映
    # ==========================================
    if 105 in data_dict:
        data_dict[105][col] = sumV1

    # 138行目に計算した差額をセット
    if 138 in data_dict:
        data_dict[138][col] = other_expenses_138

    # 139行目は元の値を保持（または再セット）
    if 139 in data_dict:
        data_dict[139][col] = total_ga_139

    kakou = r112 - r114 - (r84 + sumV1 + r110 + r118 + sumV2 - r109)

    # ==========================================
    # 計算結果をデータに反映させる
    # ==========================================
    if 105 in data_dict:
        data_dict[105][col] = sumV1

    # 139行目が「PL記載値を採用」の場合は、ここでsumV2（元の値）を再代入、
    # もしくはこのifブロック自体を「自動計算させたい時だけ」動くように制限します。
    if 139 in data_dict and data_dict[139].get("集計方法") != "PL記載値を採用":
        data_dict[139][col] = sumV2
    # ==========================================

    r154 = _get_num(154, col); r161 = _get_num(161, col)
    r155 = _get_num(155, col); r156 = _get_num(156, col)
    cf = r154 + r161 - r155 - r156

    kariire = _calc_borrowings_excel(col)

    log = f"<div style='border-left:4px solid #17a2b8; padding:8px; margin:5px; background:#f0faff; font-family:monospace; font-size:12px;'>"
    log += f"<b>【データ解析実行ログ: {col}】</b><br>"
    log += f" <b>▶ 160.加工高: {kakou:,.0f}</b> (内訳: 売上等{r112-r114:,.0f} - 控除{r84+sumV1+r110+r118+sumV2:,.0f} - 他勘定{r109:,.0f})<br>"
    log += f" <b>▶ 162.CF: {cf:,.0f}</b> (内訳: 利益{r154:,.0f} + 償却(161行){r161:,.0f} - 配当{r155:,.0f} - 賞与{r156:,.0f})<br>"
    log += f" <b>▶ 163.借入金合計: {kariire:,.0f}</b> (内訳: 48行+57行+58行+77行+78行)<br>"
    log += "</div>"
    debug_logs.append(log)

    return {"kakou": kakou, "cf": cf, "kariire": kariire}

# ------------------------------------------------------------------
# 3.5. 追加項目（77-80行）の取込・計算
# ------------------------------------------------------------------

# 77-78行目：入力項目（前々期/前期/今期は手入力）
for rn in [77, 78]:
    name = mapping.get(rn, f"項目{rn}")
    if rn not in data_dict:
        data_dict[rn] = {"行番号": rn, "勘定科目": name}
        for pk in PERIOD_KEYS:
            data_dict[rn][pk] = 0
    data_dict[rn]["勘定科目"] = name
    data_dict[rn]["集計方法"] = "入力"
    _set_row_data(rn, name, {pk: _get_num(rn, pk) for pk in PERIOD_KEYS})
    data_dict[rn]["集計方法"] = "入力"

# 79-80行目：集計項目（Pythonで計算）
for rn in [79, 80]:
    name = mapping.get(rn, f"項目{rn}")
    vals = {}
    for pk in PERIOD_KEYS:
        if rn == 79:
            vals[pk] = _get_num(45, pk) - _get_num(30, pk) - _get_num(34, pk)
        elif rn == 80:
            vals[pk] = (_get_num(4, pk) + _get_num(3, pk) + _get_num(11, pk) + _get_num(77, pk) + _get_num(78, pk)
                - (_get_num(46, pk) + _get_num(47, pk) + _get_num(78, pk)))
    _set_row_data(rn, name, vals)

# ------------------------------------------------------------------
# 4. メイン集計実行ループ（155-164）
# ------------------------------------------------------------------
print("LOG: メイン集計実行ループを開始します") # そもそもループに入ったか確認

for rn in range(155, 165):
    name = mapping.get(rn, f"項目{rn}")
    vals = {}

# A. 161行目（減価償却費合計）の強制計算
    if rn == 161:
        for pk in PERIOD_KEYS:
            # _get_num を使い、データがなくても 0.0 を確保
            v90 = _get_num(90, pk)
            v125 = _get_num(125, pk)  # ← 追加：今回集計した125行目を取得
            v126 = _get_num(126, pk)

            # 125行目も含めて合計を算出
            total_dep = v90 + v125 + v126
            vals[pk] = total_dep

            # 画面表示用のデータ辞書を直接更新
            if 161 in data_dict:
                data_dict[161][pk] = total_dep

            # 【強制ログ】125行目が含まれていることを確認できるように修正
            print(f"★★★ 161行目計算確定({pk}): 90行({v90}) + 125行({v125}) + 126行({v126}) = {total_dep}")

    # B. その他の自動計算行
    elif rn == 159:
        vals = {pk: (_get_num(157, pk) + _get_num(158, pk)) for pk in PERIOD_KEYS}

    elif rn in [160, 162, 163]:
        # results の計算中にエラーが出ても止まらないように処理
        try:
            results = {pk: calc_and_log_metrics(pk) for pk in PERIOD_KEYS}
            if rn == 160:
                vals = {pk: results[pk]["kakou"] for pk in PERIOD_KEYS}
            elif rn == 162:
                vals = {pk: results[pk]["cf"] for pk in PERIOD_KEYS}
            elif rn == 163:
                vals = {pk: results[pk]["kariire"] for pk in PERIOD_KEYS}
        except Exception as e:
            print(f"ERROR: {rn}行目の計算中にエラー: {e}")
            vals = {pk: 0 for pk in PERIOD_KEYS}

    elif rn == 164:
        vals = {pk: (_get_num(89, pk) + _get_num(121, pk) + _get_num(122, pk) + _get_num(123, pk) + _get_num(124, pk)) for pk in PERIOD_KEYS}

    # C. 通常の入力行（155, 156, 157, 158 など）
    else:
        vals = {pk: _get_num(rn, pk) for pk in PERIOD_KEYS}

    # 最終的な値をセット（前期比なども自動計算される）
    _set_row_data(rn, name, vals)

print("LOG: メイン集計実行ループが終了しました")

# ==========================================
# ★ 全計算確定後に構成比を再計算（A案）A-1
# ==========================================

def recalc_all_component_ratios():

    for period in PERIOD_KEYS:

        total_asset = float(data_dict.get(45, {}).get(period, 0))   # 資産合計
        total_liab  = float(data_dict.get(75, {}).get(period, 0))   # 負債純資産合計
        total_mfg   = float(data_dict.get(111, {}).get(period, 0))  # 製造原価合計
        total_sales = float(data_dict.get(112, {}).get(period, 0))  # 売上高

        for row_no, row in data_dict.items():

            val = float(row.get(period, 0))

            if row_no <= 45 or row_no in [79, 80]:
                denom = total_asset
            elif row_no <= 78:
                denom = total_liab
            elif row_no <= 111:
                denom = total_mfg
            else:
                denom = total_sales

            ratio = (val / denom * 100) if denom else 0

            row[f"{period}構成比"] = round(ratio, 2)


# 必ずここで実行（json_output生成前）
recalc_all_component_ratios()
print("LOG: 構成比再計算完了")

# ===== ここに貼る =====
print("45:", data_dict.get(45))
print("79:", data_dict.get(79))
print("45 前期:", data_dict.get(45, {}).get("前期"))
print("79 前期:", data_dict.get(79, {}).get("前期"))
print("79 前期構成比:", data_dict.get(79, {}).get("前期構成比"))
# =====================

json_output = sorted(data_dict.values(), key=lambda x: x.get("行番号", 0))
# ==========================================
# ★ 全行確定後に構成比を再計算する ★
# ==========================================

def recalc_all_component_ratios():
    for period in PERIOD_KEYS:

        total_asset = float(data_dict.get(45, {}).get(period, 0))   # 資産合計
        total_liab  = float(data_dict.get(75, {}).get(period, 0))   # 負債純資産合計
        total_mfg   = float(data_dict.get(111, {}).get(period, 0))  # 製造原価合計
        total_sales = float(data_dict.get(112, {}).get(period, 0))  # 売上高

        for row_no, row in data_dict.items():

            val = float(row.get(period, 0))

            # 分母決定ロジック
            if row_no <= 45 or row_no in [79, 80]:
                denom = total_asset
            elif row_no <= 78:
                denom = total_liab
            elif row_no <= 111:
                denom = total_mfg
            else:
                denom = total_sales

            ratio = (val / denom * 100) if denom else 0

            row[f"{period}構成比"] = round(ratio, 2)

recalc_all_component_ratios()

print("79 前期構成比:", data_dict[79]["前期構成比"])
print("45 前期:", data_dict[45]["前期"])
# 実行


# ------------------------------------------------------------------
# 5. 表示用 HTML/CSS/JS 生成（デバッグログは非表示：復活可）
# ------------------------------------------------------------------

style = """
<style id="report-styles">
    .report-title { font-size: 18px; font-weight: bold; margin: 25px 0 8px 0; color: #333; border-left: 5px solid #333; padding-left: 10px; }

.excel-table {
    border-collapse: collapse;
    width: fit-content !important;
    display: inline-table !important;
    font-family: "Meiryo", sans-serif;
    font-size: 13px;
    table-layout: fixed !important;

    /* ★ここが解決策Bの核：外枠2pxを border ではなく outline で描く */
    border: 0;                 /* 2px border をやめる */
    outline: 2px solid #333;    /* 外側に2pxの枠 */
    outline-offset: 0;          /* ずらさない */
    /* 任意：outlineが弱い環境で外枠を確実に見せる */
    box-shadow: 0 0 0 2px #333;
    margin-bottom: 20px;
}



    .excel-table th, .excel-table td {
        border-top: 0;
        border-left: 1px solid #999;
        border-bottom: 1px solid #999;
        border-right: 0;
        padding: 4px 6px;
        overflow: hidden;
        white-space: nowrap !important;
        text-overflow: clip;
        box-sizing: border-box;
    }
    .excel-table tr > *:last-child {
        border-right: 1px solid #999;
    }


    /* 最終行に下外枠を付ける（tbody 内の最後の行） */
    .excel-table tbody tr:last-child > td {
        border-bottom: 1px solid #999;
    }


    .excel-table th { background-color: #f2f2f2; text-align: center; font-weight: bold; }

    .w-v { width: 28px !important; }
    .w-subject { width: 300px !important; }

    .excel-table col.c-amt { width: 180px !important; }
    th.col-amt, td.col-amt { width: 180px !important; text-align: right !important; font-family: "Consolas", monospace; }
    th.col-amt { text-align: center !important; }

/* clickable period header */
th.clickable-period{cursor:pointer;text-decoration:underline;}
th.clickable-period:hover{background:#e8f0ff;}
th.clickable-period:focus{outline:2px solid #4d90fe;outline-offset:-2px;}

    .excel-table col.c-pct { display: none !important; width: 0px !important; }
    .col-pct { display: none !important; width: 60px !important; text-align: center !important; font-size: 11px; color: #666; }

    .excel-table col.c-diff { display: none !important; width: 0px !important; }
    .col-diff, .diff-group { display: none !important; width: 180px !important; text-align: right !important; font-family: "Consolas", monospace; }
    th.col-diff, th.diff-group { text-align: center !important; }

    .excel-table col.c-memo { width: 300px !important; }
    td.col-memo { width: 300px !important; text-align: left !important; white-space: normal !important; }

    .show-all .excel-table col.c-pct { display: table-column !important; width: 60px !important; }
    .show-all .excel-table col.c-diff { display: table-column !important; width: 180px !important; }
    .show-all .col-pct, .show-all .col-diff, .show-all .diff-group { display: table-cell !important; }

    .btn-container { position: sticky; top: 0; background: white; z-index: 100; padding: 10px 0; display: flex; gap: 10px; border-bottom: 1px solid #ddd; }
    .btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;

  padding: 8px 16px;          /* ← サイズ基準（表示切替に合わせる） */
  min-width: 120px;           /* ← 横幅を揃える（重要） */
  font-size: 14px;
  font-weight: 500;

  border: none;
  border-radius: 6px;
  cursor: pointer;

  background: #e5e7eb;        /* 表示切替の色 */
  color: #111827;

  transition: background 0.15s ease, transform 0.1s ease;
}
.btn:hover {
  transform: translateY(-1px);
}

.btn:active {
  transform: translateY(0);
}
    .save-panel { margin-top: 20px; padding: 15px; border: 1px solid #ddd; background: #fff; display: flex; justify-content: flex-end; }
    .btn-save {
  background: #2563eb;
  color: #ffffff;
}
    /* --- ヘッダの段間で縦線が切れて見えるのを防ぐ（強制的に段間の横線を描く） --- */
.excel-table thead tr:first-child th {
    border-bottom-color: #999 !important;
}

.excel-table thead tr + tr th {
    border-top-color: #999 !important;
}
/* 小数px丸めによる罫線の“抜け”を軽減 */
.excel-table {
    transform: translateZ(0);
}


input:focus {
    outline: none;
    border: 2px solid #3498db; /* 入力中のセルを強調 */
    background-color: #fff;
}

/* 区分セル（F/V）をクリック可能に見せる（ベストプラクティス） */
/* 区分セル（F/V）をクリック可能に見せる（ベストプラクティス）
   - 狭い列幅(28px)に収めるため固定幅＋ゼロパディング
   - button を使い、キーボード操作(Enter/Space)も自然に対応
*/
.kubun-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;              /* 28px列内に収める */
    min-width: 24px;
    height: 22px;
    padding: 0;
    margin: 0;
    border: 1px solid #666;
    border-radius: 4px;
    background: #fff;
    font-weight: 700;
    font-size: 12px;
    line-height: 1;
    cursor: pointer;
    user-select: none;
    box-sizing: border-box;
}
.kubun-toggle:hover {
    background: #f5f5f5;
}
.kubun-toggle:active {
    transform: translateY(1px);
}
.kubun-toggle:focus-visible {
    outline: 2px solid #3498db;
    outline-offset: 2px;
}
.kubun-toggle[disabled] {
    opacity: 0.6;
    cursor: not-allowed;
}

.kubun-cell { padding: 0 !important; text-align: center !important; }


/* 区分セル（F/V）を列幅内に収める */
td.kubun-cell { padding: 0 !important; text-align: center !important; }
.kubun-toggle { width: 24px !important; min-width: 24px !important; padding: 0 !important; }

/* ===== Simple Modal (Modern) ===== */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45); /* slate系 */
  z-index: 999999;
  backdrop-filter: blur(2px);
}

.modal-card {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(0.96);
  background: #ffffff;
  min-width: 260px;
  max-width: 360px;
  padding: 24px 22px 20px;
  border-radius: 14px;
  box-shadow:
    0 20px 40px rgba(0, 0, 0, 0.18),
    0 2px 6px rgba(0, 0, 0, 0.12);
  text-align: center;
  opacity: 0;
  transition: all 0.18s ease-out;
}

.modal-overlay.show .modal-card {
  opacity: 1;
  transform: translate(-50%, -50%) scale(1);
}

.modal-message {
  font-size: 15px;
  line-height: 1.6;
  color: #0f172a; /* slate-900 */
  margin-bottom: 18px;
}

.modal-ok-btn {
  appearance: none;
  border: none;
  border-radius: 9999px;
  padding: 8px 22px;
  font-size: 14px;
  font-weight: 600;
  background: linear-gradient(135deg, #22c55e, #16a34a);
  color: #111827;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease, opacity 0.12s ease;
}

.modal-ok-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(34, 197, 94, 0.35);
}

.modal-ok-btn:active {
  transform: translateY(0);
  box-shadow: none;
  opacity: 0.9;
}
/* ボタンコンテナ（横並び） */
.btn-container.vertical {
  display: flex;
  flex-direction: row;      /* ← 横並び */
  gap: 12px;                /* ボタン間隔 */
  align-items: center;
  margin: 16px 0;
}


/* 保存ボタンを少し強調 */
.btn-save {
  background: #2563eb;
}


/* --- Modern message modal --- */
.modal-overlay{
  position: fixed; inset: 0;
  background: rgba(10,12,20,0.45);
  backdrop-filter: blur(6px);
  display:none; align-items:center; justify-content:center;
  z-index: 99999;
}
.modal-overlay.show{display:flex;}
.modal-card.modern{
  width: min(520px, calc(100% - 40px));
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,255,255,0.86));
  box-shadow: 0 18px 60px rgba(0,0,0,0.25);
  border: 1px solid rgba(255,255,255,0.55);
  overflow:hidden;
}
.modal-header{
  display:flex; align-items:center; justify-content:space-between;
  padding: 12px 14px;
  background: linear-gradient(90deg, rgba(76,110,245,0.16), rgba(34,197,94,0.10));
}
.modal-title{font-weight:700; color:#1f2937;}
.modal-x{
  border:none; background: transparent; cursor:pointer;
  font-size: 18px; line-height: 1;
  padding: 4px 8px; border-radius: 8px;
}
.modal-x:hover{background: rgba(0,0,0,0.06);}
.modal-message{padding: 12px 14px; color:#111827; white-space:pre-wrap;}
.modal-actions{padding: 12px 14px; display:flex; justify-content:flex-end; gap: 8px;}
.modal-ok-btn{
  border: 1px solid rgba(0,0,0,0.18);
  background: rgba(255,255,255,0.75);
  color: #111827;
  padding: 8px 14px;
  border-radius: 10px;
  cursor:pointer;
  font-weight: 600;
}
.modal-ok-btn:hover{background: rgba(255,255,255,0.95);}

/* --- Period editor modal --- */
.period-overlay{
  position: fixed; inset: 0;
  background: radial-gradient(1200px 600px at 20% 10%, rgba(76,110,245,0.35), transparent 60%),
              radial-gradient(900px 500px at 80% 20%, rgba(34,197,94,0.28), transparent 60%),
              rgba(10,12,20,0.55);
  backdrop-filter: blur(8px);
  display:none;
  align-items:center; justify-content:center;
  z-index: 100000;
}
.period-overlay.show{display:flex;}
.period-card{
  width: min(560px, calc(100% - 40px));
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,255,255,0.82));
  box-shadow: 0 22px 70px rgba(0,0,0,0.35);
  border: 1px solid rgba(255,255,255,0.55);
  overflow:hidden;
}
.period-top{
  display:flex; align-items:center; gap: 10px;
  padding: 14px 16px;
  background: linear-gradient(90deg, rgba(76,110,245,0.18), rgba(34,197,94,0.12));
}
.period-badge{
  width: 40px; height: 40px;
  border-radius: 12px;
  display:flex; align-items:center; justify-content:center;
  font-weight: 800;
  background: rgba(255,255,255,0.65);
  border: 1px solid rgba(0,0,0,0.10);
}
.period-head{flex:1;}
.period-title{font-size: 16px; font-weight: 800; color:#111827;}
.period-sub{font-size: 12px; color:#4b5563; margin-top: 2px;}
.period-x{
  border:none; background: rgba(255,255,255,0.55);
  cursor:pointer;
  width: 34px; height: 34px;
  border-radius: 12px;
  font-size: 18px;
}
.period-x:hover{background: rgba(255,255,255,0.85);}
.period-body{padding: 14px 16px 6px 16px;}
.period-label{display:block; font-size: 12px; color:#374151; margin-bottom: 6px; font-weight: 700;}
.period-input{
  width: 100%;
  font-size: 18px;
  padding: 12px 12px;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.16);
  background: rgba(255,255,255,0.8);
  outline: none;
}
.period-input:focus{border-color: rgba(76,110,245,0.6); box-shadow: 0 0 0 4px rgba(76,110,245,0.15);}
.period-hint{margin-top: 8px; font-size: 12px; color:#6b7280;}
.period-error{margin-top: 10px; font-size: 12px; color:#b91c1c; background: rgba(185,28,28,0.08); border: 1px solid rgba(185,28,28,0.25); padding: 8px 10px; border-radius: 12px;}
.period-actions{
  padding: 12px 16px 16px 16px;
  display:flex; justify-content:flex-end; gap: 10px;
}
.period-btn{
  padding: 10px 14px;
  border-radius: 12px;
  cursor:pointer;
  font-weight: 700;
  border: 1px solid rgba(0,0,0,0.16);
  background: rgba(255,255,255,0.65);
}
.period-btn.ghost:hover{background: rgba(255,255,255,0.90);}
.period-btn.primary{
  border: 1px solid rgba(76,110,245,0.35);
  background: linear-gradient(90deg, rgba(76,110,245,0.95), rgba(34,197,94,0.85));
  color: white;
}
.period-btn.primary:hover{filter: brightness(1.03);}
.debit-credit-alert td {
    background-color: #ffff00 !important;
}

</style>
"""

# ------------------------------------------------------------------
# 5. 追加：タイトル行と列の定義（左側0～3列の見出し配置）
# ------------------------------------------------------------------
SPEC_PATH = "タイトル行と列の定義.txt"


SPEC_TEXT_EMBEDDED = r'''■全体レイアウト
以下の７つのブロックがあります。
・第１ブロック
大見出し：貸借対照表（B/S）
タイトル行：
明細行：1～76
・第２ブロック
大見出し：入力項目
タイトル行：
明細行：77～78
・第３ブロック
大見出し：集計項目
タイトル行：
明細行：79～80
・第４ブロック
大見出し：製造原価報告書
タイトル行：
明細行：81～111
・第５ブロック
大見出し：損益計算書（P/L）
タイトル行：
明細行：112～154
・第６ブロック
大見出し：入力項目／集計項目
タイトル行：
明細行：155～159
・第７ブロック
大見出し：集計項目
タイトル行：
明細行：160～164

■タイトルの定義
(列の定義)
・列は0～1の2行とする。
（行番号,列番号,表示文字,hは横書きvは縦書き,カラーコード,枠線の情報）
・列番号は0～15
[a,b]という記述は、a以上b未満で、bは含みません。
([0,2],[0,4],項目,h,0)
([0,1],[4,5],前々期,h,0,下線なし)
([1,2],[4,5],{決算年月日_前々期},h,0,上線なし)
([0,2],[5,6],構成比%,v,0)
([0,1],[6,7],前期,h,0,下線なし)
([1,2],[6,7],{決算年月日_前期},h,0,上線なし)
([0,2],[7,8],構成比%,v,0)
([0,2],[8,9],前年比増加率%,v,0)、タイトルの前年比増加率%が縦書きで左から右へ折り返すこと
([0,2],[9,10],今期,h,0,下線なし)
([1,2],[9,10],{決算年月日_今期},h,0,上線なし)
([0,2],[10,11],構成比%,v,0)
([0,2],[11,12],前年比増加率%,v,0)、タイトルの前年比増加率%が縦書きで左から右へ折り返すこと
([0,1],[12,14],増減額,h,0)
([1,2],[12,13],前期,h,0)
([1,2],[13,14],今期,h,0,右線なし)
([0,2],[14,15],備考,h,0)

■列幅の定義（ピクセル）
0列目から以下の列幅とする
(28，28，28，300,180,60,180,60,60,180,60,60,180,180,300)
列幅の調整は14列目で行う
前年比増加率%は前年比で折り返す

■カラーコード
階層    英語表記例    カラーコード
0.　タイトル　Title  #f2f2f2
1. 総合計    Grand Total    #d9ead3
2. 合計    Total    #2E86C1
3. 中計    Intermediate Total    #85C1E9
4. 小計    Subtotal    #e6f3ff
5. 明細行 Detail #ffffff

■行列要素の定義：
（行番号,列番号,表示文字,hは横書きvは縦書き,色番号,罫線制御）

第１ブロックの項目見出しの定義
0～3列目について見出しを作成します。
([1,46],[0,1],資産の部,v,1,右線なし)
([1,24],[1,2],流動資産,v,2,右線なし)
([23,24],[2,4],流動資産合計,h,2,左線なし)
([24,45],[1,2],固定資産,v,2,右線なし)
([44,45],[2,4],固定資産合計,h,2,左線なし)
([45,46],[1,4],資産合計,h,1,左線なし)
([1,7],[2,3],当座資産,v,3,右線なし)
([6,7],[3,4],小計,h,3,左線なし)
([7,12],[2,3],棚卸資産,v,3,右線なし)
([11,12],[3,4],小計,h,3,左線なし)
([12,23],[2,3],その他流動資産,v,3,右線なし)
([22,23],[3,4],小計,h,3,左線なし)
([24,33],[2,3],有形固定資産,v,3)
([32,33],[3,4],小計,h,3,左線なし)
([33,34],[2,4],無形固定資産,h,3)
([34,43],[2,3],投資等,v,3)
([42,43],[3,4],小計,h,3,左線なし)
([43,44],[2,4],繰延資産,h,3)
([1,2],[3,4],現金・預金,h,5)
([2,3],[3,4],（うち定期預金）,h,5)
([3,4],[3,4],受取手形,h,5)
([4,5],[3,4],売掛金,h,5)
([7,8],[3,4],製品・商品,h,5)
([8,9],[3,4],原材料,h,5)
([9,10],[3,4],仕掛品,h,5)
([20,21],[3,4],貸倒引当金（▲）,h,5)
([24,25],[3,4],建物付属設備,h,5)
([25,26],[3,4],構築物,h,5)
([26,27],[3,4],機械装置,h,5)
([27,28],[3,4],車両運搬具,h,5)
([28,29],[3,4],什器・備品,h,5)
([29,30],[3,4],土地,h,5)
([30,31],[3,4],建設仮勘定,h,5)
([38,39],[3,4],関係会社株式,h,5)
([39,40],[3,4],保険積立金,h,5)
([40,41],[3,4],貸倒引当金（▲）,h,5)
([41,42],[3,4],長期前払費用,h,5)
([46,66],[0,1],負債の部,v,1,右線なし)
([65,66],[1,4],負債合計,h,1,左線なし)
([66,75],[0,1],純資産の部,v,1,右線なし)
([74,75],[1,4],純資産合計,h,1,左線なし)
([75,76],[0,4],負債・純資産合計,h,1)
([46,57],[1,3],流動負債,v,2,右線なし)
([56,57],[3,4],流動負債合計,h,2,左線なし)
([57,65],[1,3],固定負債,v,2,右線なし)
([64,65],[3,4],固定負債合計,h,2,左線なし)
([66,72],[1,3],資本等,v,2,右線なし)
([71,72],[3,4],資本等小計,h,2,左線なし)
([72,73],[1,4],自己株式(▲),h,5)
([73,74],[1,4],"",h,5)
([46,47],[3,4],支払手形,h,5)
([47,48],[3,4],買掛金,h,5)
([53,54],[3,4],未払法人税等,h,5)
([54,55],[3,4],未払消費税,h,5)
([59,60],[3,4],設備支払手形,h,5)
([66,67],[3,4],資本金,h,5)
([67,68],[3,4],資本剰余金,h,5)
([68,69],[3,4],利益剰余金,h,5)
([69,70],[3,4],うち準備金、積立金,h,5)
([70,71],[3,4],うち繰越利益剰余金,h,5)
([76,77],[0,4],借方／貸方照合,h,5)
第２ブロックの項目見出しの定義
0～3列目について見出しを作成します。
([77,78],[0,4],受取手形割引高,h,5)
([78,79],[0,4],受取手形裏書譲渡高,h,5)

第３ブロックの項目見出しの定義
0～3列目について見出しを作成します。
([79,80],[0,4],経営資本額（総資本-建設仮勘定-投資等-繰延資産),h,5)
([80,81],[0,4],経常運転資金額（売上債権＋棚卸資産－買入債務）,h,5)

第４ブロックの項目見出しの定義
0～3列目について見出しを作成します。
([81,112],[0,1],製造原価報告書,v,1,右線なし)
([81,85],[1,2],材料費,v,2,右線なし)
([84,85],[2,4],当期材料費(V),h,2,左線なし)
([85,90],[1,2],労務費,v,2,右線なし)
([89,90],[2,4],当期労務費(V),h,2,左線なし)
([90,106],[1,2],製造経費,v,2,右線なし)
([105,106],[2,4],当期製造経費(V),h,2,左線なし)
([106,107],[1,4],期首仕掛品,h,5)
([107,108],[1,4],小計,h,4)
([108,109],[1,4],期末仕掛品,h,5)
([109,110],[1,4],他勘定振替高,h,2)
([110,111],[1,4],期首-期末仕掛品差額(V),h,2)
([111,112],[1,4],当期製造原価,h,1,左線なし)
([81,82],[2,4],材料棚卸高,h,5)
([82,83],[2,4],当期材料仕入高,h,5)
([83,84],[2,4],期末材料棚卸高,h,5)
([85,86],[2,3],{区分},h,5)
([85,86],[3,4],{勘定科目},h,5)
([86,87],[2,3],{区分},h,5)
([86,87],[3,4],{勘定科目},h,5)
([87,88],[2,3],{区分},h,5)
([87,88],[3,4],{勘定科目},h,5)
([88,89],[2,3],{区分},h,5)
([88,89],[3,4],{勘定科目},h,5)
([90,91],[2,3],{区分},h,5)
([90,91],[3,4],{勘定科目},h,5)
([91,92],[2,3],{区分},h,5)
([91,92],[3,4],{勘定科目},h,5)
([92,93],[2,3],{区分},h,5)
([92,93],[3,4],{勘定科目},h,5)
([93,94],[2,3],{区分},h,5)
([93,94],[3,4],{勘定科目},h,5)
([94,95],[2,3],{区分},h,5)
([94,95],[3,4],{勘定科目},h,5)
([95,96],[2,3],{区分},h,5)
([95,96],[3,4],{勘定科目},h,5)
([96,97],[2,3],{区分},h,5)
([96,97],[3,4],{勘定科目},h,5)
([97,98],[2,3],{区分},h,5)
([97,98],[3,4],{勘定科目},h,5)
([98,99],[2,3],{区分},h,5)
([98,99],[3,4],{勘定科目},h,5)
([99,100],[2,3],{区分},h,5)
([99,100],[3,4],{勘定科目},h,5)
([100,101],[2,3],{区分},h,5)
([100,101],[3,4],{勘定科目},h,5)
([101,102],[2,3],{区分},h,5)
([101,102],[3,4],{勘定科目},h,5)
([102,103],[2,3],{区分},h,5)
([102,103],[3,4],{勘定科目},h,5)
([103,104],[2,3],{区分},h,5)
([103,104],[3,4],{勘定科目},h,5)
([104,105],[2,3],{区分},h,5)
([104,105],[3,4],{勘定科目},h,5)

第５ブロックの項目見出しの定義
0～3列目について見出しを作成します。
([112,113],[0,4],売上高,h,1)
([113,120],[0,2],売上原価,v,1,右線なし)
([120,121],[0,4],売上総利益,h,1)
([121,140],[0,2],販売管理費,v,1)
([140,141],[0,4],営業利益,h,1)
([141,149],[0,1],〔支出-収入=F〕,v,1,右線なし)
([141,149],[1,2],営業外収支,v,1,左線なし)
([149,150],[0,4],経常利益,h,1)
([150,152],[0,2],特別<br>損益,h,1)
([150,151],[2,4],特別利益,h,5)
([151,152],[2,4],特別損失,h,5)
([152,153],[0,4],税引前当期利益,h,1)
([153,154],[0,4],法人税充当額,h,5)
([154,155],[0,4],当期利益,h,1)
([141,146],[2,3],収入,v,2,右線なし)
([146,149],[2,3],支出,v,2,右線なし)
([145,146],[3,4],｛勘定科目｝,h,2,左線なし)
([148,149],[3,4],｛勘定科目｝,h,2,左線なし)
([113,114],[2,4],{勘定科目},h,5)
([114,115],[2,4],{勘定科目},h,5)
([115,116],[2,4],{勘定科目},h,5)
([116,117],[2,4],{勘定科目},h,5)
([117,118],[2,4],{勘定科目},h,5)
([118,119],[2,4],{勘定科目},h,5)
([119,120],[2,4],{勘定科目},h,1,左線なし)
([139,140],[2,4],{勘定科目},h,1,左線なし)
([121,122],[2,3],{区分},h,5)
([122,123],[2,3],{区分},h,5)
([123,124],[2,3],{区分},h,5)
([124,125],[2,3],{区分},h,5)
([125,126],[2,3],{区分},h,5)
([126,127],[2,3],{区分},h,5)
([127,128],[2,3],{区分},h,5)
([128,129],[2,3],{区分},h,5)
([129,130],[2,3],{区分},h,5)
([130,131],[2,3],{区分},h,5)
([131,132],[2,3],{区分},h,5)
([132,133],[2,3],{区分},h,5)
([133,134],[2,3],{区分},h,5)
([134,135],[2,3],{区分},h,5)
([135,136],[2,3],{区分},h,5)
([136,137],[2,3],{区分},h,5)
([137,138],[2,3],{区分},h,5)


第６ブロックの項目見出しの定義
0～3列目について見出しを作成します。
([155,156],[0,4],配当金,h,5)
([156,157],[0,4],役員賞与,h,5)
([157,158],[0,4],常用従業員数（ﾊﾟｰﾄも換算）①,h,5)
([158,159],[0,4],行金役員数②,h,5)
([159,160],[0,4],①＋②,h,5)

第７ブロックの項目見出しの定義
0～3列目について見出しを作成します。
([160,161],[0,4],加工高,h,5)
([161,162],[0,4],減価償却費合計,h,5)
([162,163],[0,4],キャッシュフロー（当期利益＋減価償却費－配当金－役員賞与）,h,5)
([163,164],[0,4],借入金合計,h,5)
([164,165],[0,4],人件費合計,h,5)

・指定のない勘定科目、前々期、構成比%、前期、構成比%、前年比増加率%、今期、構成比%、前年比増加率%、増減額の前期と今期、備考はoutput.jsonから取得すること。

■計算式
数字は行番号です。
79=45-30-42-43
80=3+4+11+77-(46+47)
110=106-108

'''

# ベストプラクティス：背景色と文字色のペア定義
# --- 1. カラー設定（背景色と文字色のペア） ---
# key: (背景色, 文字色)
_COLOR_CONFIG = {0: ("#f2f2f2", "#333333"),  # ヘッダー
1: ("#1B4F72", "#ffffff"),  # 1：濃い青（白抜き）
2: ("#85C1E9", "#333333"),  # 2：青（白抜き）
3: ("#EBF5FB", "#333333"),  # 3：水色
4: ("#F0F8FF", "#333333"),  # 4：薄い水色
5: ("#ffffff", "#333333"),  # 5：無色（白）
}

def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

import re

def _parse_spec_cell_defs(spec_text: str):
    defs = []
    if not spec_text:
        return defs

    trans = str.maketrans({
        "（": "(", "）": ")",
        "［": "[", "］": "]",
        "，": ",", "　": " ",
    })

    def _normalize_line(x: str) -> str:
        # ★修正点：
        # 文字列中に ")" が含まれても途中で切らない。
        # 行全体を正規化して返す（行末の ")" まで保持する）。
        x = (x or "").translate(trans).strip()
        return x

    line_re = re.compile(r'^\(\[\s*(\d+)\s*,\s*(\d+)\s*\],\[\s*(\d+)\s*,\s*(\d+)\s*\],(.*)\)$')

    for raw in spec_text.splitlines():
        s = _normalize_line(raw)
        if not s.startswith("(") or not s.endswith(")"):
            continue

        m = line_re.match(s)
        if not m:
            continue

        r0 = _safe_int(m.group(1)); r1 = _safe_int(m.group(2))
        c0 = _safe_int(m.group(3)); c1 = _safe_int(m.group(4))
        rest = m.group(5).strip()

        parts = []
        cur = ""
        in_quote = False
        quote_char = ""
        for ch in rest:
            if in_quote:
                cur += ch
                if ch == quote_char:
                    in_quote = False
                continue
            if ch in ('"', "'"):
                in_quote = True
                quote_char = ch
                cur += ch
                continue
            if ch == ",":
                parts.append(cur.strip())
                cur = ""
            else:
                cur += ch
        if cur.strip() != "" or rest.endswith(","):
            parts.append(cur.strip())

        if len(parts) < 2:
            continue

        text_raw = parts[0].strip()
        if (text_raw.startswith('"') and text_raw.endswith('"')) or (text_raw.startswith("\'") and text_raw.endswith("\'")):
            text_raw = text_raw[1:-1]

        orient      = parts[1] if len(parts) > 1 else "h"
        color_no    = parts[2] if len(parts) > 2 else "0"
        border_info = parts[3] if len(parts) > 3 else ""

        defs.append({
            "r0": r0, "r1": r1,
            "c0": c0, "c1": c1,
            "text": text_raw,
            "orient": orient,
            "color": color_no,
            "border": border_info,
        })

    return defs


def _load_spec_text():
    # 仕様ファイルを外部から読み込まず、コード内に内包した定義を使用する。
    return SPEC_TEXT_EMBEDDED

_SPEC_TEXT = _load_spec_text()
_SPEC_CELL_DEFS = _parse_spec_cell_defs(_SPEC_TEXT)

def _build_left_layout_for_range(row_start: int, row_end: int, col_max_exclusive: int = 4):
    """
    左側 0～3列（4列）のセル結合レイアウトを作る。
    戻り値: dict[(row, col)] = {"def":..., "is_topleft":bool}
    """
    layout = {}
    if not _SPEC_CELL_DEFS:
        return layout

    for d in _SPEC_CELL_DEFS:
        # 0～3列のみ対象
        if d["c0"] >= col_max_exclusive or d["c1"] <= 0:
            continue
        # 対象行範囲のみ
        if d["r1"] <= row_start or d["r0"] > row_end:
            continue

        r0 = max(d["r0"], row_start)
        r1 = min(d["r1"], row_end + 1)
        c0 = max(d["c0"], 0)
        c1 = min(d["c1"], col_max_exclusive)

        for r in range(r0, r1):
            for c in range(c0, c1):
                layout[(r, c)] = {"def": d, "is_topleft": (r == r0 and c == c0), "r0": r0, "r1": r1, "c0": c0, "c1": c1}
    return layout

def _style_for_left_cell(d: dict) -> str:
    """
    左側(0..3列)のセル用スタイル。
    背景色と線なし(border_info)を整合させるのが目的。
    """
    if not d:
        return ""

    style = []

    # 背景色（SPECの color を _COLOR_CONFIG で解決）
    bg_color = None
    text_color = None
    try:
        col_no = int(d.get("color", 0) or 0)
    except Exception:
        col_no = 0

    if col_no != 0:
        bg_color, text_color = _COLOR_CONFIG.get(col_no, (None, None))

    if bg_color:
        style.append(f"background-color:{bg_color}")
    if text_color:
        style.append(f"color:{text_color}")

    # 既存の配置系（必要に応じてあなたの既存仕様に合わせて維持）
    orient = (d.get("orient") or "").lower()
    if orient == "v":
        # 縦書き系（既存の実装に合わせて適宜）
        style.append("writing-mode:vertical-rl")
        style.append("text-orientation:upright")
        style.append("text-align:center")
        style.append("vertical-align:middle")
        style.append("font-weight:bold")
    else:
        style.append("text-align:left")
        style.append("vertical-align:middle")
        style.append("font-weight:bold")
        style.append("padding-left:8px")

    # ★線なし（border_info）を背景色で溶かす
    border_info = d.get("border", "") or ""
    style.append(_border_style_from_info(border_info, bg_color))

    # 空要素除去して結合
    style = [x for x in style if x and str(x).strip() != ""]
    return "; ".join(style)


def render_rows(start, end, left_layout=None):
    def _to_float_for_highlight(x):
      try:
          if x in ['""', '\"\"', None, ""]:
              return 0.0
          return float(str(x).replace(",", ""))
      except:
          return 0.0

    h = ""

    for i in range(start, end + 1):
        row = data_dict.get(i)
        if not row:
            continue

        is_total = i in [23, 44, 56, 64, 74, 84, 89, 105, 111, 119, 139, 145, 148, 160, 163, 164]
        is_grand = i in [45, 65, 75, 112, 120, 140, 149, 152, 154]
        cls = ' class="total-row"' if is_total else ' class="grand-total"' if is_grand else ""

        subject = row.get("勘定科目", "")
        if subject in ['""', '\"\"']:
            subject = ""

        row_bg_color = None
        row_text_color = None
        if left_layout:
            info_bg = left_layout.get((i, 3))
            if info_bg and isinstance(info_bg, dict):
                try:
                    col_no = int(info_bg.get("def", {}).get("color", 0) or 0)
                except Exception:
                    col_no = 0
                if col_no != 0:
                    row_bg_color, row_text_color = _COLOR_CONFIG.get(col_no, (None, None))

        style_parts = []
        if row_bg_color:
            style_parts.append(f"background-color:{row_bg_color}")
        if row_text_color:
            style_parts.append(f"color:{row_text_color}")
        row_bg_attr = f' style="{"; ".join(style_parts)}"' if style_parts else ""

        # 行背景色（左項目列の色を最優先）
        row_style_parts = []

        if row_bg_color:
            row_style_parts.append(f"background-color:{row_bg_color}")

        if row_text_color:
            row_style_parts.append(f"color:{row_text_color}")

        # 合計行は太字だけ付与（色はSPECに従う）
        if is_total or is_grand:
            row_style_parts.append("font-weight:bold")

        row_style_attr = f' style="{"; ".join(row_style_parts)}"' if row_style_parts else ""

        h += f'<tr data-row="{i}"{row_style_attr}>'

        # ------------------------------------------------------------
        # 左側0～3列（項目4列）の描画：covered方式を廃止し、
        # left_layout の is_topleft 判定だけで結合セルを確実に制御する
        # ------------------------------------------------------------

        # 勘定科目列(c=3)が「結合範囲に含まれている」かを厳密に判定
        # (i,3) に left_layout があり、かつ is_topleft=False なら結合の一部なので出してはいけない
        subject_cell_in_merge = False
        if left_layout:
            info_c3 = left_layout.get((i, 3))
            if info_c3 and isinstance(info_c3, dict):
                # c=3 が結合定義に含まれている（とくに is_topleft=False）は、勘定科目セルを出さない
                if not info_c3.get("is_topleft", False):
                    subject_cell_in_merge = True
                else:
                    # is_topleft=True で c=3 に結合定義がある場合も、
                    # それは結合セルとして描画されるので、通常の勘定科目セルは不要
                    # （実際の出力はループ側で行う）
                    pass

        for c in range(0, 4):
            info = (left_layout or {}).get((i, c)) if left_layout else None

            if info and isinstance(info, dict):
                # 結合セルの「左上」だけ出す。左上以外は必ずスキップ（=結合の一部）
                if not info.get("is_topleft", False):
                    continue

                d = info.get("def", {}) or {}
                rs = int(info.get("r1", 0)) - int(info.get("r0", 0))
                cs = int(info.get("c1", 0)) - int(info.get("c0", 0))
                text = d.get("text", "") or ""
                if text == "{区分}" or text == "｛区分｝":
                    kubun_raw = str((row.get("区分", "") or "")).strip()
                    # 90～104行は、勘定科目が空の場合は区分も空にする
                    subj_val = str((row.get("勘定科目", "") or "")).strip()
                    if i >= 90 and i <= 104 and (subj_val == "" or subj_val in ['""', '\"\"']):
                        kubun_raw = ""
                    kubun_norm = kubun_raw.replace("Ｆ", "F").replace("Ｖ", "V").strip().upper()
                    if kubun_norm in ("F", "V"):
                        text = f"<button type='button' class='kubun-toggle' data-row='{i}' aria-label='区分を切替' onclick='var t=(this.textContent||\"\").trim().toUpperCase();this.textContent=(t===\"F\"?\"V\":\"F\");'>{kubun_norm}</button>"
                    else:
                        text = kubun_raw

                if text == "{勘定科目}" or text == "｛勘定科目｝":
                    text = str((row.get("勘定科目", "") or "")).strip()
                style = _style_for_left_cell(d)

                cs_attr = f' colspan="{cs}"' if cs and cs != 1 else ""
                rs_attr = f' rowspan="{rs}"' if rs and rs != 1 else ""
                st_attr = f' style="{style}"' if style else ""

                extra_cls = ''
                if (d.get("text", "") or "").strip() == "{区分}" or (d.get("text", "") or "").strip() == "｛区分｝":
                    extra_cls = ' class="kubun-cell"'

                if i == 76 and cs == 4:
                    try:
                        v1 = _to_float_for_highlight(row.get("前々期"))
                        v2 = _to_float_for_highlight(row.get("前期"))
                        v3 = _to_float_for_highlight(row.get("今期"))
                        if v1 != 0 or v2 != 0 or v3 != 0:
                            if style:
                                style += "; background-color:#ffff00"
                            else:
                                style = "background-color:#ffff00"
                            st_attr = f' style="{style}"'
                    except:
                        pass

                h += f'<td{extra_cls}{cs_attr}{rs_attr}{st_attr}>{text}</td>'
                continue

            # left_layout に定義が無い通常セル
            if c == 3:
                # ★ 勘定科目列(c=3)が結合に含まれている行では、絶対に勘定科目セルを出さない
                if subject_cell_in_merge:
                    continue

                # --- 借方／貸方照合（76行）差異判定 ---
                diff_cols = set()
                highlight_label = False

                if i == 76:
                    try:
                        v1 = float(str(row.get("前々期", 0)).replace(",", "") or 0)
                        v2 = float(str(row.get("前期", 0)).replace(",", "") or 0)
                        v3 = float(str(row.get("今期", 0)).replace(",", "") or 0)
                    except:
                        v1 = v2 = v3 = 0

                    if v1 != 0:
                        diff_cols.add("前々期")
                        highlight_label = True
                    if v2 != 0:
                        diff_cols.add("前期")
                        highlight_label = True
                    if v3 != 0:
                        diff_cols.add("今期")
                        highlight_label = True

                subject_style = "font-weight:bold; text-align:left; vertical-align:middle; padding-left:8px;"
                if i == 76 and highlight_label:
                    subject_style += " background-color:#ffff00;"

                h += f'<td class="w-subject" style="{subject_style}">{subject}</td>'

            else:
                if c == 2:
                    kubun_raw2 = str((row.get("区分", "") or "")).strip()
                    kubun_norm2 = kubun_raw2.replace("Ｆ", "F").replace("Ｖ", "V").strip().upper()
                    if kubun_norm2 in ("F", "V"):
                        h += f"<td class='w-v kubun-cell' style='text-align:center; padding:0;'><button type='button' class='kubun-toggle' data-row='{i}' aria-label='区分を切替' onclick='var t=(this.textContent||\"\").trim().toUpperCase();this.textContent=(t===\"F\"?\"V\":\"F\");'>{kubun_norm2}</button></td>"
                    else:
                        h += '<td class="w-v"></td>'
                else:
                    h += '<td class="w-v"></td>'

        # --- 右側の数値列描画（構成比ID付与版・最終確定） ---
        for k in ["前々期", "前々期構成比", "前期", "前期構成比", "前期前年比増加率",
                  "今期", "今期構成比", "今期前年比増加率", "前期増減額", "今期増減額"]:

            v = row.get(k, 0)
            c_cls = "col-pct" if "構成" in k or "増加率" in k else "col-diff" if "増減" in k else "col-amt"

            # =========================================
            # ① 入力対象（77,78行）
            # =========================================
            if i in [77, 78] and k in ["前々期", "前期", "今期"]:
                try:
                    num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                except:
                    num_v = 0.0

                disp = (
                    f'<input type="number" step="1" id="inp-r{i}-{k}" '
                    f'name="inp-r{i}-{k}" value="{int(round(num_v))}" '
                    f'style="width:100%; box-sizing:border-box; text-align:right; '
                    f'font-family:Consolas, monospace;">'
                )

                cell_attr = row_bg_attr

                if i == 76 and k in ["前々期", "前期", "今期"]:
                    vv = _to_float_for_highlight(row.get(k))
                    if vv != 0:
                        if cell_attr:
                            cell_attr = cell_attr[:-1] + "; background-color:#ffff00\""
                        else:
                            cell_attr = ' style="background-color:#ffff00"'

                h += f'<td class="{c_cls}"{cell_attr}>{disp}</td>'
                continue

            # =========================================
            # ② 入力対象（155〜158行）
            # =========================================
            if i in [155, 156, 157, 158] and k in ["前々期", "前期", "今期"]:
                try:
                    num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                except:
                    num_v = 0.0

                disp = (
                    f'<input type="number" step="1" id="inp-r{i}-{k}" '
                    f'name="inp-r{i}-{k}" value="{int(round(num_v))}" '
                    f'style="width:100%; box-sizing:border-box; text-align:right; '
                    f'font-family:Consolas, monospace;">'
                )

                cell_attr = row_bg_attr
                h += f'<td class="{c_cls}"{cell_attr}>{disp}</td>'
                continue

            # =========================================
            # ③ 159行（自動計算表示）
            # =========================================
            if i == 159:

                # 金額3列
                if k in ["前々期", "前期", "今期"]:
                    try:
                        num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                    except:
                        num_v = 0.0
                    disp = f'<span id="calc-r159-{k}">{int(round(num_v)):,}</span>'
                    h += f'<td class="{c_cls}">{disp}</td>'
                    continue

                # 増減額
                if k in ["前期増減額", "今期増減額"]:
                    try:
                        num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                    except:
                        num_v = 0.0
                    disp = f'<span id="calc-r159-{k}">{int(round(num_v)):,}</span>'
                    h += f'<td class="{c_cls}">{disp}</td>'
                    continue

                # 前年比
                if k in ["前期前年比増加率", "今期前年比増加率"]:
                    try:
                        num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                    except:
                        num_v = 0.0
                    disp = f'<span id="calc-r159-{k}">{num_v:.2f}%</span>'
                    h += f'<td class="{c_cls}">{disp}</td>'
                    continue

            # =========================================
            # ④ 構成比セル（Python計算値を直接表示）
            # =========================================
            if "構成比" in k:
              try:
                  num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
              except:
                  num_v = 0.0

              disp = f"{num_v:.2f}%"
              h += f'<td class="col-pct">{disp}</td>'
              continue

            # =========================================
            # ⑤ 前年比増加率（通常行）
            # =========================================
            if "増加率" in k:
                try:
                    num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                except:
                    num_v = 0.0
                disp = f"{num_v:.2f}%"
                h += f'<td class="{c_cls}">{disp}</td>'
                continue

            # =========================================
            # ⑥ 増減額
            # =========================================
            if "増減" in k:
                try:
                    num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                except:
                    num_v = 0.0
                disp = f"{int(round(num_v)):,}"
                h += f'<td class="{c_cls}">{disp}</td>'
                continue

            # =========================================
            # ⑦ 通常金額
            # =========================================
            try:
                num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
            except:
                num_v = 0.0

            disp = f"{int(round(num_v)):,}"
            h += f'<td class="{c_cls}">{disp}</td>'

        memo = row.get("集計方法", "")
        if memo in ['""', '\"\"']:
            memo = ""
        h += f'<td class="col-memo">{memo}</td>'

    return h

def _border_style_from_info(info: str, bg_color: str = None) -> str:
    """
    info: 例 "下線なし", "上線なし", "左線なし", "右線なし" の組合せを想定。
    「線なし」は border を消すのではなく、背景色と同じ色にして“見えなくする”。
    これにより、border-collapse: collapse の共有線問題を避けつつ、
    背景色のセルでは自然に溶け込む（当座資産右、小計左などが正しくなる）。
    """
    if not info:
        return ""

    if bg_color is None or str(bg_color).strip() == "":
        bg_color = "transparent"

    s = ""
    if "上線なし" in info:
        s += f"border-top-color:{bg_color} !important;"
    if "下線なし" in info:
        s += f"border-bottom-color:{bg_color} !important;"
    if "左線なし" in info:
        s += f"border-left-color:{bg_color} !important;"
    if "右線なし" in info:
        s += f"border-right-color:{bg_color} !important;"
    return s



def _th(text, colspan=1, rowspan=1, cls="", orient="h", border_info="", attrs=""):
    style = ""
    if orient == "v":
        # タイトル行の「前年比増加率%」は縦書きで左→右へ折り返す（vertical-lr）
        if "前年比" in str(text):
            style += "writing-mode:vertical-lr;text-orientation:mixed;"
        else:
            style += "writing-mode:vertical-rl;text-orientation:mixed;"
    style += _border_style_from_info(border_info, "#f2f2f2")
    cls_attr = f' class="{cls}"' if cls else ""
    cs_attr = f' colspan="{colspan}"' if colspan and colspan != 1 else ""
    rs_attr = f' rowspan="{rowspan}"' if rowspan and rowspan != 1 else ""
    st_attr = f' style="{style}"' if style else ""
    attrs_attr = f" {attrs}" if attrs else ""
    return f'<th{cls_attr}{cs_attr}{rs_attr}{st_attr}{attrs_attr}>{text}</th>'

def _build_title_thead():
    # 仕様：列は0～1の2行。列番号は0～15（実テーブルは0～14の15列）。
    # 決算年月日は json から取得（output.json 内の「決算期年月日」）。
    d_zy = closing_dates.get("前々期", "")
    d_zp = closing_dates.get("前期", "")
    d_zc = closing_dates.get("今期", "")

    r0 = []
    r1 = []

    # ([0,2],[0,4],項目,h,0)
    r0.append(_th("項目", colspan=4, rowspan=2))

    # ([0,1],[4,5],前々期,h,0,下線なし)
    r0.append(_th("前々期", cls="col-amt clickable-period", attrs='id="period-zenzenki" data-period="前々期" data-default-label="前々期" role="button" tabindex="0"'))
    # ([1,2],[4,5],{決算年月日_前々期},h,0,上線なし)
    r1.append(_th(d_zy, cls="col-amt"))

    # ([0,2],[5,6],構成比%,v,0)
    r0.append(_th("構成比%", cls="col-pct", rowspan=2, orient="v"))

    # ([0,1],[6,7],前期,h,0,下線なし)
    r0.append(_th("前期", cls="col-amt clickable-period", attrs='id="period-zenki" data-period="前期" data-default-label="前期" role="button" tabindex="0"'))
    # ([1,2],[6,7],{決算年月日_前期},h,0,上線なし)
    r1.append(_th(d_zp, cls="col-amt"))

    # ([0,2],[7,8],構成比%,v,0)
    r0.append(_th("構成比%", cls="col-pct", rowspan=2, orient="v"))

    # ([0,2],[8,9],前年比増加率%,v,0)
    r0.append(_th("前年比<br>増加率%", cls="col-pct", rowspan=2, orient="v"))

    # ([0,1],[9,10],今期,h,0,下線なし)
    r0.append(_th("今期", cls="col-amt clickable-period", attrs='id="period-konki" data-period="今期" data-default-label="今期" role="button" tabindex="0"'))
    # ([1,2],[9,10],{決算年月日_今期},h,0,上線なし)
    r1.append(_th(d_zc, cls="col-amt"))

    # ([0,2],[10,11],構成比%,v,0)
    r0.append(_th("構成比%", cls="col-pct", rowspan=2, orient="v"))

    # ([0,2],[11,12],前年比増加率%,v,0)
    r0.append(_th("前年比<br>増加率%", cls="col-pct", rowspan=2, orient="v"))

    # ([0,1],[12,14],増減額,h,0)
    r0.append(_th("増減額", colspan=2, cls="diff-group"))

    # ([1,2],[12,13],前期,h,0)
    r1.append(_th("前期", cls="col-diff"))
    # ([1,2],[13,14],今期,h,0)
    r1.append(_th("今期", cls="col-diff"))

    # ([0,2],[14,15],備考,h,0)
    r0.append(_th("備考", cls="col-memo", rowspan=2))

    # r0 は： 4cols + col4 + col5 + col6 + col7 + col8 + col9 + col10 + col11 + col12-13 + col14 = 13 th だが
    # colspan/rowspanにより列数は15に整合する。
    thead = "<thead><tr>" + "".join(r0) + "</tr><tr>" + "".join(r1) + "</tr></thead>"
    return thead

def create_table(start, end, title):
    left_layout = _build_left_layout_for_range(start, end)

    return (f'<div class="report-title">{title}</div>'
f'<table class="excel-table">'
f'<colgroup>'
f'  <col class="w-v"><col class="w-v"><col class="w-v"><col class="w-subject">'
f'  <col class="c-amt"><col class="c-pct">'
f'  <col class="c-amt"><col class="c-pct"><col class="c-pct">'
f'  <col class="c-amt"><col class="c-pct"><col class="c-pct">'
f'  <col class="c-diff"><col class="c-diff">'
f'  <col class="c-memo">'
f'</colgroup>'
f'{_build_title_thead()}'
f'<tbody>{render_rows(start, end, left_layout)}</tbody>'
f'</table>'
)

# 155-159 と 160-164 を別テーブルに分離（要件）

# 仕様定義の読み込み状況を表示（項目見出しが出ない場合の原因特定用）
_spec_warning_html = ""
try:
    if not _SPEC_CELL_DEFS:
        _spec_warning_html = (
            '<div style="border:2px solid #dc3545; background:#fff5f5; padding:10px; margin:10px 0; font-weight:bold;">'
            '警告：タイトル行と列の定義.txt のセル定義が読み取れませんでした（0件）。'
            ' 左側の項目見出し（資産の部 等）は表示されません。ファイル名/配置/文字コードを確認してください。'
            '</div>')
    else:
        # 代表定義が存在するか（資産の部）
        if not any((d.get("text") or "") == "資産の部" for d in _SPEC_CELL_DEFS):
            _spec_warning_html = (
                '<div style="border:2px solid #dc3545; background:#fff5f5; padding:10px; margin:10px 0; font-weight:bold;">'
                '警告：セル定義は読み取れましたが、「資産の部」定義が見つかりません。'
                ' 使用している タイトル行と列の定義.txt が更新版か確認してください。'
                '</div>'
            )
except Exception:
    pass
full_html = (
create_table(1, 76, "貸借対照表（B/S）") +
create_table(77, 78, "入力項目") +
create_table(79, 80, "集計項目") +
create_table(81, 111, "製造原価報告書") +
create_table(112, 154, "損益計算書（P/L）") +
create_table(155, 159, "入力項目／集計項目") +
create_table(160, 164, "集計項目")
)

debug_panel = f'<div class="debug-panel"><h3>【詳細デバッグログ】</h3>{"".join(debug_logs)}</div>'

save_panel = (
    '<div class="save-panel">'
    '<button class="btn-save" onclick="window._saveToColab()">データ更新・保存</button>'
    '</div>'
)
# ==========================================================
# 加工高（行番号160）再計算（グローバル定義）
# ==========================================================
def recalc_kakou_daka_from_excel_formula(data_list):

    # セル番号 → 行マップ作成
    cell_map = {
        str(r.get("セル")): r
        for r in data_list
        if r.get("セル")
    }

    def get_value(cell_no, period):
        row = cell_map.get(str(cell_no))
        if row is None:
            return 0
        return row.get(period, 0) or 0

    periods = ["前々期", "前期", "今期"]

    # 行番号160を取得
    kakou_row = None
    for r in data_list:
        if r.get("行番号") == 160:
            kakou_row = r
            break

    if kakou_row is None:
        return

    for p in periods:

        sales   = get_value(129, p)
        shiire  = get_value(131, p)
        zairyou = get_value(96,  p)
        shikake = get_value(122, p)
        seihin  = get_value(135, p)
        furikae = get_value(121, p)

        # SUMIF 97-116
        sum_v1 = 0
        for r in data_list:
            cell = r.get("セル")
            if not cell:
                continue
            try:
                cell_no = int(cell)
            except:
                continue

            if 97 <= cell_no <= 116:
                if r.get("区分") == "V":
                    sum_v1 += r.get(p, 0) or 0

        # SUMIF 138-155
        sum_v2 = 0
        for r in data_list:
            cell = r.get("セル")
            if not cell:
                continue
            try:
                cell_no = int(cell)
            except:
                continue

            if 138 <= cell_no <= 155:
                if r.get("区分") == "V":
                    sum_v2 += r.get(p, 0) or 0

        value = (
            sales
            - shiire
            - (
                zairyou
                + sum_v1
                + shikake
                + seihin
                + sum_v2
                - furikae
            )
        )

        kakou_row[p] = int(value)

    # 増減計算
    kakou_row["前期増減額"] = kakou_row.get("前期", 0) - kakou_row.get("前々期", 0)
    kakou_row["今期増減額"] = kakou_row.get("今期", 0) - kakou_row.get("前期", 0)

    kakou_row["前期前年比増加率"] = (
        round((kakou_row["前期"] / kakou_row["前々期"] - 1) * 100)
        if kakou_row.get("前々期") else 0
    )

    kakou_row["今期前年比増加率"] = (
        round((kakou_row["今期"] / kakou_row["前期"] - 1) * 100)
        if kakou_row.get("前期") else 0
    )

    print("DEBUG sales:", sales)
    print("DEBUG shiire:", shiire)
    print("DEBUG zairyou:", zairyou)
    print("DEBUG shikake:", shikake)
    print("DEBUG seihin:", seihin)
    print("DEBUG furikae:", furikae)
    print("DEBUG sum_v1:", sum_v1)
    print("DEBUG sum_v2:", sum_v2)
# ------------------------------------------------------------------
# 6. 初期状態の output_updated.json を保存（サーバ側）
#    ※保存前に「シート名」「セル」を付与
# ------------------------------------------------------------------
json_output = sorted(data_dict.values(), key=lambda x: x.get("行番号", 0))
json_output = add_precise_cell_references_to_data(json_output)

# --------------------------------------------
# JSON出力直前で呼び出す
# --------------------------------------------

# print("BEFORE:", [r for r in json_output if r.get("行番号") == 160])
print("DEBUG セル存在確認:",
      any(r.get("セル") for r in json_output))
recalc_kakou_daka_from_excel_formula(json_output)
# print("AFTER:", [r for r in json_output if r.get("行番号") == 160])
# ==========================================================
# ★HTML描画側が参照する data_dict を、再計算済み json_output で同期する
#   （render_rows は data_dict を参照するため必須）
# ==========================================================
data_dict = {r.get("行番号"): r for r in json_output if isinstance(r, dict) and "行番号" in r}

# ==========================================================
# ★ここでHTMLを作り直す（加工高再計算後の data_dict を参照させるため）
# ==========================================================
full_html = (
    create_table(1, 76, "貸借対照表（B/S）") +
    create_table(77, 78, "入力項目") +
    create_table(79, 80, "集計項目") +
    create_table(81, 111, "製造原価報告書") +
    create_table(112, 154, "損益計算書（P/L）") +
    create_table(155, 159, "入力項目／集計項目") +
    create_table(160, 164, "集計項目")
)

abs_out_path = os.path.abspath(OUTPUT_PATH)
_tmp_out_path = abs_out_path + f".tmp.{os.getpid()}"
with open(_tmp_out_path, 'w', encoding='utf-8') as f:
    json.dump(json_output, f, ensure_ascii=False, indent=2)
os.replace(_tmp_out_path, abs_out_path)

# ------------------------------------------------------------------
# 7. JS側に渡すデータは JSON直書きせず、application/json に埋め込む（構文エラー回避）
# ------------------------------------------------------------------
json_for_html = json.dumps(json_output, ensure_ascii=False)

# ★追加：script 埋め込み時に壊れる文字列を無害化
# 1) </script> を含むと HTML が壊れるのでエスケープ
# 2) U+2028/U+2029 は環境によってはパースが壊れるのでエスケープ
json_for_html = (
    json_for_html
    .replace("</", "<\\/")          # </script> 対策（一般化）
    .replace("\u2028", "\\u2028")   # LINE SEPARATOR 対策
    .replace("\u2029", "\\u2029")   # PARAGRAPH SEPARATOR 対策
)
# === ここに追記する ===
print("=== JSON危険文字チェック ===")
for ch in ["</script", "\u2028", "\u2029"]:
    print(repr(ch), ch in json_for_html)
print("===========================")
data_tag = (
    '<textarea id="report-data-json" style="display:none;">'
    f'{json_for_html}'
    '</textarea>'
)


# 保存確認メッセージ-------
modal_html = r"""

<!-- Message Modal -->
<div id="simple-modal-overlay" class="modal-overlay">
  <div class="modal-card modern">
    <div class="modal-header">
      <div class="modal-title">通知</div>
      <button class="modal-x" onclick="hideSimpleModal()" aria-label="close">×</button>
    </div>
    <div id="simple-modal-message" class="modal-message"></div>
    <div class="modal-actions">
      <button class="modal-ok-btn" onclick="hideSimpleModal()">OK</button>
    </div>
  </div>
</div>

<!-- Period Editor Modal -->
<div id="period-modal-overlay" class="period-overlay">
  <div class="period-card" role="dialog" aria-modal="true" aria-labelledby="period-modal-title">
    <div class="period-top">
      <div class="period-badge">期</div>
      <div class="period-head">
        <div id="period-modal-title" class="period-title">決算期（第何期）を入力</div>
        <div id="period-modal-sub" class="period-sub"></div>
      </div>
      <button class="period-x" onclick="window._hidePeriodModal()" aria-label="close">×</button>
    </div>
    <div class="period-body">
      <label class="period-label" for="period-modal-input">数値（1以上の整数）</label>
      <input id="period-modal-input" class="period-input" type="number" min="1" step="1" inputmode="numeric" />
      <div class="period-hint">入力例：11 → 表示は「11期」になります。</div>
      <div id="period-modal-error" class="period-error" style="display:none;"></div>
    </div>
    <div class="period-actions">
      <button class="period-btn ghost" onclick="window._hidePeriodModal()">キャンセル</button>
      <button class="period-btn primary" onclick="window._applyPeriodModal()">適用</button>
    </div>
  </div>
</div>

"""



# ------------------------------------------------------------------
# 8. JS（159即時更新、保存ボタンでColab callback、入力は 77-78 と 155-158 を同期）
# ------------------------------------------------------------------
script = r"""
<script>
/* ------------------------------
 * ユーティリティ
 * ------------------------------ */
function _gi(id){
  return document.getElementById(id);
}
function _numFromInput(el){
  var n = Number((el && el.value !== undefined) ? el.value : 0);
  return isNaN(n) ? 0 : Math.round(n);
}
function _fmt(n){
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function _fmtPct(n){
  if(n === null || n === undefined) n = 0;
  n = Number(n);
  if(!isFinite(n)) n = 0;
  if(Math.abs(n) < 0.0005) n = 0;
  return n.toFixed(2) + "%";
}

/* ------------------------------
 * 決算期（第何期）ヘッダー編集
 *  - どのブロックで編集しても全ブロック同期
 * ------------------------------ */
window._periodNumbers = { "前々期": null, "前期": null, "今期": null };
window._activePeriodKey = null;

function _updateAllPeriodHeaders(periodKey){
  var n = window._periodNumbers[periodKey];
  var label = (n !== null && n !== undefined && Number.isFinite(Number(n)) && Number(n) >= 1)
    ? (String(parseInt(n, 10)) + "期")
    : periodKey;

  var ths = document.querySelectorAll('th.clickable-period[data-period="' + periodKey + '"]');
  ths.forEach(function(th){
    th.textContent = label;
    th.setAttribute("aria-label", periodKey + "（クリックして第何期を編集）");
  });
}

function _showPeriodModal(periodKey){
  window._activePeriodKey = periodKey;

  var ovl = document.getElementById("period-modal-overlay");
  var sub = document.getElementById("period-modal-sub");
  var inp = document.getElementById("period-modal-input");
  var err = document.getElementById("period-modal-error");

  if(!ovl || !sub || !inp || !err) return;

  sub.textContent = "対象：" + periodKey + "（クリックで編集・保存時にExcelへ転記）";
  err.style.display = "none";
  err.textContent = "";

  var current = window._periodNumbers[periodKey];
  inp.value = (current !== null && current !== undefined) ? String(current) : "";
  ovl.classList.add("show");

  setTimeout(function(){
    try{ inp.focus(); inp.select(); }catch(e){}
  }, 20);
}

window._hidePeriodModal = function(){
  var ovl = document.getElementById("period-modal-overlay");
  if(ovl) ovl.classList.remove("show");
  window._activePeriodKey = null;
};

window._applyPeriodModal = function(){
  var key = window._activePeriodKey;
  var inp = document.getElementById("period-modal-input");
  var err = document.getElementById("period-modal-error");
  if(!key || !inp || !err) return;

  var v = String(inp.value || "").trim();
  if(!/^[0-9]+$/.test(v)){
    err.textContent = "1以上の整数を入力してください。";
    err.style.display = "block";
    return;
  }
  var n = parseInt(v, 10);
  if(!Number.isFinite(n) || n < 1){
    err.textContent = "1以上の整数を入力してください。";
    err.style.display = "block";
    return;
  }

  window._periodNumbers[key] = n;
  _updateAllPeriodHeaders(key);
  window._hidePeriodModal();
};

function _attachPeriodHeaderHandlers(){
  var ths = document.querySelectorAll("th.clickable-period[data-period]");
  ths.forEach(function(th){
    th.addEventListener("click", function(){
      var key = th.getAttribute("data-period");
      if(key) _showPeriodModal(key);
    });
    th.addEventListener("keydown", function(ev){
      if(ev.key === "Enter" || ev.key === " "){
        ev.preventDefault();
        var key = th.getAttribute("data-period");
        if(key) _showPeriodModal(key);
      }
    });
  });

  // overlay click to close
  var ovl = document.getElementById("period-modal-overlay");
  if(ovl){
    ovl.addEventListener("click", function(ev){
      if(ev.target === ovl) window._hidePeriodModal();
    });
  }
}

/* ------------------------------
 * 初期データ読込（<script type="application/json"> から）
 * ------------------------------ */
function _initReportData(){
  try{
    if (window.reportData && Array.isArray(window.reportData) && window.reportData.length > 0) {
      return;
    }

    var el = document.getElementById("report-data-json");
    if(!el){
      console.warn("report-data-json not found");
      window.reportData = [];
      return;
    }

    // textarea / script 両対応（textarea想定）
    var txt = "";
    if (el.tagName && el.tagName.toLowerCase() === "textarea") {
      txt = (el.value || "").trim();
      if(!txt){
        txt = (el.textContent || el.innerText || "").trim();
      }
    } else {
      txt = (el.textContent || el.innerText || "").trim();
    }

    if(!txt){
      console.warn("report-data-json is empty");
      window.reportData = [];
      return;
    }

    var parsed = JSON.parse(txt);
    if(!Array.isArray(parsed)){
      console.warn("report-data-json is not an array:", parsed);
      window.reportData = [];
      return;
    }

    window.reportData = parsed;
  }catch(e){
    console.error("initReportData failed:", e);
    window.reportData = [];
  }
}


/* ------------------------------
 * 157 + 158 → 159 即時再計算
 * ------------------------------ */
function _recalc159(){
  try{
    function sum(p){
      return _numFromInput(_gi("inp-r157-" + p)) +
             _numFromInput(_gi("inp-r158-" + p));
    }

    var vv = sum("前々期");
    var vp = sum("前期");
    var vc = sum("今期");

    var sp;
    sp = _gi("calc-r159-前々期"); if(sp) sp.textContent = _fmt(vv);
    sp = _gi("calc-r159-前期");   if(sp) sp.textContent = _fmt(vp);
    sp = _gi("calc-r159-今期");   if(sp) sp.textContent = _fmt(vc);

    var d1 = vp - vv;
    var d2 = vc - vp;

    sp = _gi("calc-r159-前期増減額"); if(sp) sp.textContent = _fmt(d1);
    sp = _gi("calc-r159-今期増減額"); if(sp) sp.textContent = _fmt(d2);

    var r1 = (vv !== 0) ? ((vp / vv - 1) * 100) : 0;
    var r2 = (vp !== 0) ? ((vc / vp - 1) * 100) : 0;

    sp = _gi("calc-r159-前期前年比増加率"); if(sp) sp.textContent = _fmtPct(r1);
    sp = _gi("calc-r159-今期前年比増加率"); if(sp) sp.textContent = _fmtPct(r2);

    /* reportData 側も同期 */
    if(window.reportData){
      for(var i = 0; i < window.reportData.length; i++){
        var row = window.reportData[i];
        if(row && row["行番号"] === 159){
          row["前々期"] = vv;
          row["前期"]   = vp;
          row["今期"]   = vc;
          row["前期増減額"] = d1;
          row["今期増減額"] = d2;
          row["前期前年比増加率"] = r1;
          row["今期前年比増加率"] = r2;
          break;
        }
      }
    }
  }catch(e){
    console.error("recalc159 failed:", e);
  }
}

/* ------------------------------
 * 入力欄にイベントを付与
 * （77-78, 155-158）
 * ------------------------------ */
function _attachInputHandlers(){
  var rows = [77, 78, 155, 156, 157, 158];
  var cols = ["前々期", "前期", "今期"];

  rows.forEach(function(r){
    cols.forEach(function(c){
      var el = _gi("inp-r" + r + "-" + c);
      if(el){
        el.addEventListener("input", _recalc159);
        el.addEventListener("change", _recalc159);
      }
    });
  });
}

/* ------------------------------
 * DOM → reportData 再構築
 * ------------------------------ */
window._rebuildReportDataFromDOM = function(){
  _initReportData();
  if(!window.reportData || !Array.isArray(window.reportData)) return;

  var rows = document.querySelectorAll("tr[data-row]");
  rows.forEach(function(tr){
    var rn = parseInt(tr.getAttribute("data-row"), 10);
    if(!rn) return;

    var row = null;
    for(var i = 0; i < window.reportData.length; i++){
      if(window.reportData[i] && window.reportData[i]["行番号"] === rn){
        row = window.reportData[i];
        break;
      }
    }
    if(!row) return;

    ["前々期", "前期", "今期"].forEach(function(k){
      var inp = _gi("inp-r" + rn + "-" + k);
      if(inp){
        var v = parseInt(inp.value || "0", 10);
        row[k] = isNaN(v) ? 0 : v;
      }
    });
  });
};


/* ------------------------------
 * Colab へ保存
 * ------------------------------ */
window._saveToColab = async function(){
  try{
    console.log("[save] start");
    _recalc159();

    console.log("[save] before rebuild, reportData:", window.reportData);
    try{
      window._rebuildReportDataFromDOM();
      console.log("[save] after rebuild, reportData:", window.reportData);
    }catch(rebuildErr){
      console.error("[save] rebuild error:", rebuildErr);
      alert("画面からデータ再構築に失敗しました\n" + String(rebuildErr));
      return;
    }

    var payload = { data: window.reportData || [], period_numbers: window._periodNumbers || {} };
    console.log("[save] payload.data length:", Array.isArray(payload.data) ? payload.data.length : "(not array)");

    var res = await safeInvokeSave(payload);
    return res;

  }catch(e){
    console.error(e);
    alert("Colab保存に失敗しました\n" + String(e));
  }
};


/* ------------------------------
 * 表示切替
 * ------------------------------ */
function toggleCols(){
  var c = document.getElementById("report-container");
  if(!c) return;
  c.classList.toggle("show-all");
}

/* ------------------------------
 * 初期化
 * ------------------------------ */
(function initWhenReady(){
  function ready(){
    var tbl = document.querySelector(".excel-table");
    if(!tbl){
      setTimeout(ready, 50);
      return;
    }

    _attachInputHandlers();
    _attachPeriodHeaderHandlers();
    _initReportData();
    _recalc159();

    // ★ここを追加：構成比を強制再計算
    if (typeof updateAllCalculations === "function") {
        updateAllCalculations();
    }
  }
  ready();
})();

function _parsePythonDictString(pyDictStr){
  if (typeof pyDictStr !== "string") return null;

  let s = pyDictStr.trim();

  // 改行・余分な空白を吸収（JSON化の邪魔を減らす）
  s = s.replace(/\r?\n/g, " ");

  // Python -> JSON
  s = s.replace(/\bTrue\b/g, "true").replace(/\bFalse\b/g, "false").replace(/\bNone\b/g, "null");

  // 単引用符->二重引用符（簡易）
  s = s.replace(/'/g, '"');

  // キー/値間の余分空白を軽減（任意だが安全）
  s = s.replace(/\s+/g, " ");

  try{
    return JSON.parse(s);
  }catch(_e){
    return null;
  }
}


function safeInvokeSave(payload){
  try{
    if (!(window.google && google.colab && google.colab.kernel)) {
      showSimpleModal("保存できませんでした");
      return Promise.resolve(null);
    }

    return google.colab.kernel.invokeFunction(
      "save_output_updated_json",
      [payload],
      {}
    ).then(res => {
      // 呼び出し自体の成否（Colab側の実行結果）
      if (!res || res.status !== "ok") {
        showSimpleModal("保存できませんでした");
        return res;
      }

      // Colabでは res.data["text/plain"] にPythonのdict文字列が入ることがある
      const textPlain = (res.data && res.data["text/plain"]) ? String(res.data["text/plain"]) : "";

      // Pythonが ok: False を返す場合は失敗扱い
      if (
        textPlain.includes("'ok': False") ||
        textPlain.includes("'ok': false") ||
        textPlain.includes('"ok": false')
      ) {
        showSimpleModal("保存できませんでした");
      } else {
        if (textPlain.includes("'excel_updated': True") || textPlain.includes("\"excel_updated\": true")) {
        if (textPlain.includes("'excel_error':") || textPlain.includes("\"excel_error\":")) {
          if (textPlain.includes("'excel_error': ''") || textPlain.includes("\"excel_error\": \"\"")) {
            showSimpleModal("保存できました\n（Excel転記：成功）");
          } else {
            showSimpleModal("保存できました\n（Excel転記：失敗）");
          }
        } else {
          showSimpleModal("保存できました\n（Excel転記：成功）");
        }
      } else {
        // excel_updated false の場合もあり得る
        if (textPlain.includes("excel_error") && !(textPlain.includes("'excel_error': ''") || textPlain.includes("\"excel_error\": \"\""))) {
          showSimpleModal("保存できました\n（Excel転記：失敗）");
        } else {
          showSimpleModal("保存できました");
        }
      }
      }

      return res;
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

function showSimpleModal(message){
  var msg = document.getElementById("simple-modal-message");
  var ovl = document.getElementById("simple-modal-overlay");
  if(!msg || !ovl) return;

  msg.textContent = message;
  ovl.style.display = "block";

  // アニメーション用（次フレームで class 付与）
  requestAnimationFrame(function(){
    ovl.classList.add("show");
  });
}

function hideSimpleModal(){
  var ovl = document.getElementById("simple-modal-overlay");
  if(!ovl) return;

  ovl.classList.remove("show");
  setTimeout(function(){
    ovl.style.display = "none";
  }, 150);
}

// 数値変換用のヘルパー
function parseVal(id) {
    var el = document.getElementById(id);
    if (!el) return 0;
    // カンマ、円記号、△を除去して数値化
    var val = el.innerText.replace(/,/g, '').replace('¥', '').replace('△', '-').replace('▲', '-');
    return parseFloat(val) || 0;
}

function updateAllCalculations() {
    // 期間（前々期、前期、今期）ごとにループ
    const periods = ["前々期", "前期", "今期"];

    periods.forEach(p => {
        // 1. 各区分の基準値（分母）を取得
        var totalAsset = parseVal('val-45-' + p); // 資産合計
        var totalLiab  = parseVal('val-75-' + p); // 負債純資産合計
        var totalMfg   = parseVal('val-111-' + p); // 当期製造費用
        var totalSales = parseVal('val-112-' + p); // 売上高

        // 2. 指標の計算 (79行, 80行)
        var keiei = totalAsset - (parseVal('val-25-' + p) + parseVal('val-27-' + p) + parseVal('val-44-' + p));
        var unten = (parseVal('val-5-' + p) + parseVal('val-10-' + p)) - parseVal('val-52-' + p);

        // 表示の更新 (IDは HTML生成時のID体系に合わせてください)
        if(document.getElementById('val-79-' + p)) document.getElementById('val-79-' + p).innerText = keiei.toLocaleString();
        if(document.getElementById('val-80-' + p)) document.getElementById('val-80-' + p).innerText = unten.toLocaleString();

        // 3. 全154行の構成比計算
        for (var i = 1; i <= 154; i++) {
            var val = parseVal('val-' + i + '-' + p);
            var denom = 0;

            // 行番号に応じた分母の割り当て
            if (i <= 45 || i == 79 || i == 80) denom = totalAsset;
            else if (i <= 78) denom = totalLiab;
            else if (i <= 111) denom = totalMfg;
            else if (i <= 154) denom = totalSales;

            var ratio = (denom !== 0) ? (val / denom * 100) : 0;

            // 構成比セルの更新 (例: id="ratio-1-前々期")
            var ratioEl = document.getElementById('ratio-' + i + '-' + p);
            if (ratioEl) {
                ratioEl.innerText = ratio.toFixed(2) + '%';
            }
        }
    });
}

// ページ読み込み完了時やデータ反映時に実行するように設定
window.onload = updateAllCalculations;
// 既存の数値セット処理に割り込んで構成比を計算する関数
function updateComponentRatios(period) {
    // 基準値（分母）の取得
    const getV = (n) => {
        const el = document.getElementById(`val-${n}-${period}`);
        return el ? parseFloat(el.innerText.replace(/,/g, '')) || 0 : 0;
    };

    const d45 = getV(45);  // 資産合計
    const d75 = getV(75);  // 負債純資産合計
    const d111 = getV(111); // 製造費用合計
    const d112 = getV(112); // 売上高

    // 1行目から154行目までループ
    for (let i = 1; i <= 154; i++) {
        let val = getV(i);
        let denom = (i <= 45 || i == 79 || i == 80) ? d45 :
                    (i <= 78) ? d75 :
                    (i <= 111) ? d111 : d112;

        let ratio = (denom !== 0) ? ((val / denom) * 100).toFixed(2) : "0.00";
        let ratioEl = document.getElementById(`ratio-${i}-${period}`);
        if (ratioEl) ratioEl.innerText = ratio + "%";
    }
}

// 既存の _set_row_data や数値更新イベントからこれを呼び出すように紐付けます
</script>
"""

action_buttons_vertical = (
    f'<div class="btn-container vertical">'
    f'<button class="btn" onclick="toggleCols()">表示切替</button>'
    f'<button class="btn btn-save" onclick="_saveToColab()">データ更新・保存</button>'
    f'</div>'
)


# ------------------------------------------------------------------
# 9. 表示（デバッグログはコメントアウトで非表示）
# ------------------------------------------------------------------
if (not NO_HTML) and display and HTML:
    display(HTML(
        style + data_tag + script + modal_html +
        # ===== 上部：縦2ボタン =====
        action_buttons_vertical +
        f'<div id="report-container" class="show-all">'
        f'{_spec_warning_html}{full_html}'
        # f'{debug_panel}'  # ← デバッグログを復活する場合はこの行のコメントを外す
        f'</div>'
        # ===== 下部：縦2ボタン =====
        + action_buttons_vertical
    ))
# from IPython.display import HTML, display
# import html as _html
# # ★ Colab上の表示は iframe に隔離（Colabの script 差し替え/eval を回避）
# _srcdoc = _html.escape(full_html, quote=True)

# # 高さは必要に応じて調整してください（例：900px）
# display(HTML(
#     f'<iframe srcdoc="{_srcdoc}" '
#     f'style="width:100%; height:900px; border:0; background:white;"></iframe>'
# ))



# ------------------------------------------------------------------
# 10. Cloud Run 向け：HTMLをファイルに書き出し（S3アップロード用）
# ------------------------------------------------------------------
if not NO_HTML:
    try:
        # display 用に組み立てたのと同じHTMLを保存する
        html_out = (
            style + data_tag + script + modal_html +
            action_buttons_vertical +
            f'<div id="report-container" class="show-all">'
            f'{_spec_warning_html}{full_html}'
            f'</div>'
            + action_buttons_vertical
        )
        with open(HTML_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(html_out)
    except Exception as _e:
        # HTML保存失敗でも JSON は生成済みなので落とさない
        pass
