from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    MessagingApi,
    MessagingApiBlob,
    Configuration,
    ApiClient,
    PushMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    CallbackRequest,
    UnsendEvent,
    MessageEvent,
    TextMessageContent,
)

import os
import json
import threading
import time
from datetime import datetime, timedelta

# 記錄收回次數
unsend_count = {}
unsend_messages = {}

# 設定每週清除一次記錄
def weekly_reset():
    while True:
        now = datetime.now()
        next_reset = (now + timedelta(days=(7 - now.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = (next_reset - now).total_seconds()
        print(f"🕒 等待 {int(wait_seconds)} 秒後清除收回紀錄")
        time.sleep(wait_seconds)
        unsend_count.clear()
        unsend_messages.clear()
        print("✅ 已清空本週收回次數記錄")

threading.Thread(target=weekly_reset, daemon=True).start()

# 初始化 Flask
app = Flask(__name__)

# LINE API 設定
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
handler = WebhookHandler(channel_secret)

configuration = Configuration(access_token=channel_access_token)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)

# Webhook 路由
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("❌ Webhook 處理錯誤:", str(e))
        abort(500)
    return 'OK'

@handler.add(UnsendEvent)
def handle_unsend(event: UnsendEvent):
    group_id = event.source.group_id if hasattr(event.source, 'group_id') else None
    user_id = event.source.user_id if hasattr(event.source, 'user_id') else None

    if not group_id or not user_id:
        return

    key = f"{group_id}:{user_id}"
    unsend_count[key] = unsend_count.get(key, 0) + 1
    count = unsend_count[key]

    # 抓使用者名稱
    try:
        profile = line_bot_api.get_group_member_profile(group_id, user_id)
        user_name = profile.display_name
    except Exception:
        user_name = "某位使用者"

    # 查最後一句收回訊息
    last_message = unsend_messages.get(key, "（無法得知內容）")

    warning_text = (
        f"⚠️ {user_name} 本週你已經收回過 {count} 次訊息，請注意！\n"
        f"🕵️ 收回內容可能是：{last_message}"
    )

    try:
        line_bot_api.push_message(
            PushMessageRequest(
                to=group_id,
                messages=[TextMessage(text=warning_text)]
            )
        )
    except Exception as e:
        print("❌ 發送警告訊息失敗:", str(e))

@handler.add(MessageEvent)
def handle_message(event: MessageEvent):
    if not isinstance(event.message, TextMessageContent):
        return

    group_id = event.source.group_id if hasattr(event.source, 'group_id') else None
    user_id = event.source.user_id if hasattr(event.source, 'user_id') else None

    if not group_id or not user_id:
        return

    key = f"{group_id}:{user_id}"
    unsend_messages[key] = event.message.text

# 啟動 Flask 服務
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
