import requests
from bs4 import BeautifulSoup
import json

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

for li in soup.find_all("li")[:30]:

    text = li.get_text(strip=True)

    if len(text) > 8:
        titles.append(text)

with open(
    "data/titles.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        titles,
        f,
        ensure_ascii=False,
        indent=2
    )

print(f"获取到 {len(titles)} 条标题")
