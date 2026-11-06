"""sheet_client.write のエラーの出し方の単体テスト。Google への通信は偽物に差し替える。"""

from datetime import date

import gspread
import pytest
from google.auth.exceptions import RefreshError, TransportError

import sheet_client


def fail_with(error):
    class FakeClient:
        def open_by_key(self, key):
            raise error
    return lambda: FakeClient()


class FakeResponse:
    def __init__(self, code):
        self.status_code = code
        self.text = "{}"

    def json(self):
        return {"error": {"code": self.status_code, "message": "x", "status": "x"}}


@pytest.mark.parametrize("error, words", [
    (gspread.SpreadsheetNotFound(), "SHEET_ID"),
    (gspread.exceptions.APIError(FakeResponse(403)), "編集者"),
    (TransportError("x"), "つながりませんでした"),        # つながらないのを「鍵が違う」と言わない
    (RefreshError("x"), "ログインできませんでした"),
])
def test_error_messages(monkeypatch, error, words):
    monkeypatch.setattr(sheet_client, "connect", fail_with(error))
    with pytest.raises(sheet_client.SheetError) as e:
        sheet_client.write("id", date(2026, 11, 6), [])
    assert words in str(e.value)
