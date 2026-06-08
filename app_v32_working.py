import glob
import os
import subprocess
import sys

import pandas as pd
import streamlit as st

from services.price_service import fetch_price_data
from indicators.technical import add_technical_indicators


st.set_page_config(
    page_title="台股篩選系統",
    page_icon="📊",
    layout="wide"
)


# =========================
# 基礎工具
# =========================

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
        df["資料日期"] = pd.to_datetime(df["資料日期"])

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


# =========================
# K 線資料
# =========================

@st.cache_data
def load_price_chart_data(stock_id: str):
    candidates = [
        f"{stock_id}.TW",
        f"{stock_id}.TWO",
    ]

    for symbol in candidates:
        df = fetch_price_data(symbol, period="6mo")

        if not df.empty:
            df = add_technical_indicators(df)
            df = df.reset_index()

            if "Date" not in df.columns:
                df = df.rename(columns={df.columns[0]: "Date"})

            df["Date"] = pd.to_datetime(df["Date"])

            return df, symbol

    return pd.DataFrame(), None


# =========================
# SVG 圖表工具：不用 matplotlib / altair / pyarrow
# =========================

def normalize(value, min_value, max_value, top, bottom):
    if max_value == min_value:
        return (top + bottom) / 2

    return bottom - ((value - min_value) / (max_value - min_value)) * (bottom - top)


def draw_svg_kline_chart(price_df: pd.DataFrame):
    """
    用純 SVG 畫 K 線圖。
    不使用 matplotlib、altair、pyarrow。
    """

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

    # 格線與價格刻度
    for i in range(5):
        y = price_top + i * (price_bottom - price_top) / 4
        price = high_max - i * (high_max - low_min) / 4

        svg_parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e5e5" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="8" y="{y + 4:.2f}" font-size="12" fill="#555">{price:.2f}</text>'
        )

    # 成交量格線
    svg_parts.append(
        f'<line x1="{left}" y1="{vol_bottom}" x2="{width - right}" y2="{vol_bottom}" stroke="#e5e5e5" stroke-width="1"/>'
    )
    svg_parts.append(
        f'<text x="8" y="{vol_top + 12}" font-size="12" fill="#555">Volume</text>'
    )

    # 均線 path
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

        # 影線
        svg_parts.append(
            f'<line x1="{x:.2f}" y1="{y_high:.2f}" x2="{x:.2f}" y2="{y_low:.2f}" stroke="{color}" stroke-width="1"/>'
        )

        # 實體
        rect_y = min(y_open, y_close)
        rect_height = abs(y_close - y_open)

        if rect_height < 1:
            rect_height = 1

        svg_parts.append(
            f'<rect x="{x - candle_width / 2:.2f}" y="{rect_y:.2f}" width="{candle_width:.2f}" height="{rect_height:.2f}" fill="{color}" opacity="0.85"/>'
        )

        # 成交量
        vol_height = (volume / vol_max) * (vol_bottom - vol_top)
        svg_parts.append(
            f'<rect x="{x - candle_width / 2:.2f}" y="{vol_bottom - vol_height:.2f}" width="{candle_width:.2f}" height="{vol_height:.2f}" fill="{color}" opacity="0.45"/>'
        )

        # 均線
        for ma_name in ma_paths.keys():
            if ma_name in df.columns and pd.notna(row.get(ma_name)):
                ma_value = float(row[ma_name])
                ma_y = normalize(ma_value, low_min, high_max, price_top, price_bottom)
                ma_paths[ma_name].append((x, ma_y))

    # 畫均線
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

    # 日期刻度
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
    stock_history = history_df[
        history_df["股票代號"].astype(str) == str(stock_id)
    ].copy()

    if stock_history.empty:
        return "", pd.DataFrame()

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

    # 格線
    for i in range(5):
        y = top + i * (bottom - top) / 4
        score_value = max_score - i * (max_score - min_score) / 4

        svg_parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#e5e5e5" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="12" y="{y + 4:.2f}" font-size="12" fill="#555">{score_value:.1f}</text>'
        )

    # 分數線
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

    # 日期
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

st.title("📊 台股篩選系統")
st.caption("V3.2 Prototype｜技術面 × 法人籌碼 × 融資融券 × 公司業務 × 新聞標註 × K線圖 × 歷史分數追蹤")

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
# 讀取最新 Excel
# =========================

