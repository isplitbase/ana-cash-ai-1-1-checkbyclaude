
# --- injected for non-notebook runtime ---
try:
    from IPython.display import display as display  # type: ignore
except Exception:
    def display(*args, **kwargs):
        return None
# --- end injected ---

#create_html
#

import json
import os
from IPython.display import HTML

# --- Colab専用：JS→Python コールバック登録 ---
try:
    from google.colab import output as colab_output
    _IS_COLAB = True
except Exception:
    colab_output = None
    _IS_COLAB = False

# 保存先（Colab実行ディレクトリ）
OUTPUT_PATH = "output_updated.json"

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
    """
    payload は JS から渡される dict を想定:
      {"data": [ {行番号:..., ...}, ... ]}
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

        # 保存前に精密セル情報を付与
        data = add_precise_cell_references_to_data(data)

        abs_path = os.path.abspath(OUTPUT_PATH)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        exists = os.path.exists(abs_path)
        size = os.path.getsize(abs_path) if exists else -1

        return {
            "ok": True,
            "path": abs_path,
            "exists": exists,
            "size": size
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}

# Colab上なら callback を登録
if _IS_COLAB:
    colab_output.register_callback("save_output_updated_json", _save_output_updated_json)

# ------------------------------------------------------------------
# 1. データの読み込み
# ------------------------------------------------------------------
try:
    with open('output.json', 'r', encoding='utf-8') as f:
        json_data = json.load(f)
except:
    try:
        with open('output (11).json', 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except:
        json_data = []

data_dict = {item['行番号']: item for item in json_data}

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
    return (
        _get_num(48, period_key) +
        _get_num(57, period_key) +
        _get_num(58, period_key) +
        _get_num(77, period_key)
    )

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

    # 既存の「集計方法」を保持し、無ければ補完する
    if "集計方法" not in data_dict[row_no] or data_dict[row_no].get("集計方法") in (None, "", '""', '\"\"'):
        data_dict[row_no]["集計方法"] = "自動計算"

    for pk in PERIOD_KEYS:
        data_dict[row_no][pk] = int(round(vals.get(pk, 0)))

    vv, vp, vc = [float(data_dict[row_no][k]) for k in PERIOD_KEYS]
    data_dict[row_no]["前期増減額"] = int(vp - vv)
    data_dict[row_no]["今期増減額"] = int(vc - vp)
    data_dict[row_no]["前期前年比増加率"] = int(round((vp / vv - 1) * 100)) if vv else 0
    data_dict[row_no]["今期前年比増加率"] = int(round((vc / vp - 1) * 100)) if vp else 0

    for k in ["前々期構成比", "前期構成比", "今期構成比"]:
        if k not in data_dict[row_no]:
            data_dict[row_no][k] = 0

# ------------------------------------------------------------------
# 3. 解析・ログ出力用関数（160, 162, 163行用）
# ------------------------------------------------------------------
debug_logs = []

def calc_and_log_metrics(col):
    r112 = _get_num(112, col); r114 = _get_num(114, col)
    r84  = _get_num(84, col);  r110 = _get_num(110, col)
    r118 = _get_num(118, col); r109 = _get_num(109, col)
    sumV1 = _sum_v(85, 104, col); sumV2 = _sum_v(121, 138, col)
    kakou = r112 - r114 - (r84 + sumV1 + r110 + r118 + sumV2 - r109)

    r154 = _get_num(154, col); r161 = _get_num(161, col)
    r155 = _get_num(155, col); r156 = _get_num(156, col)
    cf = r154 + r161 - r155 - r156

    kariire = _calc_borrowings_excel(col)

    log = f"<div style='border-left:4px solid #17a2b8; padding:8px; margin:5px; background:#f0faff; font-family:monospace; font-size:12px;'>"
    log += f"<b>【データ解析実行ログ: {col}】</b><br>"
    log += f" <b>▶ 160.加工高: {kakou:,.0f}</b> (内訳: 売上等{r112-r114:,.0f} - 控除{r84+sumV1+r110+r118+sumV2:,.0f} - 他勘定{r109:,.0f})<br>"
    log += f" <b>▶ 162.CF: {cf:,.0f}</b> (内訳: 利益{r154:,.0f} + 償却(161行){r161:,.0f} - 配当{r155:,.0f} - 賞与{r156:,.0f})<br>"
    log += f" <b>▶ 163.借入金合計: {kariire:,.0f}</b> (内訳: 48行+57行+58行+77行)<br>"
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
            vals[pk] = (
                _get_num(4, pk) + _get_num(3, pk) + _get_num(11, pk) + _get_num(77, pk) + _get_num(78, pk)
                - (_get_num(46, pk) + _get_num(47, pk) + _get_num(78, pk))
            )
    _set_row_data(rn, name, vals)

# ------------------------------------------------------------------
# 4. メイン集計実行ループ（155-164）
# ------------------------------------------------------------------
for rn in range(155, 165):
    name = mapping.get(rn, f"項目{rn}")

    if rn in [155, 156, 157, 158]:
        vals = {pk: _get_num(rn, pk) for pk in PERIOD_KEYS}
    elif rn == 159:
        vals = {pk: (_get_num(157, pk) + _get_num(158, pk)) for pk in PERIOD_KEYS}
    elif rn == 161:
        vals = {}
        for pk in PERIOD_KEYS:
            s_mfg = sum(_get_num(r, pk) for r in range(85, 105) if "減価償却" in (data_dict.get(r, {}).get("勘定科目") or ""))
            s_adm = sum(_get_num(r, pk) for r in range(121, 139) if "減価償却" in (data_dict.get(r, {}).get("勘定科目") or ""))
            vals[pk] = s_mfg + s_adm
    elif rn in [160, 162, 163]:
        results = {pk: calc_and_log_metrics(pk) for pk in PERIOD_KEYS}
        if rn == 160:
            vals = {pk: results[pk]["kakou"] for pk in PERIOD_KEYS}
        elif rn == 162:
            vals = {pk: results[pk]["cf"] for pk in PERIOD_KEYS}
        elif rn == 163:
            vals = {pk: results[pk]["kariire"] for pk in PERIOD_KEYS}
    elif rn == 164:
        vals = {pk: (_get_num(89, pk) + _get_num(121, pk) + _get_num(122, pk) + _get_num(123, pk) + _get_num(124, pk)) for pk in PERIOD_KEYS}
    else:
        vals = {pk: _get_num(rn, pk) for pk in PERIOD_KEYS}

    _set_row_data(rn, name, vals)

for rn in [155, 156, 157, 158]:
    if rn in data_dict:
        data_dict[rn]["集計方法"] = "入力"
if 159 in data_dict:
    data_dict[159]["集計方法"] = "自動計算(JS)"

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
        border: 2px solid #333;
        margin-bottom: 20px;
    }

    .excel-table th, .excel-table td {
        border: 1px solid #999;
        padding: 4px 6px;
        overflow: hidden;
        white-space: nowrap !important;
        text-overflow: clip;
        box-sizing: border-box;
    }
    .excel-table th { background-color: #f2f2f2; text-align: center; font-weight: bold; }

    .w-v { width: 28px !important; }
    .w-subject { width: 180px !important; }

    .excel-table col.c-amt { width: 120px !important; }
    th.col-amt, td.col-amt { width: 120px !important; text-align: right !important; font-family: "Consolas", monospace; }
    th.col-amt { text-align: center !important; }

    .excel-table col.c-pct { display: none !important; width: 0px !important; }
    .col-pct { display: none !important; width: 60px !important; text-align: center !important; font-size: 11px; color: #666; }

    .excel-table col.c-diff { display: none !important; width: 0px !important; }
    .col-diff, .diff-group { display: none !important; width: 120px !important; text-align: right !important; font-family: "Consolas", monospace; }
    th.col-diff, th.diff-group { text-align: center !important; }

    .excel-table col.c-memo { width: 400px !important; }
    td.col-memo { width: 400px !important; text-align: left !important; white-space: normal !important; }

    .show-all .excel-table col.c-pct { display: table-column !important; width: 60px !important; }
    .show-all .excel-table col.c-diff { display: table-column !important; width: 120px !important; }
    .show-all .col-pct, .show-all .col-diff, .show-all .diff-group { display: table-cell !important; }

    .total-row { background-color: #e6f3ff !important; font-weight: bold; }
    .grand-total { background-color: #d9ead3 !important; font-weight: bold; }

    .btn-container { position: sticky; top: 0; background: white; z-index: 100; padding: 10px 0; display: flex; gap: 10px; border-bottom: 1px solid #ddd; }
    .btn { padding: 8px 16px; cursor: pointer; background: #007bff; color: white; border: none; border-radius: 4px; font-weight: bold; }

    .save-panel { margin-top: 20px; padding: 15px; border: 1px solid #ddd; background: #fff; display: flex; justify-content: flex-end; }
    .btn-save { padding: 10px 18px; cursor: pointer; background: #dc3545; color: white; border: none; border-radius: 4px; font-weight: bold; }
</style>
"""

