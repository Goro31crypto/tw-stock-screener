from services.market_universe_service import export_liquidity_candidates

df = export_liquidity_candidates("data/liquidity_candidates.csv")

print("全市場異動候選股數量：", len(df))

if df.empty:
    print("沒有抓到資料，請檢查 TWSE / TPEx 是否已有今日盤後資料。")
else:
    print("\nTop 30 異動股：")
    print(
        df[
            [
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
        ].head(30).to_string(index=False)
    )

    print("\n已輸出：data/liquidity_candidates.csv")
