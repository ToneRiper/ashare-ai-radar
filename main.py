import os
import json
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ======================
# 关键词库
# ======================

with open(
    "keywords.json",
    "r",
    encoding="utf-8"
) as f:

    KEYWORDS = json.load(f)

# ======================
# 观察池
# ======================

with open(
    "watchlist.json",
    "r",
    encoding="utf-8"
) as f:

    WATCHLIST = json.load(f)

# ======================
# 历史记录
# ======================

try:

    with open(
        "history.json",
        "r",
        encoding="utf-8"
    ) as f:

        history = json.load(f)

    if not isinstance(history, list):
        history = []

except:

    history = []

history_set = set(history)

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

all_titles = list(
    dict.fromkeys(all_titles)
)

print(
    f"总标题：{len(all_titles)}"
)

# ======================
# 新增标题
# ======================

new_titles = []

for title in all_titles:

    if title not in history_set:

        new_titles.append(title)

print(
    f"新增标题：{len(new_titles)}"
)

if len(new_titles) == 0:

    print("没有新增政策")

    exit()

# ======================
# 热点统计
# ======================

result = {}

for topic, aliases in KEYWORDS.items():

    matched = []

    for title in new_titles:

        for alias in aliases:

            if alias in title:

                matched.append(
                    title
                )

                break

    if matched:

        result[topic] = {
            "count": len(matched),
            "titles": matched[:3]
        }

# ======================
# 消息
# ======================

message = "【A股AI超级雷达 V4.2】\n\n"

message += f"新增政策：{len(new_titles)}条\n\n"

for topic, info in sorted(
    result.items(),
    key=lambda x: x[1]["count"],
    reverse=True
):

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

        message += f"• {title}\n"

    message += "\n"

    if topic in WATCHLIST:

        message += "观察：\n"

        for stock in WATCHLIST[topic]:

            message += f"• {stock}\n"

    message += "\n--------------------\n\n"

print(message)

# ======================
# Telegram
# ======================

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }
)

# ======================
# 保存历史
# ======================

history.extend(
    new_titles
)

with open(
    "history.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        history,
        f,
        ensure_ascii=False,
        indent=2
    )

print(
    f"历史记录已保存：{len(history)}条"
)