def render_rows(start, end):
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
        h += f'<tr{cls}><td colspan="4">{subject}</td>'

        for k in ["前々期", "前々期構成比", "前期", "前期構成比", "前期前年比増加率",
                  "今期", "今期構成比", "今期前年比増加率", "前期増減額", "今期増減額"]:
            v = row.get(k, 0)
            c = "col-pct" if "構成" in k or "増加率" in k else "col-diff" if "増減" in k else "col-amt"

            # 77-78：入力
            if i in [77, 78] and k in ["前々期", "前期", "今期"]:
                try:
                    num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                except:
                    num_v = 0.0
                disp = (
                    f'<input type="number" step="1" '
                    f'id="inp-r{i}-{k}" name="inp-r{i}-{k}" '
                    f'value="{int(round(num_v))}" '
                    f'style="width:100%; box-sizing:border-box; text-align:right; font-family:Consolas, monospace;">'
                )
                h += f'<td class="{c}">{disp}</td>'
                continue

            # 155-158：入力
            if i in [155, 156, 157, 158] and k in ["前々期", "前期", "今期"]:
                try:
                    num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                except:
                    num_v = 0.0
                disp = (
                    f'<input type="number" step="1" '
                    f'id="inp-r{i}-{k}" name="inp-r{i}-{k}" '
                    f'value="{int(round(num_v))}" '
                    f'style="width:100%; box-sizing:border-box; text-align:right; font-family:Consolas, monospace;">'
                )
                h += f'<td class="{c}">{disp}</td>'
                continue

            # 159：JS自動計算
            if i == 159:
                if k in ["前々期", "前期", "今期"]:
                    try:
                        num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                    except:
                        num_v = 0.0
                    disp = f'<span id="calc-r159-{k}">{int(round(num_v)):,}</span>'
                    h += f'<td class="{c}">{disp}</td>'
                    continue
                if k in ["前期増減額", "今期増減額"]:
                    try:
                        num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                    except:
                        num_v = 0.0
                    disp = f'<span id="calc-r159-{k}">{int(round(num_v)):,}</span>'
                    h += f'<td class="{c}">{disp}</td>'
                    continue
                if k in ["前期前年比増加率", "今期前年比増加率"]:
                    try:
                        num_v = float(v) if v not in ['""', '\"\"', None, ""] else 0.0
                    except:
                        num_v = 0.0
                    disp = f'<span id="calc-r159-{k}">{int(round(num_v))}%</span>'
                    h += f'<td class="{c}">{disp}</td>'
                    continue

            if v in ['""', '\"\"']:
                disp = ""
            else:
                try:
                    num_v = float(v)
                    disp = f"{v}%" if "col-pct" in c else f"{int(num_v):,}"
                except:
                    disp = v
            h += f'<td class="{c}">{disp}</td>'

        memo = row.get("集計方法", "")
        if memo in ['""', '\"\"']:
            memo = ""
        h += f'<td class="col-memo">{memo}</td></tr>'
    return h

