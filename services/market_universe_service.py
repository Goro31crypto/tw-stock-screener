import re
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import requests


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


def _twse_date(date_obj: datetime) -> str:
    return date_obj.strftime("%Y%m%d")


def _tpex_roc_date(date_obj: datetime) -> str:
    return f"{date_obj.year - 1911}/{date_obj.month:02d}/{date_obj.day:02d}"


def _recent_dates(calendar_days: int = 45):
    today = datetime.today()
    for i in range(calendar_days):
        yield today - timedelta(days=i)


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _clean_number(value) -> float:
    if value is None:
        return 0.0

    text = _clean_text(value)
    text = text.replace(",", "")
    text = text.replace("--", "0")
    text = text.replace("X", "0")
    text = text.replace("除權息", "0")
    text = text.strip()

    if text == "":
        return 0.0

    text = re.sub(r"[^\d\-.]", "", text)

    if text in ["", "-", "."]:
        return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


def _is_common_stock(stock_id: str) -> bool:
    """
    先只保留 4 碼普通股，排除 ETF、ETN、權證、債券 ETF 等。
    """
    stock_id = str(stock_id).strip()
    return bool(re.fullmatch(r"\d{4}", stock_id))


def _request_json(url: str, params: dict | None = None):
    response = requests.get(url, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def _find_col(df: pd.DataFrame, keywords: list[str]):
    for col in df.columns:
        col_text = str(col)
        if all(k in col_text for k in keywords):
            return col
    return None


def _signed_change(row: pd.Series, sign_col, change_col) -> float:
    change = abs(_clean_number(row.get(change_col, 0)))

    if sign_col is None:
        raw = _clean_text(row.get(change_col, ""))
        if raw.startswith("-"):
            return -change
        return change

    sign_text = _clean_text(row.get(sign_col, ""))

    if "-" in sign_text or "跌" in sign_text:
        return -change

    return change


def _twse_payload_to_df(payload: dict) -> pd.DataFrame:
    """
    TWSE MI_INDEX 常見資料位置是 fields9 / data9。
    不同版本可能略有差異，所以保留 fallback。
    """
    fields = payload.get("fields9")
    rows = payload.get("data9")

    if fields and rows:
        return pd.DataFrame(rows, columns=fields)

    fields = payload.get("fields")
    rows = payload.get("data")

    if fields and rows:
        return pd.DataFrame(rows, columns=fields)

    return pd.DataFrame()


def fetch_twse_daily_quotes(date_obj: datetime) -> pd.DataFrame:
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"

    params = {
        "date": _twse_date(date_obj),
        "type": "ALLBUT0999",
        "response": "json",
    }

    try:
        payload = _request_json(url, params)
        raw = _twse_payload_to_df(payload)

        if raw.empty:
            return pd.DataFrame()

        code_col = _find_col(raw, ["證券", "代號"]) or _find_col(raw, ["代號"])
        name_col = _find_col(raw, ["證券", "名稱"]) or _find_col(raw, ["名稱"])
        volume_col = _find_col(raw, ["成交", "股數"])
        amount_col = _find_col(raw, ["成交", "金額"])
        close_col = _find_col(raw, ["收盤"])
        sign_col = _find_col(raw, ["漲跌", "+/-"])
        change_col = _find_col(raw, ["漲跌", "價差"])

        rows = []

        for _, row in raw.iterrows():
            stock_id = _clean_text(row.get(code_col, ""))

            if not _is_common_stock(stock_id):
                continue

            close_price = _clean_number(row.get(close_col, 0))
            volume_shares = _clean_number(row.get(volume_col, 0))
            amount = _clean_number(row.get(amount_col, 0))
            change = _signed_change(row, sign_col, change_col)

            prev_close = close_price - change
            change_pct = (change / prev_close * 100) if prev_close else 0

            rows.append({
                "市場": "上市",
                "資料日期": date_obj.strftime("%Y-%m-%d"),
                "股票代號": stock_id,
                "股票名稱": _clean_text(row.get(name_col, "")),
                "收盤價": close_price,
                "漲跌": change,
                "漲跌幅%": change_pct,
                "成交股數": volume_shares,
                "成交量張數": volume_shares / 1000,
                "成交金額": amount,
                "成交值百萬": amount / 1_000_000,
                "symbol": f"{stock_id}.TW",
            })

        return pd.DataFrame(rows)

    except Exception as e:
        print(f"TWSE 每日行情抓取失敗 {date_obj.strftime('%Y-%m-%d')}: {e}")
        return pd.DataFrame()


def _tpex_payload_to_df(payload: dict) -> pd.DataFrame:
    if "tables" in payload and payload["tables"]:
        table = payload["tables"][0]
        fields = table.get("fields", [])
        rows = table.get("data", [])
        if fields:
            return pd.DataFrame(rows, columns=fields)

    if "data" in payload:
        return pd.DataFrame(payload["data"])

    if "aaData" in payload:
        fields = [
            "代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "均價",
            "成交股數", "成交金額", "成交筆數", "最後買價", "最後買量",
            "最後賣價", "最後賣量", "發行股數", "次日漲停價", "次日跌停價",
        ]
        rows = payload.get("aaData", [])
        if rows:
            max_len = max(len(r) for r in rows)
            if max_len > len(fields):
                fields = fields + [f"欄位{i}" for i in range(len(fields), max_len)]
            return pd.DataFrame(rows, columns=fields[:max_len])

    return pd.DataFrame()


def fetch_tpex_daily_quotes(date_obj: datetime) -> pd.DataFrame:
    """
    TPEx 先試新版 dailyQuotes，不行再試舊版 stk_quote_result。
    """
    urls = [
        (
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes",
            {
                "date": _tpex_roc_date(date_obj),
                "response": "json",
            },
        ),
        (
            "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php",
            {
                "l": "zh-tw",
                "o": "json",
                "d": _tpex_roc_date(date_obj),
                "s": "0,asc,0",
            },
        ),
    ]

    raw = pd.DataFrame()

    for url, params in urls:
        try:
            payload = _request_json(url, params)
            raw = _tpex_payload_to_df(payload)
            if not raw.empty:
                break
        except Exception:
            continue

    if raw.empty:
        return pd.DataFrame()

    code_col = _find_col(raw, ["代號"])
    name_col = _find_col(raw, ["名稱"])
    close_col = _find_col(raw, ["收盤"])
    change_col = _find_col(raw, ["漲跌"])
    volume_col = _find_col(raw, ["成交", "股數"])
    amount_col = _find_col(raw, ["成交", "金額"])

    rows = []

    for _, row in raw.iterrows():
        stock_id = _clean_text(row.get(code_col, ""))

        if not _is_common_stock(stock_id):
            continue

        close_price = _clean_number(row.get(close_col, 0))
        change = _clean_number(row.get(change_col, 0))
        volume_shares = _clean_number(row.get(volume_col, 0))
        amount = _clean_number(row.get(amount_col, 0))

        prev_close = close_price - change
        change_pct = (change / prev_close * 100) if prev_close else 0

        rows.append({
            "市場": "上櫃",
            "資料日期": date_obj.strftime("%Y-%m-%d"),
            "股票代號": stock_id,
            "股票名稱": _clean_text(row.get(name_col, "")),
            "收盤價": close_price,
            "漲跌": change,
            "漲跌幅%": change_pct,
            "成交股數": volume_shares,
            "成交量張數": volume_shares / 1000,
            "成交金額": amount,
            "成交值百萬": amount / 1_000_000,
            "symbol": f"{stock_id}.TWO",
        })

    return pd.DataFrame(rows)


def fetch_full_market_history(calendar_days: int = 45) -> pd.DataFrame:
    frames = []

    for date_obj in _recent_dates(calendar_days):
        twse_df = fetch_twse_daily_quotes(date_obj)
        tpex_df = fetch_tpex_daily_quotes(date_obj)

        day_df = pd.concat([twse_df, tpex_df], ignore_index=True)

        if not day_df.empty:
            frames.append(day_df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["資料日期", "股票代號"], keep="first")
    return df


def build_liquidity_candidates(
    calendar_days: int = 45,
    min_price: float = 10,
    min_volume_lots: float = 1000,
    min_value_million: float = 30,
    volume_ratio_threshold: float = 1.8,
    min_ratio_volume_lots: float = 500,
    top_n: int = 200,
) -> pd.DataFrame:
    """
    全市場異動粗篩：

    保留條件：
    1. 收盤價 >= min_price
    2. 且符合以下任一：
       - 成交量 >= min_volume_lots 張
       - 成交值 >= min_value_million 百萬
       - 量增倍率 >= volume_ratio_threshold 且成交量 >= min_ratio_volume_lots 張
    """

    history = fetch_full_market_history(calendar_days=calendar_days)

    if history.empty:
        return pd.DataFrame()

    history["資料日期"] = pd.to_datetime(history["資料日期"])
    history = history.sort_values(["股票代號", "資料日期"])

    latest_date = history["資料日期"].max()
    latest = history[history["資料日期"] == latest_date].copy()
    previous = history[history["資料日期"] < latest_date].copy()

    avg20 = (
        previous
        .groupby("股票代號", group_keys=False)
        .tail(20)
        .groupby("股票代號")["成交量張數"]
        .mean()
        .reset_index()
        .rename(columns={"成交量張數": "近20日均量張數"})
    )

    latest = latest.merge(avg20, on="股票代號", how="left")
    latest["近20日均量張數"] = latest["近20日均量張數"].fillna(0)

    latest["量增倍率"] = latest.apply(
        lambda row: row["成交量張數"] / row["近20日均量張數"]
        if row["近20日均量張數"] > 0 else 0,
        axis=1,
    )

    latest["異動分"] = (
        latest["量增倍率"].clip(0, 5) * 20
        + latest["成交值百萬"].clip(0, 500) / 10
        + latest["漲跌幅%"].clip(-10, 10) * 2
    )

    condition = (
        (latest["收盤價"] >= min_price)
        & (
            (latest["成交量張數"] >= min_volume_lots)
            | (latest["成交值百萬"] >= min_value_million)
            | (
                (latest["量增倍率"] >= volume_ratio_threshold)
                & (latest["成交量張數"] >= min_ratio_volume_lots)
            )
        )
    )

    result = latest[condition].copy()
    result["資料日期"] = result["資料日期"].dt.strftime("%Y-%m-%d")

    result = result.sort_values("異動分", ascending=False).head(top_n)

    display_cols = [
        "市場",
        "資料日期",
        "股票代號",
        "股票名稱",
        "symbol",
        "收盤價",
        "漲跌幅%",
        "成交量張數",
        "近20日均量張數",
        "量增倍率",
        "成交值百萬",
        "異動分",
    ]

    existing_cols = [col for col in display_cols if col in result.columns]
    return result[existing_cols].reset_index(drop=True)


def export_liquidity_candidates(output_path: str = "data/liquidity_candidates.csv") -> pd.DataFrame:
    Path("data").mkdir(exist_ok=True)

    df = build_liquidity_candidates()

    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return df
