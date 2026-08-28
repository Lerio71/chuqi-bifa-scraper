"""
出奇体育必发交易指数爬虫核心模块。
出奇体育的必发数据为服务端渲染 HTML，直接请求页面并解析即可。

必发页面 URL 模式: https://live.chuqi.com/football/live-bifa/{eventid}/

数据结构:
  交易汇总: 项(主/和/客) | 价 | 交易量 | 比例 | 盈亏 | 盈亏指数 | 冷热指数
  大额明细: 价 | 交易量 | 比例 | 时间
"""

import re
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup


BASE_URL = "https://live.chuqi.com/football/live-bifa/{eventid}/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://live.chuqi.com/football/",
    "Connection": "keep-alive",
}


def scrape_bifa(eventid: str) -> dict | None:
    """
    爬取单场比赛的必发交易指数数据。

    Args:
        eventid: 出奇体育比赛 ID

    Returns:
        {
            "eventid": "13210524",
            "url": "https://live.chuqi.com/football/live-bifa/13210524/",
            "snapshot_time": "2026-08-28T14:30:00+08:00",
            "summary": [   # 交易汇总
                {"side": "主", "price": 2.18, "volume": 5442200, "ratio": 81, "pnl": -5038287, "pnl_index": -93, "hot_cold_index": 0.09},
                {"side": "和", "price": 3.45, "volume": 488600, "ratio": 7, "pnl": 4052993, "pnl_index": 75, "hot_cold_index": 0.83},
                {"side": "客", "price": 3.95, "volume": 766500, "ratio": 11, "pnl": 3127850, "pnl_index": 61, "hot_cold_index": 5.89},
            ],
            "large_trades": {  # 大额明细（按方向）
                "主": [{"price": 2.48, "volume": 1131079, "ratio": 82.23, "time": "05-24 01:51"}, ...],
                "和": [...],
                "客": [...],
            },
        }
    """
    url = BASE_URL.format(eventid=eventid)
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(url, timeout=20)
    resp.encoding = "utf-8"

    if resp.status_code != 200:
        return None

    html = resp.text
    soup = BeautifulSoup(html, "lxml")

    # 检查页面是否有必发数据
    if "交易汇总" not in html and "bifa-info" not in html:
        return None

    tz = timezone(timedelta(hours=8))
    snapshot = {
        "eventid": eventid,
        "url": url,
        "snapshot_time": datetime.now(tz).isoformat(),
        "summary": _parse_summary(soup),
        "large_trades": _parse_large_trades(soup),
    }

    return snapshot


def _parse_summary(soup: BeautifulSoup) -> list[dict]:
    """解析交易汇总表格"""
    results = []

    # 查找交易汇总区域
    bifa_info = soup.find(class_="bifa-info")
    if not bifa_info:
        # 尝试更宽泛的查找
        bifa_info = soup.find("section", class_=re.compile("bifa"))

    if not bifa_info:
        return results

    tables = bifa_info.find_all("table")
    if not tables:
        return results

    table = tables[0]
    rows = table.find_all("tr")

    # 跳过表头，解析数据行
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        side = cells[0].get_text(strip=True)
        price = _parse_float(cells[1])
        volume = _parse_int(cells[2])
        ratio = _parse_float(cells[3])
        pnl = _parse_int(cells[4])
        pnl_index = _parse_int(cells[5])
        hot_cold = _parse_float(cells[6])

        if side:
            results.append({
                "side": side,
                "price": price,
                "volume": volume,
                "ratio": ratio,
                "pnl": pnl,
                "pnl_index": pnl_index,
                "hot_cold_index": hot_cold,
            })

    return results


def _parse_large_trades(soup: BeautifulSoup) -> dict:
    """解析大额明细表格"""
    results = {"主": [], "和": [], "客": []}

    # 大额明细在 .bifa-large-detail 区域
    large_detail = soup.find(class_="bifa-large-detail")
    if not large_detail:
        return results

    # 每个方向一个 table，通过 data-labelledby 区分: 0=主胜, 2=平局, 1=客胜
    tables = large_detail.find_all("div", class_="table")

    side_map = {"0": "主", "2": "和", "1": "客"}

    for table_div in tables:
        labeledby = table_div.get("data-labelledby", "")
        side = side_map.get(labeledby, "")
        if not side:
            continue

        tbl = table_div.find("table")
        if not tbl:
            continue

        rows = tbl.find_all("tr")[1:]  # 跳过表头
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            entry = {
                "price": _parse_float(cells[0]),
                "volume": _parse_int(cells[1]),
                "ratio": _parse_float(cells[2]),
                "time": cells[3].get_text(strip=True),
            }
            results[side].append(entry)

    return results


def _parse_float(cell) -> float | None:
    """从表格单元格解析浮点数"""
    text = cell.get_text(strip=True)
    text = text.replace("%", "").replace(",", "").replace("，", "")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_int(cell) -> int | None:
    """从表格单元格解析整数"""
    text = cell.get_text(strip=True)
    text = text.replace(",", "").replace("，", "").replace("%", "")
    try:
        return int(text)
    except (ValueError, TypeError):
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None


def scrape_multiple(eventids: list[str], delay: float = 2.0) -> list[dict]:
    """
    批量爬取多场比赛的必发数据。

    Args:
        eventids: 比赛 ID 列表
        delay: 每次请求间隔（秒），避免请求过快被封

    Returns:
        成功爬取的快照列表
    """
    snapshots = []
    for eid in eventids:
        result = scrape_bifa(eid)
        if result and result["summary"]:
            snapshots.append(result)
            print(f"  [OK] {eid}: {len(result['summary'])} 条汇总数据")
        else:
            print(f"  [SKIP] {eid}: 无必发数据或页面不可用")
        time.sleep(delay)

    return snapshots


if __name__ == "__main__":
    # 测试单场
    result = scrape_bifa("13210524")
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("未获取到数据")
