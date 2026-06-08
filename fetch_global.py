import json
import feedparser
import os

RSS_FEEDS = [

    # OpenAI
    "https://openai.com/news/rss.xml",

    # NVIDIA
    "https://blogs.nvidia.com/feed/",

    # CNBC
    "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    "https://www.cnbc.com/id/19832390/device/rss/rss.html",

    # TechCrunch
    "https://techcrunch.com/feed/",

    # Bloomberg
    "https://feeds.bloomberg.com/technology/news.rss",
    "https://feeds.bloomberg.com/economics/news.rss",

    # VentureBeat AI
    "https://venturebeat.com/ai/feed/",

    # MIT Technology Review
    "https://www.technologyreview.com/feed/",

    # The Verge AI
    "https://www.theverge.com/rss/index.xml"
]

titles = []

for url in RSS_FEEDS:

    try:

        feed = feedparser.parse(url)

        for entry in feed.entries[:30]:

            title = entry.title.strip()

            if title:

                titles.append(title)

    except:

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

print(f"海外标题：{len(titles)}")
