import traceback
import inspect

from stock_list import STOCK_META
from services.price_service import fetch_price_data
from indicators.technical import add_technical_indicators
from signals.technical_signal import analyze_technical_signal
from services.chip_service import (
    fetch_institution_data,
    fetch_margin_data,
    analyze_institution_signal,
    analyze_margin_signal,
)
from services.news_service import analyze_news


symbol = "2330.TW"
stock_id = symbol.split(".")[0]
meta = STOCK_META.get(symbol, {})

print("=" * 50)
print("DEBUG 單檔測試")
print("symbol:", symbol)
print("stock_id:", stock_id)
print("meta:", meta)
print("=" * 50)


def run_step(name, func):
    print(f"\n--- 測試：{name} ---")

    try:
        result = func()
        print(f"{name} 成功")

        if hasattr(result, "shape"):
            print("shape:", result.shape)
            print(result.tail())
        else:
            print("result:", result)

        return result

    except Exception as e:
        print(f"{name} 失敗")
        print("錯誤：", repr(e))
        traceback.print_exc()
        raise SystemExit


price_df = run_step(
    "fetch_price_data",
    lambda: fetch_price_data(symbol, period="6mo")
)

if price_df is None or price_df.empty:
    print("股價資料是空的，停止")
    raise SystemExit

price_df = run_step(
    "add_technical_indicators",
    lambda: add_technical_indicators(price_df)
)

technical_result = run_step(
    "analyze_technical_signal",
    lambda: analyze_technical_signal(price_df)
)

latest = price_df.iloc[-1]
prev = price_df.iloc[-2]

close_price = float(latest["Close"])
open_price = float(latest["Open"])
prev_close = float(prev["Close"])

red_k = close_price > open_price
price_up = close_price > prev_close

print("\n--- 價格狀態 ---")
print("red_k:", red_k)
print("price_up:", price_up)
print("close:", close_price)
print("open:", open_price)
print("prev_close:", prev_close)

institution_df = run_step(
    "fetch_institution_data",
    lambda: fetch_institution_data(stock_id)
)

institution_result = run_step(
    "analyze_institution_signal",
    lambda: analyze_institution_signal(institution_df, red_k, price_up)
)

margin_df = run_step(
    "fetch_margin_data",
    lambda: fetch_margin_data(stock_id)
)

def call_margin_signal():
    sig = inspect.signature(analyze_margin_signal)
    param_count = len(sig.parameters)

    if param_count == 1:
        return analyze_margin_signal(margin_df)

    if param_count == 2:
        return analyze_margin_signal(margin_df, price_up)

    if param_count == 3:
        return analyze_margin_signal(margin_df, red_k, price_up)

    return analyze_margin_signal(margin_df)

margin_result = run_step(
    "analyze_margin_signal",
    call_margin_signal
)

news_result = run_step(
    "analyze_news",
    lambda: analyze_news(
        stock_id=stock_id,
        stock_name=meta.get("name", ""),
        days=7,
        max_items=5,
    )
)

print("\n" + "=" * 50)
print("單檔 debug 全部成功")
print("=" * 50)
