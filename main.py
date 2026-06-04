import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

url = "https://www.gov.cn"

msg = "【A股AI超级雷达】\n\n"

try:
    r = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    msg += f"状态码: {r.status_code}\n"
    msg += f"页面长度: {len(r.text)}\n"

except Exception as e:
    msg += f"错误:\n{str(e)}"

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": msg
    }
)
