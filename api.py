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
from datetime import datetime, timedelta, timezone

# 收回訊息記錄
unsend_count = {}
unsend_messages = {}

# 設定台灣時區（UTC+8）
tz_taiwan = timezone(timedelta(hours=8))

# 每週清空紀錄（台灣週一 00:00）
def weekly_reset():
    while True:
        now = datetime.now(tz=tz_taiwan)
        days_until_monday = (7 - now.weekday()) % 7  # 幾天後是週一
        next_reset = (now + timedelta(days=days_until_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if next_reset <= now:
            next_reset += timedelta(days=7)
        wait_seconds = (next_reset - now).total_seconds()
        print(f"🕒 等待 {int(wait_seconds)} 秒後清除收回紀錄（台灣週一 00:00）")
        time.sleep(wait_seconds)
        unsend_count.clear()
        unsend_messages.clear()
        print("✅ 已清空本週收回次數記錄")

threading.Thread(target=weekly_reset, daemon=True).start()

# 初始化 Flask
app = Flask(__name__)

# LINE 設定
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
handler = WebhookHandler(channel_secret)

configuration = Configuration(access_token=channel_access_token)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)

# Webhook 入口
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("❌ Webhook 錯誤:", str(e))
        abort(500)
    return 'OK'

@handler.add(UnsendEvent)
def handle_unsend(event: UnsendEvent):
    group_id = getattr(event.source, 'group_id', None)
    user_id = getattr(event.source, 'user_id', None)
    if not group_id or not user_id:
        return

    key = f"{group_id}:{user_id}"
    unsend_count[key] = unsend_count.get(key, 0) + 1
    count = unsend_count[key]

    # 查最後一句話
    last_message = unsend_messages.get(key, "（無法得知內容）")

    # 抓名稱
    try:
        profile = line_bot_api.get_group_member_profile(group_id, user_id)
        user_name = profile.display_name
    except Exception:
        user_name = "某位使用者"

    # 回覆格式
    warning_text = (
        f"收回內容是：{last_message}\n\n"
        f"⚠️ {user_name} 本週你已經收回過 {count} 次訊息，請注意！"
    )

    try:
        line_bot_api.push_message(
            PushMessageRequest(
                to=group_id,
                messages=[TextMessage(text=warning_text)]
            )
        )
    except Exception as e:
        print("❌ 發送警告失敗:", str(e))

@handler.add(MessageEvent)
def handle_message(event: MessageEvent):
    if not isinstance(event.message, TextMessageContent):
        return

    group_id = getattr(event.source, 'group_id', None)
    user_id = getattr(event.source, 'user_id', None)
    if not group_id or not user_id:
        return

    key = f"{group_id}:{user_id}"
    unsend_messages[key] = event.message.text

# 啟動 Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
