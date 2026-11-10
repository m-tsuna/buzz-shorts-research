# 毎朝のバズショート（縦動画の発信リサーチ）

縦動画の発信を始める前のリサーチを、毎朝数分の習慣にするツールです。

- 毎朝 8:15（日本時間）に、**いま伸びている YouTube ショート**を3本選び、AI（Gemini）が動画を見て書いた「構成・伸びた理由・真似できるポイント」と一緒に、**LINE に1通**で届けます
- 3本は、自分の興味のあるジャンル（料理・グルメ／商品紹介・レビュー／子ども・家族／キャリア・働き方）から、違うジャンルを1本ずつ選びます
- 毎日の**全体の上位10本**のジャンルを記録し、**日曜は「この1週間に伸びたジャンル」**の集計も届きます（ジャンル選びのヒント）
- 届いた動画は、詳しい分析（構成の型・フックの型・最初の3秒・テロップ・BGM・シーンごとの分解など）と一緒に **Google スプレッドシート**にも足していきます。★を付けて、自分で作るときに見返す資料にします

「伸びている」は、**1日あたりの再生数**（再生数 ÷ 投稿からの日数）で比べます。合計の再生数だと、古い動画が有利になるためです。
決めたことと理由は [要件定義書.md](要件定義書.md) にあります。

## 仕組み

```
YouTube で探す（全体3回＋ジャンルの言葉4回）
  → 1〜180秒・日本語・いいね率0.1%以上に絞り、1日あたりの再生数で並べる
  → 本物のショートか確かめる（youtube.com/shorts/ID が /watch に転送されないか）
  → Gemini がタイトルからジャンル分け（全体の上位10本と、送る候補）
  → 興味のあるジャンルから1本ずつ、Gemini が動画を見て分析（ジャンルが違えば次の候補へ）
  → LINE に1通送る → 記録（data/history.csv）に足す → スプレッドシートに足す
```

| ファイル | 役割 | 通信 |
|---|---|---|
| `main.py` | 全体の流れ | — |
| `config.py` | 設定値（期間・件数・ジャンルの一覧と検索の言葉・AI のモデルなど） | — |
| `youtube_client.py` | 動画を探す・動画の情報を取る・ショートか確かめる | する |
| `gemini_client.py` | 動画の分析・ジャンル分け | する |
| `line_client.py` | LINE に送る | する |
| `sheet_client.py` | スプレッドシートに書く | する |
| `selector.py` | 絞り込み・並べ替え・送る動画を選ぶ | しない |
| `history.py` | 記録と日曜の集計 | しない |
| `message.py` | LINE の文を作る | しない |
| `sheet_rows.py` | シートの見出しと行を作る | しない |
| `tests/` | 単体テスト（通信しないファイルが対象） | しない |

AI が混んでいる（HTTP 503）ときは、少し待ってやり直し、次のモデルも試します。それでも駄目なら、AI の分析なしで動画だけを送ります（届かないよりよいため）。

## 使う技術

- Python 3（requests・python-dotenv・gspread）、単体テストは pytest
- YouTube Data API（伸びているショートを探す）
- Gemini API（動画の構成を分析）
- LINE Messaging API（毎朝届ける）
- Google Sheets API（サービスアカウントで記録）
- GitHub Actions（毎朝の自動実行）

## 事前準備

- Python 3.12 くらい（手元では Anaconda の Python 3.14 で確かめました）
- ライブラリ：`pip install -r requirements.txt`
- 鍵（下の「秘密ファイルの用意」）
  - YouTube Data API v3 の API キー（Google Cloud）
  - Gemini API の鍵（Google AI Studio）
  - LINE Messaging API のチャネルアクセストークン（長期）と、自分のユーザー ID
  - Google スプレッドシートと、書き込むためのサービスアカウントの鍵

すべて無料枠で動きます。1日あたり、YouTube は約710ユニット（検索7回×100＋動画の情報）（無料枠は10,000）、LINE は1通（無料枠は月200通）を使います。

