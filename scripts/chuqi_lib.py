# -*- coding: utf-8 -*-
"""
chuqi_lib.py — 出奇体育比赛数据通用提取库
输入比赛 ID，并发抓取全部数据板块页 + 20家欧赔/亚盘变化页，
自动提取 JS 数据块（Node 求值）、解析变化表、修复编码，
输出标准化 structured.json。全程纯 HTTP，无需浏览器（除 detail 事件页）。
"""
import urllib.request, ssl, re, os, json, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}

LIVE = "https://live.chuqi.com/football/"
# 20 家公司 sid（欧赔/亚盘变化页）
# 注意：竞彩 sid 已从旧接口的 51_2 改为 51；新聚合接口仅竞彩(51)不可用，其余 19 家正常
SIDS = [("51","竞彩"),("1","Crow*"),("2","澳*"),("4","12B*"),("5","*365"),("6","易**"),
        ("10","利*"),("14","盈*"),("15","明*"),("20","立*"),("24","威廉**"),("26","伟*"),
        ("30","In*****"),("47","10B*"),("49","18B*"),("52","平*"),("62","BW**"),
        ("92","Coral"),("94","马*"),("97","1X***")]

# ---------------- 编码修复（HTML 源 UTF-8 被误当 Latin-1 时的回转） ----------------
_MOJIBAKE_CHARS = ("Ã", "Â", "å", "æ", "ä", "è", "é", "ç", "ï", "û", "Ô", "ø")
def fix_enc(obj):
    """递归修复 mojibake：UTF-8 字节被按 latin-1 解码的乱码，回转还原。"""
    if isinstance(obj, dict):
        return {k: fix_enc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fix_enc(x) for x in obj]
    if isinstance(obj, str):
        # 仅当命中 mojibake 特征字符才尝试回转，避免误伤正常中文
        if any(ch in obj for ch in _MOJIBAKE_CHARS):
            try:
                return obj.encode("latin-1").decode("utf-8")
            except Exception:
                return obj
        return obj
    return obj

# ---------------- HTTP 抓取（带 gzip 自动解压） ----------------
def http_get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read()
    # 服务器常返回 gzip 压缩而 urllib 不解压，按 magic bytes 自动解压
    if raw[:2] == b"\x1f\x8b":
        try:
            import gzip
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return raw

def fetch_page(url):
    raw = http_get(url)
    txt = raw.decode("utf-8", errors="replace")
    return txt

# ---------------- JS 数据块提取 + Node 求值 ----------------
def extract_inline_scripts(html):
    """提取 HTML 中所有无 src 的内联 <script> 内容"""
    return re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html, re.S)

_NODE_EVAL = r"""
const fs=require('fs');
let src=fs.readFileSync(0,'utf8');
let idx=src.indexOf('=[');
if(idx<0) idx=src.indexOf('= [');
if(idx<0){process.stdout.write('NOARRAY');process.exit(0);}
const start=src.indexOf('[',idx);
let depth=0;
for(let k=start;k<src.length;k++){
  const ch=src[k];
  if(ch==='[') depth++;
  else if(ch===']'){ depth--; if(depth===0){ const arr=src.slice(start,k+1); try{ process.stdout.write(JSON.stringify(new Function('return ('+arr+');')())); }catch(e){ process.stdout.write('EVALERR:'+e.message); } process.exit(0);} }
}
process.stdout.write('NOEND');
"""

def js_block_to_json(block_text):
    """用 Node 求值 JS 字面量块 → JSON 对象（list[0] 通常为数据）"""
    p = subprocess.run(["node", "-e", _NODE_EVAL], input=block_text.encode("utf-8"),
                       capture_output=True, timeout=60)
    out = p.stdout.decode("utf-8", errors="replace").strip()
    if out.startswith(("NOARRAY", "EVALERR", "NOEND")):
        return None
    try:
        return json.loads(out)
    except Exception:
        return None

def _data_score(entry):
    """评估某对象的数据完整度，用于挑选最全的数据块"""
    score = 0
    for key in ("data", "allData", "eventTrend", "records", "odds", "integrals", "datalen"):
        if isinstance(entry, dict) and entry.get(key) is not None:
            score += 2
            v = entry[key]
            if isinstance(v, (list, dict)) and len(v) > 0:
                score += 1
    return score

def extract_board_json(html):
    """从页面 HTML 提取最全的数据块 JSON（data/allData/eventTrend 等）"""
    best, best_score = None, -1
    for script in extract_inline_scripts(html):
        if len(script) < 50:
            continue
        data = js_block_to_json(script)
        if not data:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sc = _data_score(entry)
            if sc > best_score:
                best_score, best = sc, entry
    return fix_enc(best) if best else None

# ---------------- 变化页（欧赔/亚盘）解析 ----------------
def clean(s):
    import html as htmlmod
    return htmlmod.unescape(re.sub(r"\s+", " ", s)).strip()

