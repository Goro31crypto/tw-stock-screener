import os
import pandas as pd


def append_score_history(results: list):
    """
    將每日分析結果追加到歷史分數紀錄。
    如果同一天同一檔股票已存在，會先刪掉舊資料再寫入新資料，避免重複。
    """

    if not results:
        print("沒有結果可寫入歷史紀錄")
        return

    os.makedirs("data/history", exist_ok=True)

    history_path = "data/history/score_history.csv"

    df_new = pd.DataFrame(results)

    keep_cols = [
        "資料日期",
        "股票代號",
        "股票名稱",
        "產業分類",
        "分數",
        "訊號",
        "技術分",
        "法人籌碼分",
        "融資融券分",
        "收盤價",
        "近5日漲幅%",
    ]

    existing_cols = [col for col in keep_cols if col in df_new.columns]
    df_new = df_new[existing_cols].copy()

    if os.path.exists(history_path):
        df_old = pd.read_csv(history_path, dtype={"股票代號": str})

        if not df_old.empty:
            df_old["股票代號"] = df_old["股票代號"].astype(str)
            df_new["股票代號"] = df_new["股票代號"].astype(str)

            # 避免同一天同一檔重複寫入
            merge_keys = df_new[["資料日期", "股票代號"]].drop_duplicates()

            df_old = df_old.merge(
                merge_keys,
                on=["資料日期", "股票代號"],
                how="left",
                indicator=True
            )

            df_old = df_old[df_old["_merge"] == "left_only"].drop(columns=["_merge"])

            df_history = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_history = df_new
    else:
        df_history = df_new

    df_history = df_history.sort_values(
        by=["股票代號", "資料日期"],
        ascending=[True, True]
    )

    df_history.to_csv(history_path, index=False, encoding="utf-8-sig")

    print(f"歷史分數已更新：{history_path}")
