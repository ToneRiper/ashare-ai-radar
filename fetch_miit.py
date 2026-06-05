import json
import requests
from bs4 import BeautifulSoup

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

with open(
    "数据/miit_titles.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        titles,
        f,
        ensure_ascii=False,
        indent=2
    )

print(f"保存工信部标题 {len(titles)} 条")
