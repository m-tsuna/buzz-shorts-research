"""sheet_rows.py（参考動画シートに書く行）の単体テスト。通信しない。"""

from datetime import date

import sheet_rows

TODAY = date(2026, 11, 6)
VIDEO = {"id": "abc", "title": "=1+1 わざと数式に見えるタイトル", "channel": "ch", "duration": 63,
         "views": 10000, "likes": 150, "views_per_day": 5000.4}
ANALYSIS = {"structure_type": "続きは本編へ", "hook_type": "続きが気になる", "first3": "どっちだと思う？",
            "reason": "理由", "tip": "真似", "shooting": "顔出し", "voice": "地声", "tools": "風船",
            "telop": "大きく", "sound": "明るい", "tempo": "速い", "cta": "本編へ", "loop": "なし", "my_idea": "案",
            "scenes": [{"time": "0〜3秒", "role": "フック", "visual": "風船", "words": "せーの", "telop": "緊張",
                        "sound": "太鼓", "why": "期待を高める"},
                       {"time": "3〜10秒", "role": "つなぎ", "visual": "家族", "words": "男の子？", "telop": "",
                        "sound": "", "why": "共感"}]}


def test_columns_match():
    # 見出しの数と、行の値の数がそろっている（ずれると別の列に入ってしまう）
    row = sheet_rows.list_row(TODAY, VIDEO, ANALYSIS, "子ども・家族")
    assert len(row) == len(sheet_rows.LIST_COLUMNS)
    assert len(sheet_rows.scene_rows(TODAY, VIDEO, ANALYSIS)[0]) == len(sheet_rows.SCENE_COLUMNS)
    assert sheet_rows.LIST_COLUMNS[-2][0].startswith("自分ならどう作るか")   # AI の案と自分のメモは右端
    assert sheet_rows.LIST_COLUMNS[-1][0] == "自分のメモ"
    assert sheet_rows.LIST_COLUMNS[sheet_rows.LIKE_RATE_COLUMN - 1][0] == "いいね率"


def test_list_row_values():
    row = dict(zip([name for name, _ in sheet_rows.LIST_COLUMNS], sheet_rows.list_row(TODAY, VIDEO, ANALYSIS, "子ども・家族")))
    assert row["★"] == "" and row["自分のメモ"] == ""          # 本人が書く列は空
    assert row["届いた日"] == "2026-11-06"
    assert row["URL"] == "https://www.youtube.com/shorts/abc"
    assert row["いいね率"] == 0.015
    assert row["1日あたりの再生数"] == 5000
    assert row["構成の型"] == "続きは本編へ" and row["最初の3秒（言葉・文字）"] == "どっちだと思う？"
    assert row["タイトル"].startswith("'=")                    # 数式として動かないように ' を付ける


def test_without_analysis():
    # AI が使えなかった動画は、AI が書く列を空にして1行だけ。シーンは0行
    video = dict(VIDEO, likes=None)
    lists, scenes = sheet_rows.build(TODAY, [(video, None, "料理・グルメ（AI なしの推定）")])
    assert len(lists) == 1 and scenes == []
    row = dict(zip([name for name, _ in sheet_rows.LIST_COLUMNS], lists[0]))
    assert row["構成の型"] == "" and row["いいね率"] == ""      # いいね数が非公開なら空


def test_build_scenes_numbered():
    lists, scenes = sheet_rows.build(TODAY, [(VIDEO, ANALYSIS, "子ども・家族"), (VIDEO, None, "料理・グルメ")])
    assert len(lists) == 2
    assert [r[3] for r in scenes] == [1, 2]                     # 順番は1から
    assert scenes[0][5] == "フック"


def test_safe():
    assert sheet_rows.safe("-5kg") == "'-5kg"
    assert sheet_rows.safe("ふつう") == "ふつう"
    assert sheet_rows.safe(123) == 123
