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

news_list = []
seen_titles = set()

for url in RSS_FEEDS:
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]:
            title = entry.title.strip() if hasattr(entry, 'title') else ""
            # 核心变动：抓取超链接
            link = entry.link.strip() if hasattr(entry, 'link') else ""

            if title and title not in seen_titles:
                seen_titles.add(title)
                # 核心变动：存入包含 title 和 link 的字典
                news_list.append({
                    "title": title,
                    "link": link
                })
    except Exception as e:
        print(f"抓取失败 {url}: {e}")

os.makedirs("data", exist_ok=True)

with open("data/global_titles.json", "w", encoding="utf-8") as f:
    json.dump(
        news_list,
        f,
        ensure_ascii=False,
        indent=2
    )

print(f"海外数据抓取完成：{len(news_list)} 条")
