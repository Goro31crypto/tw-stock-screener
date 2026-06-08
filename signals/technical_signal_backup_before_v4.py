import pandas as pd


def analyze_technical_signal(df: pd.DataFrame) -> dict:
    """
    分析最新一天的技術面訊號。
    回傳：
    - score
    - signal
    - reasons
    - flags
    - details
    """

    if len(df) < 65:
        return {
            "score": 0,
            "signal": "資料不足",
            "reasons": "",
            "flags": "資料不足，至少需要65筆交易日資料",
            "details": {}
        }

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    score = 0
    reasons = []
    flags = []
    hard_flags = []

    close = latest["Close"]
    open_ = latest["Open"]
    high = latest["High"]
    volume = latest["Volume"]

    prev_close = prev["Close"]

    ma5 = latest["MA5"]
    ma10 = latest["MA10"]
    ma60 = latest["MA60"]
    prev_ma5 = prev["MA5"]
    prev_ma10 = prev["MA10"]

    vol_ma5_prev = latest["VOL_MA5_PREV"]
    gain_5d = latest["GAIN_5D"]
    support_60 = latest["SUPPORT_60"]
    cost_20d = latest["COST_20D"]

    # 基本價格狀態
    red_k = close > open_
    price_up = close > prev_close

    # 剛站上 MA5 / MA10
    cross_up_ma5 = prev_close <= prev_ma5 and close > ma5
    cross_up_ma10 = prev_close <= prev_ma10 and close > ma10

    # 跌破 MA10
    cross_down_ma10 = prev_close >= prev_ma10 and close < ma10

    # MA5 上彎
    ma5_turn_up = ma5 > prev_ma5

    # 放量：今日成交量 > 前5日均量 * 1.5
    volume_expand = False
    if pd.notna(vol_ma5_prev) and vol_ma5_prev > 0:
        volume_expand = volume > vol_ma5_prev * 1.5

    # K線實體與上影線
    body = abs(close - open_)
    upper_shadow = high - max(close, open_)
    body_pct = body / open_ * 100 if open_ > 0 else 0

    valid_body = body_pct >= 0.5
    short_upper = upper_shadow < body * 0.33 if body > 0 else False
    long_upper = upper_shadow > body * 2 if body > 0 else False

    healthy_volume_candle = (
        volume_expand and
        red_k and
        price_up and
        valid_body and
        short_upper
    )

    danger_volume_candle = volume_expand and long_upper

    # 支撐判斷
    near_support_60 = False
    break_support_60 = False

    if pd.notna(support_60):
        near_support_60 = close <= support_60 * 1.03
        break_support_60 = close < support_60 * 0.98

    above_cost_20d = False
    break_cost_20d = False

    if pd.notna(cost_20d):
        above_cost_20d = close > cost_20d
        break_cost_20d = close < cost_20d * 0.98

    # 加分條件
    if cross_up_ma5:
        score += 4
        reasons.append("剛站上MA5，短線轉強")

    if cross_up_ma10:
        score += 6
        reasons.append("剛站上MA10，短線趨勢確認度提高")

    if ma5_turn_up:
        score += 3
        reasons.append("MA5上彎，短線均線斜率轉正")

    if healthy_volume_candle:
        score += 8
        reasons.append("放量紅K且上影線短，買盤推升較健康")

    if near_support_60 and not break_support_60:
        score += 4
        reasons.append("接近60日支撐但未跌破，有支撐觀察價值")

    if close > ma60:
        score += 3
        reasons.append("收盤站在MA60上方，中期趨勢尚未轉弱")

    if above_cost_20d:
        score += 2
        reasons.append("收盤在20日成本線上方，近期籌碼仍偏有利")

    # 扣分與標註
    if pd.notna(gain_5d) and gain_5d > 15:
        score -= 5
        flags.append(f"近5日漲幅 {gain_5d:.1f}%｜注意追高")
        reasons.append("近5日漲幅過大，扣分處理")

    if break_cost_20d:
        score -= 3
        flags.append("跌破20日籌碼成本線")
        reasons.append("跌破20日成本線，近期籌碼轉弱")

    # 否決條件
    if danger_volume_candle:
        hard_flags.append("爆量長上影｜疑似出貨")
        reasons.append("出現爆量長上影，列為高風險")

    if cross_down_ma10:
        hard_flags.append("跌破MA10｜短線轉弱")
        reasons.append("跌破MA10，短線結構轉弱")

    if break_support_60:
        hard_flags.append("跌破60日支撐")
        reasons.append("跌破60日支撐，技術面轉弱")

    # 訊號等級
    max_score = 30
    pct = score / max_score

    if hard_flags:
        signal = "高風險排除"
    elif pct >= 0.60:
        signal = "買進觀察"
    elif pct >= 0.30:
        signal = "留意追蹤"
    elif score < 0:
        signal = "有陷阱"
    else:
        signal = "不符條件"

    if not reasons:
        reasons.append("目前沒有明確技術面加分條件")

    return {
        "score": score,
        "signal": signal,
        "reasons": "；".join(reasons),
        "flags": "；".join(flags + hard_flags),
        "details": {
            "close": round(close, 2),
            "ma5": round(ma5, 2) if pd.notna(ma5) else None,
            "ma10": round(ma10, 2) if pd.notna(ma10) else None,
            "ma60": round(ma60, 2) if pd.notna(ma60) else None,
            "gain_5d": round(gain_5d, 2) if pd.notna(gain_5d) else None,
            "cross_up_ma5": cross_up_ma5,
            "cross_up_ma10": cross_up_ma10,
            "ma5_turn_up": ma5_turn_up,
            "volume_expand": volume_expand,
            "healthy_volume_candle": healthy_volume_candle,
            "near_support_60": near_support_60,
            "above_cost_20d": above_cost_20d,
        }
    }
