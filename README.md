# 出奇体育必发交易指数快照采集工具

从出奇体育（chuqi.com）定时采集足球比赛不同时间段的必发交易指数快照数据。

## 数据来源

- **网站**: 出奇体育 https://live.chuqi.com
- **必发页面**: `https://live.chuqi.com/football/live-bifa/{eventid}/`
- **数据方式**: 服务端渲染 HTML，直接解析页面即可（无需逆向 API）
- **采集内容**:

| 数据 | 字段 |
|------|------|
| 交易汇总 | 项(主/和/客) × 价、交易量、比例、盈亏、盈亏指数、冷热指数 |
| 大额明细 | 价、交易量、比例、时间戳（按主胜/平局/客胜分类） |

## 项目结构

```
chuqi-bifa-scraper/
├── scraper/
│   ├── __init__.py
│   ├── match_list.py      # 获取今日有必发数据的比赛列表
│   ├── bifa_scraper.py    # 必发页面爬虫 + HTML 解析
│   └── storage.py         # 快照存储 + 日报生成
├── server/
│   ├── cron_scraper.py    # 云服务器高频采集脚本
│   └── setup_crontab.sh   # crontab 一键配置
├── data/                   # 快照数据（按日期/比赛ID组织）
├── .github/workflows/
│   └── scrape-bifa.yml    # GitHub Actions 定时工作流
├── run.py                  # 主入口
├── requirements.txt
└── README.md
```

## 数据存储结构

```
data/
  2026-08-28/
    match_list.json                          # 当日比赛列表
    13210524/                                # 比赛ID
      20260828_120000__pre_24h.json          # 赛前24h快照
      20260828_180000__pre_12h.json          # 赛前12h快照
      20260828_220000__pre_6h.json            # 赛前6h快照
      20260828_010000__pre_3h.json           # 赛前3h快照
      20260828_030000__pre_1h.json           # 赛前1h快照
      20260828_033000__pre_30min.json        # 赛前30min快照
      20260828_035500__pre_5min.json         # 赛前5min快照
      20260828_040200__inplay.json           # 比赛中快照
      20260828_041800__inplay.json           # 比赛中快照
      20260828_061500__post.json             # 赛后快照
    daily_report_2026-08-28.json             # 每日汇总报告
```

## 快照 JSON 格式

```json
{
  "eventid": "13210524",
  "url": "https://live.chuqi.com/football/live-bifa/13210524/",
  "snapshot_time": "2026-08-28T14:30:00+08:00",
  "summary": [
    {
      "side": "主",
      "price": 2.18,
      "volume": 5442200,
      "ratio": 81,
      "pnl": -5038287,
      "pnl_index": -93,
      "hot_cold_index": 0.09
    },
    {
      "side": "和",
      "price": 3.45,
      "volume": 488600,
      "ratio": 7,
      "pnl": 4052993,
      "pnl_index": 75,
      "hot_cold_index": 0.83
    },
    {
      "side": "客",
      "price": 3.95,
      "volume": 766500,
      "ratio": 11,
      "pnl": 3127850,
      "pnl_index": 61,
      "hot_cold_index": 5.89
    }
  ],
  "large_trades": {
    "主": [
      {"price": 2.48, "volume": 1131079, "ratio": 82.23, "time": "05-24 01:51"},
      {"price": 2.24, "volume": 436246, "ratio": 82.24, "time": "05-24 02:46"}
    ],
    "和": [],
    "客": []
  }
}
```

## 方案：GitHub Actions 定时采集（完全免费）

**公开仓库无执行分钟数限制**，拆分为 4 个 workflow 文件实现全天候覆盖。

### 部署步骤

1. **创建公开仓库**，将项目代码推送到 GitHub
2. **确保仓库 Settings → Actions → General → Workflow permissions** 设置为 `Read and write permissions`
3. 自动按以下时间表运行（北京时间）:

### 采集时间表

#### 1. 赛前快照（scrape-pre-match.yml）

| 北京时间 | 标签 | 说明 |
|---------|------|------|
| 12:00 | pre_24h | 赛前24小时 |
| 18:00 | pre_12h | 赛前12小时 |
| 22:00 | pre_6h | 赛前6小时 |
| 01:00 | pre_3h | 赛前3小时 |
| 03:00 | pre_1h | 赛前1小时 |
| 03:30 | pre_30min | 赛前30分钟 |
| 03:45 | pre_15min | 赛前15分钟 |

#### 2. 比赛中高频（scrape-inplay-late.yml）— 每10分钟

| 北京时间 | 标签 | 说明 |
|---------|------|------|
| 01:00-05:50 每10分钟 | inplay | 欧洲联赛主要比赛时段 |

#### 3. 比赛中高频（scrape-inplay-evening.yml）— 每10分钟

| 北京时间 | 标签 | 说明 |
|---------|------|------|
| 18:00-22:50 每10分钟 | inplay | 早场/亚洲比赛时段 |

#### 4. 赛后 + 日报（scrape-post-report.yml）

| 北京时间 | 标签 | 说明 |
|---------|------|------|
| 06:00 | post | 赛后最终快照 |
| 06:10 | report | 生成每日汇总报告 |

### 开机后读取数据

数据自动提交到 GitHub 仓库的 `data/` 目录。开机后只需 `git pull` 即可获取所有时间段快照:

```bash
git pull origin main
ls data/2026-08-28/
# 13210524/  13210525/  daily_report_2026-08-28.json  match_list.json
```

## 本地使用

```bash
# 安装依赖
pip install -r requirements.txt

# 采集今日所有比赛的当前快照
python run.py

# 带标签采集
python run.py --label pre_6h

# 指定比赛 ID
python run.py --eventids 13210524,13210525

# 生成每日报告
python run.py --report
```

## 数据分析示例

```python
import json
import glob

# 读取某场比赛的所有快照
files = sorted(glob.glob("data/2026-08-28/13210524/*.json"))

for f in files:
    with open(f) as fp:
        snap = json.load(fp)
    time = snap["snapshot_time"]
    for row in snap["summary"]:
        if row["side"] == "主":
            print(f"{time} | 主胜价: {row['price']} | 交易量: {row['volume']} | 盈亏指数: {row['pnl_index']}")
```

输出:
```
2026-08-28T12:00:00+08:00 | 主胜价: 2.30 | 交易量: 1200000 | 盈亏指数: -20
2026-08-28T18:00:00+08:00 | 主胜价: 2.25 | 交易量: 2800000 | 盈亏指数: -45
2026-08-28T22:00:00+08:00 | 主胜价: 2.18 | 交易量: 5442200 | 盈亏指数: -93
2026-08-28T03:00:00+08:00 | 主胜价: 2.15 | 交易量: 8200000 | 盈亏指数: -110
```

## 注意事项

1. **请求频率**: 出奇体育无严格反爬，但建议保持 1-2 秒间隔
2. **数据时效**: 必发数据在比赛进行中变化最快，赛前数据相对稳定
3. **比赛覆盖**: 并非所有比赛都有必发数据，主要覆盖主流联赛
4. **GitHub Actions 延迟**: cron 触发可能有 5-15 分钟延迟，精确时间采集建议用云服务器
5. **数据备份**: 建议定期将 data/ 目录同步到外部存储
