import requests
import pandas as pd


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


def request_json(url):
    print("\nURL:", url)
    r = requests.get(url, headers=HEADERS, timeout=20)
    print("HTTP:", r.status_code)
    print("Content-Type:", r.headers.get("content-type"))
    r.raise_for_status()
    return r.json()


def show_df(name, data):
    print("\n" + "=" * 60)
    print(name)
    print("=" * 60)

    if isinstance(data, list):
        df = pd.DataFrame(data)
    elif isinstance(data, dict):
        if "data" in data:
            df = pd.DataFrame(data.get("data", []))
        else:
            df = pd.DataFrame([data])
    else:
        df = pd.DataFrame()

    print("shape:", df.shape)
    print("columns:", list(df.columns))
    print(df.head())

    return df


def main():
    candidates = {
        "TWSE OpenAPI 融資融券 MI_MARGN": "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
        "TWSE OpenAPI 法人 T86 測試1": "https://openapi.twse.com.tw/v1/fund/T86",
        "TWSE OpenAPI 法人 TWT86U 測試2": "https://openapi.twse.com.tw/v1/exchangeReport/TWT86U",
    }

    for name, url in candidates.items():
        try:
            data = request_json(url)
            show_df(name, data)
        except Exception as e:
            print(name, "失敗：", repr(e))


if __name__ == "__main__":
    main()
