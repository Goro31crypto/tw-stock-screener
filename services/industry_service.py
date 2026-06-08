from pathlib import Path
import pandas as pd
import requests


CACHE_PATH = Path("data/industry_cache.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


TWSE_URLS = [
    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
]

TPEX_URLS = [
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_company",
]


INDUSTRY_CODE_MAP = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險業",
    "18": "貿易百貨",
    "20": "其他業",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技業",
    "34": "電子商務業",
    "35": "綠能環保業",
    "36": "數位雲端業",
    "37": "運動休閒業",
    "38": "居家生活業",
}


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_industry(value: str) -> str:
    value = _clean(value)

    if not value:
        return "待確認"

    if value.isdigit():
        key = value.zfill(2)
        return INDUSTRY_CODE_MAP.get(key, value)

    return value


def _fetch_json(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        data = res.json()
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _pick_col(df: pd.DataFrame, keywords: list[str]):
    for col in df.columns:
        col_text = str(col)
        if all(k in col_text for k in keywords):
            return col
    return None


def _normalize_company_table(data, market: str) -> pd.DataFrame:
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    if df.empty:
        return pd.DataFrame()

    code_col = (
        _pick_col(df, ["公司", "代號"])
        or _pick_col(df, ["股票", "代號"])
        or _pick_col(df, ["代號"])
        or _pick_col(df, ["Code"])
    )

    name_col = (
        _pick_col(df, ["公司", "簡稱"])
        or _pick_col(df, ["公司", "名稱"])
        or _pick_col(df, ["股票", "名稱"])
        or _pick_col(df, ["名稱"])
        or _pick_col(df, ["Name"])
    )

    industry_col = (
        _pick_col(df, ["產業", "別"])
        or _pick_col(df, ["產業"])
        or _pick_col(df, ["Industry"])
    )

    if not code_col or not industry_col:
        return pd.DataFrame()

    rows = []

    for _, row in df.iterrows():
        code = _clean(row.get(code_col, ""))
        code = "".join(ch for ch in code if ch.isdigit())

        if len(code) != 4:
            continue

        name = _clean(row.get(name_col, "")) if name_col else ""
        industry = _normalize_industry(row.get(industry_col, ""))

        suffix = ".TW" if market == "上市" else ".TWO"

        rows.append({
            "股票代號": code,
            "股票名稱": name,
            "市場": market,
            "產業分類": industry,
            "symbol": f"{code}{suffix}",
        })

    return pd.DataFrame(rows)


def build_industry_cache(force: bool = False) -> pd.DataFrame:
    if CACHE_PATH.exists() and not force:
        try:
            cached = pd.read_csv(CACHE_PATH, dtype=str).fillna("")
            if not cached.empty:
                if "產業分類" in cached.columns:
                    cached["產業分類"] = cached["產業分類"].apply(_normalize_industry)
                return cached
        except Exception:
            pass

    frames = []

    for url in TWSE_URLS:
        data = _fetch_json(url)
        df = _normalize_company_table(data, market="上市")
        if not df.empty:
            frames.append(df)
            break

    for url in TPEX_URLS:
        data = _fetch_json(url)
        df = _normalize_company_table(data, market="上櫃")
        if not df.empty:
            frames.append(df)
            break

    if not frames:
        return pd.DataFrame(columns=["股票代號", "股票名稱", "市場", "產業分類", "symbol"])

    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset=["股票代號"], keep="first")

    if "產業分類" in result.columns:
        result["產業分類"] = result["產業分類"].apply(_normalize_industry)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(CACHE_PATH, index=False, encoding="utf-8-sig")

    return result


def get_stock_industry(stock_code: str = "", stock_name: str = "") -> dict:
    stock_code = _clean(stock_code)
    stock_code = "".join(ch for ch in stock_code if ch.isdigit())
    stock_name = _clean(stock_name)

    df = build_industry_cache(force=False)

    if df.empty:
        return {
            "股票代號": stock_code,
            "股票名稱": stock_name,
            "市場": "",
            "產業分類": "待確認",
            "symbol": "",
        }

    matched = pd.DataFrame()

    if stock_code:
        matched = df[df["股票代號"].astype(str) == stock_code]

    if matched.empty and stock_name:
        matched = df[df["股票名稱"].astype(str).str.contains(stock_name, na=False)]

    if matched.empty:
        return {
            "股票代號": stock_code,
            "股票名稱": stock_name,
            "市場": "",
            "產業分類": "待確認",
            "symbol": f"{stock_code}.TW" if stock_code else "",
        }

    row = matched.iloc[0]

    return {
        "股票代號": _clean(row.get("股票代號", stock_code)),
        "股票名稱": stock_name or _clean(row.get("股票名稱", "")),
        "市場": _clean(row.get("市場", "")),
        "產業分類": _normalize_industry(row.get("產業分類", "待確認")),
        "symbol": _clean(row.get("symbol", "")),
    }


if __name__ == "__main__":
    df = build_industry_cache(force=True)
    print("產業資料筆數：", len(df))
    print(df.head(20).to_string(index=False))
