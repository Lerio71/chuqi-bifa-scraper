# -*- coding: utf-8 -*-
"""
master_sync.py — 足彩14场自动同步脚本（跨期自动版）
=====================================================
数据流：
  ① 500体育任九页 ?expect={期号}  →  14场标准对阵（联赛/北京时间/队名/fid/cid）
  ② 出奇官方API d.botidata8.com/score/data  →  当期14场 match_id（按足彩期period匹配）
  ③ 合并校验 → 输出 matches.json（含每场精确开赛时间 kickoff）

用法：
  python master_sync.py --expect 26112 [--write]   # 显式指定期号
  python master_sync.py --auto --write             # 自动识别当期（推荐，跨期通用）
  python master_sync.py --write                    # 等价 --auto

跨期自动：--auto 时从出奇API l.game(type=1) 自动识别「最近一期未开奖」，
期号变化自动跟随，无需每期手动改。
"""
import io, sys, os, re, json, argparse, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests

# 基于脚本自身位置定位输出文件（兼容本地/云端不同工作目录）
BASE = os.path.dirname(os.path.abspath(__file__))
MATCHES_FILE = os.path.join(BASE, 'matches.json')
STATE_FILE = os.path.join(BASE, 'state', 'current.json')

TZ = datetime.timezone(datetime.timedelta(hours=8))
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0'}

def rows_to_dicts(fields, data):
    return [dict(zip(fields, row)) for row in data]

# ---------- ① 500 任九页 ----------
def fetch_500(expect):
    s = requests.Session(); s.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://trade.500.com/rj/'})
    b = s.get(f'https://trade.500.com/rj/?expect={expect}', timeout=40).text
    rows = []
    for m in re.finditer(r'<tr(?=[^>]*data-fixtureid="\d+")[^>]*>(.*?)</tr>', b, re.S):
        body, tag = m.group(1), m.group(0)
        fid = (re.search(r'data-fixtureid="(\d+)"', tag) or [None, ''])[1]
        cid = (re.search(r'data-cid="(\d+)"', tag) or [None, ''])[1]
        lg = re.search(r'class="td td-evt"[^>]*>.*?>([^<]+)</a>', body, re.S)
        tm = re.search(r'class="td td-endtime"[^>]*>([\d\-: ]+)', body)
        home = re.search(r'<a[^>]*class="team-l"[^>]*>([^<]+)</a>', body)
        away = re.search(r'<a[^>]*class="team-r"[^>]*>([^<]+)</a>', body)
        rows.append({'cid': cid, 'fid': fid,
                     'league': lg.group(1).strip() if lg else '',
                     'time': tm.group(1).strip() if tm else '',
                     'home': home.group(1).strip() if home else '',
                     'away': away.group(1).strip() if away else ''})
    rows.sort(key=lambda x: int(x['cid']) if (x['cid'] or '').isdigit() else 99)
    return rows

