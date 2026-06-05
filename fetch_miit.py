import os
import json
import requests
from bs4 import BeautifulSoup

# 创建目录
os.makedirs("data", exist_ok=True)

url = "https://www.miit.gov.cn/RRSdy/index.html"

r = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    },
    timeout=20
)

r.encoding = r.apparent_encoding

print("状态码:", r.status_code)
print("页面长度:", len(r.text))

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

li_list = soup.find_all("li")

print("LI数量:", len(li_list))

titles = []

for li in li_list:

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

print(
    f"保存工信部标题 {len(titles)} 条"
)

print("\n====================\n")

for i, title in enumerate(
    titles[:20],
    start=1
):
    print(i, title)

print("\n====================\n")
