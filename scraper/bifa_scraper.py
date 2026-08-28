"""
出奇体育必发交易指数爬虫核心模块。

必发页面 URL: https://live.chuqi.com/football/live-bifa/{eventid}/

解析方式（按优先级，网页改版时自动降级）：
  1. 内嵌 JSON：页面以 `var __dataAiClientParam = [...]` 服务端渲染完整数据，
     allData 每项含 summary(交易汇总)/detail(大额明细)/echart(时间序列)，
     info 含联赛/对阵/开赛时间。最完整、最稳定。
  2. HTML 表格兜底：解析 .bifa-info 交易汇总表格 与 .bifa-large-detail 大额明细，
     比赛信息从 <title> 提取。仅当内嵌 JSON 缺失或格式变化时启用。

所有网络请求经 scraper.net 封装，带浏览器请求头、失败重试与反爬应对。
"""

import os
import sys
import re
import json
import time
import random
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup

# 兼容两种运行方式：run.py 以包方式导入 / 直接 python scraper/bifa_scraper.py
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.net import make_session, fetch, HOMEPAGE_URL


BASE_URL = "https://live.chuqi.com/football/live-bifa/{eventid}/"

TZ = timezone(timedelta(hours=8))


# ---------- 内嵌 JSON 解析（主方式） ----------

