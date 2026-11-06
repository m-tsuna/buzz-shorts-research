"""selector.py（ショートの選び方の計算）の単体テスト。通信しない。"""

from datetime import datetime, timezone

import selector

NOW = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)


def video(**kw):
    """テスト用の動画を作る（指定しなかった項目は「合格する」値）。"""
    v = {"id": "a", "title": "テスト動画", "description": "", "channel": "ch", "published_at": "2026-11-03T00:00:00Z",
         "duration": 30, "views": 100000, "likes": 1000, "days": 2, "views_per_day": 50000}
    v.update(kw)
    return v


def test_parse_duration():
    assert selector.parse_duration("PT42S") == 42
    assert selector.parse_duration("PT1M5S") == 65
    assert selector.parse_duration("PT3M") == 180
    assert selector.parse_duration("PT1H2M3S") == 3723
    assert selector.parse_duration("P0D") == 0       # ライブ配信中
    assert selector.parse_duration("") == 0
    assert selector.parse_duration("でたらめ") == 0


def test_is_japanese():
    assert selector.is_japanese("ハンコに押されないように")
    assert selector.is_japanese("Can A Robot Do My Chores?", "日本語のせつめい")  # 説明文にかながあれば日本語
    assert not selector.is_japanese("Can A Robot Do My Chores?")
    assert not selector.is_japanese("开箱测试")        # 漢字だけ（中国語）は日本語にしない
    assert selector.is_japanese("ゴジラ")
    assert selector.is_japanese("ラーメン")            # 長音「ー」


def test_like_rate():
    assert selector.like_rate(1000, 10) == 0.01
    assert selector.like_rate(1000, None) is None     # いいね数が非公開
    assert selector.like_rate(0, 10) is None


def test_views_per_day():
    # 2日前の投稿で10万回 → 1日あたり5万回
    assert selector.views_per_day(100000, "2026-11-03T00:00:00Z", NOW) == 50000
    # 6時間前の投稿でも「1日」として割る
    assert selector.views_per_day(100000, "2026-11-04T18:00:00Z", NOW) == 100000


def test_to_video():
    item = {"id": "xyz", "snippet": {"title": "た", "description": "d", "channelTitle": "c",
                                     "publishedAt": "2026-11-03T00:00:00Z"},
            "contentDetails": {"duration": "PT42S"}, "statistics": {"viewCount": "200000"}}
    v = selector.to_video(item, NOW)
    assert v["duration"] == 42 and v["views"] == 200000
    assert v["likes"] is None                         # likeCount が無い＝非公開
    assert v["views_per_day"] == 100000 and v["days"] == 2


def test_filter_candidates():
    videos = [
        video(id="ok"),
        video(id="live", duration=0),                 # ライブ配信
        video(id="long", duration=181),               # 3分を超える
        video(id="edge", duration=180),               # ちょうど3分は入る
        video(id="en", title="English only"),         # 日本語でない
        video(id="ad", views=10_000_000, likes=500),  # いいね率 0.005%（広告っぽい）
        video(id="hidden", likes=None),               # いいね非公開は除かない
    ]
    assert [v["id"] for v in selector.filter_candidates(videos, japan_only=True)] == ["ok", "edge", "hidden"]
    # 海外も入れる設定なら English only も入る
    assert "en" in [v["id"] for v in selector.filter_candidates(videos, japan_only=False)]


def test_sort_by_growth():
    videos = [video(id="slow", views_per_day=10), video(id="fast", views_per_day=1000), video(id="mid", views_per_day=100)]
    assert [v["id"] for v in selector.sort_by_growth(videos)] == ["fast", "mid", "slow"]



INTEREST = {"料理・グルメ": "料理", "子ども・家族": "育児", "キャリア・働き方": "転職"}


