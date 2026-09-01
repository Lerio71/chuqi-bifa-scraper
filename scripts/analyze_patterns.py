# -*- coding: utf-8 -*-
"""analyze_patterns.py — 验证关键规律命中率
1. 冷热指数分界与赛果关系
2. 盘赔反向信号（主胜升+降盘）命中率
3. 轮次主胜率趋势
4. 深盘(1球+)大热赢盘率
"""
import json, os, re, sys
from collections import defaultdict

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

def get_bifa(d):
    bf = d['boards'].get('bifa', {}).get('allData') or []
    out = {}
    for x in bf:
        s = x.get('summary', {})
        out[x.get('name')] = {'per': s.get('per'), 'hot': s.get('hot'), 'amount': s.get('amount')}
    return out

def per_to_float(p):
    if isinstance(p, str):
        return float(p.rstrip('%')) if p.endswith('%') else float(p)
    return float(p) if p is not None else None

def main():
    ids = [ln.strip() for ln in open('ids_100.txt', encoding='utf-8') if ln.strip()]
    scores = json.load(open('match_scores.json', encoding='utf-8'))
    # 轮次映射
    round_map = {}
    r12 = [ln.strip() for ln in open('ids_r12.txt').read().split()]
    for i, mid in enumerate(r12):
        round_map[mid] = 1 if i < 10 else 2
    for r in range(3, 11):
        for mid in open(f'ids_r{r}.txt').read().split():
            round_map[mid] = r
    # 统计
    round_stat = defaultdict(lambda: {'H':0,'D':0,'A':0})
    # 冷热分析
    hot_low = {'cases': [], 'hit': 0}   # 主队大热(per>=65) 冷热<1
    hot_mid = {'cases': [], 'hit': 0}   # 主队大热 冷热1-3
    hot_high = {'cases': [], 'hit': 0}  # 主队大热 冷热>3
    # 盘赔反向
    rev = {'cases': [], 'hit': 0}  # 主胜升>0.15 + 降盘
    same = {'cases': [], 'hit': 0} # 主胜降>0.15 + 升盘
    # 深盘大热赢盘
    deep = {'cases': 0, 'win': 0, 'draw': 0, 'lose': 0}
    for mid in ids:
        p = f'match_data/{mid}/structured.json'
        if not os.path.exists(p): continue
        d = json.load(open(p, encoding='utf-8'))
        sc = scores.get(mid, {})
        hh, aa = sc.get('h'), sc.get('a')
        if hh is None: continue
        result = 1 if hh > aa else (0 if hh == aa else 2)
        rnd = round_map.get(mid)
        if result == 1: round_stat[rnd]['H'] += 1
        elif result == 0: round_stat[rnd]['D'] += 1
        else: round_stat[rnd]['A'] += 1
        # 欧赔威廉
        o1 = get_odds1x2(d)
        oa = get_oddsah(d)
        bf = get_bifa(d)
        if '威廉**' in o1 and '威廉**' in oa:
            ih, id_, ia = o1['威廉**']['init']
            lh, ld, la = o1['威廉**']['live']
            dh = lh - ih
            il = oa['威廉**']['init'][2]
            jl = oa['威廉**']['live'][2]
            dl = jl - il
            # 盘赔反向
            if dh > 0.15 and dl < -0.05:
                rev['cases'].append((mid, result))
                if result == 2 or result == 0: rev['hit'] += 1
            if dh < -0.15 and dl > 0.05:
                same['cases'].append((mid, result))
                if result == 1: same['hit'] += 1
            # 深盘
            if abs(jl) >= 1.0 and lh < 1.9:
                deep['cases'] += 1
                if result == 1:
                    # 是否赢盘：主队净胜球 > 盘口
                    if hh - aa > jl: deep['win'] += 1
                    elif hh - aa == jl: deep['draw'] += 1
                    else: deep['lose'] += 1
                else:
                    deep['lose'] += 1
        # 冷热分析
        if bf.get('主') and '主' in bf:
            per = per_to_float(bf['主'].get('per'))
            hot = bf['主'].get('hot')
            if per is not None and hot is not None and per >= 65:
                if hot < 1:
                    hot_low['cases'].append((mid, result))
                    if result == 1: hot_low['hit'] += 1
                elif hot < 3:
                    hot_mid['cases'].append((mid, result))
                    if result == 1: hot_mid['hit'] += 1
                else:
                    hot_high['cases'].append((mid, result))
                    if result == 1: hot_high['hit'] += 1
    print("=== 轮次主胜率趋势 ===")
    for r in range(1, 11):
        s = round_stat[r]
        t = s['H'] + s['D'] + s['A']
        print(f"第{r}轮: 主{s['H']} 平{s['D']} 客{s['A']} | 主胜率{s['H']/t*100:.0f}%")
    print(f"\n=== 主队大热(占65%+) 冷热分界 ===")
    for nm, s in [('冷热<1', hot_low), ('冷热1-3', hot_mid), ('冷热>3', hot_high)]:
        n = len(s['cases'])
        if n:
            win = s['hit']
            print(f"{nm}: {n}场 主队赢{win} 主队赢率{win/n*100:.0f}%")
            # 平/客明细
            dr = sum(1 for c in s['cases'] if c[1] == 0)
            aw = sum(1 for c in s['cases'] if c[1] == 2)
            print(f"   平{dr} 客胜{aw}")
    print(f"\n=== 盘赔反向(主胜升>0.15+降盘) ===")
    n = len(rev['cases'])
    if n:
        h = sum(1 for c in rev['cases'] if c[1] == 1)
        dr = sum(1 for c in rev['cases'] if c[1] == 0)
        a = sum(1 for c in rev['cases'] if c[1] == 2)
        print(f"{n}场: 主胜{h} 平{dr} 客胜{a} | 主队未赢率{100*(n-rev['hit'])/n*100:.0f}% (客或平={rev['hit']})")
        print(f"  场次: {[c[0] for c in rev['cases']]}")
    print(f"\n=== 盘赔同向(主胜降>0.15+升盘) ===")
    n = len(same['cases'])
    if n:
        h = sum(1 for c in same['cases'] if c[1] == 1)
        dr = sum(1 for c in same['cases'] if c[1] == 0)
        a = sum(1 for c in same['cases'] if c[1] == 2)
        print(f"{n}场: 主胜{h} 平{dr} 客胜{a} | 主胜率{h/n*100:.0f}%")
        print(f"  场次: {[c[0] for c in same['cases']]}")
    print(f"\n=== 深盘(让1球+)主队大热(水<1.9) ===")
    if deep['cases']:
        print(f"{deep['cases']}场: 赢盘{deep['win']} 走盘{deep['draw']} 输盘/输{deep['lose']}")
        print(f"  赢盘率{deep['win']/deep['cases']*100:.0f}%")

if __name__ == '__main__':
    main()
