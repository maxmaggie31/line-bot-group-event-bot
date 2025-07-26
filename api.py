from flask import Flask, request, abort
from linebot import WebhookHandler, LineBotApi
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
from linebot.v3.messaging.models.mention import Mention
from linebot.v3.messaging.models.mentionee import Mentionee
import os
import threading
import datetime
import time

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 記錄訊息內容與發送者
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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg_id = event.message.id
    group_id = getattr(event.source, 'group_id', None)
    text = event.message.text

    if group_id:
        message_user_map[msg_id] = {
            'user_id': user_id,
            'group_id': group_id,
            'text': text
        }

@handler.add(UnsendEvent)
def handle_unsend(event):
    msg_id = event.unsend.message_id
    record = message_user_map.get(msg_id)

    if not record:
        print(f"[INFO] 收到未記錄的 unsend: {msg_id}")
        return

    user_id = record['user_id']
    group_id = record['group_id']
    text = record.get('text', '[內容無法識別]')

    # 累加本週收回次數
    count = weekly_unsend_count.get(user_id, 0) + 1
    weekly_unsend_count[user_id] = count

    # 嘗試抓暱稱
    try:
        profile = line_bot_api.get_group_member_profile(group_id, user_id)
        display_name = profile.display_name
    except Exception:
        display_name = f"<@{user_id}>"

    # 前半段文字（不含 mention）
    pre_text = (
        f"用戶「{display_name}」剛剛收回了一則訊息：\n"
        f"「{text}」\n"
        f"⚠️ "
    )

    # 設定 mention tag
    mention = Mention(
        mentionees=[
            Mentionee(
                index=len(pre_text),
                length=len(display_name),
                user_id=user_id
            )
        ]
    )

    # 完整訊息
    reply_text = (
        pre_text + f"{display_name} 本週你已收回第 {count} 次訊息，請注意！"
    )

    # 發送訊息
    line_bot_api.push_message(
        group_id,
        TextSendMessage(text=reply_text, mention=mention)
    )

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
