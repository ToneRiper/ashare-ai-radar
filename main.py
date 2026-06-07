import os
import json
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

with open("keywords.json", "r", encoding="utf-8") as f:
    KEYWORDS = json.load(f)

with open("watchlist.json", "r", encoding="utf-8") as f:
    WATCHLIST = json.load(f)

all_titles = []

try:
    with open("data/miit_titles.json", "r", encoding="utf-8") as f:
        all_titles.extend(json.load(f))
except:
    pass

try:
    with open("data/ndrc_titles.json", "r", encoding="utf-8") as f:
        all_titles.extend(json.load(f))
except:
    pass

all_titles = list(dict.fromkeys(all_titles))

print("总标题:", len(all_titles))

result = {}

for topic, aliases in KEYWORDS.items():

    matched_titles = []

    for title in all_titles:

        for alias in aliases:

            if alias in title:

                matched_titles.append(title)

                break

    if matched_titles:

        result[topic] = {
            "count": len(matched_titles),
            "titles": matched_titles[:3]
        }

message = "【A股AI超级雷达 V4】\n\n"

if result:

    result = dict(
        sorted(
            result.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )
    )

    for topic, info in result.items():

        score = info["count"]

        if score >= 5:
            stars = "★★★★★"
        elif score >= 3:
            stars = "★★★★"
        else:
            stars = "★★★"

        message += f"{stars} {topic}（{score}）\n\n"

        message += "政策：\n"

        for t in info["titles"]:
            message += f"• {t}\n"

        message += "\n"

        if topic in WATCHLIST:

            message += "观察：\n"

            for stock in WATCHLIST[topic]:
                message += f"• {stock}\n"

        message += "\n--------------------\n\n"

else:

    message += "未发现热点关键词"

print(message)

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }
)
