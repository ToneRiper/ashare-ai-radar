import requests
from bs4 import BeautifulSoup

url = "https://www.miit.gov.cn/RRSdy/index.html"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
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

for i, li in enumerate(li_list[:20], start=1):

    text = li.get_text(strip=True)

    print(i, text[:100])
