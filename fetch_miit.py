import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

os.makedirs("data", exist_ok=True)
url = "https://www.miit.gov.cn/RRSdy/index.html"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20
)
r.encoding = r.apparent_encoding
print("状态码:", r.status_code)

soup = BeautifulSoup(r.text, "html.parser")
li_list = soup.find_all("li")
print("LI数量:", len(li_list))

news_list = []
seen_titles = set()

for li in li_list:
    text = li.get_text(strip=True)
    a_tag = li.find("a")
    href = a_tag.get("href", "") if a_tag else ""

    if len(text) > 8 and text not in seen_titles:
        seen_titles.add(text)
        full_link = urljoin(url, href) if href else ""
        news_list.append({
            "title": text,
            "link": full_link
        })

with open("data/miit_titles.json", "w", encoding="utf-8") as f:
    json.dump(news_list, f, ensure_ascii=False, indent=2)

print(f"保存工信部标题 {len(news_list)} 条")
