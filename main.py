"""ショート動画バズリサーチ：毎朝、興味のあるジャンルで今伸びている YouTube ショートを3本、AI の構成分析つきで LINE に送る。

使い方：
  python main.py --dry-run   LINE に送らず、記録も書かずに、送る予定の文を画面に出す（試すとき）
  python main.py             本番（GitHub Actions が毎朝これを動かす）

流れ：集める（youtube_client）→ 選ぶ（selector）→ 分析・ジャンル分け（gemini_client）
     → 文を作る（message）→ 送る（line_client）→ 記録する（history）
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import config
import gemini_client
import history
import line_client
import message
import selector
import sheet_client
import sheet_rows
import youtube_client

# 鍵の名前と、何の鍵か（無いときの説明に使う）
KEYS = {
    "YOUTUBE_API_KEY": "YouTube の API キー",
    "GEMINI_API_KEY": "Gemini の API キー",
    "LINE_CHANNEL_ACCESS_TOKEN": "LINE のチャネルアクセストークン",
    "LINE_USER_ID": "LINE のユーザー ID",
    "SHEET_ID": "参考動画シートの ID（シートの URL の /d/ と /edit のあいだ）",
}
# ドライランでは使わない鍵（LINE に送らず、シートにも書かないため）
NOT_IN_DRY_RUN = ("LINE_CHANNEL_ACCESS_TOKEN", "LINE_USER_ID", "SHEET_ID")


def read_keys(dry_run):
    """鍵を読む。手元では .env、GitHub Actions では Secrets（環境変数）から。

    足りない鍵があれば、名前と説明のリストも返す。ドライランでは LINE の鍵とシートの ID は無くてもよい。
    """
    load_dotenv(config.ENV_FILE)  # すでにある環境変数は上書きしない
    keys = {name: (os.environ.get(name) or "").strip() for name in KEYS}
    missing = [f"{name}（{desc}）" for name, desc in KEYS.items()
               if not keys[name] and not (dry_run and name in NOT_IN_DRY_RUN)]
    return keys, missing


def deliver(keys, text, dry_run):
    """文を LINE に送る。ドライランなら画面に出すだけ。送れなかったら LineError。"""
    if dry_run:
        print("\n----- LINE に送る文（ドライランなので送っていません）-----")
        print(text)
        print("-----")
        return
    line_client.send(keys["LINE_CHANNEL_ACCESS_TOKEN"], keys["LINE_USER_ID"], text)
    print("LINE に送りました")


def run(dry_run=False, now=None, history_file=config.HISTORY_FILE):
    """全体の流れ。終わり方の番号（0＝成功、1＝失敗）を返す。

    now と history_file は、テストで日付や記録のファイルを差し替えるためのもの。
    """
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(config.TIMEZONE)).date()  # 「今日」は日本時間で数える

    keys, missing = read_keys(dry_run)
    if missing:
        print("鍵が足りません。.env（GitHub Actions では Secrets）に次の項目を入れてください：")
        for m in missing:
            print(f"  - {m}")
        return 1

    try:
        # 1. 集める：全体の検索3回 ＋ 興味のあるジャンルの言葉での検索 → 動画の情報
        print("YouTube から動画を集めています…")
        overall_ids = youtube_client.collect_ids(keys["YOUTUBE_API_KEY"], now)
        interest_ids = youtube_client.collect_interest_ids(keys["YOUTUBE_API_KEY"], now)  # {ジャンル: IDのリスト}
        all_ids = list(dict.fromkeys(overall_ids + [i for ids in interest_ids.values() for i in ids]))
        videos = youtube_client.fetch_videos(keys["YOUTUBE_API_KEY"], all_ids, now)
    except youtube_client.YouTubeError as e:
        print(f"エラー：{e}")
        try:
            deliver(keys, message.failure(today, e), dry_run)
        except line_client.LineError as le:
            print(f"エラー：LINE にも送れませんでした：{le}")
        return 1

    # 2. 選ぶ：ショートの候補に絞り、1日あたりの再生数で並べ、本物のショートか確かめる
    #    記録用の上位10本は「全体の検索」から（ジャンルの集計が興味のあるジャンルに偏らないため）
    #    送る候補は、全体の上位10本 ＋ ジャンルの言葉で探した動画（ジャンルごとに上から8本）。まだ送っていないものだけ
    candidates = selector.sort_by_growth(selector.filter_candidates(videos))
    shorts = youtube_client.real_shorts(only(candidates, overall_ids), config.TOP_N)
    rows = history.load(history_file)
    sent = history.sent_ids(rows)
    unsent = [v for v in candidates if v["id"] not in sent]
    by_words = {genre: youtube_client.real_shorts(only(unsent, ids), config.INTEREST_PER_GENRE)
                for genre, ids in interest_ids.items()}
    pool = [v for v in shorts if v["id"] not in sent] + [v for vs in by_words.values() for v in vs]
    pool = selector.sort_by_growth(list({v["id"]: v for v in pool}.values()))  # 重複を除いて並べ直す
    print(f"集めた動画 {len(videos)}件 → ショートの候補 {len(candidates)}件 → "
          f"全体の上位 {len(shorts)}本・送る候補 {len(pool)}本")

    # 3. ジャンル分け（タイトルと説明文から、1回でまとめて）
    print("Gemini がジャンルを分けています…")
    targets = list({v["id"]: v for v in shorts + pool}.values())
    genres = classify_with_late_retry(keys["GEMINI_API_KEY"], targets) if targets else {}
    hints = genres
    if pool and all(genres.get(v["id"]) == config.UNKNOWN_GENRE for v in pool):
        # AI が使えずジャンルが分からない日は、どの言葉の検索で見つかったかでジャンルを推し量って選ぶ
        print("ジャンルが分からないので、検索の言葉からジャンルを推し量って選びます")
        hints = {v["id"]: genre for genre, vs in reversed(list(by_words.items())) for v in vs}

    # 4. 分析：興味のあるジャンルから違うジャンルを1本ずつ、AI が動画を見て確かめながら選ぶ
    def judge(v):
        print(f"Gemini が動画を見て分析しています：{v['title'][:40]}（{v['channel']}）")
        analysis = gemini_client.analyze_video(keys["GEMINI_API_KEY"], v)
        if analysis is not None:
            genres[v["id"]] = analysis["genre"]  # 記録にも、動画を見て決めたジャンルを残す
            if analysis["genre"] not in config.INTEREST_GENRES:
                print(f"  → 動画を見たら「{analysis['genre']}」だったので、次の候補を見ます")
        return analysis

    items = selector.choose(pool, hints, judge)
    if hints is not genres:
        # 推し量ったジャンルは外れることがあるので、そう分かるように書く
        items = [(v, a, g if a is not None else f"{g}（AI なしの推定）") for v, a, g in items]
    picks = [v for v, _, _ in items]

    # 5. 文を作る（日曜はジャンルの集計を足す。今日の分も入れて数える）
    new_rows = history.make_rows(today, shorts, picks, genres)
    print("\n今日の記録（★＝送る動画、0位＝全体の上位の外）：")
    for r in new_rows:
        mark = "★" if r["sent"] else " "
        print(f" {mark}{r['rank']:>2}. {message.format_count(r['views_per_day']):>6}回/日 [{r['genre']}] "
              f"{r['title'][:30]} {config.SHORTS_URL}{r['video_id']}")
    summary = history.genre_summary(rows + new_rows, today) if message.is_summary_day(today) else None
    text = message.build(items, today, summary) if items else message.no_video(today, summary)

    # 6. 送る → 送れたら記録する（送れなかった日は記録しないので、次の日に同じ動画を送れる）
    #    → 参考動画シートに書く（シートに書けなくても LINE は届いている。書けなければ失敗として終わる）
    try:
        deliver(keys, text, dry_run)
    except line_client.LineError as e:
        print(f"エラー：{e}")
        return 1
    if dry_run:
        lists, scenes = sheet_rows.build(today, items)
        print("ドライランなので、記録（data/history.csv）も参考動画シートも書いていません"
              f"（書く予定：動画一覧 {len(lists)}行・シーン分解 {len(scenes)}行）")
        return 0
    history.append(new_rows, history_file)
    print(f"記録に {len(new_rows)}行 足しました")
    if not items:
        return 0
    try:
        n_list, n_scenes = sheet_client.write(keys["SHEET_ID"], today, items)
    except sheet_client.SheetError as e:
        print(f"エラー：参考動画シートに書けませんでした（LINE には送ってあります）：{e}")
        return 1
    print(f"参考動画シートに足しました（動画一覧 {n_list}行・シーン分解 {n_scenes}行）")
    return 0


def classify_with_late_retry(api_key, videos, classify=gemini_client.classify_genres, sleep=time.sleep):
    """ジャンル分けをする。全部「未分類」（AI が使えなかった）なら、少し長くあけて試し直す。

    classify と sleep は、テストで偽物に差し替えるためのもの。
    """
    genres = classify(api_key, videos)
    for wait in config.GEMINI_LATE_WAITS:
        if any(g != config.UNKNOWN_GENRE for g in genres.values()):
            break
        print(f"AI が使えないので、{wait // 60}分待ってから試し直します")
        sleep(wait)
        gemini_client.unavailable.clear()  # 「駄目だったモデル」の記録を消して、全部のモデルをもう一度試す
        genres = classify(api_key, videos)
    return genres


def only(videos, ids):
    """videos のうち、ids に入っている動画だけ（並び順はそのまま）。"""
    ids = set(ids)
    return [v for v in videos if v["id"] in ids]


def main():
    parser = argparse.ArgumentParser(description="今日のバズショートを LINE に送る")
    parser.add_argument("--dry-run", action="store_true", help="LINE に送らず、記録も書かずに、文を画面に出す")
    args = parser.parse_args()
    try:
        sys.exit(run(dry_run=args.dry_run))
    except KeyboardInterrupt:
        print("\n途中で止めました")
        sys.exit(1)


if __name__ == "__main__":
    main()
