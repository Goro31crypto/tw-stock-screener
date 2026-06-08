from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests


POSITIVE_KEYWORDS = [
    "營收創高", "創高", "成長", "轉盈", "獲利", "接單", "訂單",
    "漲價", "擴產", "需求強", "法說樂觀", "目標價調升",
    "買進", "升評", "AI", "伺服器", "輝達", "NVIDIA",
    "CoWoS", "先進製程", "電力", "重電"
]

NEGATIVE_KEYWORDS = [
    "下修", "砍單", "衰退", "虧損", "轉虧", "法說保守",
    "庫存調整", "毛利率下滑", "目標價調降", "降評",
    "賣出", "遭罰", "訴訟", "減產", "匯損", "裁員",
    "需求疲弱", "跌破"
]

TOPIC_KEYWORDS = {
    "AI": ["AI", "人工智慧", "輝達", "NVIDIA", "GB300", "伺服器"],
    "半導體": ["半導體", "晶圓", "先進製程", "CoWoS", "封裝"],
    "散熱": ["散熱", "水冷", "液冷", "均熱片", "熱導管"],
    "PCB": ["PCB", "CCL", "銅箔基板", "載板"],
    "記憶體": ["DRAM", "記憶體", "NAND"],
    "電力": ["電力", "重電", "電網", "變壓器", "電纜"],
    "車用": ["車用", "電動車", "EV"],
    "手機": ["手機", "SoC", "安卓", "Android"],
}


def fetch_google_news(stock_id: str, stock_name: str, days: int = 7, max_items: int = 5) -> list:
    """
    使用 Google News RSS 搜尋近期新聞。
    這裡只做新聞輔助，不做評分。
    """

    query = f"{stock_name} {stock_id} 台股 股票"
    encoded_query = quote(query)

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception:
        return []

    try:
        root = ET.fromstring(response.content)
    except Exception:
        return []

    items = root.findall(".//item")
    news_list = []

    cutoff_date = datetime.now() - timedelta(days=days)

    for item in items:
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        pub_date_text = item.findtext("pubDate", default="")
        source_el = item.find("source")
        source = source_el.text if source_el is not None else ""

        published_at = None

        if pub_date_text:
            try:
                published_at = parsedate_to_datetime(pub_date_text)
                if published_at.tzinfo is not None:
                    published_at = published_at.replace(tzinfo=None)
            except Exception:
                published_at = None

        if published_at and published_at < cutoff_date:
            continue

        if title:
            news_list.append({
                "title": title,
                "link": link,
                "source": source,
                "published_at": published_at.strftime("%Y-%m-%d") if published_at else ""
            })

        if len(news_list) >= max_items:
            break

    return news_list


def analyze_news(stock_id: str, stock_name: str, days: int = 7, max_items: int = 5) -> dict:
    """
    新聞事件標註模組。
    注意：
    - 不加分
    - 不扣分
    - 不改變總分
    - 只輸出新聞傾向、題材、摘要、風險提示
    """

    news_list = fetch_google_news(
        stock_id=stock_id,
        stock_name=stock_name,
        days=days,
        max_items=max_items
    )

    if not news_list:
        return {
            "news_count": 0,
            "news_bias": "無新聞",
            "news_topics": "",
            "news_summary": "",
            "news_flags": "",
            "news_links": ""
        }

    positive_hits = []
    negative_hits = []
    topic_hits = set()

    titles = [news["title"] for news in news_list]
    all_text = " ".join(titles)

    for kw in POSITIVE_KEYWORDS:
        if kw.lower() in all_text.lower():
            positive_hits.append(kw)

    for kw in NEGATIVE_KEYWORDS:
        if kw.lower() in all_text.lower():
            negative_hits.append(kw)

    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in all_text.lower():
                topic_hits.add(topic)

    if positive_hits and negative_hits:
        news_bias = "混合"
    elif positive_hits:
        news_bias = "偏利多"
    elif negative_hits:
        news_bias = "偏利空"
    else:
        news_bias = "中性"

    summary_parts = []

    for news in news_list[:3]:
        date = news.get("published_at", "")
        source = news.get("source", "")
        title = news.get("title", "")

        if date or source:
            summary_parts.append(f"{date} {source}｜{title}")
        else:
            summary_parts.append(title)

    risk_flags = []

    if negative_hits:
        risk_flags.append("偵測到利空關鍵字：" + "、".join(negative_hits[:5]))

    if positive_hits and negative_hits:
        risk_flags.append("利多利空混雜，需人工確認消息方向")

    links = []
    for news in news_list[:3]:
        if news.get("link"):
            links.append(news["link"])

    return {
        "news_count": len(news_list),
        "news_bias": news_bias,
        "news_topics": "、".join(sorted(topic_hits)),
        "news_summary": "；".join(summary_parts),
        "news_flags": "；".join(risk_flags),
        "news_links": "；".join(links)
    }
