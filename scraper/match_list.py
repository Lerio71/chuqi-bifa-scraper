"""
从出奇体育获取今日比赛列表。
出奇体育的比赛列表通过 d.botidata8.com 的 JSONP 接口加载比分数据，
其中包含每场比赛的 eventid，可用于构造必发页面 URL。
"""

import re
import json
import requests
from datetime import datetime, timezone, timedelta


def get_today_matches() -> list[dict]:
    """
    获取今日有必发数据的比赛列表。
    返回 [{"eventid": "13210524", "league": "西甲", "home": "阿拉维斯", "away": "巴列卡诺", "time": "2026-05-24 03:00"}, ...]
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://live.chuqi.com/football/",
    })

    # 通过出奇体育主站 HTML 提取今日比赛 eventid
    # 比赛列表页会将比赛链接渲染在 HTML 中
    url = "https://live.chuqi.com/football/"
    resp = session.get(url, timeout=15)
    resp.encoding = "utf-8"

    matches = []
    # 匹配 live-bifa/{eventid}/ 或 live-detail/{eventid}/ 的链接
    # 出奇体育在列表页会渲染比赛卡片
    seen_ids = set()

    # 先尝试从 HTML 中提取所有 eventid
    pattern = r'/football/live-detail/(\d+)/'
    for m in re.finditer(pattern, resp.text):
        eid = m.group(1)
        if eid not in seen_ids:
            seen_ids.add(eid)

    # 也尝试 live-bifa 链接
    pattern_bifa = r'/football/live-bifa/(\d+)/'
    for m in re.finditer(pattern_bifa, resp.text):
        eid = m.group(1)
        if eid not in seen_ids:
            seen_ids.add(eid)

    # 如果 HTML 提取不到，尝试从 botidata8 JSONP 接口获取
    if not seen_ids:
        seen_ids = _fetch_from_botidata(session)

    # 为每个 eventid 获取比赛基本信息
    for eid in seen_ids:
        info = _fetch_match_info(session, eid)
        if info:
            matches.append(info)

    return matches


def _fetch_from_botidata(session: requests.Session) -> set[str]:
    """通过 botidata8 JSONP 接口获取比赛列表"""
    import time
    callback = f"jQuery3410{int(time.time()*1000)}_{int(time.time()*1000)}"
    url = "https://d.botidata8.com/score/data"
    params = {
        "scheme": "1",
        "ps": "5000",
        "choose": "458783",
        "virtual": "1",
        "sportid": "1",
        "supplierid": "1",
        "number": "0",
        "jsoncallback": callback,
    }
    try:
        resp = session.get(url, params=params, timeout=15)
        # JSONP 格式: jQuery...(jsonData)
        text = resp.text
        json_str = re.search(r'\((.+)\)', text, re.DOTALL)
        if json_str:
            data = json.loads(json_str.group(1))
            ids = set()
            for match in data.get("scoredata", data.get("data", [])):
                eid = str(match.get("eventid", match.get("id", "")))
                if eid:
                    ids.add(eid)
            return ids
    except Exception:
        pass
    return set()


def _fetch_match_info(session: requests.Session, eventid: str) -> dict | None:
    """获取单场比赛的基本信息（联赛、队名、时间）"""
    url = f"https://live.chuqi.com/football/live-bifa/{eventid}/"
    try:
        resp = session.get(url, timeout=15)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return None

        html = resp.text

        # 检查页面是否有必发数据
        if "交易汇总" not in html and "bifa" not in html.lower():
            return None

        # 提取联赛
        league = ""
        league_match = re.search(r'<span class="league[^"]*"[^>]*>([^<]+)</span>', html)
        if league_match:
            league = league_match.group(1).strip()

        # 提取队名
        home = ""
        away = ""
        # 尝试多种匹配模式
        home_match = re.search(r'class="home[^"]*"[^>]*>([^<]+)<', html)
        if home_match:
            home = home_match.group(1).strip()
        away_match = re.search(r'class="away[^"]*"[^>]*>([^<]+)<', html)
        if away_match:
            away = away_match.group(1).strip()

        # 尝试从 title 或 h1 标签提取
        if not home or not away:
            title_match = re.search(r'<title>([^<]+)</title>', html)
            if title_match:
                title = title_match.group(1)
                parts = re.split(r'\s+VS\s+|\s+vs\s+', title)
                if len(parts) >= 2:
                    if not home:
                        home = parts[0].strip()
                    if not away:
                        away = parts[1].strip().split(' - ')[0].strip()

        # 提取比赛时间
        match_time = ""
        time_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', html)
        if time_match:
            match_time = time_match.group(1)

        return {
            "eventid": eventid,
            "league": league,
            "home": home,
            "away": away,
            "time": match_time,
            "url": url,
        }
    except Exception:
        return None


if __name__ == "__main__":
    matches = get_today_matches()
    print(f"找到 {len(matches)} 场有必发数据的比赛:")
    for m in matches:
        print(f"  {m['league']} | {m['home']} VS {m['away']} | {m['time']} | ID: {m['eventid']}")
