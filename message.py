"""LINE に送る文を組み立てる（通信しない）。"""

import config

WEEKDAYS = "月火水木金土日"


def format_count(n):
    """再生数を読みやすくする（例：5192706 → 519万、123456789 → 1.2億、9800 → 9,800）。"""
    n = int(n)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}億"
    if n >= 10_000:
        return f"{n // 10_000:,}万"
    return f"{n:,}"


def format_age(days):
    """投稿からの時間（例：0.4日 → 9時間前、2.3日 → 2日前）。"""
    if days < 1:
        return f"{max(int(days * 24), 1)}時間前"
    return f"{int(days)}日前"


NUMBERS = "①②③④⑤⑥⑦⑧⑨"


def header(today, count):
    """1行目（日付と本数）。"""
    return f"📱 今日のバズショート（{today.month}/{today.day}・{WEEKDAYS[today.weekday()]}）{count}本"


def video_part(video, number, genre):
    """1本の紹介（番号・ジャンル・タイトル・チャンネル・数字・URL）。"""
    return "\n".join([
        f"{NUMBERS[number - 1]} {genre}",
        video["title"],
        f"{video['channel']}｜{video['duration']}秒｜{format_count(video['views'])}回",
        f"（1日あたり{format_count(video['views_per_day'])}回・投稿{format_age(video['days'])}）",
        f"{config.SHORTS_URL}{video['id']}",
    ])


def analysis_part(analysis):
    """AI の分析。AI が使えなかった動画（None）は、そう伝える。"""
    if analysis is None:
        return "🤖 AI が混んでいて分析できませんでした"
    lines = ["🧩 構成"]
    lines += [f"{s.get('time', '').strip()}：{s['text'].strip()}" if s.get("time") else s["text"].strip()
              for s in analysis["structure"]]
    if analysis["reason"]:
        lines.append(f"💡 伸びた理由：{analysis['reason']}")
    if analysis["tip"]:
        lines.append(f"✍️ 真似ポイント：{analysis['tip']}")
    return "\n".join(lines)


def summary_part(counts, total):
    """ジャンルの集計（日曜に足す）。数えた動画が0本なら None。"""
    if total == 0:
        return None
    lines = [f"📊 この1週間に伸びたジャンル（上位に入った{total}本）"]
    for rank, (genre, n) in enumerate(counts[:config.SUMMARY_TOP], start=1):
        lines.append(f"{rank}位 {genre} {n}本")
    return "\n".join(lines)


def is_summary_day(today):
    """ジャンルの集計を送る日（日曜）か。"""
    return today.weekday() == config.SUMMARY_WEEKDAY


def build(items, today, summary=None):
    """1通分の文を作る。

    items：送る動画のリスト。1つずつ (動画, 分析 または None, ジャンル)
    summary：(ジャンルと本数のリスト, 本数)。日曜だけ渡す。
    """
    parts = [header(today, len(items))]
    for number, (video, analysis, genre) in enumerate(items, start=1):
        parts.append(video_part(video, number, genre) + "\n" + analysis_part(analysis))
    if summary is not None:
        text = summary_part(*summary)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def no_video(today, summary=None):
    """興味のあるジャンルで条件に合うショートが無かった日の文（日曜は集計だけでも送る）。"""
    text = f"📱 {today.month}/{today.day}：今日は興味のあるジャンルで、条件に合うショートが見つかりませんでした"
    extra = summary_part(*summary) if summary is not None else None
    return text + ("\n\n" + extra if extra else "")


def failure(today, reason):
    """YouTube から取れなかった日の文。"""
    return f"⚠️ {today.month}/{today.day}：今日は YouTube から動画を取れませんでした\n{reason}"
