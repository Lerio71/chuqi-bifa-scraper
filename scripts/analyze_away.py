# -*- coding: utf-8 -*-
"""analyze_away.py — 客队大热分析 + 主客大热对比"""
import json, os, re
from collections import defaultdict

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
    # 客队大热
    away_hot = {'cases': [], 'hit': 0}
    home_hot = {'cases': [], 'hit': 0}
    # 主队/客队大热+冷热低对比
    away_low = {'cases': [], 'hit': 0}
    away_high = {'cases': [], 'hit': 0}
    for mid in ids:
        p = f'match_data/{mid}/structured.json'
        if not os.path.exists(p): continue
        d = json.load(open(p, encoding='utf-8'))
        sc = scores.get(mid, {})
        hh, aa = sc.get('h'), sc.get('a')
        if hh is None: continue
        result = 1 if hh > aa else (0 if hh == aa else 2)
        bf = get_bifa(d)
        hp = per_to_float(bf.get('主', {}).get('per'))
        ap = per_to_float(bf.get('客', {}).get('per'))
        hhot = bf.get('主', {}).get('hot')
        ahot = bf.get('客', {}).get('hot')
        # 主队大热
        if hp is not None and hp >= 65:
            home_hot['cases'].append((mid, result))
            if result == 1: home_hot['hit'] += 1
        # 客队大热
        if ap is not None and ap >= 55:
            away_hot['cases'].append((mid, result))
            if result == 2: away_hot['hit'] += 1
            if ahot is not None:
                if ahot < 1:
                    away_low['cases'].append((mid, result))
                    if result == 2: away_low['hit'] += 1
                else:
                    away_high['cases'].append((mid, result))
                    if result == 2: away_high['hit'] += 1
    print("=== 主队大热(占65%+) ===")
    n = len(home_hot['cases'])
    if n:
        h = sum(1 for c in home_hot['cases'] if c[1]==1)
        d_ = sum(1 for c in home_hot['cases'] if c[1]==0)
        a = sum(1 for c in home_hot['cases'] if c[1]==2)
        print(f"{n}场: 主胜{h}({h/n*100:.0f}%) 平{d_} 客胜{a}")
    print("=== 客队大热(占55%+) ===")
    n = len(away_hot['cases'])
    if n:
        h = sum(1 for c in away_hot['cases'] if c[1]==1)
        d_ = sum(1 for c in away_hot['cases'] if c[1]==0)
        a = sum(1 for c in away_hot['cases'] if c[1]==2)
        print(f"{n}场: 主胜{h} 平{d_} 客胜{a}({a/n*100:.0f}%)")
    print("=== 客队大热细分冷热 ===")
    for nm, s in [('冷热<1', away_low), ('冷热>=1', away_high)]:
        n = len(s['cases'])
        if n:
            h = sum(1 for c in s['cases'] if c[1]==1)
            d_ = sum(1 for c in s['cases'] if c[1]==0)
            a = sum(1 for c in s['cases'] if c[1]==2)
            print(f"{nm}: {n}场 客胜{a}({a/n*100:.0f}%) 平{d_} 主胜{h}")
    # 冷热3分界（客队大热）
    away_lt3 = {'cases': [], 'hit': 0}
    away_gt3 = {'cases': [], 'hit': 0}
    for mid in ids:
        p = f'match_data/{mid}/structured.json'
        if not os.path.exists(p): continue
        d = json.load(open(p, encoding='utf-8'))
        sc = scores.get(mid, {})
        hh, aa = sc.get('h'), sc.get('a')
        if hh is None: continue
        result = 1 if hh > aa else (0 if hh == aa else 2)
        bf = get_bifa(d)
        ap = per_to_float(bf.get('客', {}).get('per'))
        ahot = bf.get('客', {}).get('hot')
        if ap is not None and ap >= 55 and ahot is not None:
            if ahot < 3:
                away_lt3['cases'].append(result); 
                if result == 2: away_lt3['hit'] += 1
            else:
                away_gt3['cases'].append(result)
                if result == 2: away_gt3['hit'] += 1
    print("\n=== 客队大热冷热3分界 ===")
    for nm, s in [('冷热<3', away_lt3), ('冷热>=3', away_gt3)]:
        n = len(s['cases'])
        if n:
            h = sum(1 for c in s['cases'] if c==1)
            d_ = sum(1 for c in s['cases'] if c==0)
            a = sum(1 for c in s['cases'] if c==2)
            print(f"{nm}: {n}场 客胜{a}({a/n*100:.0f}%) 平{d_} 主胜{h}")

if __name__ == '__main__':
    main()