def create_table(start, end, title):
    return (
        f'<div class="report-title">{title}</div>'
        f'<table class="excel-table">'
        f'<colgroup>'
        f'  <col class="w-v"><col class="w-v"><col class="w-v"><col class="w-subject">'
        f'  <col class="c-amt"><col class="c-pct">'
        f'  <col class="c-amt"><col class="c-pct"><col class="c-pct">'
        f'  <col class="c-amt"><col class="c-pct"><col class="c-pct">'
        f'  <col class="c-diff"><col class="c-diff">'
        f'  <col class="c-memo">'
        f'</colgroup>'
        f'<thead>'
        f'<tr>'
        f'  <th colspan="4" rowspan="2">勘定科目</th>'
        f'  <th class="col-amt" rowspan="2">前々期</th><th class="col-pct" rowspan="2">構成</th>'
        f'  <th class="col-amt" rowspan="2">前期</th><th class="col-pct" rowspan="2">構成</th><th class="col-pct" rowspan="2">前年比</th>'
        f'  <th class="col-amt" rowspan="2">今期</th><th class="col-pct" rowspan="2">構成</th><th class="col-pct" rowspan="2">前年比</th>'
        f'  <th colspan="2" class="diff-group">増減額</th>'
        f'  <th class="col-memo" rowspan="2">備考</th>'
        f'</tr>'
        f'<tr>'
        f'  <th class="col-diff">前期</th><th class="col-diff">今期</th>'
        f'</tr>'
        f'</thead>'
        f'<tbody>{render_rows(start, end)}</tbody>'
        f'</table>'
    )

