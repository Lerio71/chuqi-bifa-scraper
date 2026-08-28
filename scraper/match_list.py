"""
从出奇体育获取今日比赛列表（必发数据候选场次）。

数据源（按优先级）：
  1. botidata8 JSONP 接口（d.botidata8.com/score/data）—— 结构化主数据源，
     一次请求即可拿到全部比赛的 eventid / 联赛 / 对阵 / 开赛时间。
  2. 主站 HTML 兜底（live.chuqi.com/football/）—— 若接口改版失效，
     从页面链接中提取 eventid（多正则匹配，兼容不同页面版本）。

必发页面 URL: https://live.chuqi.com/football/live-bifa/{eventid}/
"""

import os
import sys
import re
import json
import requests
from datetime import datetime, timezone, timedelta

# 兼容两种运行方式：run.py 以包方式导入 / 直接 python scraper/match_list.py
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.net import make_session, fetch, HOMEPAGE_URL


TZ = timezone(timedelta(hours=8))
BOTIDATA_URL = "https://d.botidata8.com/score/data"
BOTIDATA_PARAMS = {
    "scheme": "1",
    "ps": "5000",
    "choose": "458783",
    "virtual": "1",
    "sportid": "1",
    "supplierid": "1",
    "number": "0",
}

# 主站 HTML 中可能出现的比赛链接模式（兼容不同版本页面）
EVENTID_PATTERNS = [
    r"/football/info-new-321/(\d+)/",
    r"/football/live-ai/(\d+)/",
    r"/football/live-fenxi-game/(\d+)/",
    r"/football/info-new-ai/(\d+)/",
    r"/football/live-detail/(\d+)/",
    r"/football/live-bifa/(\d+)/",
]


def _jsonp_to_json(text: str) -> dict:
    """解析 JSONP 包裹的 JSON: jQuery...(jsonData)"""
    m = re.search(r"\((.+)\)", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _table_index(payload: dict, name: str) -> dict:
    """
    把接口中的 {fields: [...], data: [[...], ...]} 表转成 {id: dict} 索引。
    """
    obj = payload.get(name)
    if not isinstance(obj, dict) or "fields" not in obj or "data" not in obj:
        return {}
    fields = obj["fields"]
    idx = {}
    for row in obj["data"]:
        rec = dict(zip(fields, row))
        idx[rec.get("id")] = rec
    return idx


def _get_matches_from_botidata(session: requests.Session) -> list[dict]:
    """从 botidata 接口获取今日比赛（含联赛/对阵/时间）"""
    import time as _time

    callback = f"jQuery3410{int(_time.time() * 1000)}_{int(_time.time() * 1000)}"
    params = dict(BOTIDATA_PARAMS, jsoncallback=callback)

    resp = fetch(session, BOTIDATA_URL, params=params, referer=HOMEPAGE_URL,
                 retries=3, backoff=2.0, warmup_url=HOMEPAGE_URL)
    if not resp or resp.status_code != 200:
        return []

    payload = _jsonp_to_json(resp.text)
    d = payload.get("data")
    if not isinstance(d, dict):
        return []

    event_obj = d.get("event")
    if not isinstance(event_obj, dict) or "fields" not in event_obj:
        return []

    league_map = _table_index(d, "match")   # matchid -> 联赛
    team_map = _table_index(d, "team")      # team id -> 队名

    # 今日比赛日: l.event.group == 今天日期 YYYYMMDD（北京时间）
    today = datetime.now(TZ).strftime("%Y%m%d")
    today_eids = set()
    le = d.get("l.event")
    if isinstance(le, dict) and "fields" in le and "data" in le:
        for row in le["data"]:
            rec = dict(zip(le["fields"], row))
            if str(rec.get("group", "")) == today:
                today_eids.add(str(rec.get("eventid")))

    event_fields = event_obj["fields"]
    matches = []
    for row in event_obj.get("data", []):
        rec = dict(zip(event_fields, row))
        eid = str(rec.get("id", ""))
        if not eid or eid not in today_eids:
            continue

        league = league_map.get(rec.get("matchid"), {}).get("zh_hans") or ""
        home = team_map.get(rec.get("home"), {}).get("zh_hans") or ""
        away = team_map.get(rec.get("away"), {}).get("zh_hans") or ""

        time_str = ""
        sched = rec.get("scheduletime")
        if sched:
            try:
                time_str = datetime.fromtimestamp(sched / 1000, TZ).strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = ""

        matches.append({
            "eventid": eid,
            "league": league,
            "home": home,
            "away": away,
            "time": time_str,
            "url": f"https://live.chuqi.com/football/live-bifa/{eid}/",
        })

    matches.sort(key=lambda m: m["time"])
    return matches


def _extract_eventids_from_homepage(html: str) -> list[str]:
    """从主站 HTML 提取全部 eventid（多模式匹配，去重、保序）"""
    ids = []
    seen = set()
    for pat in EVENTID_PATTERNS:
        for m in re.finditer(pat, html):
            eid = m.group(1)
            if eid not in seen:
                seen.add(eid)
                ids.append(eid)
    return ids


def _get_matches_from_homepage(session: requests.Session) -> list[dict]:
    """
    主站 HTML 兜底：只能拿到 eventid，无法从 SPA 直接取队名/时间。
    返回的比赛 league/home/away/time 为空，由后续必发页内嵌数据补充。
    """
    resp = fetch(session, HOMEPAGE_URL, referer=HOMEPAGE_URL,
                 retries=3, backoff=2.0, warmup_url=HOMEPAGE_URL)
    if not resp or resp.status_code != 200:
        return []

    ids = _extract_eventids_from_homepage(resp.text)
    return [{
        "eventid": eid,
        "league": "",
        "home": "",
        "away": "",
        "time": "",
        "url": f"https://live.chuqi.com/football/live-bifa/{eid}/",
    } for eid in ids]


def get_today_matches() -> list[dict]:
    """
    获取今日（按北京时间所在比赛日）的比赛列表。

    优先 botidata 结构化接口；接口失效时回退到主站 HTML。
    任何异常都不会抛出，最多返回空列表，保证采集流程不因单点故障中断。

    Returns:
        [{"eventid", "league", "home", "away", "time", "url"}, ...]
    """
    session = make_session(referer=HOMEPAGE_URL)

    matches = _get_matches_from_botidata(session)
    if matches:
        return matches

    matches = _get_matches_from_homepage(session)
    if matches:
        return matches

    return []


if __name__ == "__main__":
    matches = get_today_matches()
    print(f"找到 {len(matches)} 场今日比赛:")
    for m in matches:
        print(f"  {m['league']} | {m['home']} VS {m['away']} | {m['time']} | ID: {m['eventid']}")
