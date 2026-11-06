"""message.py（LINE の文）の単体テスト。"""

from datetime import date

import message

VIDEO = {"id": "rBgvISyYapI", "title": "ハンコに押されないように逃げたら…", "channel": "そらね",
         "duration": 42, "views": 5192706, "views_per_day": 741815, "days": 2.3}
ANALYSIS = {"genre": "ゲーム実況", "duration": 42, "reason": "テンポのよいツッコミ", "tip": "カオスな画面にツッコミ",
            "structure": [{"time": "0〜5秒", "text": "いきなり始まる"}, {"time": "6〜41秒", "text": "ボスが出てオチ"}]}
THURSDAY = date(2026, 11, 5)
SUNDAY = date(2026, 11, 8)


def test_format_count():
    assert message.format_count(9800) == "9,800"
    assert message.format_count(5192706) == "519万"
    assert message.format_count(123456789) == "1.2億"


def test_format_age():
    assert message.format_age(0.4) == "9時間前"
    assert message.format_age(0.01) == "1時間前"
    assert message.format_age(2.3) == "2日前"


VIDEO2 = dict(VIDEO, id="kid123", title="1歳の朝ごはん", channel="ママ", views_per_day=5000)


def test_build_with_analysis():
    text = message.build([(VIDEO, ANALYSIS, "ゲーム実況")], THURSDAY)
    assert "11/5・木）1本" in text
    assert "① ゲーム実況" in text
    assert "そらね｜42秒｜519万回" in text             # 動画の長さも載せる（AI の秒数と見比べるため）
    assert "https://www.youtube.com/shorts/rBgvISyYapI" in text
    assert "0〜5秒：いきなり始まる" in text
    assert "💡 伸びた理由：テンポのよいツッコミ" in text
    assert "📊" not in text                            # 日曜以外は集計なし


def test_build_three():
    # 複数の動画は①②の順に並ぶ。AI が使えなかった動画だけ「分析できませんでした」
    text = message.build([(VIDEO, ANALYSIS, "ゲーム実況"), (VIDEO2, None, "子ども・家族")], THURSDAY)
    assert "）2本" in text
    assert text.index("① ゲーム実況") < text.index("② 子ども・家族")
    assert text.count("分析できませんでした") == 1
    assert "kid123" in text
    assert len(text) < 5000                            # LINE の1通の上限


def test_build_without_analysis():
    text = message.build([(VIDEO, None, "未分類")], THURSDAY)
    assert "AI が混んでいて分析できませんでした" in text
    assert "rBgvISyYapI" in text                       # 動画は届く


def test_summary_only_sunday():
    assert message.is_summary_day(SUNDAY)
    assert not message.is_summary_day(THURSDAY)
    text = message.build([(VIDEO, ANALYSIS, "ゲーム実況")], SUNDAY, ([("ゲーム実況", 18), ("料理・グルメ", 9)], 40))
    assert "上位に入った40本" in text
    assert "1位 ゲーム実況 18本" in text and "2位 料理・グルメ 9本" in text


def test_summary_empty():
    # 記録が無い最初の日曜は、集計を付けない
    assert "📊" not in message.build([(VIDEO, ANALYSIS, "ゲーム実況")], SUNDAY, ([], 0))


def test_no_video():
    assert "見つかりませんでした" in message.no_video(THURSDAY)
    assert "1位 料理・グルメ 3本" in message.no_video(SUNDAY, ([("料理・グルメ", 3)], 3))