latest_report = find_latest_report()

if latest_report is None:
    st.error("找不到報表。請先在 Terminal 執行：python main.py")
    st.stop()

df = load_report(latest_report)

st.success(f"目前讀取報表：{latest_report}")


# =========================
# 總覽數字
# =========================

total_count = len(df)
buy_count = safe_count(df, "訊號", "買進觀察")
watch_count = safe_count(df, "訊號", "留意追蹤")
risk_count = safe_count(df, "訊號", "高風險排除")
trap_count = safe_count(df, "訊號", "有陷阱")

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("分析股票數", total_count)
col2.metric("買進觀察", buy_count)
col3.metric("留意追蹤", watch_count)
col4.metric("高風險排除", risk_count)
col5.metric("有陷阱", trap_count)

st.divider()


# =========================
# 側邊欄：篩選
# =========================

st.sidebar.header("篩選條件")

filtered_df = df.copy()

if "訊號" in filtered_df.columns:
    signal_options = ["全部"] + sorted(filtered_df["訊號"].dropna().unique().tolist())
    selected_signal = st.sidebar.selectbox("訊號篩選", signal_options)

    if selected_signal != "全部":
        filtered_df = filtered_df[filtered_df["訊號"] == selected_signal]


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
                na=False
            )

    filtered_df = filtered_df[mask]


if "分數" in filtered_df.columns and not filtered_df.empty:
    min_score = int(df["分數"].min())
    max_score = int(df["分數"].max())

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


if "法人籌碼分" in filtered_df.columns:
    if st.sidebar.checkbox("只看法人籌碼分 > 0"):
        filtered_df = filtered_df[filtered_df["法人籌碼分"] > 0]


if "融資融券分" in filtered_df.columns:
    if st.sidebar.checkbox("只看融資融券分 > 0"):
        filtered_df = filtered_df[filtered_df["融資融券分"] > 0]


if "新聞傾向" in filtered_df.columns:
    news_options = ["全部"] + sorted(filtered_df["新聞傾向"].dropna().unique().tolist())
    selected_news = st.sidebar.selectbox("新聞傾向", news_options)

    if selected_news != "全部":
        filtered_df = filtered_df[filtered_df["新聞傾向"] == selected_news]


if "分數" in filtered_df.columns:
    filtered_df = filtered_df.sort_values("分數", ascending=False)


# =========================
# 主表格
# =========================

st.subheader("📋 每日篩選結果")

display_cols = [
    "股票代號",
    "股票名稱",
    "產業分類",
    "題材標籤",
    "資料日期",
    "分數",
    "訊號",
    "技術分",
    "法人籌碼分",
    "融資融券分",
    "收盤價",
    "近5日漲幅%",
    "新聞傾向",
    "新聞題材",
    "新聞摘要",
    "新聞風險提示",
    "系統解讀",
    "風險標註",
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

col_a, col_b, col_c, col_d = st.columns(4)

col_a.metric("總分", stock_row.get("分數"))
col_b.metric("技術分", stock_row.get("技術分"))
col_c.metric("法人籌碼分", stock_row.get("法人籌碼分"))
col_d.metric("融資融券分", stock_row.get("融資融券分"))


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

st.markdown("### 📈 技術與籌碼判讀")

system_text = stock_row.get("系統解讀", "")

if pd.isna(system_text) or system_text == "":
    st.info("目前沒有明確系統解讀")
else:
    st.write(system_text)

risk_text = stock_row.get("風險標註", "")

if pd.isna(risk_text) or risk_text == "":
    st.success("目前沒有明顯系統風險標註")
else:
    st.warning(risk_text)


# =========================
# 新聞標註
# =========================

st.markdown("### 📰 近期新聞標註")

st.write(f"**新聞傾向：** {stock_row.get('新聞傾向', '')}")
st.write(f"**新聞題材：** {stock_row.get('新聞題材', '')}")

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

st.markdown("### 📊 原始條件資料")

tab1, tab2, tab3 = st.tabs(["技術面", "法人籌碼", "融資融券"])

with tab1:
    tech_cols = [
        "收盤價",
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
