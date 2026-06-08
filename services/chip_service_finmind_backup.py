import pandas as pd
import requests
from datetime import datetime, timedelta


FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"


def _symbol_to_stock_id(symbol: str) -> str:
    """
    2330.TW -> 2330
    4979.TWO -> 4979

    不能用 replace(".TW", "").replace(".TWO", "")
    因為 .TWO 會先被 .TW 吃掉，變成 4979O。
    """
    symbol = str(symbol).strip()

    if "." in symbol:
        return symbol.split(".")[0]

    return symbol


def fetch_finmind_dataset(dataset: str, symbol: str, days: int = 14) -> pd.DataFrame:
    """
    FinMind 防爆版：
    - API 超量 402：回傳空 DataFrame，不讓 main.py 整檔失敗
    - 網路錯誤：回傳空 DataFrame
    - 代號會自動從 4979.TWO 轉成 4979
    """

    stock_id = _symbol_to_stock_id(symbol)

    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=days)

    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": str(start_date),
        "end_date": str(end_date),
    }

    try:
        response = requests.get(
            FINMIND_API_URL,
            params=params,
            timeout=15
        )

        if response.status_code == 402:
            print(f"{symbol} FinMind 用量超過上限，略過 {dataset}")
            df = pd.DataFrame()
            df.attrs["data_status"] = "finmind_limit"
            return df

        if response.status_code != 200:
            print(f"{symbol} FinMind HTTP 錯誤 {response.status_code}，略過 {dataset}")
            df = pd.DataFrame()
            df.attrs["data_status"] = f"http_{response.status_code}"
            return df

        payload = response.json()

        if payload.get("status") != 200:
            print(f"{symbol} FinMind 回傳非成功狀態：{payload.get('msg', '')}")
            df = pd.DataFrame()
            df.attrs["data_status"] = "api_error"
            return df

        rows = payload.get("data", [])

        if not rows:
            df = pd.DataFrame()
            df.attrs["data_status"] = "empty"
            return df

        df = pd.DataFrame(rows)
        df.attrs["data_status"] = "success"
        return df

    except Exception as e:
        print(f"{symbol} 抓取 {dataset} 失敗：{e}")
        df = pd.DataFrame()
        df.attrs["data_status"] = "error"
        return df


def fetch_institution_data(symbol: str, days: int = 14) -> pd.DataFrame:
    return fetch_finmind_dataset(
        dataset="TaiwanStockInstitutionalInvestorsBuySell",
        symbol=symbol,
        days=days
    )


def fetch_margin_data(symbol: str, days: int = 14) -> pd.DataFrame:
    return fetch_finmind_dataset(
        dataset="TaiwanStockMarginPurchaseShortSale",
        symbol=symbol,
        days=days
    )


def analyze_institution_signal(inst_df: pd.DataFrame, red_k: bool = False, price_up: bool = False) -> dict:
    result = {
        "score": 0,
        "reasons": "",
        "flags": "",
        "details": {
            "法人近3日連買": False,
            "法人近3日連賣": False,
            "外資近3日連買": False,
            "投信近3日連買": False,
            "最新法人買賣超": 0,
            "法人資料狀態": "無資料",
        }
    }

    if inst_df is None or inst_df.empty:
        status = "無資料"

        if inst_df is not None:
            status = inst_df.attrs.get("data_status", "無資料")

        result["details"]["法人資料狀態"] = status
        result["flags"] = "法人資料未取得"
        return result

    df = inst_df.copy()
    result["details"]["法人資料狀態"] = df.attrs.get("data_status", "success")

    if "date" in df.columns:
        df = df.sort_values("date")

    if "buy" not in df.columns or "sell" not in df.columns:
        result["flags"] = "法人資料欄位不完整"
        return result

    df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
    df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)
    df["net_buy"] = df["buy"] - df["sell"]

    if "date" in df.columns:
        daily = df.groupby("date")["net_buy"].sum().reset_index()
        daily = daily.sort_values("date")
    else:
        daily = df[["net_buy"]].copy()

    if daily.empty:
        return result

    latest_net = float(daily["net_buy"].iloc[-1])
    result["details"]["最新法人買賣超"] = latest_net

    recent3 = daily.tail(3)

    if len(recent3) >= 3:
        result["details"]["法人近3日連買"] = bool((recent3["net_buy"] > 0).all())
        result["details"]["法人近3日連賣"] = bool((recent3["net_buy"] < 0).all())

    if "name" in df.columns and "date" in df.columns:
        name_series = df["name"].astype(str)

        foreign_df = df[
            name_series.str.contains("Foreign", case=False, na=False)
            | name_series.str.contains("外資", case=False, na=False)
        ]

        trust_df = df[
            name_series.str.contains("Investment", case=False, na=False)
            | name_series.str.contains("投信", case=False, na=False)
        ]

        if not foreign_df.empty:
            foreign_daily = foreign_df.groupby("date")["net_buy"].sum().reset_index().sort_values("date")
            foreign_recent3 = foreign_daily.tail(3)

            if len(foreign_recent3) >= 3:
                result["details"]["外資近3日連買"] = bool((foreign_recent3["net_buy"] > 0).all())

        if not trust_df.empty:
            trust_daily = trust_df.groupby("date")["net_buy"].sum().reset_index().sort_values("date")
            trust_recent3 = trust_daily.tail(3)

            if len(trust_recent3) >= 3:
                result["details"]["投信近3日連買"] = bool((trust_recent3["net_buy"] > 0).all())

    score = 0
    reasons = []
    flags = []

    if result["details"]["法人近3日連買"]:
        score += 3
        reasons.append("法人近3日連買")

    if result["details"]["外資近3日連買"]:
        score += 2
        reasons.append("外資近3日連買")

    if result["details"]["投信近3日連買"]:
        score += 3
        reasons.append("投信近3日連買")

    if latest_net > 0:
        score += 1
        reasons.append("最新法人買超")

    if result["details"]["法人近3日連賣"]:
        score -= 3
        flags.append("法人近3日連賣")

    if latest_net < 0:
        score -= 1
        flags.append("最新法人賣超")

    if price_up and latest_net < 0:
        score -= 2
        flags.append("股價上漲但法人賣超")

    result["score"] = score
    result["reasons"] = "｜".join(reasons)
    result["flags"] = "；".join(flags)

    return result


