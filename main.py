import os
import json
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 读取关键词
with open("keywords.json", "r", encoding="utf-8") as f:
    keywords = json.load(f)

# 读取标题
with open("data/titles.json", "r", encoding="utf-8") as f:
    titles = json.load(f)

result = {}

for keyword in keywords:
    count = 0

    for title in titles:
        if keyword in title:
            count += 1

    if count > 0:
        result[keyword] = count

result = dict(
    sorted(
        result.items(),
        key=lambda x: x[1],
        reverse=True
    )
)

message = "【A股AI超级雷达】\n\n"
message += "最近监测热点：\n\n"

for k, v in result.items():

    if v >= 3:
        stars = "★★★★★"
    elif v >= 2:
        stars = "★★★★"
    else:
        stars = "★★★"

    message += f"{stars} {k}（{v}）\n"

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)
