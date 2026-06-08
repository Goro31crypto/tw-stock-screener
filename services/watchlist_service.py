import os
import pandas as pd

from services.price_service import fetch_price_data


CUSTOM_WATCHLIST_PATH = "data/custom_watchlist.csv"


def normalize_stock_code(raw_code: str) -> str:
    """
    只保留股票代號中的數字。
    例如：
    2330 -> 2330
    2330.TW -> 2330
    3491.TWO -> 3491
    """

    raw_code = str(raw_code).strip()

    if "." in raw_code:
        raw_code = raw_code.split(".")[0]

    return "".join(ch for ch in raw_code if ch.isdigit())


def resolve_symbol(stock_code: str, market_choice: str = "自動判斷"):
    """
    依照股票代號推測 Yahoo Finance 可用代號。
    """

    stock_code = normalize_stock_code(stock_code)

    if not stock_code:
        return None, False, "股票代號不可為空"

    if market_choice == "上市 .TW":
        candidates = [f"{stock_code}.TW"]
    elif market_choice == "上櫃 .TWO":
        candidates = [f"{stock_code}.TWO"]
    else:
        candidates = [
            f"{stock_code}.TW",
            f"{stock_code}.TWO",
        ]

    for symbol in candidates:
        try:
            df = fetch_price_data(symbol, period="1mo")

            if not df.empty:
                return symbol, True, "已找到股價資料"
        except Exception:
            pass

    return candidates[0], False, "找不到股價資料，請確認上市 / 上櫃代號是否正確"


def load_custom_watchlist():
    """
    讀取使用者自行新增的候選股票。
    如果還沒有 custom_watchlist.csv，就回傳空字典。
    """

    if not os.path.exists(CUSTOM_WATCHLIST_PATH):
        return {}

    df = pd.read_csv(CUSTOM_WATCHLIST_PATH, dtype=str).fillna("")

    custom_meta = {}

    for _, row in df.iterrows():
        symbol = row.get("symbol", "").strip()

        if not symbol:
            continue

        custom_meta[symbol] = {
            "name": row.get("name", "").strip(),
            "category": row.get("category", "自訂候選").strip() or "自訂候選",
            "business": row.get("business", "使用者自行新增的候選股票。").strip() or "使用者自行新增的候選股票。",
            "themes": row.get("themes", "自訂候選").strip() or "自訂候選",
        }

    return custom_meta


def add_custom_stock(
    stock_code: str,
    market_choice: str,
    name: str,
    category: str,
    business: str,
    themes: str,
):
    """
    新增或更新自訂候選股票。
    """

    os.makedirs("data", exist_ok=True)

    symbol, is_valid, message = resolve_symbol(stock_code, market_choice)

    if symbol is None:
        return False, message, None

    stock_id = symbol.split(".")[0]

    name = str(name).strip() or f"自訂股票{stock_id}"
    category = str(category).strip() or "自訂候選"
    business = str(business).strip() or "使用者自行新增的候選股票。"
    themes = str(themes).strip() or "自訂候選"

    new_row = {
        "symbol": symbol,
        "name": name,
        "category": category,
        "business": business,
        "themes": themes,
    }

    if os.path.exists(CUSTOM_WATCHLIST_PATH):
        df = pd.read_csv(CUSTOM_WATCHLIST_PATH, dtype=str).fillna("")
    else:
        df = pd.DataFrame(columns=["symbol", "name", "category", "business", "themes"])

    df = df[df["symbol"] != symbol]
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df.to_csv(CUSTOM_WATCHLIST_PATH, index=False, encoding="utf-8-sig")

    if is_valid:
        return True, f"{symbol} 已加入候選清單", symbol

    return True, f"{symbol} 已加入候選清單，但目前抓不到股價資料：{message}", symbol
