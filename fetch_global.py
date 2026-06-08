import json
import feedparser
import os

RSS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://blogs.nvidia.com/feed/",
    "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    "https://www.cnbc.com/id/19832390/device/rss/rss.html"
]

titles = []

for url in RSS_FEEDS:

    try:

        feed = feedparser.parse(url)

        for entry in feed.entries[:20]:

            title = entry.title.strip()

            if title:

                titles.append(title)

    except Exception:

        pass

titles = list(dict.fromkeys(titles))

os.makedirs("data", exist_ok=True)

with open(
    "data/global_titles.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        titles,
        f,
        ensure_ascii=False,
        indent=2
    )

print("海外标题:", len(titles))
