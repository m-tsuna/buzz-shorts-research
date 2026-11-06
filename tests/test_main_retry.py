"""main.classify_with_late_retry（AI が使えないとき、長くあけて試し直す）の単体テスト。通信しない。"""

import config
import main

VIDEOS = [{"id": "a"}]


def fake_classify(answers):
    """決めた順に答える偽物のジャンル分け。呼ばれた回数を数える。"""
    calls = []

    def classify(api_key, videos):
        calls.append(1)
        return answers.pop(0)
    return classify, calls


def test_success_first_time():
    classify, calls = fake_classify([{"a": "料理・グルメ"}])
    waits = []
    assert main.classify_with_late_retry("k", VIDEOS, classify, waits.append) == {"a": "料理・グルメ"}
    assert len(calls) == 1 and waits == []          # 1回目で分かれば待たない


def test_success_after_wait(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_LATE_WAITS", [120, 180])
    classify, calls = fake_classify([{"a": config.UNKNOWN_GENRE}, {"a": "料理・グルメ"}])
    waits = []
    assert main.classify_with_late_retry("k", VIDEOS, classify, waits.append) == {"a": "料理・グルメ"}
    assert waits == [120]                           # 2分待って、2回目で分かった


def test_give_up(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_LATE_WAITS", [120, 180])
    classify, calls = fake_classify([{"a": config.UNKNOWN_GENRE}] * 3)
    waits = []
    assert main.classify_with_late_retry("k", VIDEOS, classify, waits.append) == {"a": config.UNKNOWN_GENRE}
    assert waits == [120, 180] and len(calls) == 3  # 3回試して駄目なら、未分類のまま返す（AI なしの推定で送る）