# 155-159 と 160-164 を別テーブルに分離（要件）
full_html = (
    create_table(1, 45, "貸借対照表（資産の部）") +
    create_table(46, 76, "貸借対照表（負債・純資産の部）") +
    create_table(77, 78, "入力項目") +
    create_table(79, 80, "集計項目") +
    create_table(81, 111, "製造原価報告書") +
    create_table(112, 154, "損益計算書") +
    create_table(155, 159, "入力項目／集計項目") +
    create_table(160, 164, "集計項目")
)

debug_panel = f'<div class="debug-panel"><h3>【詳細デバッグログ】</h3>{"".join(debug_logs)}</div>'

save_panel = (
    '<div class="save-panel">'
    '<button class="btn-save" onclick="window._saveToColab()">データ更新・保存</button>'
    '</div>'
)

# ------------------------------------------------------------------
# 6. 初期状態の output_updated.json を保存（サーバ側）
#    ※保存前に「シート名」「セル」を付与
# ------------------------------------------------------------------
json_output = sorted(data_dict.values(), key=lambda x: x.get("行番号", 0))
json_output = add_precise_cell_references_to_data(json_output)

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(json_output, f, ensure_ascii=False, indent=2)

# ------------------------------------------------------------------
# 7. JS側に渡すデータは JSON直書きせず、application/json に埋め込む（構文エラー回避）
# ------------------------------------------------------------------
json_for_html = json.dumps(json_output, ensure_ascii=False)
data_tag = f'<script id="report-data-json" type="application/json">{json_for_html}</script>'

