import pandas as pd


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    加入技術指標 V4：
    - MA5
    - MA10
    - MA20
    - MA60
    - 前5日均量
    - 前20日均量
    - 5日漲幅
    - 60日低點支撐
    - 20日成交量加權成本線
    """

    df = df.copy()
    df = df.sort_index()

    # 均線
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()

    # 前 N 日均量，不包含今天，避免偷看當日資料
    df["VOL_MA5_PREV"] = df["Volume"].shift(1).rolling(5).mean()
    df["VOL_MA20_PREV"] = df["Volume"].shift(1).rolling(20).mean()

    # 5 個交易日漲幅
    df["GAIN_5D"] = df["Close"].pct_change(5) * 100

    # 60 日低點支撐，不包含今天
    df["SUPPORT_60"] = df["Low"].shift(1).rolling(60).min()

    # 20 日成交量加權成本線，近似籌碼成本線
    df["COST_20D"] = (
        (df["Close"] * df["Volume"]).rolling(20).sum()
        / df["Volume"].rolling(20).sum()
    )

    # 股價相對 MA20 乖離率
    df["BIAS_MA20"] = (df["Close"] - df["MA20"]) / df["MA20"] * 100

    return df
