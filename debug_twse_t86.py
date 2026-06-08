import requests
import pandas as pd
from datetime import datetime, timedelta


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


def twse_date(date):
    return date.strftime("%Y%m%d")


def fetch_t86(date):
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    params = {
        "date": twse_date(date),
        "selectType": "ALLBUT0999",
        "response": "json",
    }

    r = requests.get(url, params=params, headers=HEADERS, timeout=20)

    print("URL:", r.url)
    print("HTTP:", r.status_code)
    print("Content-Type:", r.headers.get("content-type"))

    r.raise_for_status()

    data = r.json()

    print("keys:", data.keys())
    print("stat:", data.get("stat"))
    print("title:", data.get("title"))
    print("fields:", data.get("fields"))
    print("data length:", len(data.get("data", [])))

    fields = data.get("fields", [])
    rows = data.get("data", [])

    if fields and rows:
        df = pd.DataFrame(rows, columns=fields)
    else:
        df = pd.DataFrame()

    return df


today = datetime.today()

for i in range(0, 15):
    date = today - timedelta(days=i)

    print("\n" + "=" * 60)
    print("嘗試日期：", date.strftime("%Y-%m-%d"))
    print("=" * 60)

    try:
        df = fetch_t86(date)
        print("shape:", df.shape)

        if not df.empty:
            print("找到資料日期：", date.strftime("%Y-%m-%d"))
            print(df.head())
            break

    except Exception as e:
        print("失敗：", repr(e))
