"""
健壮的网络请求封装。

统一处理：
  - 模拟浏览器请求头（避免被基础反爬识别为脚本）
  - 会话复用（Cookie / 连接保持）
  - 请求失败 / 被拒（400 / 403 / 429 / 5xx）自动重试 + 指数退避 + 随机抖动
  - 出奇体育偶发 400 "refresh timeout" 时，先用首页预热会话再重试
"""

import time
import random
import requests


# 模拟主流浏览器的请求头，降低被反爬拦截的概率
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

# 首页地址：用于会话预热（触发服务器生成会话/刷新标记）
HOMEPAGE_URL = "https://live.chuqi.com/football/"


def make_session(referer: str | None = None) -> requests.Session:
    """创建带浏览器请求头的会话。"""
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    if referer:
        s.headers["Referer"] = referer
    return s


def fetch(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    referer: str | None = None,
    retries: int = 3,
    backoff: float = 2.0,
    timeout: int = 20,
    warmup_url: str | None = HOMEPAGE_URL,
) -> requests.Response | None:
    """
    带重试的 GET 请求。

    - 网络异常 / 5xx / 429 自动重试（指数退避 + 随机抖动）
    - 400（出奇体育的 "refresh timeout"）先用 warmup_url 预热会话再重试
    - 返回 200 的 Response 即成功；否则返回最后一次 Response 或 None
    """
    headers = dict(session.headers)
    if referer:
        headers["Referer"] = referer

    last = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=timeout)
        except Exception:
            last = None
            time.sleep(backoff * (attempt + 1) * random.uniform(0.7, 1.3))
            continue

        if resp.status_code == 200:
            return resp

        last = resp

        # 400/403/429/5xx → 重试
        if resp.status_code in (400, 403, 429) or resp.status_code >= 500:
            # 400 通常是 "refresh timeout"：预热会话后再试
            if resp.status_code == 400 and warmup_url:
                try:
                    session.get(
                        warmup_url,
                        headers={"Referer": referer or warmup_url},
                        timeout=timeout,
                    )
                except Exception:
                    pass
            time.sleep(backoff * (attempt + 1) * random.uniform(0.7, 1.3))
            continue

        # 其它状态码（如 404/410）直接返回，交由调用方判断
        return resp

    return last
