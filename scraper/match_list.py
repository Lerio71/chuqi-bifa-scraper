"""
从出奇体育获取比赛列表（必发数据候选场次）。

数据源（按优先级）：
  1. botidata8 JSONP 接口（d.botidata8.com/score/data）—— 结构化主数据源，
     一次请求即可拿到全部比赛的 eventid / 联赛 / 对阵 / 开赛时间。
  2. 主站 HTML 兜底（live.chuqi.com/football/）—— 若接口改版失效，
     从页面链接中提取 eventid（多正则匹配，兼容不同页面版本）。

采集范围（方案A·聚焦足彩14场）：
  - 默认只返回【当期胜负彩（足彩任九/14场）】的 14 场，自动识别当期（type=1 且未开奖，
    period 最大），也可用 expect 显式指定期号。
  - 若 14 场识别失败（出奇未收录 / 接口异常），自动回退到【当日全部比赛】，
    保证采集流程不因单点故障中断。

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


def _fetch_botidata_payload(session: requests.Session) -> dict:
    """请求 botidata 接口并返回 data 子对象；失败返回空 dict"""
    import time as _time

    callback = f"jQuery3410{int(_time.time() * 1000)}_{int(_time.time() * 1000)}"
    params = dict(BOTIDATA_PARAMS, jsoncallback=callback)

    resp = fetch(session, BOTIDATA_URL, params=params, referer=HOMEPAGE_URL,
                 retries=3, backoff=2.0, warmup_url=HOMEPAGE_URL)
    if not resp or resp.status_code != 200:
        return {}

    payload = _jsonp_to_json(resp.text)
    d = payload.get("data")
    if not isinstance(d, dict):
        return {}
    return d


def _find_lottery_game(payload: dict, expect=None) -> dict | None:
    """
    从 botidata payload 中识别当期胜负彩期（type=1）。
      - 显式 expect（期号）优先匹配；
      - 否则取「未开奖（awardtime 在未来）」且 period 最大的期；
      - 全部已开奖时取 period 最大的期。
    """
    game_obj = payload.get("l.game")
    if not isinstance(game_obj, dict) or "fields" not in game_obj:
        return None
    fields = game_obj["fields"]
    cands = []
    for row in game_obj.get("data", []):
        rec = dict(zip(fields, row))
        if rec.get("type") == 1:
            cands.append(rec)
    if not cands:
        return None

    if expect:
        for g in cands:
            if str(g.get("period")) == str(expect):
                return g

    now = datetime.now(TZ)
    active = []
    for g in cands:
        aw = g.get("awardtime")
        if aw:
            try:
                aw_dt = datetime.fromisoformat(str(aw).replace("Z", "+00:00")).astimezone(TZ)
                if aw_dt > now:
                    active.append(g)
                    continue
            except Exception:
                pass
        active.append(g)

    active.sort(key=lambda g: int(g.get("period") or 0), reverse=True)
    return active[0] if active else None


def _compose_matches(payload: dict, eids) -> list[dict]:
    """把 event/team/match 表按 eventid 白名单组装成比赛列表"""
    d = payload
    event_obj = d.get("event")
    if not isinstance(event_obj, dict) or "fields" not in event_obj:
        return []

    eid_set = {str(e) for e in eids}
    league_map = _table_index(d, "match")   # matchid -> 联赛
    team_map = _table_index(d, "team")      # team id -> 队名

    event_fields = event_obj["fields"]
    matches = []
    for row in event_obj.get("data", []):
        rec = dict(zip(event_fields, row))
        eid = str(rec.get("id", ""))
        if eid not in eid_set:
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


def _lottery_eids_from_payload(payload: dict, expect=None) -> list[str]:
    """从 botidata payload 提取当期胜负彩 14 场 eventid（按场次序号排序）"""
    game = _find_lottery_game(payload, expect)
    if not game:
        return []
    gid = game.get("id")

    le = payload.get("l.event")
    if not isinstance(le, dict) or "fields" not in le:
        return []
    le_fields = le["fields"]
    pairs = []
    for row in le.get("data", []):
        rec = dict(zip(le_fields, row))
        if rec.get("lgameid") == gid:
            pairs.append((int(rec.get("number") or 0), str(rec.get("eventid"))))
    pairs.sort(key=lambda x: x[0])
    return [e for _, e in pairs]


def _get_matches_from_botidata(session: requests.Session,
                               expect=None, lottery_only=False) -> list[dict]:
    """从 botidata 接口获取比赛（默认聚焦当期足彩14场，失败回退当日全部）"""
    d = _fetch_botidata_payload(session)
    if not d:
        return []

    if lottery_only:
        eids = _lottery_eids_from_payload(d, expect)
        if eids:
            matches = _compose_matches(d, eids)
            if matches:
                return matches

    # 回退：当日全部比赛（按北京时间所在比赛日筛选）
    today = datetime.now(TZ).strftime("%Y%m%d")
    today_eids = set()
    le = d.get("l.event")
    if isinstance(le, dict) and "fields" in le and "data" in le:
        for row in le["data"]:
            rec = dict(zip(le["fields"], row))
            if str(rec.get("group", "")) == today:
                today_eids.add(str(rec.get("eventid")))

    event_obj = d.get("event")
    if not isinstance(event_obj, dict) or "fields" not in event_obj:
        return []

    event_fields = event_obj["fields"]
    league_map = _table_index(d, "match")
    team_map = _table_index(d, "team")
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


def get_today_matches(expect=None, lottery_only=True) -> list[dict]:
    """
    获取比赛列表（默认聚焦当期足彩14场）。

    Args:
        expect: 足彩期号（如 26112），None 时自动识别当期。
        lottery_only: True 时优先返回足彩14场，失败自动回退当日全部；
                      False 时直接返回当日全部比赛。

    Returns:
        [{"eventid", "league", "home", "away", "time", "url"}, ...]
    """
    session = make_session(referer=HOMEPAGE_URL)

    matches = _get_matches_from_botidata(session, expect=expect, lottery_only=lottery_only)
    if matches:
        return matches

    matches = _get_matches_from_homepage(session)
    if matches:
        return matches

    return []


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", default=None, help="足彩期号（如 26112）")
    ap.add_argument("--all", action="store_true", help="采集当日全部而非足彩14场")
    a = ap.parse_args()

    matches = get_today_matches(expect=a.expect, lottery_only=not a.all)
    mode = "当期足彩14场" if not a.all else "当日全部"
    print(f"[{mode}] 找到 {len(matches)} 场:")
    for m in matches:
        print(f"  {m['league']} | {m['home']} VS {m['away']} | {m['time']} | ID: {m['eventid']}")
