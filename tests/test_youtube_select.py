"""youtube_client.real_shorts（本物のショートを上から集める）の単体テスト。
本物かどうかの確認（通信）は、偽物の関数に差し替える。"""

import config
import youtube_client


def vids(n):
    return [{"id": f"v{i}"} for i in range(n)]


def test_limit():
    shorts = youtube_client.real_shorts(vids(10), 3, check=lambda vid: True)
    assert [v["id"] for v in shorts] == ["v0", "v1", "v2"]


def test_skip_not_short():
    not_short = {"v1", "v3"}                          # /watch に転送される動画
    shorts = youtube_client.real_shorts(vids(10), 3, check=lambda vid: vid not in not_short)
    assert [v["id"] for v in shorts] == ["v0", "v2", "v4"]


def test_fewer_than_limit():
    assert len(youtube_client.real_shorts(vids(2), 3, check=lambda vid: True)) == 2


def test_check_limit(monkeypatch):
    monkeypatch.setattr(config, "MAX_SHORTS_CHECKS", 5)
    calls = []
    youtube_client.real_shorts(vids(100), 3, check=lambda vid: calls.append(vid) or False)
    assert len(calls) == 5                            # 上限より多くは確かめない
