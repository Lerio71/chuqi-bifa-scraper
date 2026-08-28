#!/bin/bash
# 云服务器 crontab 配置脚本
# 在云服务器上执行: bash server/setup_crontab.sh

PROJECT_DIR="/opt/chuqi-bifa-scraper"
PYTHON="/usr/bin/python3"
LOG_DIR="/var/log/bifa_scraper"

mkdir -p "$LOG_DIR"

# 生成 crontab 内容
cat << 'CRONTAB_EOF' > /tmp/bifa_crontab
# ===========================================
# 出奇体育必发交易指数快照采集
# ===========================================

# 赛前24小时快照（每日12:00）
0 4 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_24h >> /var/log/bifa_scraper/pre_24h.log 2>&1

# 赛前12小时快照（每日18:00）
0 10 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_12h >> /var/log/bifa_scraper/pre_12h.log 2>&1

# 赛前6小时快照（每日22:00）
0 14 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_6h >> /var/log/bifa_scraper/pre_6h.log 2>&1

# 赛前3小时快照（每日01:00）
0 17 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_3h >> /var/log/bifa_scraper/pre_3h.log 2>&1

# 赛前1小时快照（每日03:00）
0 19 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_1h >> /var/log/bifa_scraper/pre_1h.log 2>&1

# 赛前30分钟快照（每日03:30）
30 19 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_30min >> /var/log/bifa_scraper/pre_30min.log 2>&1

# 赛前5分钟快照（每日03:55，覆盖大部分晚间比赛）
55 19 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label pre_5min >> /var/log/bifa_scraper/pre_5min.log 2>&1

# === 高频采集（仅云服务器，GitHub Actions 无法实现） ===
# 比赛时段每2分钟采集一次（04:00-06:00 北京时间覆盖大部分比赛进行中）
*/2 20-22 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label inplay >> /var/log/bifa_scraper/inplay.log 2>&1

# 赛后快照（每日06:00）
0 22 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --label post >> /var/log/bifa_scraper/post.log 2>&1

# 生成每日报告（每日06:10）
10 22 * * * cd /opt/chuqi-bifa-scraper && /usr/bin/python3 run.py --report >> /var/log/bifa_scraper/report.log 2>&1

# === 数据同步到 GitHub（可选，每10分钟推送一次） ===
*/10 * * * * cd /opt/chuqi-bifa-scraper && git add data/ && git commit -m "auto: bifa snapshot $(date +\%Y-\%m-\%d_\%H:\%M)" && git push origin main >> /var/log/bifa_scraper/git_push.log 2>&1

CRONTAB_EOF

# 安装 crontab
crontab /tmp/bifa_crontab
echo "crontab 已安装，当前配置:"
crontab -l
echo ""
echo "日志目录: $LOG_DIR"
echo "数据目录: $PROJECT_DIR/data/"
