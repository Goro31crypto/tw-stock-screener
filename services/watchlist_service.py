import os
import pandas as pd

from services.price_service import fetch_price_data
from services.industry_service import get_stock_industry


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
    category: str = "",
    business: str = "",
    themes: str = "",
):
    """
    新增或更新自訂候選股票。

    新版邏輯：
    - 使用者只需要輸入股票代號與股票名稱
    - 系統會自動查官方產業分類
    - 系統會自動判斷上市 / 上櫃
    - 系統會自動產生 yfinance symbol，例如 2330.TW / 5426.TWO
    """

    os.makedirs("data", exist_ok=True)

    stock_code = normalize_stock_code(stock_code)

    if not stock_code:
        return False, "股票代號不可為空", None

    name = str(name).strip()

    # 優先用官方產業資料判斷市場、產業、symbol
    official_info = get_stock_industry(stock_code=stock_code, stock_name=name)

    official_symbol = str(official_info.get("symbol", "")).strip()
    official_name = str(official_info.get("股票名稱", "")).strip()
    official_market = str(official_info.get("市場", "")).strip()
    official_category = str(official_info.get("產業分類", "")).strip()

    if official_symbol:
        symbol = official_symbol

        # 用股價資料簡單驗證 symbol 是否可用
        is_valid = False
        message = "已依官方資料找到股票代號"

        try:
            df_price = fetch_price_data(symbol, period="1mo")
            if df_price is not None and not df_price.empty:
                is_valid = True
                message = "已找到股價資料"
        except Exception:
            is_valid = False
            message = "已依官方資料找到股票，但目前抓不到股價資料"

    else:
        # 官方資料找不到時，才退回原本的上市 / 上櫃判斷
        symbol, is_valid, message = resolve_symbol(stock_code, market_choice)

        if symbol is None:
            return False, message, None

    stock_id = symbol.split(".")[0]

    final_name = name or official_name or f"自訂股票{stock_id}"

    # 產業分類：優先用官方抓到的產業
    if official_category and official_category not in ["待確認", "未分類"]:
        final_category = official_category
    else:
        final_category = str(category).strip() or "待確認"

    final_business = str(business).strip()
    if not final_business:
        if official_market:
            final_business = f"{final_name}，{official_market}公司，產業分類為{final_category}。"
        else:
            final_business = f"{final_name}，產業分類為{final_category}。"

    final_themes = str(themes).strip() or final_category or "自訂候選"

    new_row = {
        "symbol": symbol,
        "name": final_name,
        "category": final_category,
        "business": final_business,
        "themes": final_themes,
    }

    if os.path.exists(CUSTOM_WATCHLIST_PATH):
        df = pd.read_csv(CUSTOM_WATCHLIST_PATH, dtype=str).fillna("")
    else:
        df = pd.DataFrame(columns=["symbol", "name", "category", "business", "themes"])

    df = df[df["symbol"] != symbol]
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df.to_csv(CUSTOM_WATCHLIST_PATH, index=False, encoding="utf-8-sig")

    if is_valid:
        return True, f"{symbol} 已加入候選清單，產業分類：{final_category}", symbol

    return True, f"{symbol} 已加入候選清單，產業分類：{final_category}，但目前抓不到股價資料：{message}", symbol

