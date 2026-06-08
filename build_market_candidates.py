from pathlib import Path

from services.market_universe_service import build_liquidity_candidates


OUTPUT_CSV_1 = "data/liquidity_candidates.csv"
OUTPUT_CSV_2 = "data/output/market_movement_top.csv"


def main():
    print("開始建立全市場異動候選股清單...")
    print("目前使用快速版：抓最近 10 個日曆日，Top 50。")

    df = build_liquidity_candidates(calendar_days=10, top_n=50)

    Path("data").mkdir(exist_ok=True)
    Path("data/output").mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_CSV_1, index=False, encoding="utf-8-sig")
    df.to_csv(OUTPUT_CSV_2, index=False, encoding="utf-8-sig")

    print("全市場異動候選股數量：", len(df))

    if df.empty:
        print("沒有抓到資料，請檢查 TWSE / TPEx 是否已有盤後資料。")
        return

    print("\nTop 30 異動股：")

    cols = [
        "市場",
        "資料日期",
        "股票代號",
        "股票名稱",
        "收盤價",
        "漲跌幅%",
        "成交量張數",
        "近20日均量張數",
        "量增倍率",
        "成交值百萬",
        "異動分",
    ]

    existing_cols = [col for col in cols if col in df.columns]
    print(df[existing_cols].head(30).to_string(index=False))

    print(f"\n已輸出：{OUTPUT_CSV_1}")
    print(f"已輸出：{OUTPUT_CSV_2}")


if __name__ == "__main__":
    main()
