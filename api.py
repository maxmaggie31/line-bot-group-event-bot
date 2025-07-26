from flask import Flask, request, abort
from linebot import WebhookHandler, LineBotApi
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
import threading
import datetime
import time

app = Flask(__name__)

# 初始化 LINE SDK
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 記錄 messageId 對應的 user_id 與 group_id
message_user_map = {}
weekly_unsend_count = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Webhook 驗證失敗")
        abort(400)

    return 'OK'

# 處理訊息事件（但不回覆）
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg_id = event.message.id
    group_id = getattr(event.source, 'group_id', None)

    if group_id:
        message_user_map[msg_id] = {
            'user_id': user_id,
            'group_id': group_id
        }

# 處理收回訊息事件
@handler.add(UnsendEvent)
def handle_unsend(event):
    msg_id = event.unsend.message_id
    record = message_user_map.get(msg_id)

    if not record:
        print(f"[INFO] 收到未記錄的 unsend: {msg_id}")
        return

    user_id = record['user_id']
    group_id = record['group_id']

    count = weekly_unsend_count.get(user_id, 0) + 1
    weekly_unsend_count[user_id] = count

    if count == 1:
        warn_text = f"⚠️ <@{user_id}> 本週你已經收回過一次訊息，請注意！"
        line_bot_api.push_message(group_id, TextSendMessage(text=warn_text))
    elif count >= 2:
        try:
            profile = line_bot_api.get_group_member_profile(group_id, user_id)
            display_name = profile.display_name
        except Exception:
            display_name = f"<@{user_id}>"

        kick_text = f"🚫 用戶「{display_name}」因為本週收回兩次訊息，已被踢出群組。"
        try:
            line_bot_api.push_message(group_id, TextSendMessage(text=kick_text))
            line_bot_api.kickout_group_member(group_id, user_id)
        except Exception as e:
            fail_text = f"⚠️ 嘗試踢出「{display_name}」失敗，可能是 BOT 沒有管理員權限"
            print(f"[ERROR] Kick failed: {e}")
            line_bot_api.push_message(group_id, TextSendMessage(text=fail_text))

# 每週一凌晨清空收回次數
def reset_unsend_count_weekly():
    def weekly_clear():
        while True:
            now = datetime.datetime.now()
            next_monday = now + datetime.timedelta(days=(7 - now.weekday()))
            next_monday = next_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            wait_seconds = (next_monday - now).total_seconds()
            print(f"🕒 等待 {wait_seconds:.0f} 秒後清除收回紀錄")
            time.sleep(wait_seconds)

            weekly_unsend_count.clear()
            print("✅ 已清空本週收回次數記錄")

    threading.Thread(target=weekly_clear, daemon=True).start()

reset_unsend_count_weekly()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