def _extract_page_data(html: str) -> dict | None:
    """从页面 HTML 提取 __dataAiClientParam 内嵌 JSON 的首个对象"""
    m = re.search(r"__dataAiClientParam = (\[.*?\]);", html, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None


def _to_number(text) -> float | int | None:
    """把 '89%' / '3,193,800' 之类的文本转为数值"""
    if text is None:
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return text
    s = str(text).replace("%", "").replace(",", "").replace("，", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _format_time(ts) -> str:
    """时间戳(ms) -> 'MM-DD HH:MM'（北京时间）"""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000, TZ).strftime("%m-%d %H:%M")
    except Exception:
        return str(ts)


def _parse_summary(all_data: list) -> list[dict]:
    """从 allData 解析交易汇总"""
    results = []
    for item in all_data or []:
        s = item.get("summary")
        if not isinstance(s, dict):
            continue
        results.append({
            "side": item.get("name", ""),
            "price": s.get("odds"),
            "volume": s.get("amount"),
            "ratio": _to_number(s.get("per")),
            "pnl": s.get("profit"),
            "pnl_index": s.get("payout"),
            "hot_cold_index": s.get("hot"),
        })
    return results


def _parse_large_trades(all_data: list) -> dict:
    """从 allData 解析大额明细（按方向）"""
    results = {"主": [], "和": [], "客": []}
    for item in all_data or []:
        side = item.get("name", "")
        if side not in results:
            continue
        detail = item.get("detail")
        if not isinstance(detail, list):
            continue
        for d in detail:
            if not isinstance(d, dict):
                continue
            results[side].append({
                "price": d.get("odds"),
                "volume": d.get("amount"),
                "ratio": _to_number(d.get("per")),
                "time": _format_time(d.get("time")),
            })
    return results


def _parse_trends(all_data: list) -> dict:
    """从 allData 解析交易量时间序列（附加字段，便于后续资金流分析）"""
    trends = {}
    for item in all_data or []:
        side = item.get("name", "")
        echart = item.get("echart")
        if not isinstance(echart, list):
            continue
        trends[side] = [
            {"volume": p.get("amount"), "time": _format_time(p.get("time"))}
            for p in echart if isinstance(p, dict)
        ]
    return trends


# ---------- HTML 表格解析（兜底方式） ----------

def _parse_float(cell) -> float | None:
    text = cell.get_text(strip=True)
    text = text.replace("%", "").replace(",", "").replace("，", "")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_int(cell) -> int | None:
    text = cell.get_text(strip=True)
    text = text.replace(",", "").replace("，", "").replace("%", "")
    try:
        return int(text)
    except (ValueError, TypeError):
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None


def _parse_summary_from_html(soup: BeautifulSoup) -> list[dict]:
    """解析 .bifa-info 交易汇总表格"""
    results = []
    bifa_info = soup.find(class_="bifa-info")
    if not bifa_info:
        bifa_info = soup.find("section", class_=re.compile("bifa"))
    if not bifa_info:
        return results

    table = bifa_info.find("table")
    if not table:
        return results

    rows = table.find_all("tr")
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        side = cells[0].get_text(strip=True)
        if not side:
            continue
        results.append({
            "side": side,
            "price": _parse_float(cells[1]),
            "volume": _parse_int(cells[2]),
            "ratio": _parse_float(cells[3]),
            "pnl": _parse_int(cells[4]),
            "pnl_index": _parse_int(cells[5]),
            "hot_cold_index": _parse_float(cells[6]),
        })
    return results


def _parse_large_trades_from_html(soup: BeautifulSoup) -> dict:
    """解析 .bifa-large-detail 大额明细表格"""
    results = {"主": [], "和": [], "客": []}
    large_detail = soup.find(class_="bifa-large-detail")
    if not large_detail:
        return results

    side_map = {"0": "主", "2": "和", "1": "客"}
    for table_div in large_detail.find_all("div", class_="table"):
        labeledby = table_div.get("data-labelledby", "")
        side = side_map.get(labeledby, "")
        if not side:
            continue
        tbl = table_div.find("table")
        if not tbl:
            continue
        for row in tbl.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            results[side].append({
                "price": _parse_float(cells[0]),
                "volume": _parse_int(cells[1]),
                "ratio": _parse_float(cells[2]),
                "time": cells[3].get_text(strip=True),
            })
    return results


def _extract_match_info_from_title(html: str) -> tuple[str, str, str]:
    """从 <title> 提取 (联赛, 主队, 客队)，如 '德甲 - 拜仁慕尼黑 VS 斯图加特 -出奇体育'"""
    league = home = away = ""
    m = re.search(r"<title>([^<]+)</title>", html)
    if not m:
        return league, home, away
    title = m.group(1).strip()
    parts = [p.strip() for p in title.replace("-出奇体育", "").split("-") if p.strip()]
    if not parts:
        return league, home, away
    # 第一段通常是联赛名
    league = parts[0]
    # 剩余部分找 VS
    vs_text = " - ".join(parts[1:]) if len(parts) > 1 else parts[0]
    vs = re.split(r"\s+VS\s+|\s+vs\s+", vs_text)
    if len(vs) >= 2:
        if not home:
            home = vs[0].strip()
        if not away:
            away = vs[1].strip()
    return league, home, away


# ---------- 主入口 ----------

def scrape_bifa(eventid: str) -> dict | None:
    """
    爬取单场比赛的必发交易指数数据。

    Returns:
        {
            "eventid", "url", "snapshot_time", "league", "home", "away",
            "summary": [ {side, price, volume, ratio, pnl, pnl_index, hot_cold_index}, ... ],
            "large_trades": { "主": [...], "和": [...], "客": [...] },
            "trends": { "主": [ {volume, time}, ... ], ... },
        }
        无必发数据或页面不可用时返回 None。
    """
    url = BASE_URL.format(eventid=eventid)
    session = make_session(referer=HOMEPAGE_URL)

    resp = fetch(session, url, referer=HOMEPAGE_URL,
                 retries=3, backoff=2.0, warmup_url=HOMEPAGE_URL)
    if not resp or resp.status_code != 200:
        return None

    html = resp.text
    snapshot_base = {
        "eventid": eventid,
        "url": url,
        "snapshot_time": datetime.now(TZ).isoformat(),
    }

    # ---- 方式 1：内嵌 JSON ----
    param = _extract_page_data(html)
    if param is not None:
        all_data = param.get("allData") or []
        summary = _parse_summary(all_data)
        if summary:
            info = param.get("info") or {}
            snapshot = dict(snapshot_base)
            snapshot.update({
                "league": info.get("match", ""),
                "home": info.get("home", ""),
                "away": info.get("away", ""),
                "summary": summary,
                "large_trades": _parse_large_trades(all_data),
                "trends": _parse_trends(all_data),
            })
            return snapshot

    # ---- 方式 2：HTML 表格兜底 ----
    if "交易汇总" not in html and "bifa-info" not in html:
        return None

    soup = BeautifulSoup(html, "lxml")
    summary = _parse_summary_from_html(soup)
    if not summary:
        return None

    league, home, away = _extract_match_info_from_title(html)
    snapshot = dict(snapshot_base)
    snapshot.update({
        "league": league,
        "home": home,
        "away": away,
        "summary": summary,
        "large_trades": _parse_large_trades_from_html(soup),
        "trends": {},
    })
    return snapshot


def scrape_multiple(eventids: list[str], delay: float = 2.0) -> list[dict]:
    """
    批量爬取多场比赛的必发数据。

    Args:
        eventids: 比赛 ID 列表
        delay: 请求间隔基准秒数（实际间隔加入随机抖动，降低被反爬识别的概率）

    Returns:
        成功爬取的快照列表
    """
    snapshots = []
    for eid in eventids:
        try:
            result = scrape_bifa(eid)
        except Exception:
            result = None
        if result and result["summary"]:
            snapshots.append(result)
            print(f"  [OK] {eid}: {len(result['summary'])} 条汇总数据")
        else:
            print(f"  [SKIP] {eid}: 无必发数据或页面不可用")
        time.sleep(delay * random.uniform(0.7, 1.3))

    return snapshots


if __name__ == "__main__":
    # 测试单场
    result = scrape_bifa("14616233")
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("未获取到数据")
