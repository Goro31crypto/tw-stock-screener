from datetime import datetime, timedelta

import pandas as pd
import requests

from config import FINMIND_TOKEN


FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def normalize_stock_id(symbol: str) -> str:
    """
    把 2330.TW / 6488.TWO 轉成 2330 / 6488。
    FinMind 使用純股票代號。
    """
    return symbol.replace(".TW", "").replace(".TWO", "")


def fetch_finmind_dataset(dataset: str, symbol: str, days: int = 30) -> pd.DataFrame:
    """
    從 FinMind 抓資料。
    dataset 範例：
    - TaiwanStockInstitutionalInvestorsBuySell
    - TaiwanStockMarginPurchaseShortSale
    """

    stock_id = normalize_stock_id(symbol)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }

    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"

    response = requests.get(
        FINMIND_URL,
        params=params,
        headers=headers,
        timeout=15
    )

    response.raise_for_status()
    data = response.json()

    if "data" not in data or not data["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["data"])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

    return df


def fetch_institution_data(symbol: str, days: int = 14) -> pd.DataFrame:
    """
    抓三大法人買賣超。
    """
    return fetch_finmind_dataset(
        dataset="TaiwanStockInstitutionalInvestorsBuySell",
        symbol=symbol,
        days=days
    )


def fetch_margin_data(symbol: str, days: int = 14) -> pd.DataFrame:
    """
    抓融資融券。
    """
    return fetch_finmind_dataset(
        dataset="TaiwanStockMarginPurchaseShortSale",
        symbol=symbol,
        days=days
    )


def analyze_institution_signal(
    inst_df: pd.DataFrame,
    red_k: bool,
    price_up: bool
) -> dict:
    """
    分析法人籌碼：
    - 三大法人連3買
    - 外資連3買
    - 投信連3買
    - 三大法人連3賣
    """

    score = 0
    reasons = []
    flags = []

    if inst_df.empty:
        return {
            "score": 0,
            "reasons": "",
            "flags": "無法人資料",
            "details": {}
        }

    df = inst_df.copy()

    required_cols = {"date", "buy", "sell", "name"}
    if not required_cols.issubset(set(df.columns)):
        return {
            "score": 0,
            "reasons": "",
            "flags": f"法人資料欄位不符合預期：{list(df.columns)}",
            "details": {}
        }

    df["net_buy"] = df["buy"] - df["sell"]

    # 每日三大法人合計
    daily_total = (
        df.groupby("date")["net_buy"]
        .sum()
        .sort_index()
    )

    recent_3_total = daily_total.tail(3)
    inst_3d_buy = len(recent_3_total) == 3 and (recent_3_total > 0).all()
    inst_3d_sell = len(recent_3_total) == 3 and (recent_3_total < 0).all()

    # 各法人分開看
    pivot = df.pivot_table(
        index="date",
        columns="name",
        values="net_buy",
        aggfunc="sum"
    ).sort_index()

    def has_3d_buy(keyword: str) -> bool:
        matched_cols = [
            col for col in pivot.columns
            if keyword.lower() in str(col).lower()
        ]

        if not matched_cols:
            return False

        s = pivot[matched_cols].sum(axis=1).tail(3)
        return len(s) == 3 and (s > 0).all()

    foreign_3d_buy = has_3d_buy("Foreign")
    trust_3d_buy = has_3d_buy("Investment")

    # 加分邏輯
    if inst_3d_buy:
        score += 10
        reasons.append("三大法人連續3日買超")

        if red_k:
            score += 3
            reasons.append("法人連買且當日紅K，價格有同步")
        else:
            flags.append("法人連買但收黑｜人工確認是否吸籌或承接無力")

        if price_up:
            score += 3
            reasons.append("法人連買且收盤高於昨收")

    if foreign_3d_buy:
        score += 5
        reasons.append("外資連續3日買超")

    if trust_3d_buy:
        score += 8
        reasons.append("投信連續3日買超")

    # 扣分 / 風險
    if inst_3d_sell:
        score -= 10
        flags.append("三大法人連續3日賣超｜籌碼偏弱")
        reasons.append("三大法人連續3日賣超，籌碼面扣分")

    latest_total_net = daily_total.iloc[-1] if len(daily_total) > 0 else 0

    return {
        "score": score,
        "reasons": "；".join(reasons),
        "flags": "；".join(flags),
        "details": {
            "法人近3日連買": inst_3d_buy,
            "法人近3日連賣": inst_3d_sell,
            "外資近3日連買": foreign_3d_buy,
            "投信近3日連買": trust_3d_buy,
            "最新法人買賣超": int(latest_total_net),
        }
    }


def analyze_margin_signal(
    margin_df: pd.DataFrame,
    price_up: bool
) -> dict:
    """
    分析融資融券：
    - 融資連2減 + 股價收漲 → 偏多
    - 融券連2增 + 股價收漲 → 軋空燃料
    """

    score = 0
    reasons = []
    flags = []

    if margin_df.empty:
        return {
            "score": 0,
            "reasons": "",
            "flags": "無融資融券資料",
            "details": {}
        }

    df = margin_df.copy()

    required_cols = {
        "MarginPurchaseTodayBalance",
        "ShortSaleTodayBalance"
    }

    if not required_cols.issubset(set(df.columns)):
        return {
            "score": 0,
            "reasons": "",
            "flags": f"融資融券欄位不符合預期：{list(df.columns)}",
            "details": {}
        }

    df = df.sort_values("date")

    margin_balance = df["MarginPurchaseTodayBalance"].astype(float)
    short_balance = df["ShortSaleTodayBalance"].astype(float)

    margin_down_2d = (
        len(margin_balance) >= 3 and
        (margin_balance.diff().tail(2) < 0).all()
    )

    short_up_2d = (
        len(short_balance) >= 3 and
        (short_balance.diff().tail(2) > 0).all()
    )

    latest_margin_change = margin_balance.diff().iloc[-1] if len(margin_balance) >= 2 else 0
    latest_short_change = short_balance.diff().iloc[-1] if len(short_balance) >= 2 else 0

    if margin_down_2d and price_up:
        score += 6
        reasons.append("融資連續2日減少且股價收漲，籌碼較乾淨")
    elif margin_down_2d and not price_up:
        score -= 3
        flags.append("融資下降但股價未轉強｜可能是停損或斷頭")
        reasons.append("融資下降但價格未同步轉強，保守扣分")

    if short_up_2d and price_up:
        score += 4
        reasons.append("融券連續2日增加且股價收漲，具軋空燃料")
    elif short_up_2d and not price_up:
        flags.append("融券增加但股價未轉強｜空方可能暫時正確")

    return {
        "score": score,
        "reasons": "；".join(reasons),
        "flags": "；".join(flags),
        "details": {
            "融資連2減": margin_down_2d,
            "融券連2增": short_up_2d,
            "最新融資增減": int(latest_margin_change),
            "最新融券增減": int(latest_short_change),
        }
    }
