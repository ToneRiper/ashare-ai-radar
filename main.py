import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

keywords = {
    "机器人": 8,
    "AI Agent": 6,
    "算力": 5,
    "芯片": 5,
    "半导体": 4,
    "脑机接口": 3,
    "创新药": 3,
    "低空经济": 2,
    "商业航天": 2,
    "数据要素": 2,
    "工业软件": 2,
    "固态电池": 1,
    "量子科技": 1,
    "6G": 1
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