def analyze_margin_signal(margin_df: pd.DataFrame, price_up: bool = False) -> dict:
    result = {
        "score": 0,
        "reasons": "",
        "flags": "",
        "details": {
            "融資連2減": False,
            "融券連2增": False,
            "最新融資增減": 0,
            "最新融券增減": 0,
            "融資融券資料狀態": "無資料",
        }
    }

    if margin_df is None or margin_df.empty:
        status = "無資料"

        if margin_df is not None:
            status = margin_df.attrs.get("data_status", "無資料")

        result["details"]["融資融券資料狀態"] = status
        result["flags"] = "融資融券資料未取得"
        return result

    df = margin_df.copy()
    result["details"]["融資融券資料狀態"] = df.attrs.get("data_status", "success")

    if "date" in df.columns:
        df = df.sort_values("date")

    margin_col_candidates = [
        "MarginPurchaseTodayBalance",
        "MarginPurchaseBuy",
        "MarginPurchaseSell",
    ]

    short_col_candidates = [
        "ShortSaleTodayBalance",
        "ShortSaleBuy",
        "ShortSaleSell",
    ]

    margin_col = None
    short_col = None

    for col in margin_col_candidates:
        if col in df.columns:
            margin_col = col
            break

    for col in short_col_candidates:
        if col in df.columns:
            short_col = col
            break

    if margin_col is None and short_col is None:
        result["flags"] = "融資融券欄位不完整"
        return result

    if margin_col is not None:
        df[margin_col] = pd.to_numeric(df[margin_col], errors="coerce").fillna(0)
        df["margin_change"] = df[margin_col].diff()

        if pd.notna(df["margin_change"].iloc[-1]):
            result["details"]["最新融資增減"] = float(df["margin_change"].iloc[-1])

        recent2_margin = df["margin_change"].tail(2)

        if len(recent2_margin) >= 2:
            result["details"]["融資連2減"] = bool((recent2_margin < 0).all())

    if short_col is not None:
        df[short_col] = pd.to_numeric(df[short_col], errors="coerce").fillna(0)
        df["short_change"] = df[short_col].diff()

        if pd.notna(df["short_change"].iloc[-1]):
            result["details"]["最新融券增減"] = float(df["short_change"].iloc[-1])

        recent2_short = df["short_change"].tail(2)

        if len(recent2_short) >= 2:
            result["details"]["融券連2增"] = bool((recent2_short > 0).all())

    score = 0
    reasons = []
    flags = []

    if result["details"]["融資連2減"]:
        score += 2
        reasons.append("融資連2減")

    if result["details"]["融券連2增"]:
        score += 1
        reasons.append("融券連2增")

    if price_up and result["details"]["最新融資增減"] < 0:
        score += 2
        reasons.append("股價上漲且融資減少")

    if price_up and result["details"]["最新融券增減"] > 0:
        score += 2
        reasons.append("股價上漲且融券增加")

    if result["details"]["最新融資增減"] > 0 and not price_up:
        score -= 2
        flags.append("股價未漲但融資增加")

    result["score"] = score
    result["reasons"] = "｜".join(reasons)
    result["flags"] = "；".join(flags)

    return result
