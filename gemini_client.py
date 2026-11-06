"""Gemini（Google の AI）に、動画の分析とジャンル分けを頼む（通信する）。

- 動画の分析：YouTube の URL を渡すと、AI が動画の中身を見て答える（公開動画のみ・試験提供中の機能）
- ジャンル分け：タイトルと説明文だけを渡して、数十本のジャンルを一度に分ける（動画は見ない）
返事は決まった形（JSON）で受け取る。ジャンルは config.GENRES の一覧から必ず選ばせる。

混雑（503）のときは少し待ってやり直し、駄目なら次のモデルへ。全部駄目なら None を返す
（呼ぶ側は、AI の一言なしで送る）。
"""

import json
import time

import requests

import config

# やり直す価値のある返事：503＝混雑、500＝サーバーの一時的な不調
RETRY_STATUS = {500, 503}
TIMEOUT = "時間切れ"

# 1回の実行の中で、一度駄目だったモデル（動画の分析で駄目なら、ジャンル分けでは飛ばして時間を節約する）
unavailable = set()

ANALYSIS_PROMPT = """このYouTubeショート動画を実際に見て、これから縦動画の発信を始める人が、あとで同じような動画を再現できるように日本語で答えてください。
動画で実際に見えたこと・聞こえたことだけを書き、推測で補わないでください。分からないことは「不明」、無いものは「なし」と書きます。
気持ちや反応は、映っている動き・表情・声だけで書き、映っていない結果や気持ちを付け足さないでください。
日本語の動画にも英語のかけ声などが混ざることがあります。言葉は聞こえた音のまま書き、自信が無い言葉には（？）を付けます。

【LINE で送る短い分析】
- genre：下のジャンルの一覧から1つ
- structure：構成を、動画の流れの順に3〜5個。time は秒数の目安（例「0〜5秒」）。動画の長さは{duration}秒なので、それを超える秒数は書かない
  動画で実際に見えたこと・聞こえたことだけを書き、推測で補わない。最後の項目は、実際に映って終わる場面を書く
  （結末を見せずに終わる、続きを別の動画やチャンネルへ誘導する、などもそのまま書く）
- reason：伸びた理由として考えられること（60文字以内）
- tip：真似できるポイント（50文字以内）

【見返して再現するための詳しい分析】
- structure_type：構成の型（下の「構成の型の一覧」から1つ）
- hook_type：最初の3秒（フック）の型（下の「フックの型の一覧」から1つ）
- first3：最初の3秒で話している言葉と、画面に出ている文字を、そのまま書き写す
- shooting：撮り方（一覧から1つ）／voice：話し方（一覧から1つ）
- tools：作るのに必要なもの（道具・場所・人）
- telop：テロップの入れ方（量・位置・色や大きさ・どの言葉を強調しているか）
- sound：BGM と効果音の雰囲気と、入るタイミング（曲名は書かない）
- tempo：場面が切り替わる速さ（一覧から1つ）
- cta：最後の呼びかけの種類と、実際の言葉（無ければ「なし」）
- loop：最後の場面が最初につながって、くり返し見たくなる仕掛けがあるか。あればどうつなげているか（無ければ「なし」）
- scenes：場面ごとに4〜8個、動画の流れの順に。time は秒数、role は役割（フック／つなぎ／本編／山場／オチ／CTA）、
  visual は映っているもの、words は話している言葉（そのまま）、telop は画面の文字、sound は音、why はなぜこうしているか（編集の意図）
  最後の場面は、動画の終わり（{duration}秒）の直前の数秒に映っているものだけを書く。そのあとに起きそうなこと（喜ぶ・抱き合う など）は書かない
  visual には気持ちの言葉（喜ぶ・驚く・楽しそう など）を使わず、体の動き（手を上げる・口を開ける など）で書く
- my_idea：同じジャンルで、初めての人がこの動画の型を使って作るなら、どんな動画にするかの案（100文字以内）

ジャンルの一覧：
{genres}

構成の型の一覧：
{structures}

フックの型の一覧：
{hooks}"""

GENRE_PROMPT = """次のYouTubeショート動画を、タイトルと説明文から、ジャンルの一覧のどれか1つに分けてください。
各ジャンルの説明をよく読んで選んでください。どれにも入らなければ「その他」にします。

ジャンルの一覧：
{genres}

動画：
{videos}"""


def genre_list_text(items=None):
    """一覧（ジャンル・型）を「- 名前：説明」の文にする（AI に渡す）。"""
    return "\n".join(f"- {name}：{desc}" for name, desc in (items or config.GENRES).items())


def _enum(values):
    return {"type": "string", "enum": list(values)}


# 詳しい分析の文字の項目（シートに書く）
DETAIL_TEXTS = ["first3", "tools", "telop", "sound", "cta", "loop", "my_idea"]
# 詳しい分析の、一覧から選ぶ項目と、その一覧
DETAIL_CHOICES = {
    "structure_type": config.STRUCTURE_TYPES,
    "hook_type": config.HOOK_TYPES,
    "shooting": config.SHOOTING_TYPES,
    "voice": config.VOICE_TYPES,
    "tempo": config.TEMPO_TYPES,
}
SCENE_TEXTS = ["time", "visual", "words", "telop", "sound", "why"]


