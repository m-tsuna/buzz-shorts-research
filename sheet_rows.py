"""参考動画シートに書く行を作る（通信しない）。

① 動画一覧：1本1行。② シーン分解：1シーン1行。
見出しの順番と、行の中身の順番は、ここで一緒に決める（ずれないように）。
"""

import config

# ① 動画一覧の見出しと、幅（ピクセル）。PC で見る前提で、長い文の列は広くする
LIST_COLUMNS = [
    ("★", 40), ("届いた日", 90), ("ジャンル", 110), ("タイトル", 260), ("URL", 120), ("チャンネル", 120),
    ("尺（秒）", 60), ("再生数", 90), ("1日あたりの再生数", 90), ("いいね率", 70),
    ("構成の型", 100), ("フックの型", 100), ("最初の3秒（言葉・文字）", 260), ("伸びた理由", 260),
    ("真似ポイント", 240), ("撮り方", 80), ("話し方", 90), ("必要なもの", 200), ("テロップ", 240),
    ("BGM・効果音", 220), ("テンポ", 60), ("最後の呼びかけ（CTA）", 200), ("ループの仕掛け", 220),
    ("動画ID", 110), ("自分ならどう作るか（AI の案）", 280), ("自分のメモ", 280),
]
# ② シーン分解の見出しと幅
SCENE_COLUMNS = [
    ("届いた日", 90), ("動画ID", 110), ("タイトル", 220), ("順番", 45), ("秒数", 70), ("役割", 70),
    ("映っているもの", 260), ("言葉", 260), ("テロップ", 200), ("音", 180), ("なぜこうしているか", 280),
]
LIKE_RATE_COLUMN = 10   # いいね率は何列目か（1から数える。％の形で見せるため）
FROZEN_COLUMNS = 4      # 左から何列を固定するか（★〜タイトル。横にスクロールしても、どの動画か分かる）


def safe(value):
    """シートに書く値を整える。

    書き込みは USER_ENTERED（シートに手で打ったのと同じ扱い。URL がリンクになる）なので、
    「=」などで始まる文字は数式として動いてしまう。先頭に ' を付けて、ただの文字にする。
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def list_row(today, video, analysis, genre):
    """① 動画一覧の1行。analysis が None（AI が使えなかった）なら、AI が書く列は空にする。"""
    a = analysis or {}
    likes = video.get("likes")
    rate = round(likes / video["views"], 4) if likes is not None and video["views"] else ""
    row = [
        "", today.isoformat(), genre, video["title"], f"{config.SHORTS_URL}{video['id']}", video["channel"],
        video["duration"], video["views"], round(video["views_per_day"]), rate,
        a.get("structure_type", ""), a.get("hook_type", ""), a.get("first3", ""), a.get("reason", ""),
        a.get("tip", ""), a.get("shooting", ""), a.get("voice", ""), a.get("tools", ""), a.get("telop", ""),
        a.get("sound", ""), a.get("tempo", ""), a.get("cta", ""), a.get("loop", ""),
        video["id"], a.get("my_idea", ""), "",
    ]
    return [safe(v) for v in row]


def scene_rows(today, video, analysis):
    """② シーン分解の行（場面の数だけ）。AI が使えなかった動画は0行。"""
    if not analysis:
        return []
    return [
        [safe(v) for v in [today.isoformat(), video["id"], video["title"], number, s["time"], s["role"],
                           s["visual"], s["words"], s["telop"], s["sound"], s["why"]]]
        for number, s in enumerate(analysis.get("scenes", []), start=1)
    ]


def build(today, items):
    """送った動画（items：(動画, 分析, ジャンル) のリスト）から、① と ② の行を作る。"""
    lists = [list_row(today, v, a, g) for v, a, g in items]
    scenes = [row for v, a, _ in items for row in scene_rows(today, v, a)]
    return lists, scenes
