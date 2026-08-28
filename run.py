"""
出奇体育必发交易指数快照采集 — 主入口

使用方式:
  python run.py                          # 采集今日所有比赛的当前快照
  python run.py --label pre_24h          # 带标签采集（标注时间段）
  python run.py --eventids 13210524,13210525  # 指定比赛 ID
  python run.py --report                 # 生成今日汇总报告

GitHub Actions 调用示例:
  python run.py --label pre_24h
  python run.py --label pre_6h
  python run.py --label pre_1h
  python run.py --label pre_30min
  python run.py --label inplay
  python run.py --report
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper.match_list import get_today_matches
from scraper.bifa_scraper import scrape_multiple
from scraper.storage import save_batch, generate_daily_report


def main():
    parser = argparse.ArgumentParser(description="出奇体育必发交易指数快照采集")
    parser.add_argument("--label", default="", help="时间段标签: pre_24h, pre_6h, pre_1h, pre_30min, inplay")
    parser.add_argument("--eventids", default="", help="指定比赛 ID（逗号分隔），为空则自动获取今日列表")
    parser.add_argument("--report", action="store_true", help="生成每日汇总报告")
    parser.add_argument("--delay", type=float, default=2.0, help="每次请求间隔秒数")
    args = parser.parse_args()

    if args.report:
        path = generate_daily_report()
        if path:
            print(f"每日报告已生成: {path}")
        else:
            print("无数据可生成报告")
        return

    # 获取比赛列表
    if args.eventids:
        eventids = [e.strip() for e in args.eventids.split(",") if e.strip()]
        print(f"使用指定比赛 ID: {eventids}")
    else:
        print("正在获取今日比赛列表...")
        matches = get_today_matches()
        eventids = [m["eventid"] for m in matches]
        print(f"找到 {len(matches)} 场今日比赛（采集时会跳过无必发数据的场次）")

        # 保存比赛列表
        from scraper.storage import DATA_DIR, TZ
        import json as _json
        from datetime import datetime
        import os as _os
        date_str = datetime.now(TZ).strftime("%Y-%m-%d")
        list_path = _os.path.join(DATA_DIR, date_str, "match_list.json")
        _os.makedirs(_os.path.dirname(list_path), exist_ok=True)
        with open(list_path, "w", encoding="utf-8") as f:
            _json.dump({
                "date": date_str,
                "count": len(matches),
                "matches": matches,
            }, f, ensure_ascii=False, indent=2)

    if not eventids:
        print("无比赛数据可采集")
        return

    # 爬取必发数据
    print(f"开始采集必发快照 (label={args.label or 'default'})...")
    snapshots = scrape_multiple(eventids, delay=args.delay)

    if not snapshots:
        print("未采集到任何必发数据")
        return

    # 保存快照
    paths = save_batch(snapshots, args.label)
    print(f"\n采集完成: {len(paths)} 场比赛快照已保存")
    for p in paths:
        print(f"  -> {p}")


if __name__ == "__main__":
    main()