def analysis_schema():
    """動画の分析の返事の形。一覧から選ぶ項目は、一覧のどれか（enum）に限る。"""
    return {
        "type": "object",
        "properties": {
            "genre": _enum(config.GENRES),
            "structure": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"time": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["time", "text"],
                },
            },
            "reason": {"type": "string"},
            "tip": {"type": "string"},
            **{k: _enum(v) for k, v in DETAIL_CHOICES.items()},
            **{k: {"type": "string"} for k in DETAIL_TEXTS},
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"role": _enum(config.SCENE_ROLES), **{k: {"type": "string"} for k in SCENE_TEXTS}},
                    "required": ["role", *SCENE_TEXTS],
                },
            },
        },
        "required": ["genre", "structure", "reason", "tip", *DETAIL_CHOICES, *DETAIL_TEXTS, "scenes"],
    }


def genre_schema():
    """ジャンル分けの返事の形：[{"id": 動画ID, "genre": ジャンル}, ...]"""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "genre": {"type": "string", "enum": list(config.GENRES)},
            },
            "required": ["id", "genre"],
        },
    }


def _post(api_key, model, parts, schema):
    """1つのモデルに1回だけ頼む。(HTTP の番号, 返事の文 または None) を返す。通信の失敗は (None, None)。"""
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema},
    }
    try:
        r = requests.post(
            f"{config.GEMINI_API_URL}{model}:generateContent",
            headers={"x-goog-api-key": api_key},  # 鍵はヘッダーで送る（URL に入れない）
            json=body,
            timeout=config.GEMINI_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        return TIMEOUT, None
    except requests.exceptions.RequestException:
        return None, None
    if r.status_code != 200:
        return r.status_code, None
    try:
        # 返事の形：candidates → [0] → content → parts → [最後] → text（JSON の文）
        return 200, r.json()["candidates"][0]["content"]["parts"][-1]["text"]
    except (ValueError, KeyError, IndexError):
        return 200, None


def ask(api_key, parts, schema, log=print, sleep=time.sleep):
    """モデルを順に試して、返事（JSON を読んだもの）を返す。全部駄目なら None。

    log：途中経過を出す関数（GitHub Actions の記録に残る）
    sleep：待つ関数（テストでは待たないものに差し替える）
    """
    for model in config.GEMINI_MODELS:
        model = model.strip()
        if model in unavailable:
            continue
        for attempt in range(len(config.GEMINI_RETRY_WAITS) + 1):
            status, text = _post(api_key, model, parts, schema)
            if text is not None:
                try:
                    return json.loads(text)
                except ValueError:
                    log(f"  Gemini（{model}）の返事が決まった形ではありませんでした")
                    break
            if status in RETRY_STATUS and attempt < len(config.GEMINI_RETRY_WAITS):
                wait = config.GEMINI_RETRY_WAITS[attempt]
                log(f"  Gemini（{model}）が混んでいます（HTTP {status}）。{wait}秒待ってやり直します")
                sleep(wait)
                continue
            why = TIMEOUT if status == TIMEOUT else (f"HTTP {status}" if status else "通信の失敗")
            log(f"  Gemini（{model}）を使えませんでした（{why}）")
            unavailable.add(model)
            break  # 次のモデルへ
    return None


def check_analysis(data, duration):
    """動画の分析の返事を確かめて整える。形がおかしければ None。"""
    if not isinstance(data, dict):
        return None
    structure = [s for s in data.get("structure", []) if isinstance(s, dict) and s.get("text")]
    if not structure:
        return None
    genre = data.get("genre")
    result = {
        "genre": genre if genre in config.GENRES else "その他",
        "structure": structure,
        "reason": str(data.get("reason", "")).strip(),
        "tip": str(data.get("tip", "")).strip(),
        "duration": duration,
    }
    # 詳しい分析（シート用）。欠けていても LINE は送れるので、空にして続ける
    for key, values in DETAIL_CHOICES.items():
        result[key] = data.get(key) if data.get(key) in values else ""
    for key in DETAIL_TEXTS:
        result[key] = str(data.get(key, "")).strip()
    result["scenes"] = [
        {"role": s.get("role") if s.get("role") in config.SCENE_ROLES else "",
         **{k: str(s.get(k, "")).strip() for k in SCENE_TEXTS}}
        for s in data.get("scenes", []) if isinstance(s, dict)
    ]
    return result


def analyze_video(api_key, video, log=print, sleep=time.sleep):
    """動画を見て、ジャンル・構成・伸びた理由・真似ポイントを返す。駄目なら None。"""
    prompt = ANALYSIS_PROMPT.format(duration=video["duration"], genres=genre_list_text(),
                                    structures=genre_list_text(config.STRUCTURE_TYPES),
                                    hooks=genre_list_text(config.HOOK_TYPES))
    parts = [
        {"text": prompt},
        {"file_data": {"file_uri": f"https://www.youtube.com/watch?v={video['id']}"}},
    ]
    return check_analysis(ask(api_key, parts, analysis_schema(), log, sleep), video["duration"])


def classify_genres(api_key, videos, log=print, sleep=time.sleep):
    """上位10本と送る候補のジャンルを、1回でまとめて分ける。{動画ID: ジャンル} を返す。分からなかった動画は「未分類」。"""
    lines = []
    for v in videos:
        desc = " ".join(v["description"].split())[:150]  # 説明文は長いので、改行をまとめて最初だけ
        lines.append(f"- id: {v['id']} ／ タイトル: {v['title']} ／ チャンネル: {v['channel']} ／ 説明: {desc}")
    prompt = GENRE_PROMPT.format(genres=genre_list_text(), videos="\n".join(lines))
    data = ask(api_key, [{"text": prompt}], genre_schema(), log, sleep)
    result = {v["id"]: config.UNKNOWN_GENRE for v in videos}
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("id") in result and row.get("genre") in config.GENRES:
                result[row["id"]] = row["genre"]
    return result