## 使い方

```bash
# 試すとき：LINE に送らず、記録もシートも書かず、送る予定の文を画面に出す
python main.py --dry-run

# 本番：LINE に1通送り、記録とシートに書く（毎朝 GitHub Actions がこれを動かす）
python main.py

# 単体テスト（通信しない）
pytest
```

興味のあるジャンルや検索の言葉は、`config.py` の `INTEREST_GENRES` で変えられます。

## 秘密ファイルの用意

鍵はプログラムに書かず、次の2つのファイルに入れます。どちらも `.gitignore` に入れてあり、GitHub には載りません。**中身を人に見せたり、画面に貼ったりしないでください。**

### 1. `.env`（このフォルダに作る）

```
YOUTUBE_API_KEY=ここに YouTube の API キー
GEMINI_API_KEY=ここに Gemini の鍵（AIza か AQ で始まる）
LINE_CHANNEL_ACCESS_TOKEN=ここに LINE のチャネルアクセストークン（長期）
LINE_USER_ID=ここに自分のユーザー ID（U で始まる）
SHEET_ID=ここにスプレッドシートの ID
```

- **YouTube**：Google Cloud Console で「YouTube Data API v3」を有効にし、「認証情報」→「API キーを作成」。「API の制限」で YouTube Data API v3 だけにしておきます
- **Gemini**：Google AI Studio（https://aistudio.google.com/apikey ）で「API キーを作成」
- **LINE**：LINE Developers で Messaging API のチャネルを作り、「Messaging API 設定」の一番下でチャネルアクセストークン（長期）を発行。ユーザー ID は「チャネル基本設定」の一番下の「あなたのユーザー ID」。スマホの LINE で、その公式アカウントを友だち追加しておきます

### 2. `service_account.json`（スプレッドシートに書くための鍵）

1. Google Cloud Console で「Google Sheets API」を有効にする
2. 「IAM と管理」→「サービスアカウント」→ サービスアカウントを作る（ロールは付けなくてよい）
3. 作ったサービスアカウントの「鍵」→「鍵を追加」→「JSON」→ ダウンロードしたファイルを、このフォルダに `service_account.json` という名前で置く
4. https://sheets.new で新しいスプレッドシートを作り、「共有」で、鍵のファイルの中の `client_email`（`…@….iam.gserviceaccount.com`）を**編集者**として追加する
5. スプレッドシートの URL の `/d/` と `/edit` の間の文字が ID。`.env` の `SHEET_ID` に入れる

シート「動画一覧」と「シーン分解」、見出し・列の幅・フィルタは、最初に書くときにプログラムが作ります。シートは下に行を足すだけなので、★やメモは直接書き込んで大丈夫です（シートの名前を変えない・途中に空行を入れない・見出しを消さない、だけ気をつけてください）。

## 毎朝の自動実行（GitHub Actions）

`.github/workflows/daily.yml` が、毎朝 8:15（UTC の 23:15）に `python main.py` を動かし、増えた記録（`data/history.csv`）をコミットします。GitHub のコンピューターで動くので、Mac の電源が切れていても届きます。

鍵は GitHub の Secrets に入れます（中身を見ずに入れられます）。

```bash
gh secret set -f .env                                         # .env の5つ
gh secret set GOOGLE_SERVICE_ACCOUNT_JSON < service_account.json  # サービスアカウントの鍵の中身
gh workflow run daily.yml                                     # 今すぐ1回動かして確かめる
```

- GitHub が混んでいると、数分〜30分ほど遅れて始まることがあります
- 公開リポジトリは、60日間コミットが無いと定期実行が止まります（このツールは毎日記録をコミットするので、動いている間は止まりません）
- 止めたいときは、GitHub の Actions タブ →「毎朝のバズショート」→「…」→「Disable workflow」

## 対象外にしたもの

Instagram リール・TikTok は対象にしていません。公式の API では、ほかの人の人気の動画を集められず、ページから抜き出すこと（スクレイピング）は利用規約で禁止されているためです。
