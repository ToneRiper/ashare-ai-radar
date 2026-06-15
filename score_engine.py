def calc_score(
    policy,
    total_hot,
    streak
):

    score = 0

    # 今日政策
    score += policy * 5

    # 累计热度
    score += total_hot * 0.2

    # 连续升温
    score += streak * 8

    return round(score, 1)
