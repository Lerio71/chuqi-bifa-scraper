# -*- coding: utf-8 -*-
"""blind_read.py <mid> — 盲测读取：只输出球队名+欧赔+亚盘+必发，不含赛果
用于模式A赛前研判（屏蔽赛果避免污染预判）"""
import json, os, sys

def _sup_map(b):
    sup = b.get('supplier')
    if isinstance(sup, list):
        return {str(s['id']): s['name'] for s in sup}
    if isinstance(sup, dict):
        return {str(v['id']): v['name'] for v in sup.values()}
    return {}

def main(mid):
    p = f'match_data/{mid}/structured.json'
    if not os.path.exists(p):
        print('数据不存在'); return
    d = json.load(open(p, encoding='utf-8'))
    info = d['boards'].get('detail', {}).get('info', {})
    print(f"{info.get('home','?')}(主) vs {info.get('away','?')}(客) | {info.get('match','')}")
    print("【赛果屏蔽中】")
    # 欧赔 威廉/立博/澳门/竞彩
    b = d['boards'].get('odds1x2', {}).get('data')
    sup = _sup_map(b) if b else {}
    if b:
        for sid, comp in b.get('odds', {}).items():
            nm = sup.get(str(sid))
            if nm in ('威廉希尔', '威廉**', '立博', '立*', '澳门', '澳*', '竞彩官方', '竞') or ('威廉' in str(nm)) or ('立' == str(nm)[:1] and '博' in str(nm)) or ('澳门' in str(nm) or '澳' == str(nm)[:1]) or ('竞' in str(nm)):
                if 'js' in comp and 'cp' in comp:
                    cp = comp['cp']; js = comp['js']
                    try:
                        print(f"  欧[{nm}] 初{float(cp['a'])}/{float(cp['b'])}/{float(cp['c'])} -> 即{float(js['a'])}/{float(js['b'])}/{float(js['c'])}")
                    except Exception: pass
    # 亚盘
    b2 = d['boards'].get('oddsah', {}).get('data')
    sup2 = _sup_map(b2) if b2 else {}
    if b2:
        for sid, comp in b2.get('odds', {}).items():
            nm = sup2.get(str(sid))
            if nm in ('威廉希尔', '威廉**', '立博', '立*', '澳门', '澳*') or ('威廉' in str(nm)) or ('博' in str(nm) and '立' in str(nm)[:1]) or ('澳门' in str(nm)):
                if 'js' in comp and 'cp' in comp:
                    try:
                        print(f"  亚[{nm}] 初水{float(comp['cp']['a'])}/盘{float(comp['cp']['c'])} -> 即水{float(comp['js']['a'])}/盘{float(comp['js']['c'])}")
                    except Exception: pass
    # 必发
    bf = d['boards'].get('bifa', {}).get('allData') or []
    for x in bf:
        s = x.get('summary', {})
        print(f"  必发[{x.get('name')}] 赔{s.get('odds')} 量{s.get('amount')} 占{s.get('per')} 盈亏{s.get('profit')} 冷热{s.get('hot')}")

if __name__ == '__main__':
    main(sys.argv[1])
