import glob
import importlib
import os
import subprocess
import sys

import pandas as pd
import streamlit as st

import stock_list
from indicators.technical import add_technical_indicators
from services.price_service import fetch_price_data
from services.watchlist_service import add_custom_stock


st.set_page_config(



    page_title="台股篩選系統",
    page_icon="📊",
    layout="wide"
)


# =========================
# 表格顏色修正：避免偶數列白字看不到
# =========================
st.markdown("""
<style>
/* FORCE_TABLE_VISIBILITY_FIX */

table {
    width: 100%;
    border-collapse: collapse;
    background-color: #ffffff !important;
}

thead tr,
table thead tr,
table th {
    background-color: #111827 !important;
    color: #ffffff !important;
    font-weight: 700 !important;
}

tbody tr:nth-child(odd),
table tbody tr:nth-child(odd) {
    background-color: #ffffff !important;
    color: #111827 !important;
}

tbody tr:nth-child(even),
table tbody tr:nth-child(even) {
    background-color: #f3f4f6 !important;
    color: #111827 !important;
}

table td,
tbody td {
    color: #111827 !important;
    border-bottom: 1px solid #d1d5db !important;
    padding: 8px 10px !important;
}

table th {
    border-bottom: 1px solid #374151 !important;
    padding: 9px 10px !important;
}

.dataframe {
    color: #111827 !important;
    background-color: #ffffff !important;
}

.dataframe td {
    color: #111827 !important;
}

.dataframe tr:nth-child(even) td {
    background-color: #f3f4f6 !important;
}

.dataframe tr:nth-child(odd) td {
    background-color: #ffffff !important;
}
</style>
""", unsafe_allow_html=True)




# =========================
# 基礎工具
# =========================

def get_current_stock_meta():
    """
    重新讀取 stock_list.py。
    使用者新增自訂股票後，下一次 rerun 可以讀到最新候選清單。
    """
    reloaded_stock_list = importlib.reload(stock_list)
    return reloaded_stock_list.STOCK_META


def find_latest_report():
    patterns = [
        "data/output/stock_screener_v23_*.xlsx",
        "data/output/stock_screener_v22_*.xlsx",
        "data/output/stock_screener_v21_*.xlsx",
        "data/output/stock_screener_v2_*.xlsx",
        "data/output/stock_screener_*.xlsx",
    ]

    files = []

    for pattern in patterns:
        files.extend(glob.glob(pattern))

    if not files:
        return None

    return max(files, key=os.path.getmtime)


@st.cache_data
def load_report(file_path):
    return pd.read_excel(file_path)


@st.cache_data
def load_score_history():
    history_path = "data/history/score_history.csv"

    if not os.path.exists(history_path):
        return pd.DataFrame()

    df = pd.read_csv(history_path, dtype={"股票代號": str})

    if "資料日期" in df.columns:
        df["資料日期"] = pd.to_datetime(df["資料日期"], errors="coerce")

    return df


def clean_stock_id(value):
    value = str(value).strip()
    value = value.replace(".0", "")

    if "." in value:
        value = value.split(".")[0]

    return value