# ------------------------------------------------------------------
# 8. JS（159即時更新、保存ボタンでColab callback、入力は 77-78 と 155-158 を同期）
# ------------------------------------------------------------------
script = """
<script>
    window.toggleCols = function() {
        var c = document.getElementById('report-container');
        if (c) c.classList.toggle('show-all');
    };

    window.downloadHTML = function() {
        var styles = document.getElementById('report-styles');
        var container = document.getElementById('report-container');
        if (!styles || !container) return;
        var isShowAll = container.classList.contains('show-all');
        var content = container.innerHTML;
        var fullHtml = '<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">' +
                       styles.outerHTML +
                       '</head><body>' +
                       '<div class="btn-container">' +
                       '<button class="btn" onclick="toggleCols()">表示切替</button>' +
                       '<button class="btn" style="background:#28a745" onclick="downloadHTML()">HTML保存</button>' +
                       '</div>' +
                       '<div id="report-container" class="' + (isShowAll ? 'show-all' : '') + '">' +
                       content +
                       '</div>' +
                       '<script>' +
                       'window.toggleCols = ' + window.toggleCols.toString() + '; ' +
                       'window.downloadHTML = ' + window.downloadHTML.toString() + '; ' +
                       '<\\/script>' +
                       '</body></html>';
        var blob = new Blob([fullHtml], {type:'text/html'});
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'report.html';
        a.click();
    };

    // JSONは scriptタグから読み込む（JS構文として直書きしない）
    (function(){
        var el = document.getElementById('report-data-json');
        if (!el) {
            window.reportData = [];
            return;
        }
        try {
            window.reportData = JSON.parse(el.textContent || '[]');
        } catch (e) {
            console.error(e);
            window.reportData = [];
        }
    })();

    window._findRowObj = function(rowNo) {
        for (var i = 0; i < window.reportData.length; i++) {
            if (window.reportData[i] && window.reportData[i]['行番号'] === rowNo) return window.reportData[i];
        }
        return null;
    };

    window._toInt = function(v) {
        if (v === null || v === undefined || v === '') return 0;
        var n = Number(v);
        if (isNaN(n)) return 0;
        return Math.round(n);
    };

    window._fmtInt = function(n) {
        var x = window._toInt(n);
        return x.toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",");
    };

    window._updateDerivedFields = function(rowObj) {
        if (!rowObj) return;

        var vv = window._toInt(rowObj['前々期']);
        var vp = window._toInt(rowObj['前期']);
        var vc = window._toInt(rowObj['今期']);

        rowObj['前期増減額'] = vp - vv;
        rowObj['今期増減額'] = vc - vp;

        rowObj['前期前年比増加率'] = (vv !== 0) ? Math.round((vp / vv - 1) * 100) : 0;
        rowObj['今期前年比増加率'] = (vp !== 0) ? Math.round((vc / vp - 1) * 100) : 0;

        if (rowObj['前々期構成比'] === undefined) rowObj['前々期構成比'] = 0;
        if (rowObj['前期構成比'] === undefined) rowObj['前期構成比'] = 0;
        if (rowObj['今期構成比'] === undefined) rowObj['今期構成比'] = 0;
    };

    // 入力（77-78,155-158）を reportData に反映し、159 を即時再計算
    window._syncInputsAndRecalc159 = function() {
        // 77-78
        [77,78].forEach(function(rn) {
            var rowObj = window._findRowObj(rn);
            if (!rowObj) return;

            ['前々期','前期','今期'].forEach(function(pk) {
                var inp = document.getElementById('inp-r' + rn + '-' + pk);
                if (!inp) return;
                rowObj[pk] = window._toInt(inp.value);
            });

            window._updateDerivedFields(rowObj);
        });

        // 155-158
        [155,156,157,158].forEach(function(rn) {
            var rowObj = window._findRowObj(rn);
            if (!rowObj) return;

            ['前々期','前期','今期'].forEach(function(pk) {
                var inp = document.getElementById('inp-r' + rn + '-' + pk);
                if (!inp) return;
                rowObj[pk] = window._toInt(inp.value);
            });

            window._updateDerivedFields(rowObj);
        });

        // 159 = 157 + 158（即時）
        var r157 = window._findRowObj(157);
        var r158 = window._findRowObj(158);
        var r159 = window._findRowObj(159);

        if (r157 && r158 && r159) {
            ['前々期','前期','今期'].forEach(function(pk) {
                r159[pk] = window._toInt(r157[pk]) + window._toInt(r158[pk]);
                var sp = document.getElementById('calc-r159-' + pk);
                if (sp) sp.textContent = window._fmtInt(r159[pk]);
            });

            window._updateDerivedFields(r159);

            var spDiffPrev = document.getElementById('calc-r159-前期増減額');
            var spDiffCurr = document.getElementById('calc-r159-今期増減額');
            if (spDiffPrev) spDiffPrev.textContent = window._fmtInt(r159['前期増減額']);
            if (spDiffCurr) spDiffCurr.textContent = window._fmtInt(r159['今期増減額']);

            var spRatePrev = document.getElementById('calc-r159-前期前年比増加率');
            var spRateCurr = document.getElementById('calc-r159-今期前年比増加率');
            if (spRatePrev) spRatePrev.textContent = window._toInt(r159['前期前年比増加率']).toString() + '%';
            if (spRateCurr) spRateCurr.textContent = window._toInt(r159['今期前年比増加率']).toString() + '%';
        }
    };

    window._attachInputHandlers = function() {
        var ids = [];

        // 77-78
        [77,78].forEach(function(rn) {
            ['前々期','前期','今期'].forEach(function(pk) {
                ids.push('inp-r' + rn + '-' + pk);
            });
        });

        // 155-158
        [155,156,157,158].forEach(function(rn) {
            ['前々期','前期','今期'].forEach(function(pk) {
                ids.push('inp-r' + rn + '-' + pk);
            });
        });

        ids.forEach(function(id) {
            var el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('input', function() {
                window._syncInputsAndRecalc159();
            });
            el.addEventListener('change', function() {
                window._syncInputsAndRecalc159();
            });
        });
    };
    window._rebuildReportDataFromDOM = function() {
      var result = [];

      var tables = document.querySelectorAll('table.excel-table');
      tables.forEach(function(tbl) {
          var rows = tbl.querySelectorAll('tbody tr');
          rows.forEach(function(tr) {
              var tds = tr.querySelectorAll('td');
              if (tds.length === 0) return;

              // 行番号は data_dict 由来で reportData にのみ存在するため、
              // 表示されている勘定科目名で逆引きする
              var subject = tds[0].innerText.trim();
              if (!subject) return;

              var rowObj = null;
              for (var i = 0; i < window.reportData.length; i++) {
                  if (window.reportData[i]['勘定科目'] === subject) {
                      rowObj = window.reportData[i];
                      break;
                  }
              }
              if (!rowObj) return;

              ['前々期','前期','今期'].forEach(function(pk) {
                  var inp = document.getElementById('inp-r' + rowObj['行番号'] + '-' + pk);
                  if (inp) {
                      rowObj[pk] = Number(inp.value) || 0;
                  }
              });

              result.push(rowObj);
          });
    // Colab callback 保存（暫定）
    window._saveToColab = async function() {
        try {
            // ★ ここが重要：保存前に必ず再構築
            window._rebuildReportDataFromDOM();

            if (!(window.google && google.colab && google.colab.kernel && google.colab.kernel.invokeFunction)) {
                alert('Colab環境ではないため、callback保存は実行できません。');
                return;
            }

            var payload = { data: window.reportData };
            var r = await google.colab.kernel.invokeFunction(
                'save_output_updated_json',
                [payload],
                {}
            );

            var res = r && r.data ? r.data : r;

            if (res && res['text/plain']) {
                var s = res['text/plain']
                    .replace(/\bTrue\b/g,'true')
                    .replace(/\bFalse\b/g,'false')
                    .replace(/'/g,'"');
                try { res = JSON.parse(s); } catch(e) {}
            }

            if (res && res.ok === true) {
                alert('保存しました: ' + (res.path || 'output_updated.json'));
                return;
            }

            alert('保存に失敗しました\n' + JSON.stringify(r));
        } catch (e) {
            console.error(e);
            alert('保存に失敗しました: ' + e);
        }
    };

    window._initWhenReady = function(retry) {
        // 155系の入力が見えるまで待つ（Colab埋め込み対策）
        var el = document.getElementById('inp-r157-前々期');
        if (!el) {
            if (retry > 0) {
                setTimeout(function(){ window._initWhenReady(retry - 1); }, 50);
            }
            return;
        }
        window._attachInputHandlers();
        window._syncInputsAndRecalc159();
    };

    setTimeout(function(){ window._initWhenReady(200); }, 0);
</script>
"""

# ------------------------------------------------------------------
# 9. 表示（デバッグログはコメントアウトで非表示）
# ------------------------------------------------------------------
display(HTML(
    style + data_tag + script +
    f'<div class="btn-container">'
    f'<button class="btn" onclick="toggleCols()">表示切替</button>'
    f'<button class="btn" style="background:#28a745" onclick="downloadHTML()">HTML保存</button>'
    f'</div>'
    f'<div id="report-container" class="show-all">'
    f'{full_html}'
    # f'{debug_panel}'  # ← デバッグログを復活する場合はこの行のコメントを外す
    f'{save_panel}'
    f'</div>'
))

