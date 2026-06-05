import os
import json
import requests
from bs4 import BeautifulSoup

os.makedirs("data", exist_ok=True)

url = "https://www.gov.cn/zhengce/"

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

    if len(text) > 10:
        titles.append(text)

titles = list(dict.fromkeys(titles))

with open(
    "data/gov_titles.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        titles,
        f,
        ensure_ascii=False,
        indent=2
    )

print("国务院标题:", len(titles))

for i, t in enumerate(titles[:20], start=1):
    print(i, t)
