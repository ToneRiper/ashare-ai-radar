import os
import json
import requests
from bs4 import BeautifulSoup

# 确保目录存在
os.makedirs("data", exist_ok=True)

url = "https://www.miit.gov.cn/RRSdy/index.html"

headers = {
    "User-Agent": "Mozilla/5.0"
}

r = requests.get(
    url,
    headers=headers,
    timeout=20
)

r.encoding = r.apparent_encoding

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

titles = []

for li in soup.find_all("li")[:50]:

    text = li.get_text(strip=True)

    if len(text) > 8:
        titles.append(text)

# 去重
titles = list(dict.fromkeys(titles))

with open(
    "data/miit_titles.json",
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

print("\n====================\n")

for i, title in enumerate(titles[:20], start=1):
    print(f"{i}. {title}")

print("\n====================\n")
