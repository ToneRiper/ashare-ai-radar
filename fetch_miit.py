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

for li in soup.find_all("li")[:20]:

    text = li.get_text(strip=True)

    if len(text) > 8:
        titles.append(text)

message = "【工信部最新标题调试】\n\n"

for i, title in enumerate(titles[:10], start=1):
    message += f"{i}. {title}\n\n"

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }
)

print(f"获取到 {len(titles)} 条标题")
