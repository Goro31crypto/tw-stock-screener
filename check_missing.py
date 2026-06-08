import glob
import os
import pandas as pd

from stock_list import STOCK_META


files = glob.glob("data/output/stock_screener_v23_*.xlsx")

if not files:
    print("找不到 v23 報表，請先執行 python main.py")
    raise SystemExit

latest_file = max(files, key=os.path.getmtime)

df = pd.read_excel(latest_file, dtype={"股票代號": str})

got = set(
    df["股票代號"]
    .astype(str)
    .str.replace(".0", "", regex=False)
    .tolist()
)

missing = []

for symbol, meta in STOCK_META.items():
    stock_id = symbol.split(".")[0]

    if stock_id not in got:
        missing.append(
            {
                "完整代號": symbol,
                "股票代號": stock_id,
                "股票名稱": meta.get("name", ""),
                "產業分類": meta.get("category", ""),
            }
        )

print("讀取報表：", latest_file)
print("成功股票數：", len(got))
print("缺少股票數：", len(missing))
print("-" * 40)

for item in missing:
    print(
        item["完整代號"],
        item["股票名稱"],
        item["產業分類"]
    )
