import os
import json
import requests
from deep_translator import GoogleTranslator

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

for file in [
    "data/miit_titles.json",
    "data/ndrc_titles.json",
    "data/gov_titles.json",
    "data/global_titles.json"
]:

    try:

        with open(
            file,
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
# 自动翻译
# ======================

translated_titles = {}

for title in new_titles:

    try:

        if any(
            '\u4e00' <= c <= '\u9fff'
            for c in title
        ):

            translated_titles[title] = title

        else:

            translated_titles[title] = GoogleTranslator(
                source="auto",
                target="zh-CN"
            ).translate(title)

    except:

        translated_titles[title] = title

# ======================
# 热点统计
# ======================

result = {}

for topic, aliases in KEYWORDS.items():

    matched = []

    for title in new_titles:

        for alias in aliases:

            if alias.lower() in title.lower():

                matched.append(title)

                break

    if matched:

        result[topic] = {
            "count": len(matched),
            "titles": matched[:3]
        }


# ======================
# 热度总榜
# ======================

try:

    with open(
        "hot_rank.json",
        "r",
        encoding="utf-8"
    ) as f:

        hot_rank = json.load(f)

except:

    hot_rank = {}

for topic, info in result.items():

    hot_rank[topic] = hot_rank.get(
        topic,
        0
    ) + info["count"]

with open(
    "hot_rank.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        hot_rank,
        f,
        ensure_ascii=False,
        indent=2
    )

rank_text = "🔥 热度总榜\\n\\n"

for idx, item in enumerate(
    sorted(
        hot_rank.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5],
    start=1
):

    rank_text += (
        f"{idx}. {item[0]}（{item[1]}）\\n"
    )

rank_text += "\\n==================\\n\\n"

# ======================
# 消息
# ======================

message = rank_text + "【A股AI超级雷达 V7】\n\n"

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

        show_title = translated_titles.get(
            title,
            title
        )

        message += f"• {show_title}\n"

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

# ======================
# 趋势数据库
# ======================

try:

    with open(
        "trend.json",
        "r",
        encoding="utf-8"
    ) as f:

        trend = json.load(f)

except:

    trend = {}

run_id = str(
    len(trend) + 1
)

trend[run_id] = {

    topic: info["count"]

    for topic, info in result.items()
}

with open(
    "trend.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        trend,
        f,
        ensure_ascii=False,
        indent=2
    )

print(
    "趋势库已更新"
)

# ======================
# 趋势分析
# ======================

print(
    "\n===== 热度趋势 ====="
)

if len(trend) >= 2:

    keys = list(
        trend.keys()
    )

    latest = trend[
        keys[-1]
    ]

    previous = trend[
        keys[-2]
    ]

    for topic in latest:

        now_count = latest.get(
            topic,
            0
        )

        old_count = previous.get(
            topic,
            0
        )

        if now_count > old_count:

            arrow = "↑"

        elif now_count < old_count:

            arrow = "↓"

        else:

            arrow = "→"

        print(
            f"{topic}: "
            f"{arrow} "
            f"({old_count} -> {now_count})"
        )

else:

    print(
        "趋势数据不足，需要至少运行2次"
    )
