from flask import Flask, request, abort
import os
import threading
from collections import defaultdict # ★★★ defaultdictをインポート ★★★

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage
)

import google.generativeai as genai

# --- (Gemini APIキーとモデルの初期化部分は変更なし) ---
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    print("エラー: GOOGLE_API_KEY 環境変数が設定されていません。")
    exit()
genai.configure(api_key=GEMINI_API_KEY)
# モデルは 'gemini-1.5-flash-latest' を使用。
# 会話履歴を扱うため、モデルインスタンスはユーザーごとに管理します。
# 直接 'model.generate_content()' を使うのではなく、chatセッションを使います。
# --- (ここまで変更なし) ---

app = Flask(__name__)

line_bot_api = LineBotApi('YOUR_CHANNEL_ACCESS_TOKEN') # あなたのアクセストークンに置き換えてください
handler = WebhookHandler('YOUR_CHANNEL_SECRET') # あなたのチャネルシークレットに置き換えてください

# ★★★ 会話履歴をユーザーIDごとに保存する辞書 ★★★
# defaultdictを使うことで、存在しないキーにアクセスしたときに自動的に空のリストが作成される
user_chats = defaultdict(lambda: genai.GenerativeModel('gemini-1.5-flash-latest').start_chat(history=[]))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK' # すぐにOKを返すことでLINEの再送を防ぐ

# 時間のかかる処理をバックグラウンドで実行する関数
def handle_gemini_in_background(user_id, received_text):
    """Geminiとの通信とメッセージ送信をバックグラウンドで行う"""
    try:
        # ユーザーごとのチャットセッションを取得
        chat = user_chats[user_id]

        # 前回の修正で提案した、生成トークン数の設定も入れておきます
        generation_config = genai.GenerationConfig(
            max_output_tokens=2048 # 最大出力トークン数を設定
        )

        # ★★★ ここでチャットセッションにメッセージを送信し、応答を取得 ★★★
        # chat.send_message() は自動的に会話履歴を管理してくれる
        response = chat.send_message(
            received_text,
            generation_config=generation_config
        )
        gemini_response_text = response.text
        print(f"Gemini Response: {gemini_response_text}")

    except Exception as e:
        gemini_response_text = f"Geminiからの応答中にエラーが発生しました: {e}"
        print(f"Gemini API Error: {e}")

    # 処理が終わったら、Push APIを使ってユーザーにメッセージを送信
    line_bot_api.push_message(
        user_id,
        TextSendMessage(text=gemini_response_text)
    )

# メッセージを受け取ったときの処理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # ユーザーIDと受信テキストを取得
    user_id = event.source.user_id
    received_text = event.message.text

    # バックグラウンドで handle_gemini_in_background 関数を実行するスレッドを開始
    # これにより、この関数はすぐに終了し、LINEにOKが返される
    thread = threading.Thread(
        target=handle_gemini_in_background,
        args=(user_id, received_text)
    )
    thread.start()

if __name__ == "__main__":
    # Repl.it用のポート設定
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)