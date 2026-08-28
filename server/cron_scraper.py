"""
云服务器高频采集脚本 — 通过 crontab 定时运行。
用于在比赛进行中（inplay）和临场阶段进行高频快照采集。

部署方式:
  1. 将项目上传到云服务器（国内/香港均可，出奇体育在大陆可直连）
  2. 安装依赖: pip install -r requirements.txt
  3. 配置 crontab:

     # 每分钟采集进行中比赛的必发快照（比赛时间段）
     * * * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label inplay >> /var/log/bifa_scraper.log 2>&1

     # 赛前每5分钟采集一次
     */5 * * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_5min >> /var/log/bifa_scraper.log 2>&1

     # 每日赛后生成报告
     0 6 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --report >> /var/log/bifa_scraper.log 2>&1

  4. 通过 git push 将数据同步到 GitHub 仓库（可选）

数据同步到 GitHub（可选）:
  配置一个 deploy key 或使用 Personal Access Token，
  然后 crontab 中增加:
     */10 * * * * cd /opt/chuqi-bifa-scraper && git add data/ && git commit -m "auto: bifa snapshot $(date +%%Y-%%m-%%d_%%H:%%M)" && git push origin main
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.match_list import get_today_matches
from scraper.bifa_scraper import scrape_multiple
from scraper.storage import save_batch, generate_daily_report


def run(label: str = "inplay", eventids: list[str] = None, delay: float = 1.5):
    """单次采集执行"""
    print(f"[{label}] 开始采集...")

    if not eventids:
        matches = get_today_matches()
        eventids = [m["eventid"] for m in matches]
        print(f"  获取到 {len(eventids)} 场比赛")

    if not eventids:
        print("  无比赛可采集")
        return

    snapshots = scrape_multiple(eventids, delay=delay)
    if snapshots:
        paths = save_batch(snapshots, label)
        print(f"  保存 {len(paths)} 个快照")
    else:
        print("  未采集到数据")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="inplay")
    parser.add_argument("--eventids", default="")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    eids = [e.strip() for e in args.eventids.split(",") if e.strip()] if args.eventids else None
    run(args.label, eids, args.delay)
