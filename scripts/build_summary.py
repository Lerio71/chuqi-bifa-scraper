# -*- coding: utf-8 -*-
"""build_summary.py — 生成10轮100场盲测复盘汇总表(CSV)
逐场判定：赛果方向 vs 盘赔+冷热信号推导的方向
输出 match_data/summary_100.csv
"""
import json, os, csv
from collections import defaultdict

def get_odds1x2(d):
    b = d['boards'].get('odds1x2', {}).get('data')
    if not b: return {}
    sup = b.get('supplier')
    sup = {str(s['id']): s['name'] for s in sup} if isinstance(sup, list) else ({str(v['id']): v['name'] for v in sup.values()} if isinstance(sup, dict) else {})
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
    sup = b.get('supplier')
    sup = {str(s['id']): s['name'] for s in sup} if isinstance(sup, list) else ({str(v['id']): v['name'] for v in sup.values()} if isinstance(sup, dict) else {})
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

def get_bifa(d):
    bf = d['boards'].get('bifa', {}).get('allData') or []
    out = {}
    for x in bf:
        s = x.get('summary', {})
        out[x.get('name')] = {'per': s.get('per'), 'hot': s.get('hot'), 'amount': s.get('amount')}
    return out

def pct(p):
    if p is None: return None
    if isinstance(p, str): return float(p.rstrip('%')) if p.endswith('%') else float(p)
    return float(p)

def predict(d, o1, oa, bf):
    """基于盘赔+冷热推导赛前方向判定(盲测用)"""
    if '威廉**' in o1 and '威廉**' in oa:
        ih, id_, ia = o1['威廉**']['init']
        lh, ld, la = o1['威廉**']['live']
        dh = lh - ih
        il = oa['威廉**']['init'][2]
        jl = oa['威廉**']['live'][2]
        dl = jl - il
        hp = pct(bf.get('主', {}).get('per')) or 0
        ap = pct(bf.get('客', {}).get('per')) or 0
        hhot = bf.get('主', {}).get('hot')
        ahot = bf.get('客', {}).get('hot')
        # 规则优先级
        # 1) 主队大热(>=65)
        if hp >= 65:
            if hhot is not None and hhot >= 1: return 1, '主胜(主大热)'
            return 1, '主胜(主大热冷热低)'
        # 2) 客队大热(>=55)
        if ap >= 55:
            if ahot is not None and ahot < 3: return 2, '客胜(客大热冷热<3)'
            return 0, '平/主胜(客大热过热)'
        # 3) 盘赔反向(主胜升>0.15+降盘)
        if dh > 0.15 and dl < -0.05:
            return 2, '客胜/平(盘赔反向)'
        # 4) 盘赔同向(主胜降+升盘)=诱上
        if dh < -0.15 and dl > 0.05:
            return 0, '平/客胜(诱上)'
        # 5) 主胜微降+平赔升=看好主
        if dh < -0.05:
            return 1, '主胜(盘赔微看主)'
        if dh > 0.05:
            return 2, '客胜/平(盘赔微看客)'
    return 1, '主胜(中性)'

def main():
    scores = json.load(open('match_scores.json', encoding='utf-8'))
    round_map = {}
    r12 = [ln.strip() for ln in open('ids_r12.txt').read().split() if ln.strip()]
    for i, mid in enumerate(r12): round_map[mid] = 1 if i < 10 else 2
    for r in range(3, 11):
        for mid in open(f'ids_r{r}.txt').read().split(): round_map[mid] = r
    rows = []
    total = {'n': 0, 'hit': 0}
    for rnd in range(1, 11):
        ids = r12[:10] if rnd == 1 else (r12[10:] if rnd == 2 else [ln.strip() for ln in open(f'ids_r{rnd}.txt').read().split() if ln.strip()])
        for mid in ids:
            p = f'match_data/{mid}/structured.json'
            if not os.path.exists(p): continue
            d = json.load(open(p, encoding='utf-8'))
            info = d['boards'].get('detail', {}).get('info', {})
            home, away = info.get('home', ''), info.get('away', '')
            sc = scores.get(mid, {})
            hh, aa = sc.get('h'), sc.get('a')
            if hh is None: continue
            result = 1 if hh > aa else (0 if hh == aa else 2)
            o1 = get_odds1x2(d); oa = get_oddsah(d); bf = get_bifa(d)
            pred, rule = predict(d, o1, oa, bf)
            hit = 1 if pred == result else 0
            total['n'] += 1; total['hit'] += hit
            hp = pct(bf.get('主', {}).get('per')); ap = pct(bf.get('客', {}).get('per'))
            hhot = bf.get('主', {}).get('hot'); ahot = bf.get('客', {}).get('hot')
            rows.append({
                '轮': rnd, 'id': mid, '对阵': f'{home} vs {away}', '赛果': f'{hh}-{aa}',
                '方向': {1: '主胜', 0: '平', 2: '客胜'}[result],
                '主占%': hp, '客占%': ap, '主冷热': hhot, '客冷热': ahot,
                '盲测方向': {1: '主胜', 0: '平', 2: '客胜'}[pred], '判定规则': rule, '命中': hit
            })
    with open('match_data/summary_100.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['轮', 'id', '对阵', '赛果', '方向', '主占%', '客占%', '主冷热', '客冷热', '盲测方向', '判定规则', '命中'])
        w.writeheader(); w.writerows(rows)
    print(f"总判定{total['n']}场 命中{total['hit']} 命中率{total['hit']/total['n']*100:.1f}%")
    for rnd in range(1, 11):
        rr = [r for r in rows if r['轮'] == rnd]
        h = sum(1 for r in rr if r['命中'])
        print(f"第{rnd}轮: {h}/10")

if __name__ == '__main__':
    main()
