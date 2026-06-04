import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

keywords = {
    "机器人": 8,
    "AI Agent": 6,
    "算力": 5,
    "创新药": 3,
    "低空经济": 2
}

message = "【A股AI超级雷达】\n\n"
message += "今日政策热点：\n\n"

for k, v in keywords.items():

    if v >= 8:
        stars = "★★★★★"
    elif v >= 6:
        stars = "★★★★"
    elif v >= 4:
        stars = "★★★"
    else:
        stars = "★★"

    message += f"{stars} {k}（{v}）\n"

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)
