# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要
縦動画の発信を始める前のリサーチを、時間をかけずに毎日の習慣にするツール（講座 5-1-2② オリジナルツール2つ目）。
毎朝、興味のあるジャンル（`config.INTEREST_GENRES`）で今伸びている YouTube ショートを3本（違うジャンルから1本ずつ）選び、Gemini が動画を見て書いた構成の分析と一緒に LINE に1通で送る。
毎日の**全体の**上位10本のジャンルを記録し、日曜は先週のジャンルの集計も送る。使い道は「ジャンル選びのヒント」と「構成の勉強」。
送った動画は、詳しい分析（構成の型・フックの型・最初の3秒・シーン分解など）と一緒に Google スプレッドシート「参考ショート動画」にも足す。本人が★を付け、将来自分で作るときに見返して再現する資料にする。
決めたことと理由は `要件定義書.md`、進捗と記事の材料は `作業記録.md` にある。

## 使う技術
- Python 3（手元は Anaconda の `/opt/anaconda3/bin/python`、GitHub Actions では 3.12）／requests／python-dotenv／pytest
- YouTube Data API v3（API キー）：`search.list` で集める。`mostPopular` にはショートが入らないので使わない
- Gemini API（API キー、`AQ` で始まる形）：YouTube の URL を `file_data.file_uri` で渡すと動画の中身を見る
- LINE Messaging API（プッシュ送信）。LINE自動通知と同じボットで、無料枠は月200通
- Google スプレッドシート（gspread＋サービスアカウント。5-1-1② の鍵を使い回し、スコープは spreadsheets だけ）
- GitHub Actions（`.github/workflows/daily.yml`）：日本時間 8:15（UTC 23:15）に動かし、`data/history.csv` をコミットする

## 動かし方（コマンド）
- `python main.py --dry-run`：LINE に送らず、記録も書かずに、送る予定の文を画面に出す。試すときは基本これを使う
- `python main.py`：本番（LINE に1通送り、記録を書く）。LINE の無料枠を使うので、受け入れテスト T6 以外では使わない
- `pytest`：単体テスト（通信しない）。1つだけなら `pytest tests/test_selector.py::関数名`
- `gh workflow run daily.yml`：Actions を今すぐ動かす。鍵は `gh secret set -f .env` で Secrets に入れる
- 鍵は `.env`（`YOUTUBE_API_KEY`・`GEMINI_API_KEY`・`LINE_CHANNEL_ACCESS_TOKEN`・`LINE_USER_ID`・`SHEET_ID`）と `service_account.json`（Actions では Secrets の `GOOGLE_SERVICE_ACCOUNT_JSON`）。中身は表示しない

## 全体の仕組み
`main.py` が流れだけを持ち、通信するファイルと通信しないファイルを分けている。
- 通信する：`youtube_client.py`（検索・動画の情報・`/shorts/` の転送確認）、`gemini_client.py`（分析・ジャンル分け）、`line_client.py`、`sheet_client.py`（シートの準備と書き込み）
- 通信しない（単体テストの対象）：`selector.py`（日本語の判定・1日あたりの再生数・並べ替え・送る動画を選ぶ）、`history.py`（記録・集計）、`message.py`（LINE の文）、`sheet_rows.py`（シートの見出しと行）
- 設定値（期間・件数・いいね率の下限・ジャンルの一覧と説明・モデルの順番・日本だけか）は `config.py` に集める

流れ：全体を3回検索（直近7日の1・2ページ目＋直近2日）＋興味のあるジャンルの言葉で1回ずつ → 重複をまとめる → 1〜180秒・日本語（ハッシュタグを除いた文にかな）・いいね率0.1%以上 → 1日あたりの再生数で並べる → `/shorts/` の転送を確かめて、全体の上位10本と送る候補（ジャンルごとに8本）→ まとめてジャンル分け → `selector.choose` で興味のあるジャンルから1本ずつ、Gemini が動画を見て確かめながら3本 → 送信 → 記録 → シートに書く（ドライランではどれもしない）

## このプロジェクト独自のルール
- 本物のショートかは `https://www.youtube.com/shorts/ID` に HEAD で問い合わせ、`location` に `/watch` があれば除く（API では縦長か分からない）
- 1日あたりの再生数は、投稿から1日未満でも「1日」として割る
- Gemini は `config.py` のモデルの順に試す。503（混雑）は15秒・30秒待ってやり直し、全部駄目なら AI の一言なしで送る（届かないより動画だけでも届くほうがよい）
- AI が書く秒数は動画の長さを超えることがあるので、LINE には動画の長さも載せる
- ジャンルは `config.py` の一覧（16種類、説明つき）から必ず選ばせる。自由に書かせると集計できない
- 記録と日曜の集計は全体の上位10本だけ。上位の外から送った動画は `rank` 0 で記録し、集計に入れない（興味のあるジャンルに偏らないため）
- 動画を見たジャンルが興味の外なら飛ばして次の候補へ（1ジャンル2回・全部で8回まで）
- 日付は `datetime.now(ZoneInfo("Asia/Tokyo"))` で数える（Actions は UTC で動く）。日曜の集計のテストは日付を差し替えて関数を呼ぶ
- 通信エラーの表示や LINE の文に、鍵や鍵の入った URL を出さない（鍵はヘッダーで送る）
- Instagram リール・TikTok は対象外（公式 API でほかの人の人気動画を集められず、スクレイピングは規約違反）
- シートには下に行を足すだけ（本人が直接直してよい）。書き込みは USER_ENTERED、先頭が = + - @ の値には ' を付ける（数式として動かないように）
- 構成の型・フックの型は `config.py` の一覧（説明つき）から選ばせる。名前だけだと取り違えた（T15）
- 映っていない気持ちの付け足しは「推測しない」だけでは消えない。「どの欄に・どの言葉を使わないか」まで頼み方に書く（T15）
- `作業記録.md`・`提出記事.md`・`service_account.json` は GitHub に載せない

## 進捗（2026-11-06 時点。詳しくは `作業記録.md` の「▶ 次にやること」）
- 要件定義 ✅（版1.3）→ 実装 ✅ → テスト ✅ → 公開 ✅（https://github.com/m-tsuna/buzz-shorts-research 。T13 は 11/7 の朝）→ **記事**
- 関数を一つ読む ✅。記事は `提出記事.md` に下書き済み
- 次：T13（11/7 の朝9時までに届いたか、`gh run list` で時刻を見る）→ 時間を測る（測り方を最初から説明し直す）→ 記事の仕上げ（読み直し・難易度・HTML）
- 子ども・キャリアの検索の言葉を 11/6 に変えた（広い言葉だとドラマ・コントばかり）。数日使って様子を見る