def prepare_report_df(df):
    df = df.copy()

    if "股票代號" in df.columns:
        df["股票代號"] = df["股票代號"].apply(clean_stock_id)

    numeric_cols = [
        "分數",
        "技術分",
        "法人籌碼分",
        "融資融券分",
        "收盤價",
        "近5日漲幅%",
        "MA5",
        "MA10",
        "MA60",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "收盤價" in df.columns:
        df["是否低於100"] = df["收盤價"].apply(
            lambda x: "是" if pd.notna(x) and x < 100 else "否"
        )

    return df


def safe_count(df, column, value):
    if column not in df.columns:
        return 0

    return len(df[df[column] == value])


def run_main_script():
    result = subprocess.run(
        [sys.executable, "main.py"],
        capture_output=True,
        text=True
    )

    return result


def show_html_table(df):
    if df.empty:
        st.info("沒有資料可以顯示")
        return

    html = df.to_html(index=False, escape=False)

    st.markdown(
        """
        <style>
        .table-container {
            width: 100%;
            overflow-x: auto;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 8px;
            margin-bottom: 12px;
        }

        table {
            border-collapse: collapse;
            width: 100%;
            font-size: 14px;
        }

        th {
            background-color: #1f4e78;
            color: white;
            padding: 8px;
            text-align: left;
            white-space: nowrap;
        }

        td {
            border-bottom: 1px solid #ddd;
            padding: 8px;
            vertical-align: top;
            white-space: nowrap;
        }

        tr:nth-child(even) {
            background-color: #f8f8f8;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f'<div class="table-container">{html}</div>',
        unsafe_allow_html=True
    )


def show_key_value_table(data: dict):
    rows = []

    for key, value in data.items():
        rows.append({
            "項目": key,
            "內容": value
        })

    df = pd.DataFrame(rows)
    show_html_table(df)


def build_candidate_symbols(stock_id: str):
    """
    盡量先用 stock_list.py 裡的正確 .TW / .TWO。
    找不到才自動試 .TW、.TWO。
    """
    stock_id = clean_stock_id(stock_id)

    candidates = []

    try:
        meta = get_current_stock_meta()

        for symbol in meta.keys():
            if symbol.split(".")[0] == stock_id:
                candidates.append(symbol)
    except Exception:
        pass

    candidates.extend([
        f"{stock_id}.TW",
        f"{stock_id}.TWO",
    ])

    # 去重但保留順序
    unique_candidates = []

    for symbol in candidates:
        if symbol not in unique_candidates:
            unique_candidates.append(symbol)

    return unique_candidates


# =========================
# K 線資料
# =========================

@st.cache_data
def load_price_chart_data(stock_id: str):
    candidates = build_candidate_symbols(stock_id)

    for symbol in candidates:
        try:
            df = fetch_price_data(symbol, period="6mo")

            if not df.empty:
                df = add_technical_indicators(df)
                df = df.reset_index()

                if "Date" not in df.columns:
                    df = df.rename(columns={df.columns[0]: "Date"})

                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

                return df, symbol
        except Exception:
            pass

    return pd.DataFrame(), None


# =========================
# SVG 圖表工具
# =========================

def normalize(value, min_value, max_value, top, bottom):
    if max_value == min_value:
        return (top + bottom) / 2

    return bottom - ((value - min_value) / (max_value - min_value)) * (bottom - top)


def draw_svg_kline_chart(price_df: pd.DataFrame):
    df = price_df.tail(90).copy().reset_index(drop=True)

    if df.empty:
        return ""

    width = 1100
    height = 560

    price_top = 40
    price_bottom = 360

    vol_top = 410
    vol_bottom = 520

    left = 50
    right = 30

    chart_width = width - left - right

    high_max = float(df["High"].max())
    low_min = float(df["Low"].min())

    price_padding = (high_max - low_min) * 0.08 if high_max > low_min else 1
    high_max += price_padding
    low_min -= price_padding

    vol_max = float(df["Volume"].max()) if float(df["Volume"].max()) > 0 else 1

    candle_count = len(df)
    step_x = chart_width / max(candle_count - 1, 1)
    candle_width = max(min(step_x * 0.55, 8), 3)

    svg_parts = []

    svg_parts.append(f"""
    <div style="width:100%; overflow-x:auto; border:1px solid #ddd; border-radius:8px; padding:8px;">
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    <rect x="0" y="0" width="{width}" height="{height}" fill="white"/>
    <text x="{left}" y="24" font-size="18" font-weight="bold">K Line Chart - Last 90 Trading Days</text>
    """)

    # 價格格線
    for i in range(5):
        y = price_top + i * (price_bottom - price_top) / 4
        price = high_max - i * (high_max - low_min) / 4

        svg_parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e5e5" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="8" y="{y + 4:.2f}" font-size="12" fill="#555">{price:.2f}</text>'
        )

    # 成交量區
    svg_parts.append(
        f'<line x1="{left}" y1="{vol_bottom}" x2="{width - right}" y2="{vol_bottom}" stroke="#e5e5e5" stroke-width="1"/>'
    )
    svg_parts.append(
        f'<text x="8" y="{vol_top + 12}" font-size="12" fill="#555">Volume</text>'
    )

    ma_paths = {
        "MA5": [],
        "MA10": [],
        "MA60": [],
    }

    for i, row in df.iterrows():
        x = left + i * step_x

        open_price = float(row["Open"])
        close_price = float(row["Close"])
        high_price = float(row["High"])
        low_price = float(row["Low"])
        volume = float(row["Volume"])

        color = "#d62728" if close_price >= open_price else "#2ca02c"

        y_open = normalize(open_price, low_min, high_max, price_top, price_bottom)
        y_close = normalize(close_price, low_min, high_max, price_top, price_bottom)
        y_high = normalize(high_price, low_min, high_max, price_top, price_bottom)
        y_low = normalize(low_price, low_min, high_max, price_top, price_bottom)

        svg_parts.append(
            f'<line x1="{x:.2f}" y1="{y_high:.2f}" x2="{x:.2f}" y2="{y_low:.2f}" stroke="{color}" stroke-width="1"/>'
        )

        rect_y = min(y_open, y_close)
        rect_height = abs(y_close - y_open)

        if rect_height < 1:
            rect_height = 1

        svg_parts.append(
            f'<rect x="{x - candle_width / 2:.2f}" y="{rect_y:.2f}" width="{candle_width:.2f}" height="{rect_height:.2f}" fill="{color}" opacity="0.85"/>'
        )

        vol_height = (volume / vol_max) * (vol_bottom - vol_top)

        svg_parts.append(
            f'<rect x="{x - candle_width / 2:.2f}" y="{vol_bottom - vol_height:.2f}" width="{candle_width:.2f}" height="{vol_height:.2f}" fill="{color}" opacity="0.45"/>'
        )

        for ma_name in ma_paths.keys():
            if ma_name in df.columns and pd.notna(row.get(ma_name)):
                ma_value = float(row[ma_name])
                ma_y = normalize(ma_value, low_min, high_max, price_top, price_bottom)
                ma_paths[ma_name].append((x, ma_y))

    ma_colors = {
        "MA5": "#1f77b4",
        "MA10": "#ff7f0e",
        "MA60": "#9467bd",
    }

    for ma_name, points in ma_paths.items():
        if len(points) >= 2:
            path_data = " ".join(
                [
                    f"{'M' if idx == 0 else 'L'} {x:.2f} {y:.2f}"
                    for idx, (x, y) in enumerate(points)
                ]
            )

            svg_parts.append(
                f'<path d="{path_data}" fill="none" stroke="{ma_colors[ma_name]}" stroke-width="2"/>'
            )

    # 圖例
    legend_x = left
    legend_y = height - 18

    legend_items = [
        ("上漲", "#d62728"),
        ("下跌", "#2ca02c"),
        ("MA5", "#1f77b4"),
        ("MA10", "#ff7f0e"),
        ("MA60", "#9467bd"),
    ]

    offset = 0

    for label, color in legend_items:
        svg_parts.append(
            f'<rect x="{legend_x + offset}" y="{legend_y - 10}" width="12" height="12" fill="{color}"/>'
        )
        svg_parts.append(
            f'<text x="{legend_x + offset + 18}" y="{legend_y}" font-size="12">{label}</text>'
        )
        offset += 75

    # 日期
    date_labels = df["Date"].dt.strftime("%m-%d").tolist()
    label_step = max(len(df) // 10, 1)

    for i in range(0, len(df), label_step):
        x = left + i * step_x
        label = date_labels[i]

        svg_parts.append(
            f'<text x="{x - 12:.2f}" y="{height - 38}" font-size="11" fill="#555" transform="rotate(45 {x:.2f},{height - 38})">{label}</text>'
        )

    svg_parts.append("</svg></div>")

    return "\n".join(svg_parts)


def draw_svg_score_history(history_df: pd.DataFrame, stock_id: str):
    if history_df.empty:
        return "", pd.DataFrame()

    stock_history = history_df[
        history_df["股票代號"].astype(str).apply(clean_stock_id) == str(stock_id)
    ].copy()

    if stock_history.empty:
        return "", pd.DataFrame()

    if "資料日期" in stock_history.columns:
        stock_history["資料日期"] = pd.to_datetime(stock_history["資料日期"], errors="coerce")

    stock_history = stock_history.sort_values("資料日期").reset_index(drop=True)

    width = 1000
    height = 360

    top = 40
    bottom = 300
    left = 55
    right = 30

    chart_width = width - left - right

    score_cols = [
        ("分數", "#d62728"),
        ("技術分", "#1f77b4"),
        ("法人籌碼分", "#ff7f0e"),
        ("融資融券分", "#2ca02c"),
    ]

    existing_score_cols = [
        (col, color)
        for col, color in score_cols
        if col in stock_history.columns
    ]

    if not existing_score_cols:
        return "", stock_history

    values = []

    for col, _ in existing_score_cols:
        stock_history[col] = pd.to_numeric(stock_history[col], errors="coerce")
        values.extend(stock_history[col].dropna().astype(float).tolist())

    if not values:
        return "", stock_history

    min_score = min(values)
    max_score = max(values)

    score_padding = max((max_score - min_score) * 0.15, 3)
    min_score -= score_padding
    max_score += score_padding

    count = len(stock_history)
    step_x = chart_width / max(count - 1, 1)

    svg_parts = []

    svg_parts.append(f"""
    <div style="width:100%; overflow-x:auto; border:1px solid #ddd; border-radius:8px; padding:8px;">
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    <rect x="0" y="0" width="{width}" height="{height}" fill="white"/>
    <text x="{left}" y="24" font-size="18" font-weight="bold">{stock_id} Score History</text>
    """)

    for i in range(5):
        y = top + i * (bottom - top) / 4
        score_value = max_score - i * (max_score - min_score) / 4

        svg_parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e5e5" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="12" y="{y + 4:.2f}" font-size="12" fill="#555">{score_value:.1f}</text>'
        )

    for col, color in existing_score_cols:
        points = []

        for i, row in stock_history.iterrows():
            if pd.notna(row.get(col)):
                x = left + i * step_x
                y = normalize(float(row[col]), min_score, max_score, top, bottom)
                points.append((x, y))

        if len(points) >= 2:
            path_data = " ".join(
                [
                    f"{'M' if idx == 0 else 'L'} {x:.2f} {y:.2f}"
                    for idx, (x, y) in enumerate(points)
                ]
            )

            svg_parts.append(
                f'<path d="{path_data}" fill="none" stroke="{color}" stroke-width="2"/>'
            )

        for x, y in points:
            svg_parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"/>'
            )

    # 圖例
    legend_x = left
    legend_y = height - 18
    offset = 0

    for col, color in existing_score_cols:
        svg_parts.append(
            f'<rect x="{legend_x + offset}" y="{legend_y - 10}" width="12" height="12" fill="{color}"/>'
        )
        svg_parts.append(
            f'<text x="{legend_x + offset + 18}" y="{legend_y}" font-size="12">{col}</text>'
        )
        offset += 100

    if "資料日期" in stock_history.columns:
        date_labels = stock_history["資料日期"].dt.strftime("%m-%d").tolist()
        label_step = max(len(stock_history) // 8, 1)

        for i in range(0, len(stock_history), label_step):
            x = left + i * step_x
            label = date_labels[i]

            svg_parts.append(
                f'<text x="{x - 12:.2f}" y="{height - 42}" font-size="11" fill="#555" transform="rotate(45 {x:.2f},{height - 42})">{label}</text>'
            )

    svg_parts.append("</svg></div>")

    return "\n".join(svg_parts), stock_history


# =========================
# 頁面標題
# =========================

st.title("台股篩選系統")


# ===== 全市場法人買賣超排行榜 =====
from services.market_chip_ranking import fetch_market_institution_ranking

@st.cache_data(ttl=3600)
def load_market_chip_ranking():
    return fetch_market_institution_ranking(days=14)


def format_chip_ranking_table(df):
    if df is None or df.empty:
        return "<p>目前沒有排行榜資料。</p>"

    show_cols = [
        "市場",
        "資料日期",
        "股票代號",
        "股票名稱",
        "三大法人買賣超張數",
        "外資買賣超張數",
        "投信買賣超張數",
        "自營商買賣超張數",
    ]

    work = df[show_cols].copy()

    number_cols = [
        "三大法人買賣超張數",
        "外資買賣超張數",
        "投信買賣超張數",
        "自營商買賣超張數",
    ]

    for col in number_cols:
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
        work[col] = work[col].map(lambda x: f"{x:,.0f}")

    return work.to_html(index=False, escape=False)


st.markdown("""
<style>
.chip-ranking-box table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}
.chip-ranking-box th {
    background-color: #111827;
    color: #ffffff;
    padding: 9px 8px;
    text-align: left;
    border-bottom: 1px solid #374151;
    font-weight: 700;
}
.chip-ranking-box td {
    padding: 7px 8px;
    border-bottom: 1px solid #eee;
}
.chip-ranking-box tr:hover {
    background-color: #fafafa;
}
</style>
""", unsafe_allow_html=True)


with st.expander("全市場法人買賣超排行榜", expanded=False):
    try:
        ranking_df = load_market_chip_ranking()

        if ranking_df.empty:
            st.info("目前沒有抓到全市場法人買賣超資料。")
        else:
            latest_dates = ", ".join(sorted(ranking_df["資料日期"].dropna().unique()))
            st.caption(f"資料來源：TWSE / TPEx 官方資料｜資料日期：{latest_dates}")

            rank_col = st.selectbox(
                "排行依據",
                [
                    "三大法人買賣超張數",
                    "外資買賣超張數",
                    "投信買賣超張數",
                    "自營商買賣超張數",
                ],
                index=0,
                key="market_chip_rank_col",
            )

            top_n = st.slider(
                "顯示檔數",
                min_value=10,
                max_value=50,
                value=20,
                step=5,
                key="market_chip_top_n",
            )

            buy_df = ranking_df.sort_values(rank_col, ascending=False).head(top_n)
            sell_df = ranking_df.sort_values(rank_col, ascending=True).head(top_n)

            buy_tab, sell_tab = st.tabs(["買超排行", "賣超排行"])

            with buy_tab:
                st.markdown(
                    '<div class="chip-ranking-box">' + format_chip_ranking_table(buy_df) + "</div>",
                    unsafe_allow_html=True,
                )

            with sell_tab:
                st.markdown(
                    '<div class="chip-ranking-box">' + format_chip_ranking_table(sell_df) + "</div>",
                    unsafe_allow_html=True,
                )

    except Exception as e:
        st.warning(f"讀取全市場法人買賣超排行榜失敗：{e}")



# ===== 最近執行狀態 =====
RUN_LOG_PATH = "data/history/run_log.csv"

with st.expander("最近執行狀態", expanded=False):
    try:
        if os.path.exists(RUN_LOG_PATH):
            run_log_df = pd.read_csv(RUN_LOG_PATH)

            if not run_log_df.empty:
                latest_run = run_log_df.iloc[-1]

                expected_count = int(latest_run.get("expected_count", 0))
                success_count = int(latest_run.get("success_count", 0))
                chip_success_count = int(latest_run.get("chip_success_count", 0))
                chip_limit_count = int(latest_run.get("chip_limit_count", 0))
                margin_success_count = int(latest_run.get("margin_success_count", 0))
                margin_limit_count = int(latest_run.get("margin_limit_count", 0))
                did_output = str(latest_run.get("did_output", "")).lower() in ["true", "1", "yes"]

                st.markdown("### 最近執行狀態")

                run_col1, run_col2, run_col3, run_col4, run_col5 = st.columns(5)

                run_col1.metric("最近執行時間", latest_run.get("run_time", ""))
                run_col2.metric("成功分析", f"{success_count} / {expected_count}")
                run_col3.metric("法人資料", f"{chip_success_count} 成功 / {chip_limit_count} 超量")
                run_col4.metric("融資融券", f"{margin_success_count} 成功 / {margin_limit_count} 超量")
                run_col5.metric("報表輸出", "成功" if did_output else "未輸出")

                if chip_limit_count > 0 or margin_limit_count > 0:
                    st.warning("部分籌碼資料來源有異常或超量，請以資料狀態欄位輔助判斷。")
                else:
                    st.success("本次資料來源狀態正常。")
            else:
                st.info("目前尚未建立執行紀錄。請先執行 python main.py。")
        else:
            st.info("目前尚未建立執行紀錄。請先執行 python main.py。")
    except Exception as e:
        st.warning(f"讀取執行紀錄失敗：{e}")



st.caption("V3.4｜候選清單 × 自訂新增 × 題材搜尋 × 產業篩選 × 百元以下篩選 × K線圖 × 歷史分數追蹤")

st.warning(
    "目前這是盤後選股工具，不是即時報價或自動交易系統。"
    "新聞只做輔助標註，不參與分數。"
)


# =========================
# 側邊欄：操作
# =========================

st.sidebar.header("操作")

if st.sidebar.button("重新產生今日報表"):
    with st.spinner("正在執行 main.py，重新分析股票..."):
        result = run_main_script()

    if result.returncode == 0:
        st.success("報表已重新產生")
        st.cache_data.clear()
        st.rerun()
    else:
        st.error("執行 main.py 失敗")
        st.code(result.stderr)


# =========================
# 側邊欄：搜尋 / 新增候選股票
# =========================

current_stock_meta = get_current_stock_meta()

st.sidebar.markdown("### 🔎 搜尋 / 新增候選股票")

with st.sidebar.expander("搜尋或新增股票", expanded=False):
    search_watch_keyword = st.text_input(
        "搜尋現有候選股票",
        placeholder="例如：台積電、2330、無人機、儲能、LEO"
    )

    if search_watch_keyword:
        search_watch_keyword = search_watch_keyword.strip()
        matched_items = []

        for symbol, meta in current_stock_meta.items():
            text = " ".join([
                symbol,
                symbol.split(".")[0],
                meta.get("name", ""),
                meta.get("category", ""),
                meta.get("business", ""),
                meta.get("themes", ""),
            ])

            if search_watch_keyword.lower() in text.lower():
                matched_items.append(
                    f"{symbol}｜{meta.get('name', '')}｜{meta.get('category', '')}"
                )

        if matched_items:
            st.write("搜尋結果：")
            for item in matched_items[:15]:
                st.write(item)

            if len(matched_items) > 15:
                st.caption(f"還有 {len(matched_items) - 15} 筆結果未顯示")
        else:
            st.info("目前候選清單找不到，可在下方用股票代號新增。")

    st.divider()

    st.write("新增自訂候選股票")

    new_stock_code = st.text_input(
        "股票代號",
        placeholder="例如：2330、1319、3491"
    )

    new_stock_name = st.text_input(
        "股票名稱",
        placeholder="例如：台積電"
    )

    st.caption("只要輸入股票代號與股票名稱即可。系統會自動判斷上市 / 上櫃、產業分類與 symbol。")

    if st.button("加入候選清單"):
        ok, message, added_symbol = add_custom_stock(
            stock_code=new_stock_code,
            market_choice="自動判斷",
            name=new_stock_name,
            category="",
            business="",
            themes="",
        )

        if ok:
            st.success(message)
            st.info("已寫入 data/custom_watchlist.csv。請按「重新產生今日報表」讓它進入分析結果。")
            st.cache_data.clear()
        else:
            st.error(message)


# =========================
# 讀取最新 Excel
# =========================

latest_report = find_latest_report()

if latest_report is None:
    st.error("找不到報表。請先在 Terminal 執行：python main.py")
    st.stop()

df = load_report(latest_report)
df = prepare_report_df(df)

st.success(f"目前讀取報表：{latest_report}")


# =========================
# 總覽數字
# =========================

total_count = len(df)
buy_count = safe_count(df, "訊號", "買進觀察")
watch_count = safe_count(df, "訊號", "留意追蹤")
risk_count = safe_count(df, "訊號", "高風險排除")
trap_count = safe_count(df, "訊號", "有陷阱")

under_100_count = 0

if "是否低於100" in df.columns:
    under_100_count = len(df[df["是否低於100"] == "是"])

col1, col2, col3, col4, col5, col6 = st.columns(6)

col1.metric("分析股票數", total_count)
col2.metric("買進觀察", buy_count)
col3.metric("留意追蹤", watch_count)
col4.metric("高風險排除", risk_count)
col5.metric("有陷阱", trap_count)
col6.metric("百元以下", under_100_count)

st.divider()


# =========================
# 側邊欄：篩選
# =========================

st.sidebar.header("篩選條件")

filtered_df = df.copy()


# 產業分類篩選
if "產業分類" in filtered_df.columns:
    category_options = ["全部"] + sorted(
        filtered_df["產業分類"].dropna().astype(str).unique().tolist()
    )

    selected_category = st.sidebar.selectbox(
        "產業分類",
        category_options
    )

    if selected_category != "全部":
        filtered_df = filtered_df[
            filtered_df["產業分類"].astype(str) == selected_category
        ]


# 題材快速篩選
if "題材標籤" in filtered_df.columns:
    theme_set = set()

    for item in filtered_df["題材標籤"].dropna().astype(str).tolist():
        normalized_item = (
            item.replace(",", "、")
                .replace("，", "、")
                .replace("/", "、")
        )

        for theme in normalized_item.split("、"):
            theme = theme.strip()

            if theme:
                theme_set.add(theme)

    theme_options = ["全部"] + sorted(theme_set)

    selected_theme = st.sidebar.selectbox(
        "題材快速篩選",
        theme_options
    )

    if selected_theme != "全部":
        filtered_df = filtered_df[
            filtered_df["題材標籤"].astype(str).str.contains(
                selected_theme,
                case=False,
                na=False,
                regex=False
            )
        ]


# 百元以下篩選
if "是否低於100" in filtered_df.columns:
    only_under_100 = st.sidebar.checkbox("只看百元以下股票")

    if only_under_100:
        filtered_df = filtered_df[filtered_df["是否低於100"] == "是"]


# 訊號篩選
if "訊號" in filtered_df.columns:
    signal_options = ["全部"] + sorted(
        filtered_df["訊號"].dropna().astype(str).unique().tolist()
    )

    selected_signal = st.sidebar.selectbox("訊號篩選", signal_options)

    if selected_signal != "全部":
        filtered_df = filtered_df[filtered_df["訊號"] == selected_signal]


# 關鍵字搜尋
keyword = st.sidebar.text_input("搜尋股票代號 / 名稱 / 產業 / 題材 / 新聞")

if keyword:
    keyword = keyword.strip()

    search_cols = [
        "股票代號",
        "股票名稱",
        "產業分類",
        "公司業務",
        "題材標籤",
        "新聞題材",
        "新聞摘要",
    ]

    mask = pd.Series(False, index=filtered_df.index)

    for col in search_cols:
        if col in filtered_df.columns:
            mask = mask | filtered_df[col].astype(str).str.contains(
                keyword,
                case=False,
                na=False,
                regex=False
            )

    filtered_df = filtered_df[mask]


# 分數區間
if "分數" in filtered_df.columns and not filtered_df.empty:
    score_series = pd.to_numeric(df["分數"], errors="coerce").dropna()

    if not score_series.empty:
        min_score = int(score_series.min())
        max_score = int(score_series.max())

        score_range = st.sidebar.slider(
            "分數區間",
            min_value=min_score,
            max_value=max_score,
            value=(min_score, max_score)
        )

        filtered_df = filtered_df[
            (filtered_df["分數"] >= score_range[0]) &
            (filtered_df["分數"] <= score_range[1])
        ]


# 法人籌碼篩選
if "法人籌碼分" in filtered_df.columns:
    if st.sidebar.checkbox("只看法人籌碼分 > 0"):
        filtered_df = filtered_df[filtered_df["法人籌碼分"] > 0]


# 融資融券篩選
if "融資融券分" in filtered_df.columns:
    if st.sidebar.checkbox("只看融資融券分 > 0"):
        filtered_df = filtered_df[filtered_df["融資融券分"] > 0]


# 新聞傾向篩選
if "新聞傾向" in filtered_df.columns:
    news_options = ["全部"] + sorted(
        filtered_df["新聞傾向"].dropna().astype(str).unique().tolist()
    )

    selected_news = st.sidebar.selectbox("新聞傾向", news_options)

    if selected_news != "全部":
        filtered_df = filtered_df[filtered_df["新聞傾向"] == selected_news]


# 排序
if "分數" in filtered_df.columns:
    filtered_df = filtered_df.sort_values("分數", ascending=False)


# =========================
# 主表格
# =========================


# =========================
# 全市場異動股資料
# =========================

market_movement_path = "data/output/market_movement_top.csv"

def _market_try_symbols(row):
    symbol = str(row.get("symbol", "")).strip()
    code = str(row.get("股票代號", "")).strip()
    market = str(row.get("市場", "")).strip()

    candidates = []

    if symbol.endswith(".TW") or symbol.endswith(".TWO"):
        candidates.append(symbol)

    digits = "".join(ch for ch in code if ch.isdigit())

    if len(digits) == 4:
        if "上櫃" in market:
            candidates.extend([f"{digits}.TWO", f"{digits}.TW"])
        elif "上市" in market:
            candidates.extend([f"{digits}.TW", f"{digits}.TWO"])
        else:
            candidates.extend([f"{digits}.TW", f"{digits}.TWO"])

    result = []
    for item in candidates:
        if item and item not in result:
            result.append(item)

    return result


def _fetch_market_stock_history(row):
    try:
        import yfinance as yf

        for yf_symbol in _market_try_symbols(row):
            hist = yf.download(
                yf_symbol,
                period="6mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )

            if hist is None or hist.empty:
                continue

            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)

            if "Close" not in hist.columns:
                continue

            hist = hist.dropna(subset=["Close"]).copy()

            if len(hist) < 60:
                continue

            hist["MA10"] = hist["Close"].rolling(10).mean()
            hist["MA20"] = hist["Close"].rolling(20).mean()
            hist["MA60"] = hist["Close"].rolling(60).mean()

            return yf_symbol, hist.tail(80).copy()

        return None, pd.DataFrame()

    except Exception as e:
        st.warning(f"個股歷史資料抓取失敗：{e}")
        return None, pd.DataFrame()


def _make_svg_line_chart(hist):
    if hist is None or hist.empty or "Close" not in hist.columns:
        return ""

    data = hist[["Close", "MA10", "MA20", "MA60"]].dropna().tail(60).copy()

    if data.empty:
        data = hist[["Close"]].dropna().tail(60).copy()

    if data.empty:
        return ""

    width = 900
    height = 260
    padding_x = 42
    padding_y = 28

    values = []
    for col in ["Close", "MA10", "MA20", "MA60"]:
        if col in data.columns:
            values.extend([float(v) for v in data[col].dropna().tolist()])

    if not values:
        return ""

    min_v = min(values)
    max_v = max(values)

    if max_v == min_v:
        max_v += 1
        min_v -= 1

    def x_pos(i, n):
        if n <= 1:
            return padding_x
        return padding_x + i * (width - padding_x * 2) / (n - 1)

    def y_pos(v):
        return height - padding_y - (float(v) - min_v) * (height - padding_y * 2) / (max_v - min_v)

    colors = {
        "Close": "#111827",
        "MA10": "#2563eb",
        "MA20": "#16a34a",
        "MA60": "#dc2626",
    }

    names = {
        "Close": "收盤價",
        "MA10": "MA10",
        "MA20": "MA20",
        "MA60": "MA60",
    }

    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#ffffff" rx="12"/>',
        f'<line x1="{padding_x}" y1="{height-padding_y}" x2="{width-padding_x}" y2="{height-padding_y}" stroke="#e5e7eb"/>',
        f'<line x1="{padding_x}" y1="{padding_y}" x2="{padding_x}" y2="{height-padding_y}" stroke="#e5e7eb"/>',
    ]

    for idx, level in enumerate([min_v, (min_v + max_v) / 2, max_v]):
        y = y_pos(level)
        svg_parts.append(f'<line x1="{padding_x}" y1="{y:.1f}" x2="{width-padding_x}" y2="{y:.1f}" stroke="#f3f4f6"/>')
        svg_parts.append(f'<text x="6" y="{y+4:.1f}" font-size="11" fill="#6b7280">{level:.1f}</text>')

    for col in ["Close", "MA10", "MA20", "MA60"]:
        if col not in data.columns:
            continue

        series = data[col].dropna()

        if series.empty:
            continue

        points = []
        n = len(data)

        for i, (_, row) in enumerate(data.iterrows()):
            v = row.get(col, None)
            if pd.isna(v):
                continue
            points.append(f"{x_pos(i, n):.1f},{y_pos(v):.1f}")

        if len(points) >= 2:
            svg_parts.append(
                f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[col]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
            )

    legend_x = padding_x
    legend_y = 18

    for i, col in enumerate(["Close", "MA10", "MA20", "MA60"]):
        if col in data.columns:
            x = legend_x + i * 95
            svg_parts.append(f'<rect x="{x}" y="{legend_y-9}" width="10" height="10" fill="{colors[col]}" rx="2"/>')
            svg_parts.append(f'<text x="{x+15}" y="{legend_y}" font-size="12" fill="#374151">{names[col]}</text>')

    svg_parts.append("</svg>")

    return "\n".join(svg_parts)


def _calc_snipe_points(hist):
    if hist is None or hist.empty:
        return None

    latest = hist.dropna(subset=["Close"]).iloc[-1]

    close_price = float(latest["Close"])
    ma10 = float(latest["MA10"])
    ma20 = float(latest["MA20"])
    ma60 = float(latest["MA60"])

    entry = round(ma10 * 1.005, 2)
    sl = round(ma20 * 0.98, 2)
    risk = entry - sl

    if risk <= 0:
        tp = 0
        rr = 0
    else:
        tp = round(entry + risk * 2, 2)
        rr = round((tp - entry) / risk, 2)

    return {
        "close": close_price,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "risk": risk,
    }


def _render_market_fibo_section(hist):
    if hist is None or hist.empty or "Close" not in hist.columns:
        st.info("歷史資料不足，無法計算 Fibonacci 回測區。")
        return

    data = hist.dropna(subset=["Close"]).tail(60).copy()

    if data.empty or len(data) < 20:
        st.info("近 60 日資料不足，無法計算 Fibonacci 回測區。")
        return

    swing_high = float(data["Close"].max())
    swing_low = float(data["Close"].min())
    latest_close = float(data["Close"].iloc[-1])

    high_date = data["Close"].idxmax()
    low_date = data["Close"].idxmin()

    price_range = swing_high - swing_low

    if price_range <= 0:
        st.info("近 60 日波段高低點差距不足，無法計算 Fibonacci。")
        return

    fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786]

    fib_levels = []
    for ratio in fib_ratios:
        level = swing_high - price_range * ratio
        fib_levels.append({
            "Fibo": f"{ratio:.3f}",
            "價格": round(level, 2),
        })

    latest = data.iloc[-1]

    ma_values = {}
    for ma_name in ["MA10", "MA20", "MA60"]:
        if ma_name in data.columns and pd.notna(latest.get(ma_name, None)):
            ma_values[ma_name] = float(latest[ma_name])

    st.markdown("#### 🧮 Fibonacci 回測參考區（近 60 日波段）")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("近60日高點", f"{swing_high:.2f}")
    c2.metric("近60日低點", f"{swing_low:.2f}")
    c3.metric("目前收盤", f"{latest_close:.2f}")
    c4.metric("波段幅度", f"{price_range:.2f}")

    st.caption(f"波段計算：以近 60 日收盤價高點 {swing_high:.2f} 與低點 {swing_low:.2f} 推估回測位置。")

    # 產出 Fibo 表格
    fib_table = pd.DataFrame(fib_levels)

    if ma_values:
        overlap_notes = []
        tolerance_pct = 0.012

        for fib in fib_levels:
            fib_name = fib["Fibo"]
            fib_price = float(fib["價格"])

            for ma_name, ma_price in ma_values.items():
                distance_pct = abs(fib_price - ma_price) / fib_price if fib_price else 999

                if distance_pct <= tolerance_pct:
                    overlap_notes.append({
                        "Fibo": fib_name,
                        "Fibo價格": round(fib_price, 2),
                        "均線": ma_name,
                        "均線價格": round(ma_price, 2),
                        "差距%": round(distance_pct * 100, 2),
                    })

        st.markdown("##### 📐 Fibo 分割價位")

        if "show_html_table" in globals():
            show_html_table(fib_table)
        else:
            st.markdown(fib_table.to_html(index=False, escape=False), unsafe_allow_html=True)

        st.markdown("##### 🎯 均線與 Fibo 重疊偵測")

        if overlap_notes:
            for note in overlap_notes:
                st.success(
                    f'{note["Fibo"]}（{note["Fibo價格"]}）與 {note["均線"]}（{note["均線價格"]}）重疊 '
                    f'→ 強支撐區，差距約 {note["差距%"]}%'
                )
        else:
            st.info("目前沒有明顯的均線與 Fibo 重疊支撐區。")

    else:
        st.markdown("##### 📐 Fibo 分割價位")

        if "show_html_table" in globals():
            show_html_table(fib_table)
        else:
            st.markdown(fib_table.to_html(index=False, escape=False), unsafe_allow_html=True)

        st.info("目前缺少 MA10 / MA20 / MA60，無法偵測均線與 Fibo 重疊。")

    # 價格位置判讀
    fib_382 = swing_high - price_range * 0.382
    fib_500 = swing_high - price_range * 0.5
    fib_618 = swing_high - price_range * 0.618

    st.markdown("##### 🧠 目前位置解讀")

    if latest_close >= fib_382:
        st.success(f"目前股價在 0.382 回測位 {fib_382:.2f} 之上，代表短線仍偏強。")
    elif latest_close >= fib_500:
        st.warning(f"目前股價位於 0.382～0.5 區間，屬於健康回測區，但要觀察量縮與止跌。")
    elif latest_close >= fib_618:
        st.warning(f"目前股價回測到 0.5～0.618 區間，這是關鍵支撐區，跌破後結構會轉弱。")
    else:
        st.error(f"目前股價已跌破 0.618 回測位 {fib_618:.2f}，波段結構偏弱，不適合追價。")



if os.path.exists(market_movement_path):
    market_df = pd.read_csv(market_movement_path)

    if market_df.empty:
        st.info("目前沒有全市場異動股資料。")
    else:
        number_cols = [
            "收盤價",
            "漲跌幅%",
            "成交量張數",
            "近20日均量張數",
            "量增倍率",
            "成交值百萬",
            "異動分",
        ]

        for col in number_cols:
            if col in market_df.columns:
                market_df[col] = pd.to_numeric(market_df[col], errors="coerce")

        latest_date = ""
        if "資料日期" in market_df.columns and not market_df["資料日期"].empty:
            latest_date = str(market_df["資料日期"].iloc[0])

        top_names = []
        for _, r in market_df.head(3).iterrows():
            top_names.append(f'{r.get("股票代號", "")} {r.get("股票名稱", "")}')

        top_text = "、".join(top_names) if top_names else "尚無資料"

        with st.expander(
            f"🚨 全市場異動股｜{latest_date}｜共 {len(market_df)} 檔｜Top：{top_text}",
            expanded=False,
        ):
            st.caption("這裡不是單純股票名單。點選個股後，可以看到異動原因、狙擊點位與近 60 日歷史走勢。")

            rank_options = {
                "異動分排行": "異動分",
                "漲幅排行": "漲跌幅%",
                "成交量排行": "成交量張數",
                "成交值排行": "成交值百萬",
                "量增倍率排行": "量增倍率",
            }

            rank_name = st.selectbox(
                "選擇排行方式",
                list(rank_options.keys()),
                key="market_movement_rank_select",
            )

            sort_col = rank_options[rank_name]

            show_count = st.slider(
                "顯示檔數",
                min_value=10,
                max_value=50,
                value=20,
                step=5,
                key="market_movement_show_count",
            )

            show_df = market_df.copy()

            if sort_col in show_df.columns:
                show_df = show_df.sort_values(sort_col, ascending=False)

            show_df = show_df.head(show_count).copy()
            show_df.insert(0, "排名", range(1, len(show_df) + 1))

            table_cols = [
                "排名",
                "市場",
                "股票代號",
                "股票名稱",
                "收盤價",
                "漲跌幅%",
                "量增倍率",
                "成交量張數",
                "成交值百萬",
                "異動分",
            ]

            existing_cols = [col for col in table_cols if col in show_df.columns]
            table_df = show_df[existing_cols].copy()

            format_map = {
                "收盤價": "{:.2f}",
                "漲跌幅%": "{:.2f}%",
                "量增倍率": "{:.2f}x",
                "成交量張數": "{:.0f}",
                "成交值百萬": "{:.1f}",
                "異動分": "{:.1f}",
            }

            for col, fmt in format_map.items():
                if col in table_df.columns:
                    table_df[col] = table_df[col].apply(lambda x: "" if pd.isna(x) else fmt.format(x))

            st.markdown("#### 📋 異動排行清單")

            if "show_html_table" in globals():
                show_html_table(table_df)
            else:
                st.markdown(table_df.to_html(index=False, escape=False), unsafe_allow_html=True)

            st.markdown("#### 🔍 個股詳細資料")

            option_labels = []
            option_map = {}

            for _, r in show_df.iterrows():
                code = str(r.get("股票代號", ""))
                name = str(r.get("股票名稱", ""))
                pct = r.get("漲跌幅%", None)
                ratio = r.get("量增倍率", None)
                value_m = r.get("成交值百萬", None)

                pct_text = "" if pd.isna(pct) else f"{pct:.2f}%"
                ratio_text = "" if pd.isna(ratio) else f"{ratio:.2f}x"
                value_text = "" if pd.isna(value_m) else f"{value_m:.1f}百萬"

                label = f"{code} {name}｜漲跌幅 {pct_text}｜量增 {ratio_text}｜成交值 {value_text}"
                option_labels.append(label)
                option_map[label] = r

            if option_labels:
                selected_label = st.selectbox(
                    "選一檔股票看完整資料",
                    option_labels,
                    key="market_movement_stock_detail_select",
                )

                selected = option_map[selected_label]

                st.markdown(f'### {selected.get("股票代號", "")} {selected.get("股票名稱", "")}')

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("收盤價", f'{selected.get("收盤價", 0):.2f}')
                c2.metric("漲跌幅", f'{selected.get("漲跌幅%", 0):.2f}%')
                c3.metric("量增倍率", f'{selected.get("量增倍率", 0):.2f}x')
                c4.metric("異動分", f'{selected.get("異動分", 0):.1f}')

                c5, c6, c7, c8 = st.columns(4)
                c5.metric("成交量張數", f'{selected.get("成交量張數", 0):.0f}')
                c6.metric("近20日均量", f'{selected.get("近20日均量張數", 0):.0f}')
                c7.metric("成交值百萬", f'{selected.get("成交值百萬", 0):.1f}')
                c8.metric("市場", str(selected.get("市場", "")))

                st.markdown("#### 🧠 為什麼它出現在名單？")

                reasons = []

                pct = selected.get("漲跌幅%", 0)
                ratio = selected.get("量增倍率", 0)
                volume = selected.get("成交量張數", 0)
                value_m = selected.get("成交值百萬", 0)

                if pd.notna(pct) and pct >= 7:
                    reasons.append("漲幅明顯，短線資金正在推動。")
                elif pd.notna(pct) and pct >= 3:
                    reasons.append("股價漲幅有表現，開始出現攻擊性。")

                if pd.notna(ratio) and ratio >= 2:
                    reasons.append("量增倍率超過 2 倍，成交量明顯放大。")
                elif pd.notna(ratio) and ratio >= 1.5:
                    reasons.append("量能高於近期均量，市場關注度上升。")

                if pd.notna(volume) and volume >= 10000:
                    reasons.append("成交量超過 1 萬張，流動性足夠。")

                if pd.notna(value_m) and value_m >= 1000:
                    reasons.append("成交值超過 10 億元，屬於較明顯資金流入標的。")
                elif pd.notna(value_m) and value_m >= 300:
                    reasons.append("成交值達 3 億元以上，有一定資金參與。")

                if not reasons:
                    reasons.append("主要因綜合異動分進入名單，需要再搭配 K 線與籌碼確認。")

                for reason in reasons:
                    st.markdown(f"- {reason}")

                st.markdown("#### 🎯 狙擊點位分析")

                used_symbol, hist = _fetch_market_stock_history(selected)

                if hist is not None and not hist.empty:
                    snipe = _calc_snipe_points(hist)

                    if snipe:
                        st.caption(f"歷史資料來源：yfinance，代號 {used_symbol}")

                        s1, s2, s3, s4 = st.columns(4)
                        s1.metric("進場觀察價", f'{snipe["entry"]:.2f}')
                        s2.metric("停損觀察價 SL", f'{snipe["sl"]:.2f}')
                        s3.metric("停利觀察價 TP", f'{snipe["tp"]:.2f}')
                        s4.metric("風報比 RR", f'1 : {snipe["rr"]}')

                        if snipe["risk"] <= 0:
                            st.warning("目前 MA10 與 MA20 結構不適合用這組進出場點位。")
                        elif snipe["rr"] < 2:
                            st.warning("風報比低於 1 : 2，追價風險較高，等待回測會更安全。")
                        else:
                            st.success("風報比達 1 : 2 以上，具備基本觀察條件。")

                        if snipe["close"] > snipe["ma60"]:
                            st.success("位置：股價站上 MA60，結構相對健康。")
                        else:
                            st.warning("位置：股價仍在 MA60 下方，結構偏弱。")

                        if snipe["ma10"] > snipe["ma20"] > snipe["ma60"]:
                            st.success("趨勢：MA10 > MA20 > MA60，均線多頭排列。")
                        elif snipe["ma10"] < snipe["ma20"]:
                            st.warning("趨勢：MA10 低於 MA20，短線結構尚未轉強。")
                        else:
                            st.warning("趨勢：均線仍在整理，方向尚未完全明確。")

                    _render_market_fibo_section(hist)

                    st.markdown("#### 📈 近 60 日歷史走勢")

                    svg = _make_svg_line_chart(hist)

                    if svg:
                        st.markdown(svg, unsafe_allow_html=True)
                    else:
                        st.info("歷史走勢資料不足，無法繪製走勢。")

                else:
                    st.info("抓不到這檔股票的歷史資料，暫時無法顯示狙擊點位與歷史走勢。")

                st.caption("提醒：全市場異動股只是幫你找出今天市場有動靜的股票，不等於可以直接進場。實際操作仍要搭配籌碼、型態、支撐壓力與大盤風險。")

else:
    with st.expander("🚨 全市場異動股｜尚未產生", expanded=False):
        st.info("尚未找到 data/output/market_movement_top.csv。請先執行：python run_dashboard_data.py --mode market")

st.subheader("📋 每日篩選結果")

display_cols = [
    "股票代號",
    "股票名稱",
    "產業分類",
    "分數",
    "訊號",
    "技術分",
    "法人籌碼分",
    "融資融券分",
]

existing_cols = [col for col in display_cols if col in filtered_df.columns]

if filtered_df.empty:
    st.info("目前篩選條件下沒有股票。")
    st.stop()

show_html_table(filtered_df[existing_cols])

st.caption(f"目前篩選後剩下 {len(filtered_df)} 檔股票")

st.divider()


# =========================
# 個股詳細分析
# =========================

st.subheader("🔍 個股詳細分析")

stock_labels = (
    filtered_df["股票代號"].astype(str) + " " + filtered_df["股票名稱"].astype(str)
).tolist()

selected_stock_label = st.selectbox("選擇股票", stock_labels)
selected_stock_id = selected_stock_label.split(" ")[0]

stock_row = filtered_df[
    filtered_df["股票代號"].astype(str) == selected_stock_id
].iloc[0]


st.markdown(f"## {stock_row.get('股票代號')} {stock_row.get('股票名稱')}")

col_a, col_b, col_c, col_d, col_e = st.columns(5)

col_a.metric("總分", stock_row.get("分數"))
col_b.metric("技術分", stock_row.get("技術分"))
col_c.metric("法人籌碼分", stock_row.get("法人籌碼分"))
col_d.metric("融資融券分", stock_row.get("融資融券分"))
col_e.metric("百元以下", stock_row.get("是否低於100", ""))


# =========================
# K 線圖
# =========================

st.markdown("### 📈 個股 K 線圖")

stock_code = str(stock_row.get("股票代號")).strip()

with st.spinner("正在載入 K 線資料..."):
    price_chart_df, chart_symbol = load_price_chart_data(stock_code)

if price_chart_df.empty:
    st.warning("目前抓不到這檔股票的 K 線資料")
else:
    st.caption(
        f"K 線資料來源：Yahoo Finance / yfinance｜代號：{chart_symbol}｜日 K，非即時"
    )

    kline_svg = draw_svg_kline_chart(price_chart_df)
    st.markdown(kline_svg, unsafe_allow_html=True)


# =========================
# 歷史分數追蹤
# =========================

st.markdown("### 📊 歷史分數追蹤")

history_df = load_score_history()

if history_df.empty:
    st.info("目前尚未建立歷史分數紀錄。請先執行 python main.py。")
else:
    history_svg, stock_history = draw_svg_score_history(
        history_df=history_df,
        stock_id=selected_stock_id
    )

    if stock_history.empty:
        st.info("這檔股票目前還沒有歷史分數紀錄。")
    else:
        st.markdown(history_svg, unsafe_allow_html=True)

        latest_history = stock_history.tail(5).copy()

        st.write("最近 5 次分析紀錄：")

        show_cols = [
            "資料日期",
            "分數",
            "訊號",
            "技術分",
            "法人籌碼分",
            "融資融券分",
            "收盤價",
            "近5日漲幅%",
        ]

        existing_history_cols = [
            col for col in show_cols
            if col in latest_history.columns
        ]

        latest_history_display = latest_history[existing_history_cols].copy()

        if "資料日期" in latest_history_display.columns:
            latest_history_display["資料日期"] = latest_history_display["資料日期"].dt.strftime("%Y-%m-%d")

        show_html_table(latest_history_display)


# =========================
# 公司資訊
# =========================

st.markdown("### 🏭 公司在做什麼")

st.write(f"**產業分類：** {stock_row.get('產業分類', '')}")
st.write(f"**公司業務：** {stock_row.get('公司業務', '')}")
st.write(f"**題材標籤：** {stock_row.get('題材標籤', '')}")


# =========================
# 技術與籌碼判讀
# =========================

st.markdown("### 技術與籌碼判讀")

system_text = stock_row.get("系統解讀", "")

if pd.isna(system_text) or system_text == "":
    st.caption("目前沒有明確系統解讀")
else:
    st.markdown(f'''<div style="font-size:13px;color:#444;background:#f9f9f9;border-left:3px solid #ccc;padding:10px 14px;border-radius:4px;line-height:1.8;">{system_text}</div>''', unsafe_allow_html=True)

risk_text = stock_row.get("風險標註", "")

if pd.isna(risk_text) or risk_text == "":
    st.success("目前沒有明顯系統風險標註")
else:
    st.warning(risk_text)


# =========================
# 新聞標註
# =========================


# =========================
# 狙擊點位分析
# =========================

st.markdown("### 🎯 狙擊點位分析")

# 這個區塊只做「觀察用點位估算」，不等於買賣建議。
_snipe_row = None

for _candidate_name in ["stock_row", "selected_row", "selected_stock_row", "row"]:
    _candidate = locals().get(_candidate_name)
    if hasattr(_candidate, "get"):
        _snipe_row = _candidate
        break


def _pick_value(row, names):
    if row is None:
        return None

    for name in names:
        try:
            value = row.get(name, None)
        except Exception:
            value = None

        if value is not None and pd.notna(value):
            return value

    return None


def _normalize_tw_symbol(raw_symbol, market=None):
    if raw_symbol is None:
        return []

    symbol = str(raw_symbol).strip()

    if symbol == "":
        return []

    if symbol.endswith(".TW") or symbol.endswith(".TWO"):
        return [symbol]

    digits = "".join(ch for ch in symbol if ch.isdigit())

    if len(digits) != 4:
        return []

    market_text = str(market or "")

    if "上櫃" in market_text:
        return [f"{digits}.TWO", f"{digits}.TW"]

    if "上市" in market_text:
        return [f"{digits}.TW", f"{digits}.TWO"]

    # 如果不知道上市/上櫃，就兩個都試
    return [f"{digits}.TW", f"{digits}.TWO"]


def _fetch_snipe_ma(symbol):
    try:
        import yfinance as yf

        hist = yf.download(
            symbol,
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        if hist is None or hist.empty:
            return None

        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)

        if "Close" not in hist.columns:
            return None

        hist = hist.dropna(subset=["Close"]).copy()

        if len(hist) < 60:
            return None

        close_price = float(hist["Close"].iloc[-1])
        ma10 = float(hist["Close"].rolling(10).mean().iloc[-1])
        ma20 = float(hist["Close"].rolling(20).mean().iloc[-1])
        ma60 = float(hist["Close"].rolling(60).mean().iloc[-1])

        return {
            "close_price": close_price,
            "ma10": ma10,
            "ma20": ma20,
            "ma60": ma60,
        }

    except Exception as e:
        st.warning(f"即時均線資料抓取失敗：{e}")
        return None


if _snipe_row is None:
    st.info("尚未找到個股資料列，無法計算狙擊點位。")
else:
    close_price = _pick_value(_snipe_row, ["收盤價", "Close", "close", "最新收盤價"])
    ma10 = _pick_value(_snipe_row, ["MA10", "10日均線", "ma10"])
    ma20 = _pick_value(_snipe_row, ["MA20", "20日均線", "ma20"])
    ma60 = _pick_value(_snipe_row, ["MA60", "60日均線", "ma60"])

    symbol_raw = _pick_value(_snipe_row, ["symbol", "股票代號", "代號", "股票代碼"])
    market = _pick_value(_snipe_row, ["市場", "上市櫃", "交易市場"])

    # 如果 Excel 沒有 MA10 / MA20 / MA60，就用 yfinance 即時計算。
    if not (pd.notna(close_price) and pd.notna(ma10) and pd.notna(ma20) and pd.notna(ma60)):
        yf_symbols = _normalize_tw_symbol(symbol_raw, market)
        fetched = None
        used_symbol = None

        for yf_symbol in yf_symbols:
            fetched = _fetch_snipe_ma(yf_symbol)
            if fetched:
                used_symbol = yf_symbol
                break

        if fetched:
            close_price = fetched["close_price"]
            ma10 = fetched["ma10"]
            ma20 = fetched["ma20"]
            ma60 = fetched["ma60"]
            st.caption(f"均線資料來源：yfinance 即時計算，代號 {used_symbol}")
        else:
            st.caption(f"已嘗試 yfinance 代號：{yf_symbols}，但沒有成功取得 60 日以上資料。")

    if pd.notna(close_price) and pd.notna(ma10) and pd.notna(ma20) and pd.notna(ma60):
        close_price = float(close_price)
        ma10 = float(ma10)
        ma20 = float(ma20)
        ma60 = float(ma60)

        entry = round(ma10 * 1.005, 2)
        sl = round(ma20 * 0.98, 2)
        risk = entry - sl
        tp = round(entry + risk * 2, 2) if risk > 0 else 0
        rr = round((tp - entry) / risk, 2) if risk > 0 else 0

        snipe_col1, snipe_col2, snipe_col3, snipe_col4 = st.columns(4)

        snipe_col1.metric("進場觀察價", f"{entry}")
        snipe_col2.metric(
            "停損觀察價 SL",
            f"{sl}",
            delta=f"{round((sl - entry) / entry * 100, 1)}%" if entry else None,
        )
        snipe_col3.metric(
            "停利觀察價 TP",
            f"{tp}",
            delta=f"+{round((tp - entry) / entry * 100, 1)}%" if entry and tp else None,
        )
        snipe_col4.metric("風報比 RR", f"1 : {rr}")

        st.divider()

        # Fibonacci 回測進場區
        if not price_chart_df.empty:
            fib_df = price_chart_df.tail(60).copy()
            fib_high = float(fib_df["High"].max())
            fib_low = float(fib_df["Low"].min())
            fib_range = fib_high - fib_low

            f382 = round(fib_high - fib_range * 0.382, 2)
            f500 = round(fib_high - fib_range * 0.500, 2)
            f618 = round(fib_high - fib_range * 0.618, 2)

            st.markdown("**Fibonacci 回測參考區（近 60 日波段）**")
            fib_col1, fib_col2, fib_col3, fib_col4 = st.columns(4)
            fib_col1.metric("波段高點", f"{fib_high}")
            fib_col2.metric("0.382 淺回測", f"{f382}")
            fib_col3.metric("0.500 中回測", f"{f500}")
            fib_col4.metric("0.618 深回測", f"{f618}")

            # 判斷目前收盤價落在哪個 Fibo 區間
            if close_price >= f382:
                fib_note = f"目前收盤價 {close_price} 尚未回測到 0.382（{f382}），尚在強勢區，等回測再考慮進場。"
                st.info(fib_note)
            elif f382 > close_price >= f500:
                fib_note = f"目前收盤價 {close_price} 落在 0.382–0.500 區間，屬強勢回測，可搭配均線支撐考慮進場。"
                st.success(fib_note)
            elif f500 > close_price >= f618:
                fib_note = f"目前收盤價 {close_price} 落在 0.500–0.618 區間，屬中性回測，需確認止跌訊號再進場。"
                st.warning(fib_note)
            else:
                fib_note = f"目前收盤價 {close_price} 已跌破 0.618（{f618}），波段結構偏弱，不建議進場。"
                st.error(fib_note)

            # Fibo 與均線重疊提示
            overlap_notes = []
            for fib_val, fib_name in [(f382, "0.382"), (f500, "0.500"), (f618, "0.618")]:
                for ma_val, ma_name in [(ma10, "MA10"), (ma20, "MA20"), (ma60, "MA60")]:
                    if abs(fib_val - ma_val) / ma_val < 0.015:
                        overlap_notes.append(f"{fib_name}（{fib_val}）與 {ma_name}（{round(ma_val,2)}）重疊 → 強支撐區")
            if overlap_notes:
                st.success("均線與 Fibo 重疊偵測：" + "　".join(overlap_notes))

            st.caption(f"Fibo 計算基準：近 60 日高點 {fib_high} / 低點 {fib_low}")

        st.divider()

        if close_price > ma60:
            st.success("位置：站上季線，結構相對健康。")
        else:
            st.warning("位置：季線以下，結構偏弱，需降低追價衝動。")

        if ma10 > ma20 > ma60:
            st.success("趨勢：均線多頭排列，方向偏上。")
        elif ma10 < ma20:
            st.warning("趨勢：短均線弱於中期均線，方向偏保守。")
        else:
            st.warning("趨勢：均線糾結，方向尚未明確。")

        if risk <= 0:
            st.error("目前進場觀察價低於或接近停損價，風險結構不合理，暫不適合用這組點位。")
        elif rr < 2:
            st.warning(f"風報比目前為 1 : {rr}，低於 1 : 2，等待更好的價格會比較安全。")
        else:
            st.success(f"風報比目前為 1 : {rr}，符合 1 : 2 以上的基本觀察條件。")

        st.caption("提醒：此區塊僅為技術面觀察用，不構成買賣建議。實際操作仍需搭配籌碼、量能、支撐壓力與大盤風險。")

    else:
        st.info("仍然缺少收盤價或 MA10 / MA20 / MA60，無法計算狙擊點位。")


st.markdown("### 近期新聞標註")

_news_direction = stock_row.get('新聞傾向', '')
_news_theme = stock_row.get('新聞題材', '')
_news_direction = '—' if (str(_news_direction).strip() in ['', 'nan', 'NaN']) else _news_direction
_news_theme = '—' if (str(_news_theme).strip() in ['', 'nan', 'NaN']) else _news_theme
st.markdown(f"**新聞傾向：** {_news_direction}")
st.markdown(f"**新聞題材：** {_news_theme}")

news_summary = stock_row.get("新聞摘要", "")

if pd.isna(news_summary) or news_summary == "":
    st.info("近期沒有抓到明確新聞摘要")
else:
    st.write(news_summary)

news_flags = stock_row.get("新聞風險提示", "")

if not pd.isna(news_flags) and news_flags != "":
    st.warning(news_flags)

news_links = stock_row.get("新聞連結", "")

if not pd.isna(news_links) and news_links != "":
    st.markdown("**新聞連結：**")
    for link in str(news_links).split("；"):
        if link.strip():
            st.write(link.strip())


# =========================
# 原始條件資料
# =========================

st.markdown("### 原始條件資料")

tab1, tab2, tab3 = st.tabs(["技術面", "法人籌碼", "融資融券"])

with tab1:
    tech_cols = [
        "收盤價",
        "是否低於100",
        "MA5",
        "MA10",
        "MA60",
        "近5日漲幅%",
        "剛站上MA5",
        "剛站上MA10",
        "MA5上彎",
        "放量",
        "健康放量紅K",
        "接近60日支撐",
        "站上20日成本線",
    ]

    tech_data = {
        col: stock_row.get(col)
        for col in tech_cols
        if col in stock_row.index
    }

    show_key_value_table(tech_data)


with tab2:
    chip_cols = [
        "法人近3日連買",
        "法人近3日連賣",
        "外資近3日連買",
        "投信近3日連買",
        "最新法人買賣超",
    ]

    chip_data = {
        col: stock_row.get(col)
        for col in chip_cols
        if col in stock_row.index
    }

    show_key_value_table(chip_data)


with tab3:
    margin_cols = [
        "融資連2減",
        "融券連2增",
        "最新融資增減",
        "最新融券增減",
    ]

    margin_data = {
        col: stock_row.get(col)
        for col in margin_cols
        if col in stock_row.index
    }

    show_key_value_table(margin_data)
