# -*- coding: utf-8 -*-
"""batch_read.py — 批量读取多场比赛关键摘要（精简版 read_one）
输出：对阵/赛果/欧赔初即(主流4家)/亚盘初即/必发/历史/身价/阵型/伤停
"""
import json, os, sys, re

def clean_state(tag):
    m = re.search(r'>([^<]*)<', tag or '')
    return m.group(1).strip() if m else ''

def _sup_map(b):
    sup = b.get('supplier')
    if isinstance(sup, list):
        return {str(s['id']): s['name'] for s in sup}
    if isinstance(sup, dict):
        return {str(v['id']): v['name'] for v in sup.values()}
    return {}

def get_odds1x2(d):
    b = d['boards'].get('odds1x2', {}).get('data')
    if not b: return {}
    sup = _sup_map(b)
    odds = b.get('odds', {})
    out = {}
    for sid, comp in odds.items():
        nm = sup.get(str(sid))
        if not nm or 'js' not in comp or 'cp' not in comp: continue
        try:
            out[nm] = {'init': (float(comp['cp']['a']), float(comp['cp']['b']), float(comp['cp']['c'])),
                       'live': (float(comp['js']['a']), float(comp['js']['b']), float(comp['js']['c']))}
        except Exception: pass
    return out

def get_oddsah(d):
    b = d['boards'].get('oddsah', {}).get('data')
    if not b: return {}
    sup = _sup_map(b)
    odds = b.get('odds', {})
    out = {}
    for sid, comp in odds.items():
        nm = sup.get(str(sid))
        if not nm or 'js' not in comp or 'cp' not in comp: continue
        try:
            out[nm] = {'init': (float(comp['cp']['a']), float(comp['cp']['b']), float(comp['cp']['c'])),
                       'live': (float(comp['js']['a']), float(comp['js']['b']), float(comp['js']['c']))}
        except Exception: pass
    return out

def read(mid):
    p = f'match_data/{mid}/structured.json'
    if not os.path.exists(p):
        return f'{mid}: 数据不存在'
    d = json.load(open(p, encoding='utf-8'))
    scores = json.load(open('match_scores.json', encoding='utf-8'))
    sc = scores.get(mid, {})
    lines = []
    # 对阵信息
    info = d['boards'].get('detail', {}).get('info', {})
    home = info.get('home', '?')
    away = info.get('away', '?')
    match = info.get('match', '')
    hh, aa = sc.get('h', '?'), sc.get('a', '?')
    lines.append(f"{mid} {home}(主) vs {away}(客) | {match} 赛果 {hh}:{aa}")
    # 欧赔主流
    o1 = get_odds1x2(d)
    for nm in ['威廉**', '立*', '澳*', '竞']:
        if nm in o1:
            i, l = o1[nm]['init'], o1[nm]['live']
            lines.append(f"  欧[{nm}] 初{i[0]}/{i[1]}/{i[2]} -> 即{l[0]}/{l[1]}/{l[2]}")
    # 亚盘主流
    oa = get_oddsah(d)
    for nm in ['威廉**', '立*', '澳*', 'Crow*']:
        if nm in oa:
            i, l = oa[nm]['init'], oa[nm]['live']
            lines.append(f"  亚[{nm}] 初水{i[0]}/盘{i[2]} -> 即水{l[0]}/盘{l[2]}")
    # 必发
    bf = d['boards'].get('bifa', {}).get('allData') or []
    for x in bf[:3]:
        s = x.get('summary', {})
        lines.append(f"  必发{x.get('name')}: 赔{s.get('odds')} 量{s.get('amount')} 占{s.get('per')} 盈亏{s.get('profit')} 冷热{s.get('hot')}")
    return '\n'.join(lines)

if __name__ == '__main__':
    ids = [ln.strip() for ln in open(sys.argv[1], encoding='utf-8') if ln.strip()]
    for mid in ids:
        print(read(mid))
        print('-' * 70)
