import requests
import pandas as pd
from datetime import datetime, timedelta


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


def twse_date(date):
    return date.strftime("%Y%m%d")


def tpex_roc_date(date):
    return f"{date.year - 1911}/{date.month:02d}/{date.day:02d}"


def clean_number(x):
    if x is None:
        return 0
    return str(x).replace(",", "").strip()


def request_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    print("URL:", r.url)
    print("HTTP:", r.status_code)
    r.raise_for_status()
    return r.json()


def df_from_twse_payload(payload):
    fields = payload.get("fields", [])
    rows = payload.get("data", [])

    if not fields or not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows, columns=fields)


def df_from_tpex_payload(payload):
    if "tables" in payload and payload["tables"]:
        table = payload["tables"][0]
        fields = table.get("fields", [])
        rows = table.get("data", [])

        if fields:
            return pd.DataFrame(rows, columns=fields)

    if "data" in payload:
        return pd.DataFrame(payload["data"])

    return pd.DataFrame()


def find_recent_data(name, fetch_func, lookback_days=10):
    print("\n" + "=" * 60)
    print(name)
    print("=" * 60)

    today = datetime.today()

    for i in range(0, lookback_days):
        date = today - timedelta(days=i)

        try:
            print(f"\n嘗試日期：{date.strftime('%Y-%m-%d')}")
            df = fetch_func(date)

            print("shape:", df.shape)

            if not df.empty:
                print("找到資料日期：", date.strftime("%Y-%m-%d"))
                print(df.head())
                return date, df

        except Exception as e:
            print("失敗：", repr(e))

    print("最近幾天都沒有抓到資料")
    return None, pd.DataFrame()


def fetch_twse_institutional(date):
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    params = {
        "date": twse_date(date),
        "selectType": "ALLBUT0999",
        "response": "json",
    }

    payload = request_json(url, params=params)
    return df_from_twse_payload(payload)


def fetch_twse_margin(date):
    url = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
    params = {
        "date": twse_date(date),
        "selectType": "ALL",
        "response": "json",
    }

    payload = request_json(url, params=params)
    return df_from_twse_payload(payload)


def fetch_tpex_institutional_new(date):
    url = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
    params = {
        "date": tpex_roc_date(date),
        "type": "Daily",
        "response": "json",
    }

    payload = request_json(url, params=params)
    return df_from_tpex_payload(payload)


def fetch_tpex_institutional_old(date):
    url = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
    params = {
        "l": "zh-tw",
        "o": "json",
        "se": "EW",
        "t": "D",
        "d": tpex_roc_date(date),
    }

    payload = request_json(url, params=params)
    return df_from_tpex_payload(payload)


def fetch_tpex_margin_old(date):
    url = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"
    params = {
        "l": "zh-tw",
        "o": "json",
        "se": "EW",
        "d": tpex_roc_date(date),
    }

    payload = request_json(url, params=params)
    return df_from_tpex_payload(payload)


def fetch_tpex_institutional(date):
    df = fetch_tpex_institutional_new(date)

    if not df.empty:
        return df

    return fetch_tpex_institutional_old(date)


if __name__ == "__main__":
    print("=" * 60)
    print("測試 TWSE / TPEx 官方籌碼資料 V2")
    print("會自動往前找最近有資料的交易日")
    print("=" * 60)

    find_recent_data("TWSE 上市三大法人", fetch_twse_institutional)
    find_recent_data("TWSE 上市融資融券", fetch_twse_margin)
    find_recent_data("TPEx 上櫃三大法人", fetch_tpex_institutional)
    find_recent_data("TPEx 上櫃融資融券", fetch_tpex_margin_old)
