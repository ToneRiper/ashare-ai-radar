import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

os.makedirs("data", exist_ok=True)
url = "https://www.ndrc.gov.cn/xwdt/xwfb/"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20
)
r.encoding = r.apparent_encoding
print("状态码:", r.status_code)

soup = BeautifulSoup(r.text, "html.parser")
news_list = []
seen_titles = set()

for a in soup.find_all("a"):
    text = a.get_text(strip=True)
    href = a.get("href", "")

    if len(text) > 12 and text not in seen_titles:
        seen_titles.add(text)
        full_link = urljoin(url, href) if href else ""
        news_list.append({
            "title": text,
            "link": full_link
        })

with open("data/ndrc_titles.json", "w", encoding="utf-8") as f:
    json.dump(news_list, f, ensure_ascii=False, indent=2)

print(f"保存发改委标题 {len(news_list)} 条")
