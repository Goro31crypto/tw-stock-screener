import os
from datetime import datetime
import pandas as pd

RUN_LOG_PATH = "data/history/run_log.csv"


def append_run_log(
    expected_count: int,
    success_count: int,
    min_success_count: int,
    did_output: bool,
    output_path: str = "",
    results: list | None = None,
    message: str = "",
):
    os.makedirs("data/history", exist_ok=True)

    results = results or []
    df = pd.DataFrame(results)

    chip_success_count = 0
    chip_limit_count = 0
    margin_success_count = 0
    margin_limit_count = 0

    if not df.empty:
        if "法人資料狀態" in df.columns:
            chip_success_count = int((df["法人資料狀態"] == "success").sum())
            chip_limit_count = int((df["法人資料狀態"] == "finmind_limit").sum())

        if "融資融券資料狀態" in df.columns:
            margin_success_count = int((df["融資融券資料狀態"] == "success").sum())
            margin_limit_count = int((df["融資融券資料狀態"] == "finmind_limit").sum())

    row = {
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expected_count": expected_count,
        "success_count": success_count,
        "min_success_count": min_success_count,
        "did_output": did_output,
        "output_path": output_path,
        "chip_success_count": chip_success_count,
        "chip_limit_count": chip_limit_count,
        "margin_success_count": margin_success_count,
        "margin_limit_count": margin_limit_count,
        "message": message,
    }

    if os.path.exists(RUN_LOG_PATH):
        old_df = pd.read_csv(RUN_LOG_PATH)
        new_df = pd.concat([old_df, pd.DataFrame([row])], ignore_index=True)
    else:
        new_df = pd.DataFrame([row])

    new_df.to_csv(RUN_LOG_PATH, index=False, encoding="utf-8-sig")

    print(f"執行紀錄已更新：{RUN_LOG_PATH}")
