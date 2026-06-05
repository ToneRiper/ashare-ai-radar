import os
import json
import requests
from bs4 import BeautifulSoup

# 创建目录
os.makedirs("data", exist_ok=True)

url = "https://www.ndrc.gov.cn/xwdt/xwfb/"

r = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    },
    timeout=20
)

r.encoding = r.apparent_encoding

print("状态码:", r.status_code)

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

titles = []

for a in soup.find_all("a"):

    text = a.get_text(strip=True)

    if len(text) > 12:
        titles.append(text)

# 去重
titles = list(dict.fromkeys(titles))

with open(
    "data/ndrc_titles.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        titles,
        f,
        ensure_ascii=False,
        indent=2
    )

print(
    f"保存发改委标题 {len(titles)} 条"
)

print("\n====================\n")

for i, title in enumerate(
    titles[:20],
    start=1
):
    print(f"{i}. {title}")

print("\n====================\n")
