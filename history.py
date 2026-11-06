"""毎日の記録（data/history.csv）の読み書きと、ジャンルの集計（通信しない）。

1行＝その日の上位の動画1本。送った動画は sent が 1 になる。
送った動画が全体の上位10本に入っていないときは、rank を 0 にして足す（ジャンルの集計には入れない）。
GitHub Actions が毎朝この記録をコミットするので、「60日間更新が無いと定期実行が止まる」も防げる。
"""

import csv
from collections import Counter
from datetime import date, timedelta

import config

COLUMNS = ["date", "rank", "video_id", "title", "channel", "duration_sec",
           "views", "views_per_day", "published_at", "genre", "sent"]


def load(path=config.HISTORY_FILE):
    """記録を読む。ファイルがまだ無ければ空のリスト。"""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def sent_ids(rows):
    """これまでに送った動画の ID の集まり（同じ動画を二度送らないため）。"""
    return {r["video_id"] for r in rows if r.get("sent") == "1"}


def make_rows(today, shorts, picks, genres):
    """今日の上位の動画と、送る動画を、記録の行の形にする。

    shorts：全体の上位 TOP_N 本（rank 1〜）
    picks：今日送る動画。上位に入っていなければ rank 0 で最後に足す
    genres：{動画ID: ジャンル}
    """
    pick_ids = {v["id"] for v in picks}
    top_ids = {v["id"] for v in shorts}
    ranked = [(rank, v) for rank, v in enumerate(shorts, start=1)]
    ranked += [(0, v) for v in picks if v["id"] not in top_ids]
    rows = []
    for rank, v in ranked:
        rows.append({
            "date": today.isoformat(),
            "rank": rank,
            "video_id": v["id"],
            "title": v["title"],
            "channel": v["channel"],
            "duration_sec": v["duration"],
            "views": v["views"],
            "views_per_day": round(v["views_per_day"]),
            "published_at": v["published_at"],
            "genre": genres.get(v["id"], config.UNKNOWN_GENRE),
            "sent": 1 if v["id"] in pick_ids else 0,
        })
    return rows


def append(rows, path=config.HISTORY_FILE):
    """記録の最後に行を足す。ファイルが無ければ、見出しの行から作る。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def genre_summary(rows, today, days=config.SUMMARY_DAYS):
    """直近 days 日（今日を含む）に上位に入った動画のジャンルを数える。

    同じ動画が何日も上位に入ることがあるので、動画ごとに1回だけ数える（1本のバズで偏らないため）。
    「未分類」（AI が使えなかった日）と、上位の外から送った動画（rank 0）は数えない
    （興味のあるジャンルで選んだ動画を数えると、集計が偏るため）。
    返すもの：(ジャンルと本数のリスト（多い順）, 数えた本数)
    """
    start = today - timedelta(days=days - 1)
    genre_by_video = {}
    for r in rows:
        try:
            d = date.fromisoformat(r["date"])
        except (KeyError, ValueError):
            continue
        if str(r.get("rank", "1")) == "0":
            continue
        if start <= d <= today and r.get("genre") in config.GENRES:
            genre_by_video[r["video_id"]] = r["genre"]  # 新しい日の分類で上書き
    counts = Counter(genre_by_video.values())
    return counts.most_common(), len(genre_by_video)
