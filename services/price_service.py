import yfinance as yf
import pandas as pd


def fetch_price_data(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """
    抓取單一股票的歷史股價資料。
    symbol 範例：2330.TW
    period 範例：3mo, 6mo, 1y
    """

    df = yf.download(symbol, period=period, auto_adjust=False, progress=False)

    if df.empty:
        return pd.DataFrame()

    # yfinance 有時候欄位會是 MultiIndex，先攤平
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.sort_index()

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    df = df[required_cols].dropna()

    return df
