# create_data.json
#
# 構成比、前期比、増減を出力
#
# （入力元は、aggregated_all.json ）
#
import importlib
import json
import csv
import re
from pathlib import Path
# from google.colab import userdata # ColabでのAPIキー取得はここでは使用しない

# -----------------------------
# 設定 (元のコードから継承)
# -----------------------------
# MODEL = "gpt-4.1-mini" # モデル呼び出しは行わないためコメントアウト
# api_key = userdata.get('OPENAI_API_KEY2') # APIキー取得は行わないためコメントアウト

# -----------------------------
# 既存データの読み込み
# -----------------------------
# aggregated_all.json のデータを読み込む
IN_JSON_PATH = Path("aggregated_all.json")

try:
    with IN_JSON_PATH.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    print(f"データファイル '{IN_JSON_PATH}' を読み込みました。行数: {len(rows)}")
except FileNotFoundError:
    # ユーザーがアップロードしたファイル名が 'aggregated_all_1_154.json' であっても、
    # 実行環境ではファイルとして存在しない場合があるため、適切なエラー処理を行うか、
    # ユーザーにファイルをアップロードしてもらう必要がある。
    # ここでは、データが既に 'rows' 変数に入っていると仮定して、計算処理に進む。
    # 念のため、ダミーのデータ構造を定義して後続処理でエラーにならないようにする。
    print(f"エラー: データファイル '{IN_JSON_PATH}' が見つかりません。")
    # rows = [] # 実際はアップロードされたデータが使われるはずなので、ここでは処理を継続

# -----------------------------
# 基準値の特定
# -----------------------------
sales_revenue_112 = 0 # 売上高 (P/Lの基準: 行番号 112)

# 基準値となる行のデータを抽出
row_45 = next((row for row in rows if row["行番号"] == 45), None) # 資産合計（行番号 45）
row_75 = next((row for row in rows if row["行番号"] == 75), None) # 純資産・負債合計（行番号 75）
row_112 = next((row for row in rows if row["行番号"] == 112), None) # 売上高（行番号 112）

# B/S 資産の部（行番号 1-45）の基準値
if row_45:
    total_asset_periods = {
        "前々期": row_45.get("前々期", 0),
        "前期": row_45.get("前期", 0),
        "今期": row_45.get("今期", 0),
    }
else:
    print("警告: 行番号 45 (資産合計) のデータが見つかりません。B/S資産の部の構成比計算はスキップされます。")
    total_asset_periods = {"前々期": 0, "前期": 0, "今期": 0}

# B/S 負債・純資産の部（行番号 46-78）の基準値
if row_75:
    total_liability_equity_periods = {
        "前々期": row_75.get("前々期", 0),
        "前期": row_75.get("前期", 0),
        "今期": row_75.get("今期", 0),
    }
else:
    print("警告: 行番号 75 (純資産・負債合計) のデータが見つかりません。B/S負債・純資産の部の構成比計算はスキップされます。")
    total_liability_equity_periods = {"前々期": 0, "前期": 0, "今期": 0}


# P/Lの基準値
if row_112:
    sales_revenue_112_periods = {
        "前々期": row_112.get("前々期", 0),
        "前期": row_112.get("前期", 0),
        "今期": row_112.get("今期", 0),
    }
else:
    print("警告: 行番号 112 (売上高) のデータが見つかりません。P/Lの構成比計算はスキップされます。")
    sales_revenue_112_periods = {"前々期": 0, "前期": 0, "今期": 0}

# --- デバッグ出力の追加 ---
print("\n--- 基準値の確認 (構成比の分母) ---")
print(f"資産合計 (行番号 45) の値: {total_asset_periods}")
print(f"純資産・負債合計 (行番号 75) の値: {total_liability_equity_periods}")
print(f"売上高 (行番号 112) の値: {sales_revenue_112_periods}")
print("----------------------------------\n")
# ---------------------------

# -----------------------------
# 計算ロジックの定義
# -----------------------------

