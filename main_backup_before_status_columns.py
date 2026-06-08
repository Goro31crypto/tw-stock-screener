from datetime import datetime
import os

from stock_list import STOCK_LIST, STOCK_META
from services.price_service import fetch_price_data
from services.chip_service import (
    fetch_institution_data,
    fetch_margin_data,
    analyze_institution_signal,
    analyze_margin_signal,
)
from services.news_service import analyze_news
from indicators.technical import add_technical_indicators
from signals.technical_signal import analyze_technical_signal
from reports.excel_report import export_to_excel
from reports.history_report import append_score_history
from reports.run_log_report import append_run_log


def decide_final_signal(total_score: int, tech_signal: str) -> str:
    """
    最終訊號判斷。
    新聞不參與分數，也不改變訊號。
    """

    if tech_signal == "高風險排除":
        return "高風險排除"

    if total_score >= 28:
        return "買進觀察"

    if total_score >= 15:
        return "留意追蹤"

    if total_score < 0:
        return "有陷阱"

    return "不符條件"


def main():
    print("台股篩選程式開始執行...")
    print("V2.3：技術面 + 法人籌碼 + 融資融券 + 公司業務 + 新聞標註 + 歷史分數")
    print("注意：新聞只做標註，不加分、不扣分")

    results = []

    for symbol in STOCK_LIST:
        meta = STOCK_META.get(symbol, {})

        stock_id = symbol.split(".")[0]
        name = meta.get("name", "")
        category = meta.get("category", "")
        business = meta.get("business", "")
        themes = meta.get("themes", "")

        print(f"正在分析：{stock_id} {name}")

        try:
            # 1. 股價資料
            price_df = fetch_price_data(symbol, period="6mo")

            if price_df.empty:
                print(f"{symbol} 無股價資料")
                continue

            price_df = price_df.sort_index()
            price_date = price_df.index[-1].strftime("%Y-%m-%d")
            price_source = "Yahoo Finance / yfinance（日K，非即時）"

            # 2. 技術面
            price_df = add_technical_indicators(price_df)
            tech_analysis = analyze_technical_signal(price_df)

            latest = price_df.iloc[-1]
            prev = price_df.iloc[-2]

            red_k = latest["Close"] > latest["Open"]
            price_up = latest["Close"] > prev["Close"]

            # 3. 法人籌碼
            inst_df = fetch_institution_data(symbol, days=14)
            inst_analysis = analyze_institution_signal(
                inst_df=inst_df,
                red_k=red_k,
                price_up=price_up
            )

            # 4. 融資融券
            margin_df = fetch_margin_data(symbol, days=14)
            margin_analysis = analyze_margin_signal(
                margin_df=margin_df,
                price_up=price_up
            )

            # 5. 新聞事件標註，不加分
            news_analysis = analyze_news(
                stock_id=stock_id,
                stock_name=name,
                days=7,
                max_items=5
            )

            # 6. 分數合併，新聞不參與
            tech_score = tech_analysis["score"]
            inst_score = inst_analysis["score"]
            margin_score = margin_analysis["score"]

            total_score = tech_score + inst_score + margin_score

            final_signal = decide_final_signal(
                total_score=total_score,
                tech_signal=tech_analysis["signal"]
            )

            # 7. 整理原因與風險
            details = tech_analysis["details"]
            inst_details = inst_analysis["details"]
            margin_details = margin_analysis["details"]

            system_reasons = []

            if tech_analysis["reasons"]:
                system_reasons.append("技術面：" + tech_analysis["reasons"])

            if inst_analysis["reasons"]:
                system_reasons.append("籌碼面：" + inst_analysis["reasons"])

            if margin_analysis["reasons"]:
                system_reasons.append("信用交易：" + margin_analysis["reasons"])

            flags = []

            if tech_analysis["flags"]:
                flags.append(tech_analysis["flags"])

            if inst_analysis["flags"]:
                flags.append(inst_analysis["flags"])

            if margin_analysis["flags"]:
                flags.append(margin_analysis["flags"])

            # 8. 輸出資料
            result = {
                "股票代號": stock_id,
                "股票名稱": name,
                "產業分類": category,
                "公司業務": business,
                "題材標籤": themes,

                "資料日期": price_date,
                "價格來源": price_source,

                "分數": total_score,
                "訊號": final_signal,

                "技術分": tech_score,
                "法人籌碼分": inst_score,
                "融資融券分": margin_score,

                "系統解讀": "｜".join(system_reasons),
                "風險標註": "；".join(flags),

                "收盤價": details.get("close"),
                "MA5": details.get("ma5"),
                "MA10": details.get("ma10"),
                "MA60": details.get("ma60"),
                "近5日漲幅%": details.get("gain_5d"),

                "剛站上MA5": details.get("cross_up_ma5"),
                "剛站上MA10": details.get("cross_up_ma10"),
                "MA5上彎": details.get("ma5_turn_up"),
                "放量": details.get("volume_expand"),
                "健康放量紅K": details.get("healthy_volume_candle"),
                "接近60日支撐": details.get("near_support_60"),
                "站上20日成本線": details.get("above_cost_20d"),

                "法人近3日連買": inst_details.get("法人近3日連買"),
                "法人近3日連賣": inst_details.get("法人近3日連賣"),
                "外資近3日連買": inst_details.get("外資近3日連買"),
                "投信近3日連買": inst_details.get("投信近3日連買"),
                "最新法人買賣超": inst_details.get("最新法人買賣超"),

                "融資連2減": margin_details.get("融資連2減"),
                "融券連2增": margin_details.get("融券連2增"),
                "最新融資增減": margin_details.get("最新融資增減"),
                "最新融券增減": margin_details.get("最新融券增減"),

                "近期新聞數": news_analysis.get("news_count"),
                "新聞傾向": news_analysis.get("news_bias"),
                "新聞題材": news_analysis.get("news_topics"),
                "新聞摘要": news_analysis.get("news_summary"),
                "新聞風險提示": news_analysis.get("news_flags"),
                "新聞連結": news_analysis.get("news_links"),
            }

            results.append(result)

        except Exception as e:
            print(f"{symbol} 分析失敗：{e}")

    expected_count = len(STOCK_LIST)
    success_count = len(results)
    min_success_count = min(expected_count, max(80, int(expected_count * 0.75)))

    print("-" * 50)
    print(f"預期分析股票數：{expected_count}")
    print(f"成功分析股票數：{success_count}")
    print(f"最低輸出門檻：{min_success_count}")

    if success_count < min_success_count:
        print("本次成功股票數低於最低門檻，停止輸出。")
        print("舊報表會被保留，不會被這次異常結果覆蓋。")
        print("請檢查上方失敗訊息或資料來源狀態。")
        return

    os.makedirs("data/output", exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    output_path = f"data/output/stock_screener_v23_{today}.xlsx"

    export_to_excel(results, output_path)

    # 寫入歷史分數紀錄
    append_score_history(results)

    print("完成！")
    print(f"結果已輸出到：{output_path}")


if __name__ == "__main__":
    main()
