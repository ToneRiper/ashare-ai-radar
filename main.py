import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

message = """
【A股AI超级雷达】

测试版本 V1

今日热点：

1. AI
2. 机器人
3. 算力
4. 低空经济

系统运行正常。
"""

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)
