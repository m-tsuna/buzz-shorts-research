"""LINE に1通送る（通信する）。

使う API：LINE Messaging API のプッシュ送信（POST /v2/bot/message/push）
無料プランは月200通まで。送れたかは HTTP 200 で分かる（送った中身は API では読み返せない）。
"""

import requests

import config


class LineError(Exception):
    """LINE に送れなかったときのエラー（利用者に見せる日本語のメッセージを持つ）。"""


# LINE の返事の番号を、日本語の説明に直す表
STATUS = {
    400: "送り先（LINE_USER_ID）か文の形が正しくありません",
    401: "LINE のトークン（LINE_CHANNEL_ACCESS_TOKEN）が正しくありません",
    403: "このトークンでは送る許可がありません",
    429: "今月の無料の送信数（200通）を使い切ったか、送る回数が多すぎます",
}

MAX_LENGTH = 5000  # LINE の1通の文字数の上限


def send(token, user_id, text):
    """文を1通送る。送れなかったら LineError。"""
    try:
        r = requests.post(
            config.LINE_PUSH_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={"to": user_id, "messages": [{"type": "text", "text": text[:MAX_LENGTH]}]},
            timeout=config.HTTP_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise LineError(f"LINE につながりませんでした（インターネットの接続を確かめてください：{type(e).__name__}）")
    if r.status_code != 200:
        raise LineError(STATUS.get(r.status_code, f"LINE に送れませんでした（HTTP {r.status_code}）"))
