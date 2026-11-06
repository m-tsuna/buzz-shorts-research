"""参考動画シート（Google スプレッドシート）に書き込む（通信する）。

使うもの：gspread（Google スプレッドシートを Python で扱うライブラリ）と、サービスアカウント
（プログラム専用の Google アカウント）。シートは本人が作り、サービスアカウントに編集者として共有してある。
許可の範囲（スコープ）は、スプレッドシートだけ（Drive 全体には触らない）。
"""

import json
import os

import gspread
from google.auth.exceptions import GoogleAuthError, TransportError
from requests.exceptions import RequestException

import config
import sheet_rows

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetError(Exception):
    """シートに書けなかったときのエラー（利用者に見せる日本語のメッセージを持つ）。"""


def connect():
    """サービスアカウントでログインする。

    GitHub Actions では Secrets の GOOGLE_SERVICE_ACCOUNT_JSON（鍵の中身）、手元では service_account.json を使う。
    """
    text = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    try:
        if text:
            return gspread.service_account_from_dict(json.loads(text), scopes=SCOPES)
        return gspread.service_account(filename=str(config.SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    except FileNotFoundError:
        raise SheetError("サービスアカウントの鍵（service_account.json）がありません。README の「秘密ファイルの用意」を見てください")
    except (ValueError, KeyError):
        raise SheetError("サービスアカウントの鍵の形が正しくありません（GOOGLE_SERVICE_ACCOUNT_JSON か service_account.json を確かめてください）")


def prepare(book, title, columns):
    """シートが無ければ作り、見出しが無ければ書いて、見た目（固定・幅・折り返し）を整える。最初の1回だけ。"""
    try:
        sheet = book.worksheet(title)
    except gspread.WorksheetNotFound:
        first = book.sheet1
        empty = not any(cell for row in first.get_all_values() for cell in row)  # 空のシートは [[]] で返る
        if title == config.SHEET_LIST and empty:
            first.update_title(title)  # 新しいシートの「シート1」が空なら、名前を変えて使う
            sheet = first
        else:
            sheet = book.add_worksheet(title, rows=1000, cols=len(columns))
    if sheet.acell("A1").value:
        return sheet  # 見出しがある＝もう整えてある
    sheet.update([[name for name, _ in columns]], "A1")
    sheet.freeze(rows=1, cols=sheet_rows.FROZEN_COLUMNS if title == config.SHEET_LIST else 3)
    sheet.format("1:1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.93, "blue": 0.98}})
    sheet.format(f"A:{gspread.utils.rowcol_to_a1(1, len(columns))[:-1]}",
                 {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"})
    requests = [{
        "updateDimensionProperties": {
            "range": {"sheetId": sheet.id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize",
        }
    } for i, (_, width) in enumerate(columns)]
    if title == config.SHEET_LIST:
        col = sheet_rows.LIKE_RATE_COLUMN - 1
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet.id, "startRowIndex": 1, "startColumnIndex": col, "endColumnIndex": col + 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}}},
            "fields": "userEnteredFormat.numberFormat",
        }})
    book.batch_update({"requests": requests})
    return sheet


def append(sheet, rows):
    """表の最後に行を足し、フィルタを表全体にかけ直す（足した行もフィルタで絞れるように）。"""
    if rows:
        sheet.append_rows(rows, value_input_option="USER_ENTERED", table_range="A1")
    sheet.set_basic_filter()


def write(sheet_id, today, items):
    """送った動画を、① 動画一覧と ② シーン分解に書き込む。足した行数 (①, ②) を返す。失敗したら SheetError。"""
    lists, scenes = sheet_rows.build(today, items)
    try:
        book = connect().open_by_key(sheet_id)
        append(prepare(book, config.SHEET_LIST, sheet_rows.LIST_COLUMNS), lists)
        append(prepare(book, config.SHEET_SCENES, sheet_rows.SCENE_COLUMNS), scenes)
    except SheetError:
        raise
    except gspread.SpreadsheetNotFound:
        raise SheetError("シートが見つかりません。SHEET_ID が正しいか、シートをサービスアカウントに共有したかを確かめてください")
    except gspread.exceptions.APIError as e:
        code = getattr(e.response, "status_code", "")
        if code == 403:
            raise SheetError("シートに書く許可がありません。サービスアカウントを「編集者」として共有したかを確かめてください")
        if code == 404:
            raise SheetError("シートが見つかりません。SHEET_ID が正しいかを確かめてください")
        raise SheetError(f"Google スプレッドシートでエラーが起きました（HTTP {code}）")
    except (TransportError, RequestException) as e:  # GoogleAuthError より先に書く（つながらないのも GoogleAuthError の仲間のため）
        raise SheetError(f"Google につながりませんでした（インターネットの接続を確かめてください：{type(e).__name__}）")
    except GoogleAuthError:
        raise SheetError("Google にログインできませんでした。サービスアカウントの鍵が正しいか（消されていないか）を確かめてください")
    return len(lists), len(scenes)
