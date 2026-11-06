"""gemini_client.py の単体テスト。Gemini への通信（_post）は偽物の関数に差し替える。"""

import json

import config
import gemini_client


def fake_post(answers):
    """決めた順に返事をする偽物の _post。呼ばれたモデル名を記録する。"""
    calls = []

    def post(api_key, model, parts, schema):
        calls.append(model)
        return answers.pop(0)
    return post, calls


def no_sleep(seconds):
    pass


def setup_function():
    gemini_client.unavailable.clear()   # テストごとに「駄目だったモデル」の記録を空にする


def test_retry_then_success(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MODELS", ["m1", "m2"])
    post, calls = fake_post([(503, None), (200, json.dumps({"ok": 1}))])
    monkeypatch.setattr(gemini_client, "_post", post)
    assert gemini_client.ask("k", [], {}, log=lambda s: None, sleep=no_sleep) == {"ok": 1}
    assert calls == ["m1", "m1"]                      # 混雑なら同じモデルでやり直す


def test_fallback_to_next_model(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MODELS", ["m1", "m2"])
    post, calls = fake_post([(503, None)] * 3 + [(200, json.dumps({"ok": 2}))])
    monkeypatch.setattr(gemini_client, "_post", post)
    assert gemini_client.ask("k", [], {}, log=lambda s: None, sleep=no_sleep) == {"ok": 2}
    assert calls == ["m1", "m1", "m1", "m2"]          # 3回駄目なら次のモデル


def test_not_found_goes_next_without_retry(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MODELS", ["old", "m2"])
    post, calls = fake_post([(404, None), (None, None)])
    monkeypatch.setattr(gemini_client, "_post", post)
    assert gemini_client.ask("k", [], {}, log=lambda s: None, sleep=no_sleep) is None
    assert calls == ["old", "m2"]                     # 404・通信の失敗はやり直さない


def test_check_analysis():
    data = {"genre": "でたらめ", "structure": [{"time": "0〜3秒", "text": "つかみ"}, {"time": "x"}],
            "reason": " 理由 ", "tip": "まね"}
    a = gemini_client.check_analysis(data, 30)
    assert a["genre"] == "その他"                     # 一覧に無いジャンルは「その他」
    assert a["structure"] == [{"time": "0〜3秒", "text": "つかみ"}]
    assert a["reason"] == "理由"
    assert gemini_client.check_analysis({"structure": []}, 30) is None
    assert gemini_client.check_analysis(None, 30) is None


def test_classify_genres(monkeypatch):
    videos = [{"id": "a", "title": "t", "channel": "c", "description": "d"},
              {"id": "b", "title": "t", "channel": "c", "description": "d"},
              {"id": "c", "title": "t", "channel": "c", "description": "d"}]
    answer = [{"id": "a", "genre": "料理・グルメ"}, {"id": "b", "genre": "でたらめ"}, {"id": "zzz", "genre": "スポーツ"}]
    monkeypatch.setattr(gemini_client, "ask", lambda *a, **k: answer)
    assert gemini_client.classify_genres("k", videos) == {
        "a": "料理・グルメ", "b": config.UNKNOWN_GENRE, "c": config.UNKNOWN_GENRE}
    monkeypatch.setattr(gemini_client, "ask", lambda *a, **k: None)   # AI が全部駄目な日
    assert set(gemini_client.classify_genres("k", videos).values()) == {config.UNKNOWN_GENRE}


def test_skip_unavailable_model(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MODELS", ["m1", "m2"])
    post, calls = fake_post([(404, None), (200, json.dumps({"ok": 1})), (200, json.dumps({"ok": 2}))])
    monkeypatch.setattr(gemini_client, "_post", post)
    gemini_client.ask("k", [], {}, log=lambda s: None, sleep=no_sleep)
    gemini_client.ask("k", [], {}, log=lambda s: None, sleep=no_sleep)
    assert calls == ["m1", "m2", "m2"]                # 2回目は駄目だった m1 を飛ばす
