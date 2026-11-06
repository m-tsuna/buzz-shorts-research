"""history.py（記録とジャンルの集計）の単体テスト。本物の data/history.csv は使わない。"""

from datetime import date

import config
import history


def v(id_, **kw):
    d = {"id": id_, "title": "た", "channel": "c", "duration": 30, "views": 1000,
         "views_per_day": 500.4, "published_at": "2026-11-03T00:00:00Z"}
    d.update(kw)
    return d


def test_write_and_read(tmp_path):
    path = tmp_path / "data" / "history.csv"
    assert history.load(path) == []                   # まだ無いときは空
    rows = history.make_rows(date(2026, 11, 5), [v("a"), v("b")], [v("a")], {"a": "料理・グルメ"})
    history.append(rows, path)
    history.append(history.make_rows(date(2026, 11, 6), [v("c")], [v("c")], {}), path)
    loaded = history.load(path)
    assert [r["video_id"] for r in loaded] == ["a", "b", "c"]
    assert loaded[0]["genre"] == "料理・グルメ" and loaded[1]["genre"] == config.UNKNOWN_GENRE
    assert loaded[0]["views_per_day"] == "500"
    assert history.sent_ids(loaded) == {"a", "c"}


def test_picks_outside_top():
    # 送る動画が全体の上位に入っていなければ、rank 0 で最後に足す。上位にある動画は印だけつける
    rows = history.make_rows(date(2026, 11, 5), [v("a"), v("b")], [v("z"), v("b"), v("y")], {})
    assert [(r["video_id"], r["rank"], r["sent"]) for r in rows] == [
        ("a", 1, 0), ("b", 2, 1), ("z", 0, 1), ("y", 0, 1)]


def test_no_picks():
    rows = history.make_rows(date(2026, 11, 5), [v("a")], [], {})
    assert [(r["rank"], r["sent"]) for r in rows] == [(1, 0)]


def row(d, id_, genre, rank="1"):
    return {"date": d, "rank": rank, "video_id": id_, "genre": genre}


def test_genre_summary():
    rows = [
        row("2026-11-01", "old", "スポーツ"),          # 8日前は入らない
        row("2026-11-02", "a", "ゲーム実況"),
        row("2026-11-03", "a", "ゲーム実況"),          # 同じ動画は1回だけ
        row("2026-11-03", "b", "ゲーム実況"),
        row("2026-11-04", "c", "料理・グルメ"),
        row("2026-11-08", "d", config.UNKNOWN_GENRE),  # 未分類は数えない
        row("2026-11-09", "future", "スポーツ"),       # 今日より後は入らない
        row("2026-11-05", "pick", "子ども・家族", "0"),  # 上位の外から送った動画は数えない
    ]
    counts, total = history.genre_summary(rows, date(2026, 11, 8))
    assert counts == [("ゲーム実況", 2), ("料理・グルメ", 1)]
    assert total == 3


def test_genre_summary_empty():
    assert history.genre_summary([], date(2026, 11, 8)) == ([], 0)
