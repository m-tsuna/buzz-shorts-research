"""YouTube から動画を集める（通信する）。

使う API：YouTube Data API v3
- search.list：条件に合う動画の ID を集める（1回100ユニット）
- videos.list：長さ・再生数・いいね数などをまとめて取る（1回1ユニット、50件まで）
鍵は URL ではなくヘッダー（x-goog-api-key）で送る。エラーの表示に URL が出ても、鍵が出ないようにするため。
"""

import functools
from datetime import timedelta

import requests

import config
import selector


class YouTubeError(Exception):
    """YouTube から取れなかったときのエラー（利用者に見せる日本語のメッセージを持つ）。"""


# YouTube のエラーの理由（reason）を、日本語の説明に直す表
REASONS = {
    "quotaExceeded": "今日の無料枠（10,000ユニット）を使い切りました。明日になると戻ります",
    "keyInvalid": "YouTube の API キーが正しくありません。.env（Actions では Secrets）の YOUTUBE_API_KEY を確かめてください",
    "badRequest": "YouTube への頼み方が正しくありません",
    "forbidden": "YouTube の API キーに、この操作の許可がありません",
    "accessNotConfigured": "Google Cloud で YouTube Data API が有効になっていません",
}


def _get(api_key, path, params):
    """YouTube API に GET で問い合わせ、返事（JSON）を返す。失敗したら YouTubeError。"""
    try:
        r = requests.get(
            config.YOUTUBE_API_URL + path,
            params=params,
            headers={"x-goog-api-key": api_key},
            timeout=config.HTTP_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise YouTubeError(f"YouTube につながりませんでした（インターネットの接続を確かめてください：{type(e).__name__}）")
    try:
        data = r.json()
    except ValueError:
        raise YouTubeError(f"YouTube の返事が読めませんでした（HTTP {r.status_code}）")
    if "error" in data:
        errors = data["error"].get("errors") or [{}]
        reason = errors[0].get("reason", "")
        raise YouTubeError(REASONS.get(reason, f"YouTube でエラーが起きました（HTTP {r.status_code}：{reason or '理由不明'}）"))
    return data


def search_ids(api_key, now, days, page_token=None, query=None):
    """直近 days 日の短い動画を、再生数の多い順に50件探す。(動画IDのリスト, 次のページの印) を返す。

    query：探す言葉（例「料理|レシピ」。「|」は「または」）。None なら言葉なしで全体から探す。
    """
    params = {
        "part": "id",
        "type": "video",
        "order": "viewCount",
        "publishedAfter": (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "videoDuration": "short",  # YouTube の「短い」は4分未満。3分以内かは後で確かめる
        "regionCode": config.REGION_CODE,
        "relevanceLanguage": config.RELEVANCE_LANGUAGE,
        "maxResults": config.SEARCH_MAX_RESULTS,
    }
    if page_token:
        params["pageToken"] = page_token
    if query:
        params["q"] = query
    data = _get(api_key, "search", params)
    ids = [item["id"]["videoId"] for item in data.get("items", []) if "videoId" in item.get("id", {})]
    return ids, data.get("nextPageToken")


def collect_ids(api_key, now):
    """3回検索する（直近7日の1・2ページ目＋直近2日）。同じ動画は1つにまとめる。"""
    ids = []
    token = None
    for _ in range(config.SEARCH_PAGES_LONG):
        page, token = search_ids(api_key, now, config.SEARCH_DAYS_LONG, token)
        ids += page
        if not token:
            break  # 次のページが無い
    page, _ = search_ids(api_key, now, config.SEARCH_DAYS_SHORT)
    ids += page
    return list(dict.fromkeys(ids))  # 順番を保ったまま重複を消す


def collect_interest_ids(api_key, now):
    """興味のあるジャンルごとに、ジャンルの言葉で1回ずつ検索する。{ジャンル: 動画IDのリスト} を返す。"""
    return {genre: search_ids(api_key, now, config.SEARCH_DAYS_INTEREST, query=words)[0]
            for genre, words in config.INTEREST_GENRES.items()}


def fetch_videos(api_key, ids, now):
    """動画の ID から、長さ・再生数などの情報をまとめて取る（50件ずつ）。"""
    videos = []
    for i in range(0, len(ids), 50):
        data = _get(api_key, "videos", {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(ids[i:i + 50]),
        })
        videos += [selector.to_video(item, now) for item in data.get("items", [])]
    return videos


@functools.cache  # 同じ動画は1回の実行で1回だけ問い合わせる（上位10本と送る候補の両方で確かめるため）
def is_real_short(video_id):
    """本物のショート（縦長）か確かめる。

    youtube.com/shorts/ID を開くと、ショートでない動画は /watch?v=ID に転送される。
    中身は受け取らず、返事の見出し（HEAD）だけ見る。YouTube の API ではないのでユニットは使わない。
    確かめられなかったとき（通信の失敗）は False にする（違う動画を送るよりよい）。
    """
    try:
        r = requests.head(config.SHORTS_URL + video_id, allow_redirects=False, timeout=config.HTTP_TIMEOUT)
    except requests.exceptions.RequestException:
        return False
    return "/watch" not in r.headers.get("location", "")


def real_shorts(candidates, limit, check=is_real_short):
    """並べた候補を上から確かめ、本物のショートを limit 本集める（全部は確かめない）。

    確かめるのは MAX_SHORTS_CHECKS 本まで（時間をかけすぎないため）。
    """
    shorts = []
    for checks, v in enumerate(candidates):
        if len(shorts) >= limit or checks >= config.MAX_SHORTS_CHECKS:
            break
        if check(v["id"]):
            shorts.append(v)
    return shorts
