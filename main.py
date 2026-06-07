import os
import json
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ======================
# 读取关键词库
# ======================

with open(
    "keywords.json",
    "r",
    encoding="utf-8"
) as f:
    KEYWORDS = json.load(f)

# ======================
# 读取观察池
# ======================

with open(
    "watchlist.json",
    "r",
    encoding="utf-8"
) as f:
    WATCHLIST = json.load(f)

# ======================
# 读取标题
# ======================

all_titles = []

try:

    with open(
        "data/miit_titles.json",
        "r",
        encoding="utf-8"
    ) as f:

        all_titles.extend(
            json.load(f)
        )

except:

    pass

try:

    with open(
        "data/ndrc_titles.json",
        "r",
        encoding="utf-8"
    ) as f:

        all_titles.extend(
            json.load(f)
        )

except:

    pass

# 去重
all_titles = list(
    dict.fromkeys(all_titles)
)

print(
    f"总标题: {len(all_titles)}"
)

# ======================
# 热点统计
# ======================

result = {}

for topic, aliases in KEYWORDS.items():

    matched_titles = []

    for title in all_titles:

        for alias in aliases:

            if alias in title:

                matched_titles.append(
                    title
                )

                break

    if matched_titles:

        result[topic] = {
            "count": len(
                matched_titles
            ),
            "titles": matched_titles[:3]
        }

# ======================
# 生成消息
# ======================

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

        message += (
            f"{stars} "
            f"{topic}"
            f"（{score}）\n\n"
        )

        message += "政策：\n"

        for title in info["titles"]:

            message += (
                f"• {title}\n"
            )

        message += "\n"

        if topic in WATCHLIST:

            message += "观察：\n"

            for stock in WATCHLIST[topic]:

                message += (
                    f"• {stock}\n"
                )

        message += (
            "\n"
            "--------------------\n\n"
        )

else:

    message += (
        "未发现热点关键词"
    )

print(message)

# ======================
# Telegram推送
# ======================

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }
)
