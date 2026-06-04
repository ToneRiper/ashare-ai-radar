import requests
from bs4 import BeautifulSoup

url = "https://www.ndrc.gov.cn/xwdt/xwfb/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

r = requests.get(
    url,
    headers=headers,
    timeout=20
)

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

print(f"获取到 {len(titles)} 条标题")

for i, title in enumerate(titles[:20], start=1):
    print(f"{i}. {title}")
