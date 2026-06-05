import os
import json
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =====================
# 调试目录
# =====================

print("\n===== 当前目录 =====")
print(os.listdir("."))

if os.path.exists("data"):
    print("\n===== data目录 =====")
    print(os.listdir("data"))

if os.path.exists("数据"):
    print("\n===== 数据目录 =====")
    print(os.listdir("数据"))

# =====================
# 读取关键词
# =====================

with open(
    "keywords.json",
    "r",
    encoding="utf-8"
) as f:

    keywords = json.load(f)

# =====================
# 读取工信部标题
# =====================

miit_titles = []

try:

    with open(
        "data/miit_titles.json",
        "r",
        encoding="utf-8"
    ) as f:

        miit_titles = json.load(f)

except Exception as e:

    print("MIIT READ ERROR:", e)

# =====================
# 读取发改委标题
# =====================

ndrc_titles = []

try:

    with open(
        "data/ndrc_titles.json",
        "r",
        encoding="utf-8"
    ) as f:

        ndrc_titles = json.load(f)

except Exception as e:

    print("NDRC READ ERROR:", e)

# =====================
# 合并标题
# =====================

titles = miit_titles + ndrc_titles

print("\n===== 数据统计 =====")
print("工信部标题:", len(miit_titles))
print("发改委标题:", len(ndrc_titles))
print("总标题:", len(titles))

# =====================
# 热点统计
# =====================

result = {}

for keyword in keywords:

    count = 0

    for title in titles:

        if keyword in title:
            count += 1

    if count > 0:
        result[keyword] = count

result = dict(
    sorted(
        result.items(),
        key=lambda x: x[1],
        reverse=True
    )
)

# =====================
# 生成消息
# =====================

message = "【A股AI超级雷达】\n\n"

if result:

    message += "最近监测热点：\n\n"

    for k, v in result.items():

        if v >= 5:
            stars = "★★★★★"
        elif v >= 3:
            stars = "★★★★"
        else:
            stars = "★★★"

        message += f"{stars} {k}（{v}）\n"

else:

    message += "未发现关键词热点"

# =====================
# 发送TG
# =====================

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)

print("\n===== 最终消息 =====")
print(message)
