import re
from functools import lru_cache
from datetime import datetime, timedelta

import pandas as pd
import requests


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


def _stock_id(symbol: str) -> str:
    return str(symbol).strip().split(".")[0]


def _is_tpex(symbol: str) -> bool:
    return str(symbol).upper().endswith(".TWO")


def _twse_date(date_obj: datetime) -> str:
    return date_obj.strftime("%Y%m%d")


def _tpex_roc_date(date_obj: datetime) -> str:
    return f"{date_obj.year - 1911}/{date_obj.month:02d}/{date_obj.day:02d}"


def _clean_number(value) -> float:
    if value is None:
        return 0

    text = str(value).strip()
    text = text.replace(",", "")
    text = text.replace("--", "0")
    text = text.replace("X", "0")
    text = text.replace("除權息", "0")

    if text == "":
        return 0

    text = re.sub(r"[^\d\-.]", "", text)

    if text in ["", "-", "."]:
        return 0

    try:
        return float(text)
    except ValueError:
        return 0


def _net_to_buy_sell(net_value: float):
    net_value = float(net_value)

    if net_value >= 0:
        return net_value, 0

    return 0, abs(net_value)


def _request_json(url: str, params: dict | None = None):
    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def _twse_df_from_payload(payload: dict) -> pd.DataFrame:
    fields = payload.get("fields", [])
    rows = payload.get("data", [])

    if not fields or not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows, columns=fields)


def _tpex_df_from_payload(payload: dict) -> pd.DataFrame:
    if "tables" in payload and payload["tables"]:
        table = payload["tables"][0]
        fields = table.get("fields", [])
        rows = table.get("data", [])

        if fields:
            return pd.DataFrame(rows, columns=fields)

    if "data" in payload:
        return pd.DataFrame(payload["data"])

    return pd.DataFrame()