# ---------- ② 出奇官方 API ----------
def fetch_chuqi(expect=None):
    """
    获取当期足彩14场。
    Args:
        expect: 期号（如 26112）；None 时自动识别 type=1 且未开奖、period 最大的期
    Returns:
        (out, period)：out 为14场列表；period 为实际使用的期号
    """
    s = requests.Session(); s.headers.update({**UA, 'Referer': 'https://live.chuqi.com/football/schedule/',
                                              'Origin': 'https://live.chuqi.com'})
    params = {'scheme': '1', 'ps': '5000', 'choose': '458783', 'virtual': '1'}
    j = s.get('https://d.botidata8.com/score/data', params=params, timeout=60).json()
    data = j['data']
    ev = {e['id']: e for e in rows_to_dicts(data['event']['fields'], data['event']['data'])}
    team = {t['id']: t for t in rows_to_dicts(data['team']['fields'], data['team']['data'])}
    mch = {m['id']: m for m in rows_to_dicts(data['match']['fields'], data['match']['data'])}
    games = rows_to_dicts(data['l.game']['fields'], data['l.game']['data'])
    levs = rows_to_dicts(data['l.event']['fields'], data['l.event']['data'])

    # 定位期
    g = None
    if expect:
        for x in games:
            if str(x.get('period')) == str(expect) and x.get('type') == 1:
                g = x; break
        if not g:
            for x in games:
                if str(x.get('period')) == str(expect):
                    g = x; break
    if not g:
        # 自动识别：type=1，未开奖优先，否则 period 最大
        cands = [x for x in games if x.get('type') == 1]
        now = datetime.datetime.now()
        active = []
        for x in cands:
            aw = x.get('awardtime')
            if aw:
                try:
                    aw_dt = datetime.datetime.fromisoformat(str(aw).replace('Z', '+00:00'))
                    if aw_dt > now:
                        active.append(x)
                        continue
                except Exception:
                    pass
            active.append(x)
        active.sort(key=lambda x: int(x.get('period') or 0), reverse=True)
        if active:
            g = active[0]
            expect = g.get('period')
            print(f'  [自动识别] 当期足彩期号: {expect}')
        else:
            print(f'  未找到胜负彩期，现有期: {[x.get("period") for x in games]}')
            return [], None

    gid = g['id']
    out = []
    for le in levs:
        if le.get('lgameid') == gid:
            e = ev.get(le.get('eventid'))
            if not e: continue
            ht = team.get(e.get('home'), {}).get('zh_hans') or team.get(e.get('home'), {}).get('name')
            at = team.get(e.get('away'), {}).get('zh_hans') or team.get(e.get('away'), {}).get('name')
            m = mch.get(e.get('matchid'), {})
            ts = e.get('scheduletime') or 0
            dt = datetime.datetime.fromtimestamp(ts/1000, TZ).strftime('%Y-%m-%d %H:%M') if ts else ''
            out.append({'id': str(e['id']), 'league': m.get('zh_hans') or m.get('name') or '',
                        'time': dt, 'home': ht or '', 'away': at or '', 'number': le.get('number')})
    return out, expect

# ---------- 跨期状态 ----------
def load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expect', default=None, help='期号（如 26112），留空自动识别当期')
    ap.add_argument('--auto', action='store_true', help='自动识别当期（默认行为）')
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()

    # 自动识别当期（无论是否传 --expect，None 即自动）
    print('=== 出奇官方 API ===')
    cq, period = fetch_chuqi(a.expect)
    if not cq or period is None:
        print('无法获取当期14场，退出')
        return
    print(f'  出奇: {len(cq)} 场')

    print(f'\n=== 500 任九 {period} 期 ===')
    m500 = fetch_500(period)
    print(f'  500: {len(m500)} 场')
    for r in m500:
        print(f"    [{r['cid']}] {r['league']} {r['time']} {r['home']} VS {r['away']} fid={r['fid']}")

    print('\n=== 合并（按顺序一一对应）===')
    res = []
    for i, r in enumerate(m500):
        c = cq[i] if i < len(cq) else None
        if c:
            print(f"  ✓ [{r['cid']}] {r['home']}vs{r['away']} → 出奇ID={c['id']} ({c['home']}vs{c['away']})")
            ko = r['time'].strip()
            m = re.match(r'(\d{2})-(\d{2}) (\d{2}):(\d{2})', ko)
            if m:
                year = str(datetime.datetime.now(TZ).year)
                ko = f'{year}-{m.group(1)}-{m.group(2)} {m.group(3)}:{m.group(4)}'
            res.append({'id': c['id'], 'name': f"{r['home']}vs{r['away']}",
                        'kickoff': ko, 'league': r['league'], 'fid': r['fid']})
        else:
            print(f"  ✗ [{r['cid']}] {r['home']}vs{r['away']} 无出奇ID")
            res.append({'id': None, 'name': f"{r['home']}vs{r['away']}",
                        'kickoff': r['time'], 'league': r['league'], 'fid': r['fid']})

    ok = sum(1 for x in res if x['id'])
    print(f'\n匹配 {ok}/{len(res)}')

    # 跨期状态：检测期号是否变化（用于云端跨期切换/归档）
    state = load_state()
    prev = state.get('period')
    if prev and str(prev) != str(period):
        print(f'  [跨期切换] {prev} → {period}')
    state['period'] = int(period)
    state['updated_at'] = datetime.datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')

    if a.write and ok == len(res):
        with open(MATCHES_FILE, 'w', encoding='utf-8') as f:
            json.dump([{'id': x['id'], 'name': x['name'], 'kickoff': x['kickoff']} for x in res],
                      f, ensure_ascii=False, indent=2)
        save_state(state)
        print(f'已写入 {MATCHES_FILE}')
        print(f'当期期号: {period}（已记录到 state/current.json）')
    elif ok < len(res):
        print('匹配不足14场，未写入（保留旧配置）')

if __name__ == '__main__':
    main()
