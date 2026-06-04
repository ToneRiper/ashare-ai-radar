import os
import requests
from bs4 import BeautifulSoup

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

url = "https://www.miit.gov.cn/RRSdy/index.html"

headers = {
    "User-Agent": "Mozilla/5.0"
}

r = requests.get(
    url,
    headers=headers,
    timeout=20
)

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

titles = []

for li in soup.find_all("li")[:50]:

    text = li.get_text(strip=True)

    if len(text) > 8:
        titles.append(text)

KEYWORDS = {
    "AI": ["人工智能", "AI"],
    "芯片": ["芯片", "集成电路", "半导体"],
    "机器人": ["机器人", "人形机器人"],
    "脑机接口": ["脑机接口", "脑机"],
    "算力": ["算力"],
    "创新药": ["创新药"],
    "低空经济": ["低空经济"],
    "商业航天": ["商业航天"],
    "工业软件": ["工业软件"],
    "数据要素": ["数据要素"]
}

result = {}

for keyword, aliases in KEYWORDS.items():

    count = 0

    for title in titles:

        for alias in aliases:

            if alias in title:
                count += 1
                break

    if count > 0:
        result[keyword] = count

message = "【A股AI超级雷达】\n\n"

if result:

    message += "工信部热点统计：\n\n"

    result = dict(
        sorted(
            result.items(),
            key=lambda x: x[1],
            reverse=True
        )
    )

    for k, v in result.items():
        message += f"{k}（{v}）\n"

else:

    message += "未发现关键词热点"

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)