@lru_cache(maxsize=128)
def _fetch_twse_institutional_by_date(date_str: str) -> pd.DataFrame:
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"

    params = {
        "date": date_str,
        "selectType": "ALLBUT0999",
        "response": "json",
    }

    try:
        payload = _request_json(url, params)
        return _twse_df_from_payload(payload)
    except Exception as e:
        print(f"TWSE 法人資料抓取失敗 {date_str}: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=128)
def _fetch_twse_margin_all() -> pd.DataFrame:
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"

    try:
        payload = _request_json(url)
        return pd.DataFrame(payload)
    except Exception as e:
        print(f"TWSE 融資融券 OpenAPI 抓取失敗: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=128)
def _fetch_tpex_institutional_by_date(roc_date_str: str) -> pd.DataFrame:
    url = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"

    params = {
        "date": roc_date_str,
        "type": "Daily",
        "response": "json",
    }

    try:
        payload = _request_json(url, params)
        return _tpex_df_from_payload(payload)
    except Exception as e:
        print(f"TPEx 法人資料抓取失敗 {roc_date_str}: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=128)
def _fetch_tpex_margin_by_date(roc_date_str: str) -> pd.DataFrame:
    url = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"

    params = {
        "l": "zh-tw",
        "o": "json",
        "se": "EW",
        "d": roc_date_str,
    }

    try:
        payload = _request_json(url, params)
        return _tpex_df_from_payload(payload)
    except Exception as e:
        print(f"TPEx 融資融券資料抓取失敗 {roc_date_str}: {e}")
        return pd.DataFrame()


def _recent_dates(days: int):
    today = datetime.today()

    for i in range(days):
        yield today - timedelta(days=i)


def _normalize_twse_institutional_row(row: pd.Series, trade_date: str) -> list[dict]:
    stock_id = str(row.get("證券代號", "")).strip()
    stock_name = str(row.get("證券名稱", "")).strip()

    foreign_net = _clean_number(row.get("外陸資買賣超股數(不含外資自營商)", 0))
    trust_net = _clean_number(row.get("投信買賣超股數", 0))
    dealer_net = _clean_number(row.get("自營商買賣超股數", 0))

    records = []

    for inst_name, net in [
        ("Foreign_Investor", foreign_net),
        ("Investment_Trust", trust_net),
        ("Dealer", dealer_net),
    ]:
        buy, sell = _net_to_buy_sell(net)

        records.append({
            "date": trade_date,
            "stock_id": stock_id,
            "stock_name": stock_name,
            "name": inst_name,
            "buy": buy,
            "sell": sell,
            "net_buy": net,
            "source": "TWSE",
        })

    return records


def _normalize_tpex_institutional_row(row: pd.Series, trade_date: str) -> list[dict]:
    values = list(row.values)

    if len(values) < 12:
        return []

    stock_id = str(values[0]).strip()
    stock_name = str(values[1]).strip()

    # TPEx dailyTrade 欄位名稱會重複，所以用位置取值：
    # 0 代號
    # 1 名稱
    # 4 外資買賣超
    # 10 投信買賣超
    # 13 自營商買賣超
    foreign_net = _clean_number(values[4]) if len(values) > 4 else 0
    trust_net = _clean_number(values[10]) if len(values) > 10 else 0
    dealer_net = _clean_number(values[19]) if len(values) > 19 else 0

    records = []

    for inst_name, net in [
        ("Foreign_Investor", foreign_net),
        ("Investment_Trust", trust_net),
        ("Dealer", dealer_net),
    ]:
        buy, sell = _net_to_buy_sell(net)

        records.append({
            "date": trade_date,
            "stock_id": stock_id,
            "stock_name": stock_name,
            "name": inst_name,
            "buy": buy,
            "sell": sell,
            "net_buy": net,
            "source": "TPEx",
        })

    return records


def fetch_institution_data(symbol: str, days: int = 14) -> pd.DataFrame:
    """
    官方批次版法人資料：
    - .TW  上市：TWSE T86
    - .TWO 上櫃：TPEx dailyTrade

    回傳格式維持 chip_service 原本分析函式可讀：
    date, name, buy, sell
    """

    target_id = _stock_id(symbol)
    records = []

    for date_obj in _recent_dates(days):
        trade_date = date_obj.strftime("%Y-%m-%d")

        if _is_tpex(symbol):
            df = _fetch_tpex_institutional_by_date(_tpex_roc_date(date_obj))

            if df.empty:
                continue

            code_col = df.columns[0]
            matched = df[df[code_col].astype(str).str.strip() == target_id]

            for _, row in matched.iterrows():
                records.extend(_normalize_tpex_institutional_row(row, trade_date))

        else:
            df = _fetch_twse_institutional_by_date(_twse_date(date_obj))

            if df.empty or "證券代號" not in df.columns:
                continue

            matched = df[df["證券代號"].astype(str).str.strip() == target_id]

            for _, row in matched.iterrows():
                records.extend(_normalize_twse_institutional_row(row, trade_date))

    result = pd.DataFrame(records)

    if not result.empty:
        result = result.sort_values(["date", "name"]).reset_index(drop=True)

    if result.empty:
        result.attrs["data_status"] = "empty"
    else:
        result.attrs["data_status"] = "success"

    return result


def _normalize_twse_margin_row(row: pd.Series) -> dict:
    stock_id = str(row.get("股票代號", row.get("證券代號", ""))).strip()
    stock_name = str(row.get("股票名稱", row.get("證券名稱", ""))).strip()

    margin_balance = _clean_number(
        row.get("融資今日餘額", row.get("融資餘額", row.get("融資(交易單位)今日餘額", 0)))
    )

    short_balance = _clean_number(
        row.get("融券今日餘額", row.get("融券餘額", row.get("融券(交易單位)今日餘額", 0)))
    )

    date_value = (
        row.get("出表日期")
        or row.get("資料日期")
        or datetime.today().strftime("%Y-%m-%d")
    )

    return {
        "date": str(date_value),
        "stock_id": stock_id,
        "stock_name": stock_name,
        "MarginPurchaseTodayBalance": margin_balance,
        "ShortSaleTodayBalance": short_balance,
        "source": "TWSE",
    }


def _normalize_tpex_margin_row(row: pd.Series, trade_date: str) -> dict:
    return {
        "date": trade_date,
        "stock_id": str(row.get("代號", "")).strip(),
        "stock_name": str(row.get("名稱", "")).strip(),
        "MarginPurchaseTodayBalance": _clean_number(row.get("資餘額", 0)),
        "ShortSaleTodayBalance": _clean_number(row.get("券餘額", 0)),
        "source": "TPEx",
    }


def fetch_margin_data(symbol: str, days: int = 14) -> pd.DataFrame:
    """
    官方批次版融資融券：
    - .TW  上市：TWSE OpenAPI MI_MARGN，目前多為單日全市場
    - .TWO 上櫃：TPEx margin_bal_result，往前抓多日
    """

    target_id = _stock_id(symbol)
    records = []

    if _is_tpex(symbol):
        for date_obj in _recent_dates(days):
            trade_date = date_obj.strftime("%Y-%m-%d")
            df = _fetch_tpex_margin_by_date(_tpex_roc_date(date_obj))

            if df.empty or "代號" not in df.columns:
                continue

            matched = df[df["代號"].astype(str).str.strip() == target_id]

            for _, row in matched.iterrows():
                records.append(_normalize_tpex_margin_row(row, trade_date))

    else:
        df = _fetch_twse_margin_all()

        if not df.empty:
            possible_code_cols = ["股票代號", "證券代號", "Code", "STOCK_ID"]
            code_col = None

            for col in possible_code_cols:
                if col in df.columns:
                    code_col = col
                    break

            if code_col is None and len(df.columns) > 0:
                code_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

            if code_col is not None:
                matched = df[df[code_col].astype(str).str.strip() == target_id]

                for _, row in matched.iterrows():
                    records.append(_normalize_twse_margin_row(row))

    result = pd.DataFrame(records)

    if not result.empty:
        result = result.sort_values("date")

    if result.empty:
        result.attrs["data_status"] = "empty"
    else:
        result.attrs["data_status"] = "success"

    return result