def parse_change_table(txt):
    """解析变化页：返回 title, headers, rows"""
    m = re.search(r'<div class="z9odds2list[^"]*"[^>]*>\s*(.*?)(?=</div>\s*<div class="z8hspace"|<!--|$)', txt, re.S)
    if not m:
        m = re.search(r'<div class="z9odds2list[^"]*"[^>]*>(.*)', txt, re.S)
    seg = m.group(0) if m else txt
    tm = re.search(r'<h3[^>]*>(.*?)</h3>', seg)
    title = clean(tm.group(1)) if tm else ""
    hm = re.search(r'<ul class="z8thead">(.*?)</ul>', seg, re.S)
    headers = [clean(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', hm.group(1), re.S)] if hm else []
    rows = []
    for rm in re.finditer(r'<ul class="z8tr">(.*?)</ul>', seg, re.S):
        cells = [clean(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', rm.group(1), re.S)]
        rows.append(cells)
    return title, headers, rows

# ---------------- 新聚合接口（info-new-lists 全场一览） ----------------
# 2026-09-01 站点改版：旧接口 info-new-list-spf/rq/<mid>-<sid>-0-3|0-1/ 全部下线(HTTP 400)
# 新接口 info-new-lists/<mid>-<sid>-4/ 每家公司一个页面，内含多张变化表（标题→业务键）
_LISTS_TABLE_KEY = {"胜平负": "spf", "让球变化": "rq", "进球数变化": "dxq"}

def parse_lists_page(txt):
    """解析 info-new-lists 聚合页：返回 {表标题: {title, headers, rows, n}}"""
    out = {}
    for t in re.split(r'<div class="z8table', txt)[1:]:
        tm = re.search(r'<h3[^>]*>(.*?)</h3>', t, re.S)
        title = clean(tm.group(1)) if tm else ""
        hm = re.search(r'<ul class="z8thead">(.*?)</ul>', t, re.S)
        headers = [clean(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', hm.group(1), re.S)] if hm else []
        rows = []
        for rm in re.finditer(r'<ul class="z8tr">(.*?)</ul>', t, re.S):
            cells = [clean(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', rm.group(1), re.S)]
            rows.append(cells)
        out[title] = {"title": title, "headers": headers, "rows": rows, "n": len(rows)}
    return out

# ---------------- 板块页抓取清单 ----------------
def build_urls(match_id):
    urls = []
    # 数据板块页（含内联 JS 块：detail/lineup/fenxi/stats/bifa/欧赔亚盘总表）
    for key, path in [("detail", "live-detail"), ("lineup", "live-lineup"),
                      ("fenxi", "live-fenxi-game"), ("stats", "data-integral"),
                      ("bifa", "live-bifa"), ("odds1x2", "info-new-1x2"),
                      ("oddsah", "info-new-ah")]:
        urls.append((key, f"{LIVE}{path}/{match_id}/"))
    # 20 家公司欧赔/亚盘/大小球变化（新聚合接口：info-new-lists/<mid>-<sid>-4/ 全场一览，每家公司 1 页）
    for sid, name in SIDS:
        urls.append((f"lists_{sid}", f"{LIVE}info-new-lists/{match_id}-{sid}-4/"))
    return urls

# ---------------- 主流程：并发抓取 + 解析 ----------------
def extract_match(match_id, outdir, workers=12, use_cache=True):
    """抓取并解析一场比赛，输出 structured.json 到 outdir"""
    os.makedirs(outdir, exist_ok=True)
    cache_dir = os.path.join(outdir, "html")
    os.makedirs(cache_dir, exist_ok=True)
    urls = build_urls(match_id)
    html_store = {}

    def job(item, tries=3):
        """单页抓取，失败自动重试（站点间歇性 400 限流应对；退避固定 1s 避免拖慢批量）"""
        key, url = item
        fpath = os.path.join(cache_dir, f"{key}.html")
        if use_cache and os.path.exists(fpath):
            with open(fpath, "rb") as f:
                txt = f.read().decode("utf-8", errors="replace")
            return key, txt, True
        last_err = None
        for attempt in range(tries):
            try:
                txt = fetch_page(url)
                with open(fpath, "wb") as f:
                    f.write(txt.encode("utf-8", errors="replace"))
                return key, txt, False
            except Exception as e:
                last_err = str(e)
                if attempt < tries - 1:
                    time.sleep(1)
        return key, None, last_err

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(job, it) for it in urls]
        for fut in as_completed(futs):
            key, txt, flag = fut.result()
            html_store[key] = txt

    # 解析各板块
    result = {"match_id": match_id, "boards": {}, "changes": {}, "warnings": []}

    # 1) 板块页：提取内联 JS 块求值（自动选数据最全块）
    for key in ["detail", "lineup", "fenxi", "stats", "bifa", "odds1x2", "oddsah"]:
        txt = html_store.get(key)
        if not txt:
            result["warnings"].append(f"{key}: 抓取失败")
            continue
        data = extract_board_json(txt)
        if data:
            result["boards"][key] = data
        else:
            result["warnings"].append(f"{key}: 未提取到数据块")

    # 2) 20 家变化页解析（新聚合接口：每家公司一个页面，含 欧赔/亚盘/大小球 三张表）
    for sid, name in SIDS:
        row = {"name": name, "spf": None, "rq": None, "dxq": None}
        txt = html_store.get(f"lists_{sid}")
        if txt:
            tables = parse_lists_page(txt)
            for ttitle, tdata in tables.items():
                key = _LISTS_TABLE_KEY.get(ttitle)
                if key:
                    row[key] = tdata
        result["changes"][name] = row

    # 统计
    ok_boards = sum(1 for k in ["detail", "lineup", "fenxi", "stats", "bifa", "odds1x2", "oddsah"]
                    if result["boards"].get(k))
    ok_changes = sum(1 for name in [x[1] for x in SIDS]
                     if result["changes"].get(name, {}).get("spf") or result["changes"].get(name, {}).get("rq"))
    result["summary"] = {"boards_ok": ok_boards, "boards_total": 7,
                         "companies_with_change": ok_changes, "companies_total": len(SIDS)}

    spath = os.path.join(outdir, "structured.json")
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result

if __name__ == "__main__":
    import sys, time
    mid = sys.argv[1] if len(sys.argv) > 1 else "14586460"
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "match_data", mid)
    t0 = time.time()
    r = extract_match(mid, outdir, workers=12)
    t1 = time.time()
    print(f"抓取+解析完成，耗时 {t1-t0:.1f}s")
    print("板块命中:", r["summary"])
    print("warnings:", r["warnings"][:10])
