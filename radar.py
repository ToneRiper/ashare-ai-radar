import os
import requests
from bs4 import BeautifulSoup

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

all_titles = []

# ====================
# 工信部
# ====================

try:

    url = "https://www.miit.gov.cn/RRSdy/index.html"

    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20
    )

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    for li in soup.find_all("li")[:50]:

        text = li.get_text(strip=True)

        if len(text) > 8:
            all_titles.append(text)

except Exception as e:

    print("MIIT ERROR:", e)

# ====================
# 发改委
# ====================

try:

    url = "https://www.ndrc.gov.cn/xwdt/xwfb/"

    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20
    )

    r.encoding = r.apparent_encoding

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    for a in soup.find_all("a"):

        text = a.get_text(strip=True)

        if len(text) > 12:
            all_titles.append(text)

except Exception as e:

    print("NDRC ERROR:", e)

# ====================
# 关键词映射
# ====================

KEYWORDS = {

    "AI": [
        "人工智能",
        "AI",
        "大模型",
        "智能体"
    ],

    "算力": [
        "算力",
        "智算",
        "计算中心",
        "数据中心"
    ],

    "芯片": [
        "芯片",
        "半导体",
        "集成电路"
    ],

    "机器人": [
        "机器人",
        "人形机器人",
        "具身智能"
    ],

    "新能源": [
        "新能源",
        "动力电池"
    ],

    "工业软件": [
        "工业软件",
        "工业互联网",
        "信息技术标准化"
    ],

    "未来产业": [
        "未来产业"
    ],

    "低空经济": [
        "低空经济"
    ],

    "商业航天": [
        "商业航天"
    ],

    "数据要素": [
        "数据要素",
        "数据资源"
    ]
}

result = {}

for topic, aliases in KEYWORDS.items():

    count = 0

    for title in all_titles:

        for alias in aliases:

            if alias in title:
                count += 1
                break

    if count > 0:
        result[topic] = count

message = "【A股AI超级雷达】\n\n"

if result:

    result = dict(
        sorted(
            result.items(),
            key=lambda x: x[1],
            reverse=True
        )
    )

    for k, v in result.items():

        if v >= 5:
            stars = "★★★★★"
        elif v >= 3:
            stars = "★★★★"
        else:
            stars = "★★★"

        message += f"{stars} {k}（{v}）\n"

else:

    message += "未发现热点关键词\n"

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }
)
