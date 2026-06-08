import argparse
import subprocess
import sys


def run_watchlist_mode():
    print("\n========== 模式一：自選股指標 ==========")
    subprocess.run([sys.executable, "main.py"], check=True)


def run_market_mode():
    print("\n========== 模式二：全市場異動指標 ==========")
    subprocess.run([sys.executable, "build_market_candidates.py"], check=True)


def main():
    parser = argparse.ArgumentParser(description="台股儀表板資料更新器")
    parser.add_argument(
        "--mode",
        choices=["watchlist", "market", "all"],
        default="all",
        help="watchlist=自選股指標, market=全市場異動指標, all=兩個都跑",
    )

    args = parser.parse_args()

    if args.mode in ["watchlist", "all"]:
        run_watchlist_mode()

    if args.mode in ["market", "all"]:
        run_market_mode()

    print("\n資料更新完成。")


if __name__ == "__main__":
    main()
