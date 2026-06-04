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

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

titles = []

for a in soup.find_all("a"):

    text = a.get_text(strip=True)

    if len(text) > 12:
        titles.append(text)

print("\n".join(titles[:20]))
