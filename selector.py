"""集めた動画から、ショートを選んで並べるための計算（通信しない）。

ここの関数は通信しないので、単体テスト（tests/test_selector.py）で確かめられる。
"""

import re
from datetime import datetime

import config

# ひらがな（ぁ〜ゖ）とカタカナ（ァ〜ヺ・ー）。漢字だけだと中国語の動画も入るので、かなで判定する
KANA = re.compile(r"[ぁ-ゖァ-ヺー]")
# ハッシュタグ（#赤ちゃん など）。海外の動画が日本語のハッシュタグだけ付けていることがあるので、判定の前に除く
HASHTAG = re.compile(r"[#＃]\S+")

# YouTube の長さの書き方（例：PT1M5S＝1分5秒、PT42S＝42秒、P0D＝ライブ配信中）
DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(text):
    """YouTube の長さ（PT1M5S など）を秒に直す。読めない形なら 0 を返す。"""
    m = DURATION.match(text or "")
    if not m:
        return 0
    days, hours, minutes, seconds = (int(x or 0) for x in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def is_japanese(title, description=""):
    """タイトルか説明文に、ひらがな・カタカナが1文字でもあれば日本語の動画とみなす（ハッシュタグは除いて見る）。"""
    return bool(KANA.search(HASHTAG.sub("", title or "")) or KANA.search(HASHTAG.sub("", description or "")))


def like_rate(views, likes):
    """いいね率（いいね数 ÷ 再生数）。いいね数が非公開（None）や再生0なら None を返す。"""
    if likes is None or not views:
        return None
    return likes / views


def days_since(published_at, now):
    """投稿からの日数（小数）。published_at は YouTube の形（2026-11-02T10:00:00Z）。"""
    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return (now - published).total_seconds() / 86400


def views_per_day(views, published_at, now):
    """1日あたりの再生数。投稿から1日未満なら「1日」として割る（数時間の動画が極端に大きくならないため）。"""
    return views / max(days_since(published_at, now), 1)


def to_video(item, now):
    """YouTube の返事（videos.list の1件）を、使いやすい形の辞書に直す。"""
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    views = int(stats.get("viewCount", 0))
    likes = int(stats["likeCount"]) if "likeCount" in stats else None
    published_at = snippet.get("publishedAt", "")
    return {
        "id": item["id"],
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "channel": snippet.get("channelTitle", ""),
        "published_at": published_at,
        "duration": parse_duration(item.get("contentDetails", {}).get("duration", "")),
        "views": views,
        "likes": likes,
        "days": days_since(published_at, now) if published_at else 0,
        "views_per_day": views_per_day(views, published_at, now) if published_at else 0,
    }


def filter_candidates(videos, japan_only=config.JAPAN_ONLY):
    """ショートの候補に絞る：1〜180秒・日本語（設定による）・広告っぽくない。

    本物のショートか（縦長か）は、ここでは分からない。youtube_client.is_real_short で確かめる。
    """
    result = []
    for v in videos:
        if not (1 <= v["duration"] <= config.MAX_SHORT_SECONDS):
            continue  # 0秒はライブ配信、181秒以上はショートではない
        if japan_only and not is_japanese(v["title"], v["description"]):
            continue
        rate = like_rate(v["views"], v["likes"])
        if rate is not None and rate < config.MIN_LIKE_RATE:
            continue  # いいね率がとても低い＝広告で再生だけ伸びた動画
        result.append(v)
    return result


def sort_by_growth(videos):
    """1日あたりの再生数が多い順に並べる（今まさに伸びている順）。"""
    return sorted(videos, key=lambda v: v["views_per_day"], reverse=True)




def choose(videos, genres, judge, interest=config.INTEREST_GENRES, n=config.SEND_COUNT,
           max_tries=config.MAX_ANALYSES, per_genre=config.MAX_TRIES_PER_GENRE):
    """送る動画を選ぶ：興味のあるジャンルから、違うジャンルを1本ずつ、上から n 本まで。

    videos：1日あたりの再生数の順に並んだ、まだ送っていない本物のショート
    genres：{動画ID: ジャンル}（タイトルと説明文から分けたもの）
    judge：動画を見て分析する関数。分析（genre を含む辞書）か、AI が使えなければ None を返す
    動画を見たらジャンルが違った（興味の外・もう選んだジャンル）ときは、その動画を飛ばして次を見る。
    分析は全部で max_tries 回、1つのジャンルで per_genre 回まで（時間と無料枠をかけすぎないため）。
    返すもの：[(動画, 分析 または None, ジャンル), ...]（1日あたりの再生数の順。忙しい日は1本目だけ見ればよい）
    """
    items, used, tries, tries_by_genre = [], set(), 0, {}
    for v in videos:
        if len(items) >= n or tries >= max_tries:
            break
        genre = genres.get(v["id"])
        if genre not in interest or genre in used:
            continue  # 同じジャンルの2本目は飛ばす（ジャンルによる構成の違いを比べやすくするため）
        if tries_by_genre.get(genre, 0) >= per_genre:
            continue
        tries += 1
        tries_by_genre[genre] = tries_by_genre.get(genre, 0) + 1
        analysis = judge(v)
        if analysis is not None and analysis["genre"] != genre:
            if analysis["genre"] not in interest or analysis["genre"] in used:
                continue
            genre = analysis["genre"]  # 動画を見て決めたジャンルのほうが確か
        items.append((v, analysis, genre))
        used.add(genre)
    return items
