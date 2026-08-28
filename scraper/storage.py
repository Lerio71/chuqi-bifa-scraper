"""
数据存储模块。
按日期组织快照数据，每次采集保存为带时间戳的 JSON 文件。
"""

import os
import json
from datetime import datetime, timezone, timedelta


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# 北京时间
TZ = timezone(timedelta(hours=8))


def save_snapshot(snapshot: dict, label: str = "") -> str:
    """
    保存单场比赛的必发快照。

    目录结构:
      data/
        2026-08-28/
          13210524/
            20260828_143000__pre_24h.json
            20260828_200000__pre_6h.json
            20260828_233000__pre_30min.json

    Args:
        snapshot: 爬取的快照数据
        label: 时间段标签，如 "pre_24h", "pre_6h", "pre_1h", "pre_30min", "inplay", "post"

    Returns:
        保存的文件路径
    """
    now = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y%m%d_%H%M%S")

    eventid = snapshot.get("eventid", "unknown")
    dir_path = os.path.join(DATA_DIR, date_str, eventid)
    os.makedirs(dir_path, exist_ok=True)

    filename = f"{time_str}__{label}.json" if label else f"{time_str}.json"
    filepath = os.path.join(dir_path, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    return filepath


def save_batch(snapshots: list[dict], label: str = "") -> list[str]:
    """批量保存快照"""
    paths = []
    for snap in snapshots:
        path = save_snapshot(snap, label)
        paths.append(path)
    return paths


def get_latest_snapshots(date_str: str = None) -> dict:
    """
    获取某日所有比赛的最新快照（用于汇总）。

    Returns:
        { eventid: { "match": {...}, "snapshots": [filepath1, filepath2, ...] } }
    """
    if date_str is None:
        date_str = datetime.now(TZ).strftime("%Y-%m-%d")

    date_dir = os.path.join(DATA_DIR, date_str)
    if not os.path.exists(date_dir):
        return {}

    result = {}
    for eventid in os.listdir(date_dir):
        event_dir = os.path.join(date_dir, eventid)
        if not os.path.isdir(event_dir):
            continue

        files = sorted([f for f in os.listdir(event_dir) if f.endswith(".json")])
        if not files:
            continue

        # 读取最新文件
        latest_path = os.path.join(event_dir, files[-1])
        with open(latest_path, "r", encoding="utf-8") as f:
            latest_data = json.load(f)

        result[eventid] = {
            "latest_snapshot": latest_data,
            "snapshot_count": len(files),
            "files": files,
        }

    return result


def generate_daily_report(date_str: str = None) -> str:
    """
    生成每日汇总报告 JSON，包含所有比赛的所有时间点快照。
    方便后续分析不同时间段的指数变化。
    """
    if date_str is None:
        date_str = datetime.now(TZ).strftime("%Y-%m-%d")

    date_dir = os.path.join(DATA_DIR, date_str)
    if not os.path.exists(date_dir):
        return ""

    report = {
        "date": date_str,
        "generated_at": datetime.now(TZ).isoformat(),
        "matches": {},
    }

    for eventid in os.listdir(date_dir):
        event_dir = os.path.join(date_dir, eventid)
        if not os.path.isdir(event_dir):
            continue

        snapshots = []
        for fname in sorted(os.listdir(event_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(event_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                snapshots.append(json.load(f))

        if snapshots:
            first = snapshots[0]
            report["matches"][eventid] = {
                "eventid": eventid,
                "league": first.get("league", ""),
                "home": first.get("home", ""),
                "away": first.get("away", ""),
                "snapshot_count": len(snapshots),
                "snapshots": snapshots,
            }

    report_path = os.path.join(date_dir, f"daily_report_{date_str}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report_path


if __name__ == "__main__":
    # 测试
    test_snap = {
        "eventid": "test123",
        "snapshot_time": datetime.now(TZ).isoformat(),
        "summary": [
            {"side": "主", "price": 2.0, "volume": 1000000, "ratio": 80, "pnl": -100000, "pnl_index": -50, "hot_cold_index": 0.1},
        ],
        "large_trades": {"主": [], "和": [], "客": []},
    }
    path = save_snapshot(test_snap, "pre_24h")
    print(f"保存到: {path}")
    print(f"数据目录: {DATA_DIR}")
