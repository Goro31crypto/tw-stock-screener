import re
from datetime import datetime, timedelta

import pandas as pd

from services.chip_service_official import (
    _fetch_twse_institutional_by_date,
    _fetch_tpex_institutional_by_date,
    _twse_date,
    _tpex_roc_date,
    _clean_number,
)


def _recent_dates(days: int = 14):
    today = datetime.today()

    for i in range(days):
        yield today - timedelta(days=i)


def _is_common_stock(stock_id: str) -> bool:
    """
    先只保留 4 碼普通股，排除 ETF / ETN / 權證。
    """
    stock_id = str(stock_id).strip()
    return bool(re.fullmatch(r"\d{4}", stock_id))


def _parse_twse_rows(df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    rows = []

    for _, row in df.iterrows():
        stock_id = str(row.get("證券代號", "")).strip()

        if not _is_common_stock(stock_id):
            continue

        foreign_net = _clean_number(row.get("外陸資買賣超股數(不含外資自營商)", 0))
        trust_net = _clean_number(row.get("投信買賣超股數", 0))
        dealer_net = _clean_number(row.get("自營商買賣超股數", 0))
        total_net = _clean_number(row.get("三大法人買賣超股數", 0))

        rows.append({
            "市場": "上市",
            "資料日期": trade_date,
            "股票代號": stock_id,
            "股票名稱": str(row.get("證券名稱", "")).strip(),
            "外資買賣超股數": foreign_net,
            "投信買賣超股數": trust_net,
            "自營商買賣超股數": dealer_net,
            "三大法人買賣超股數": total_net,
        })

    return pd.DataFrame(rows)


def _parse_tpex_rows(df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    rows = []

    for _, row in df.iterrows():
        values = list(row.values)

        if len(values) < 24:
            continue

        stock_id = str(values[0]).strip()

        if not _is_common_stock(stock_id):
            continue

        foreign_net = _clean_number(values[4]) if len(values) > 4 else 0
        trust_net = _clean_number(values[10]) if len(values) > 10 else 0
        dealer_net = _clean_number(values[19]) if len(values) > 19 else 0
        total_net = _clean_number(values[23]) if len(values) > 23 else 0

        rows.append({
            "市場": "上櫃",
            "資料日期": trade_date,
            "股票代號": stock_id,
            "股票名稱": str(values[1]).strip(),
            "外資買賣超股數": foreign_net,
            "投信買賣超股數": trust_net,
            "自營商買賣超股數": dealer_net,
            "三大法人買賣超股數": total_net,
        })

    return pd.DataFrame(rows)


def _find_latest_twse_institution(days: int = 14) -> pd.DataFrame:
    for date_obj in _recent_dates(days):
        df = _fetch_twse_institutional_by_date(_twse_date(date_obj))

        if not df.empty:
            trade_date = date_obj.strftime("%Y-%m-%d")
            return _parse_twse_rows(df, trade_date)

    return pd.DataFrame()


def _find_latest_tpex_institution(days: int = 14) -> pd.DataFrame:
    for date_obj in _recent_dates(days):
        df = _fetch_tpex_institutional_by_date(_tpex_roc_date(date_obj))

        if not df.empty:
            trade_date = date_obj.strftime("%Y-%m-%d")
            return _parse_tpex_rows(df, trade_date)

    return pd.DataFrame()


def fetch_market_institution_ranking(days: int = 14) -> pd.DataFrame:
    """
    全市場法人買賣超排行榜。
    來源：
    - 上市：TWSE T86
    - 上櫃：TPEx dailyTrade
    """

    twse_df = _find_latest_twse_institution(days)
    tpex_df = _find_latest_tpex_institution(days)

    df = pd.concat([twse_df, tpex_df], ignore_index=True)

    if df.empty:
        return df

    number_cols = [
        "外資買賣超股數",
        "投信買賣超股數",
        "自營商買賣超股數",
        "三大法人買賣超股數",
    ]

    for col in number_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df[col.replace("股數", "張數")] = df[col] / 1000

    df = df.sort_values("三大法人買賣超股數", ascending=False).reset_index(drop=True)

    return df