def look(seen=None):
    """偽物の「動画を見る分析」。seen に書いた動画は、そのジャンルだったことにする。見た動画を記録する。"""
    seen = seen or {}
    calls = []

    def judge(v):
        calls.append(v["id"])
        return {"genre": seen[v["id"]]} if v["id"] in seen else None
    return judge, calls


def test_is_japanese_ignores_hashtags():
    # 海外の動画が日本語のハッシュタグだけ付けていても、日本語の動画とみなさない
    assert not selector.is_japanese("wow sitti babu #赤ちゃんのいる生活 #癒し", "#赤ちゃん #shorts")
    assert selector.is_japanese("朝ごはんを作る #料理")


def test_choose_different_genres():
    # 伸び順に並んだ動画から、興味のあるジャンルを1本ずつ。同じジャンルの2本目と、興味の外は飛ばす（見もしない）
    videos = [{"id": i} for i in ["sport", "cook1", "cook2", "kid", "game", "work", "kid2"]]
    genres = {"sport": "スポーツ", "cook1": "料理・グルメ", "cook2": "料理・グルメ", "kid": "子ども・家族",
              "game": "ゲーム実況", "work": "キャリア・働き方", "kid2": "子ども・家族"}
    judge, calls = look()
    items = selector.choose(videos, genres, judge, INTEREST, 3, 6)
    assert [(v["id"], g) for v, _, g in items] == [("cook1", "料理・グルメ"), ("kid", "子ども・家族"),
                                                   ("work", "キャリア・働き方")]
    assert calls == ["cook1", "kid", "work"]


def test_choose_fewer():
    # 興味のあるジャンルが2種類しか無い日は、2本だけ（同じジャンルで埋めない）
    videos = [{"id": i} for i in ["cook1", "cook2", "kid"]]
    genres = {"cook1": "料理・グルメ", "cook2": "料理・グルメ", "kid": "子ども・家族"}
    judge, _ = look()
    assert [v["id"] for v, _, _ in selector.choose(videos, genres, judge, INTEREST, 3, 6)] == ["cook1", "kid"]


def test_choose_video_says_other_genre():
    # 文字では「子ども」でも、動画を見たら「お笑い」なら飛ばす。動画を見て別の興味のジャンルなら、そちらで選ぶ
    videos = [{"id": i} for i in ["kid1", "kid2", "cook"]]
    genres = {"kid1": "子ども・家族", "kid2": "子ども・家族", "cook": "料理・グルメ"}
    judge, _ = look({"kid1": "お笑い・コント", "cook": "キャリア・働き方"})
    items = selector.choose(videos, genres, judge, INTEREST, 3, 6)
    assert [(v["id"], g) for v, _, g in items] == [("kid2", "子ども・家族"), ("cook", "キャリア・働き方")]


def test_choose_max_tries():
    # 動画を見る分析は上限の回数まで
    videos = [{"id": f"k{i}"} for i in range(10)]
    genres = {v["id"]: "子ども・家族" for v in videos}
    judge, calls = look({v["id"]: "お笑い・コント" for v in videos})
    assert selector.choose(videos, genres, judge, INTEREST, 3, 4, per_genre=10) == []
    assert len(calls) == 4


def test_choose_per_genre():
    # 外れが続くジャンルは2回で切り上げ、ほかのジャンルに番を回す
    videos = [{"id": f"k{i}"} for i in range(5)] + [{"id": "cook"}]
    genres = dict({v["id"]: "子ども・家族" for v in videos}, cook="料理・グルメ")
    judge, calls = look({f"k{i}": "お笑い・コント" for i in range(5)})
    items = selector.choose(videos, genres, judge, INTEREST, 3, 8, per_genre=2)
    assert [v["id"] for v, _, _ in items] == ["cook"]
    assert calls == ["k0", "k1", "cook"]


def test_choose_unknown():
    # ジャンルが分からない（未分類）動画は選ばない
    judge, calls = look()
    assert selector.choose([{"id": "a"}], {"a": "未分類"}, judge, INTEREST, 3, 6) == []
    assert calls == []
