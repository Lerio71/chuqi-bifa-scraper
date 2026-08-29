"""
出奇体育必发交易指数快照采集 — 主入口（动态窗口版）

核心逻辑：以【每一场比赛自己的开赛时间】为基准，动态计算采集时点。
14 场开赛时间各不相同（凌晨 00:30 ~ 03:30），因此不采用全局固定时点，
而是每次运行时针对每场独立判断"距开赛还剩多久"，落入哪个窗口就采哪个标签。

使用方式:
  python run.py                        # 动态窗口：自动识别当期14场，按每场开赛时间采集
  python run.py --label pre_6h         # 强制统一标签（兼容旧用法/手动指定）
  python run.py --eventids 13210524,13210525  # 指定比赛 ID
  python run.py --expect 26112         # 显式指定期号（留空则自动识别当期）
  python run.py --all                  # 采集当日全部比赛而非足彩14场
  python run.py --report               # 生成每日汇总报告

动态窗口（每场独立）:
  距开赛 >24h     → 不采（盘口未定）
  12~24h          → pre_24h
  6~12h           → pre_12h
  3~6h            → pre_6h
  1~3h            → pre_3h
  30min~1h        → pre_1h
  15~30min        → pre_30min
  0~15min         → pre_15min
  已开赛~2.5h内   → inplay
  已结束          → 不采

GitHub Actions 调用示例（云端每15分钟触发一次，脚本内部按每场时间自动分流）:
  python run.py
"""

import argparse
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper.match_list import get_today_matches
from scraper.bifa_scraper import scrape_multiple
from scraper.storage import save_snapshot, generate_daily_report, DATA_DIR, TZ


def decide_label(kickoff_str: str, now: datetime):
    """
    根据开赛时间与当前时间差，决定本场本次采集的标签。
    Returns:
        str 标签；None 表示本次不采（未到窗口或已结束）
    """
    if not kickoff_str:
        return "default"
    try:
        ko = datetime.strptime(kickoff_str, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except Exception:
        return "default"
    delta = (ko - now).total_seconds()

    if delta > 24 * 3600:
        return None
    if delta > 12 * 3600:
        return "pre_24h"
    if delta > 6 * 3600:
        return "pre_12h"
    if delta > 3 * 3600:
        return "pre_6h"
    if delta > 3600:
        return "pre_3h"
    if delta > 1800:
        return "pre_1h"
    if delta > 900:
        return "pre_30min"
    if delta > 0:
        return "pre_15min"
    # 已开赛：开赛后 2.5h 内视为比赛中
    if delta > -2.5 * 3600:
        return "inplay"
    return None


def main():
    parser = argparse.ArgumentParser(description="出奇体育必发交易指数快照采集（动态窗口版）")
    parser.add_argument("--label", default="", help="强制标签: pre_24h/pre_12h/pre_6h/pre_3h/pre_1h/pre_30min/pre_15min/inplay/post（留空则按每场开赛时间动态判断）")
    parser.add_argument("--eventids", default="", help="指定比赛 ID（逗号分隔），为空则自动获取当期14场")
    parser.add_argument("--expect", default=None, help="足彩期号（如 26112），留空自动识别当期")
    parser.add_argument("--all", action="store_true", help="采集当日全部比赛而非足彩14场")
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

    # ---- 获取比赛列表 ----
    if args.eventids:
        eventids = [e.strip() for e in args.eventids.split(",") if e.strip()]
        matches = [{"eventid": e, "home": "", "away": "", "time": ""} for e in eventids]
        print(f"使用指定比赛 ID: {eventids}")
    else:
        mode = "当日全部" if args.all else "当期足彩14场"
        print(f"正在获取{mode}比赛列表 (expect={args.expect or '自动'})...")
        matches = get_today_matches(expect=args.expect, lottery_only=not args.all)
        print(f"找到 {len(matches)} 场 {mode}（采集时会按每场开赛时间动态分流）")

        # 保存比赛列表（含开赛时间）
        date_str = datetime.now(TZ).strftime("%Y-%m-%d")
        list_path = os.path.join(DATA_DIR, date_str, "match_list.json")
        os.makedirs(os.path.dirname(list_path), exist_ok=True)
        with open(list_path, "w", encoding="utf-8") as f:
            json.dump({
                "date": date_str,
                "count": len(matches),
                "expect": args.expect,
                "matches": matches,
            }, f, ensure_ascii=False, indent=2)

    if not matches:
        print("无比赛数据可采集")
        return

    # ---- 动态窗口分流（核心）----
    now = datetime.now(TZ)
    tasks = []  # (eventid, label)
    skipped = 0
    for m in matches:
        eid = m.get("eventid", "")
        if not eid:
            continue
        if args.label:
            label = args.label
        else:
            label = decide_label(m.get("time", ""), now)
        if label is None:
            skipped += 1
            print(f"  [跳过] {m.get('home','')}vs{m.get('away','')} 开赛{m.get('time','')}（未到窗口或已结束）")
            continue
        tasks.append((eid, label))

    print(f"本次进入采集窗口: {len(tasks)} 场, 跳过: {skipped} 场")
    if not tasks:
        print("无场比赛进入采集窗口，本次结束")
        return

    # ---- 爬取必发数据 ----
    eventids = [t[0] for t in tasks]
    label_map = {t[0]: t[1] for t in tasks}
    # 打印每场的标签分布
    from collections import Counter
    dist = Counter(label_map.values())
    print("标签分布:", dict(dist))

    print(f"开始采集必发快照...")
    snapshots = scrape_multiple(eventids, delay=args.delay)

    if not snapshots:
        print("未采集到任何必发数据")
        return

    # ---- 保存（每场按自己的标签）----
    paths = []
    for snap in snapshots:
        eid = snap.get("eventid", "")
        label = label_map.get(eid, "default")
        p = save_snapshot(snap, label)
        paths.append(p)

    print(f"\n采集完成: {len(paths)} 场快照已保存")
    for p in paths:
        print(f"  -> {p}")


if __name__ == "__main__":
    main()
