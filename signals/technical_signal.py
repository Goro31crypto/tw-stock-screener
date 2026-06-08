import pandas as pd


def _safe_round(value, digits=2):
    if pd.isna(value):
        return None
    return round(float(value), digits)


def _cap_score(score: int, lower: int = -10, upper: int = 20) -> int:
    return max(lower, min(upper, score))


def analyze_technical_signal(df: pd.DataFrame) -> dict:
    """
    技術面評分 V4

    核心邏輯：
    1. 單純站上均線只給小分
    2. 剛站上均線不再重分，避免假突破名單過多
    3. 放量紅K才視為突破確認
    4. 乖離過高扣分，避免追高
    5. 近5日大跌也扣分，避免接弱勢刀
    6. 技術分限制在 -10 到 +20
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
    low = latest["Low"]
    volume = latest["Volume"]

    prev_close = prev["Close"]

    ma5 = latest.get("MA5")
    ma10 = latest.get("MA10")
    ma20 = latest.get("MA20")
    ma60 = latest.get("MA60")

    prev_ma5 = prev.get("MA5")
    prev_ma10 = prev.get("MA10")
    prev_ma20 = prev.get("MA20")
    prev_ma60 = prev.get("MA60")

    vol_ma5_prev = latest.get("VOL_MA5_PREV")
    vol_ma20_prev = latest.get("VOL_MA20_PREV")
    gain_5d = latest.get("GAIN_5D")
    bias_ma20 = latest.get("BIAS_MA20")
    support_60 = latest.get("SUPPORT_60")
    cost_20d = latest.get("COST_20D")

    # ===== 基本價格狀態 =====
    red_k = close > open_
    price_up = close > prev_close

    # ===== 均線狀態 =====
    above_ma5 = pd.notna(ma5) and close > ma5
    above_ma10 = pd.notna(ma10) and close > ma10
    above_ma20 = pd.notna(ma20) and close > ma20
    above_ma60 = pd.notna(ma60) and close > ma60

    below_ma60 = pd.notna(ma60) and close < ma60

    cross_up_ma5 = (
        pd.notna(prev_ma5) and
        pd.notna(ma5) and
        prev_close <= prev_ma5 and
        close > ma5
    )

    cross_up_ma10 = (
        pd.notna(prev_ma10) and
        pd.notna(ma10) and
        prev_close <= prev_ma10 and
        close > ma10
    )

    cross_up_ma20 = (
        pd.notna(prev_ma20) and
        pd.notna(ma20) and
        prev_close <= prev_ma20 and
        close > ma20
    )

    cross_down_ma10 = (
        pd.notna(prev_ma10) and
        pd.notna(ma10) and
        prev_close >= prev_ma10 and
        close < ma10
    )

    cross_down_ma60 = (
        pd.notna(prev_ma60) and
        pd.notna(ma60) and
        prev_close >= prev_ma60 and
        close < ma60
    )

    ma5_turn_up = pd.notna(prev_ma5) and pd.notna(ma5) and ma5 > prev_ma5
    ma10_turn_up = pd.notna(prev_ma10) and pd.notna(ma10) and ma10 > prev_ma10

    # ===== 成交量狀態 =====
    volume_expand = False
    volume_extreme = False

    if pd.notna(vol_ma20_prev) and vol_ma20_prev > 0:
        volume_expand = volume > vol_ma20_prev
        volume_extreme = volume > vol_ma20_prev * 2
    elif pd.notna(vol_ma5_prev) and vol_ma5_prev > 0:
        volume_expand = volume > vol_ma5_prev * 1.5
        volume_extreme = volume > vol_ma5_prev * 2.5

    # ===== K 線狀態 =====
    body = abs(close - open_)
    upper_shadow = high - max(close, open_)
    lower_shadow = min(close, open_) - low

    body_pct = body / open_ * 100 if open_ > 0 else 0
    valid_body = body_pct >= 0.5

    short_upper = upper_shadow < body * 0.5 if body > 0 else False
    long_upper = upper_shadow > body * 2 if body > 0 else False

    volume_red_k = volume_expand and red_k and price_up
    healthy_volume_candle = volume_red_k and valid_body and short_upper
    danger_volume_candle = volume_extreme and long_upper

    breakout_confirmed = (
        volume_red_k and
        (
            cross_up_ma5 or
            cross_up_ma10 or
            cross_up_ma20
        )
    )

    # ===== 支撐 / 成本線 =====
    near_support_60 = False
    break_support_60 = False

    if pd.notna(support_60):
        near_support_60 = close <= support_60 * 1.03 and close >= support_60 * 0.98
        break_support_60 = close < support_60 * 0.98

    above_cost_20d = False
    break_cost_20d = False

    if pd.notna(cost_20d):
        above_cost_20d = close > cost_20d
        break_cost_20d = close < cost_20d * 0.98

    # ======================================================
    # 1. 趨勢結構分：站上均線只小加分
    # ======================================================

    if cross_up_ma5:
        score += 1
        reasons.append("剛站上MA5，短線轉強但仍需量能確認")
    elif above_ma5:
        score += 1
        reasons.append("收盤站上MA5，短線偏強")

    if cross_up_ma10:
        score += 1
        reasons.append("剛站上MA10，短線結構改善")
    elif above_ma10:
        score += 1
        reasons.append("收盤站上MA10，短線趨勢尚可")

    if cross_up_ma20:
        score += 2
        reasons.append("剛站上MA20，站回短中期成本區")
    elif above_ma20:
        score += 2
        reasons.append("收盤站上MA20，短中期結構偏強")

    if above_ma60:
        score += 3
        reasons.append("收盤站上MA60，中期趨勢未轉弱")

    if below_ma60:
        score -= 4
        flags.append("收盤跌破MA60，中期結構偏弱")

    # ======================================================
    # 2. 均線斜率
    # ======================================================

    if ma5_turn_up:
        score += 1
        reasons.append("MA5上彎，短線動能改善")

    if ma10_turn_up:
        score += 1
        reasons.append("MA10上彎，短線趨勢改善")

    # ======================================================
    # 3. 量價確認
    # ======================================================

    if volume_red_k:
        score += 2
        reasons.append("放量紅K，買盤有表態")

    if breakout_confirmed:
        score += 3
        reasons.append("站上均線並搭配放量紅K，突破可信度提高")

    if healthy_volume_candle:
        reasons.append("紅K實體有效且上影線短，量價表現健康")

    if danger_volume_candle:
        score -= 3
        flags.append("爆大量長上影，疑似高檔出貨或上檔賣壓沉重")

    # ======================================================
    # 4. 支撐與成本
    # ======================================================

    if near_support_60 and not break_support_60:
        score += 2
        reasons.append("接近60日支撐但未跌破，有支撐觀察價值")

    if above_cost_20d:
        score += 1
        reasons.append("收盤在20日成本線上方，近期籌碼成本偏有利")

    if break_cost_20d:
        score -= 2
        flags.append("跌破20日成本線，近期籌碼成本轉弱")

    # ======================================================
    # 5. 追高 / 弱勢風險
    # ======================================================

    if pd.notna(bias_ma20) and bias_ma20 > 10:
        score -= 3
        flags.append(f"股價離MA20過遠，乖離率 {bias_ma20:.1f}%｜注意追高")

    if pd.notna(gain_5d):
        if gain_5d > 25:
            score -= 4
            flags.append(f"近5日漲幅 {gain_5d:.1f}%｜短線過熱")
        elif gain_5d > 20:
            score -= 3
            flags.append(f"近5日漲幅 {gain_5d:.1f}%｜注意追高")
        elif gain_5d < -10:
            score -= 3
            flags.append(f"近5日跌幅 {gain_5d:.1f}%｜短線弱勢，不急著接刀")
        elif -10 <= gain_5d < -5:
            score -= 1
            flags.append(f"近5日跌幅 {gain_5d:.1f}%｜偏弱整理")
        elif -5 <= gain_5d <= 8:
            score += 1
            reasons.append("近5日漲跌幅位於健康區間")

    # ======================================================
    # 6. 否決 / 高風險條件
    # ======================================================

    if cross_down_ma10:
        hard_flags.append("跌破MA10｜短線轉弱")

    if cross_down_ma60:
        hard_flags.append("跌破MA60｜波段轉弱")

    if break_support_60:
        hard_flags.append("跌破60日支撐")

    # 分數上下限保護
    score = _cap_score(score, lower=-10, upper=20)

    # ======================================================
    # 7. 訊號等級
    # ======================================================

    if hard_flags:
        signal = "高風險排除"
    elif score >= 14:
        signal = "買進觀察"
    elif score >= 7:
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
            "close": _safe_round(close),
            "ma5": _safe_round(ma5),
            "ma10": _safe_round(ma10),
            "ma20": _safe_round(ma20),
            "ma60": _safe_round(ma60),
            "gain_5d": _safe_round(gain_5d),
            "bias_ma20": _safe_round(bias_ma20),

            "cross_up_ma5": bool(cross_up_ma5),
            "cross_up_ma10": bool(cross_up_ma10),
            "cross_up_ma20": bool(cross_up_ma20),

            "ma5_turn_up": bool(ma5_turn_up),
            "ma10_turn_up": bool(ma10_turn_up),

            "volume_expand": bool(volume_expand),
            "volume_red_k": bool(volume_red_k),
            "healthy_volume_candle": bool(healthy_volume_candle),
            "danger_volume_candle": bool(danger_volume_candle),
            "breakout_confirmed": bool(breakout_confirmed),

            "near_support_60": bool(near_support_60),
            "above_cost_20d": bool(above_cost_20d),

            "above_ma5": bool(above_ma5),
            "above_ma10": bool(above_ma10),
            "above_ma20": bool(above_ma20),
            "above_ma60": bool(above_ma60),
            "below_ma60": bool(below_ma60),
        }
    }