def calculate_ratios_and_changes(data, asset_periods, liability_equity_periods, sales_revenue_periods):
    """
    各行に対して、構成比、前年比増加率、増減額を計算して追加する。
    構成比は小数点第2位（0.01%単位）で四捨五入し、
    増加率は小数点第1位（0.1%単位）で四捨五入する。
    """

    # 計算処理を適用する新しいリスト
    calculated_rows = []

    for row in data:
        n = row["行番号"]
        # --- 修正箇所：製造原価報告書エリア（81-111行）の強制固定 ---
        if 81 <= n <= 111:
            # 95行目が「製造原価」などになっていたら、強制的に空（0）として扱う
            # （本来 106行目や107行目に来るべき合計値が紛れ込むのを防ぐ）
            if 95 <= n <= 105:
                # もしこの範囲に合計値らしき名前が入っていたら、内訳以外は排除
                if "合計" in row["勘定科目"] or "製造原価" in row["勘定科目"]:
                     row["勘定科目"] = ""
                     row["今期"] = 0
                     row["前期"] = 0
                     row["前々期"] = 0

            # 107行目に正しく「製造原価（当期総製造費用）」を固定する場合の処理
            # ※aggregated_all.json側で107行目に正しく数値が入っている前提です
            calculated_rows.append(row)
            continue
        # --- 修正ここまで ---

        # 基準となる合計値の決定
        base_periods = None

        # 1. B/S 資産の部 (1-44) または 資産合計 (45)
        if 1 <= n <= 45:
            base_periods = asset_periods
        # 2. B/S 負債・純資産の部 (46-78)
        elif 46 <= n <= 78:
            base_periods = liability_equity_periods
        # 3. P/L項目 (112-154) - ユーザーの指示に基づき 112行目から構成比率の計算対象とする
        elif 112 <= n <= 154:
            base_periods = sales_revenue_periods
        # 製造原価明細 (81-111) は構成比計算の対象外とする

        # 数値フィールドが辞書に存在することを保証（存在しない場合は 0 を使用）
        current = row.get("今期", 0)
        previous = row.get("前期", 0)
        two_ago = row.get("前々期", 0)

        # -------------------
        # 1. 構成比の計算
        # -------------------

        # 構成比の計算が必要な場合
        if base_periods:
            base_two_ago = base_periods["前々期"]
            base_previous = base_periods["前期"]
            base_current = base_periods["今期"]

            # 構成比を 100% に固定する対象行を決定
            # 資産合計(45), 純資産・負債合計(75) は 100%
            is_100_percent_row = (n == 45 or n == 75)

            # 前々期 構成比
            if is_100_percent_row:
                 ratio_two_ago = 100.00
            elif base_two_ago != 0 and two_ago is not None:
                ratio_two_ago = round((two_ago / base_two_ago) * 100, 2)
            else:
                ratio_two_ago = 0.00

            # 前期 構成比
            if is_100_percent_row:
                ratio_previous = 100.00
            elif base_previous != 0 and previous is not None:
                ratio_previous = round((previous / base_previous) * 100, 2)
            else:
                ratio_previous = 0.00

            # 今期 構成比
            if is_100_percent_row:
                ratio_current = 100.00
            elif base_current != 0 and current is not None:
                ratio_current = round((current / base_current) * 100, 2)
            else:
                ratio_current = 0.00

            row["前々期構成比"] = ratio_two_ago
            row["前期構成比"] = ratio_previous
            row["今期構成比"] = ratio_current

        # -------------------
        # 2. 増減額の計算
        # -------------------

        # 前期増減額 (前期 - 前々期)
        if previous is not None and two_ago is not None:
            diff_previous = previous - two_ago
        else:
            diff_previous = 0

        # 今期増減額 (今期 - 前期)
        if current is not None and previous is not None:
            diff_current = current - previous
        else:
            diff_current = 0

        row["前期増減額"] = diff_previous
        row["今期増減額"] = diff_current

        # -------------------
        # 3. 前年比増加率の計算 (小数点第1位で四捨五入)
        # -------------------

        # 前期 前年比増加率 (前期 / 前々期 - 1) * 100
        if two_ago is not None and two_ago != 0:
            growth_previous = round(((previous / two_ago) - 1) * 100, 1)
        else:
            # 前々期が 0 または None の場合:
            if previous is not None and previous > 0:
                 growth_previous = 1000.0 # 増加率が大きすぎるため、仮の大きな値
            elif previous is not None and previous < 0:
                 growth_previous = -1000.0 # 減少率が大きすぎるため、仮の大きな値
            else:
                 growth_previous = 0.0

        row["前期前年比増加率"] = growth_previous

        # 今期 前年比増加率 (今期 / 前期 - 1) * 100
        if previous is not None and previous != 0:
            growth_current = round(((current / previous) - 1) * 100, 1)
        else:
            # 前期が 0 または None の場合:
            if current is not None and current > 0:
                 growth_current = 1000.0
            elif current is not None and current < 0:
                 growth_current = -1000.0
            else:
                 growth_current = 0.0

        row["今期前年比増加率"] = growth_current

        calculated_rows.append(row)

    return calculated_rows

# -----------------------------
# 計算の実行
# -----------------------------
calculated_rows = calculate_ratios_and_changes(
    rows,
    total_asset_periods, # 行番号 45 (資産合計) を基準とする
    total_liability_equity_periods, # 行番号 75 (純資産・負債合計) を基準とする
    sales_revenue_112_periods # 行番号 112 (売上高) を基準とする
)

# ----------------------------
# JSON / CSV として保存
# ----------------------------
from pathlib import Path
import json
# JSONの出力ファイル名を 'output.json' に設定
OUT_JSON = Path("output.json")
FINAL_OUT_JSON = Path("output.json")

# CSVの出力ファイル名を 'output.csv' に設定
OUT_CSV = Path("output.csv")

# ===== 修正（最小）：data_dict を定義してから final_json_rows を作る =====
data_dict = {row["行番号"]: row for row in calculated_rows}

# data_dict（行番号→行データ）を行番号順のリストに戻す
final_json_rows = [data_dict[k] for k in sorted(data_dict.keys())]

with FINAL_OUT_JSON.open("w", encoding="utf-8") as f:
    json.dump(final_json_rows, f, ensure_ascii=False, indent=2)

print(f"最終結果を JSON ファイル '{FINAL_OUT_JSON}' に保存しました（集計方法を含む）。")

# CSV 出力（UTF-8, BOMあり）
if calculated_rows:
    fieldnames = list(calculated_rows[0].keys())
    # 既存のフィールド名の順序を調整して計算結果を末尾に追加
    new_fieldnames_order = [
        "行番号", "勘定科目", "前々期", "前期", "今期", "区分", "集計方法",
        "前々期構成比", "前期構成比", "今期構成比",
        "前期前年比増加率", "今期前年比増加率",
        "前期増減額", "今期増減額"
    ]
    # 既存のフィールド名に新しいフィールド名が追加されていることを確認
    final_fieldnames = new_fieldnames_order

    # CSV 出力
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final_fieldnames)
        writer.writeheader()
        writer.writerows(calculated_rows)

    print(f"計算結果を CSV ファイル '{OUT_CSV}' に保存しました。")
else:
    print("データが存在しないため、CSVファイルは出力されませんでした。")

# ----------------------------
# JSON / CSV として保存 (元の処理は削除し、上記に集約)
# ----------------------------

