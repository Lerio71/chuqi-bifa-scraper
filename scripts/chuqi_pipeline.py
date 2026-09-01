# -*- coding: utf-8 -*-
"""
chuqi_pipeline.py — 出奇体育比赛数据一键提取 → 复盘表格
用法：
  python chuqi_pipeline.py <match_id> [match_id ...]     # 批量提取多场
  python chuqi_pipeline.py --batch ids.txt               # 从文件读 id 列表（每行一个）
输出：match_data/<id>/<id>_比赛数据.xlsx（7个sheet）
全程纯 HTTP 并发抓取（约3秒/场），无需浏览器。
"""
import os, sys, time, argparse
import chuqi_lib
import chuqi_build


def run(mid, workers=12):
    outdir = os.path.join(os.getcwd(), "match_data", mid)
    t0 = time.time()
    r = chuqi_lib.extract_match(mid, outdir, workers=workers, use_cache=False)
    t1 = time.time()
    xlsx = chuqi_build.main(mid)
    t2 = time.time()
    ok = r["summary"]
    return {
        "id": mid,
        "fetch_s": round(t1 - t0, 1),
        "build_s": round(t2 - t1, 1),
        "total_s": round(t2 - t0, 1),
        "boards": ok["boards_ok"],
        "companies": ok["companies_with_change"],
        "warnings": len(r["warnings"]),
        "xlsx": xlsx,
    }


def main():
    ap = argparse.ArgumentParser(description="出奇体育比赛数据一键提取→复盘表格")
    ap.add_argument("ids", nargs="*", help="比赛ID列表")
    ap.add_argument("--batch", help="从文件读取ID列表（每行一个）")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    ids = list(args.ids)
    if args.batch:
        ids += [ln.strip() for ln in open(args.batch, encoding="utf-8") if ln.strip()]

    if not ids:
        ap.print_help()
        return

    print(f"共 {len(ids)} 场比赛，开始提取...")
    for i, mid in enumerate(ids, 1):
        try:
            r = run(mid, args.workers)
            print(f"[{i}/{len(ids)}] 比赛 {mid}: 抓取{r['fetch_s']}s + 生成{r['build_s']}s "
                  f"(共{r['total_s']}s) | 板块{r['boards']}/7 公司{r['companies']}/20 警告{r['warnings']}")
            print(f"    → {r['xlsx']}")
        except Exception as e:
            print(f"[{i}/{len(ids)}] 比赛 {mid} 失败: {e}")


if __name__ == "__main__":
    main()
