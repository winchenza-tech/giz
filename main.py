import os
import datetime
import pytz
import json
import random
import asyncio
from collections import OrderedDict

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, MessageReactionHandler
)

from pyrogram import Client

# ==================== ENV & AYARLAR ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_GROUP_ID = os.getenv("ALLOWED_GROUP_ID")

USERBOT_API_ID = int(os.getenv("USERBOT_API_ID", 0))
USERBOT_API_HASH = os.getenv("USERBOT_API_HASH")
USERBOT_SESSION_STRING = os.getenv("USERBOT_SESSION_STRING")

# Pyrogram Userbot
userbot_client = None
if USERBOT_API_ID and USERBOT_API_HASH and USERBOT_SESSION_STRING:
    try:
        userbot_client = Client(
            "userbot",
            api_id=USERBOT_API_ID,
            api_hash=USERBOT_API_HASH,
            session_string=USERBOT_SESSION_STRING,
            in_memory=True
        )
        print("Pyrogram userbot client oluşturuldu.")
    except Exception as e:
        print(f"Pyrogram client oluşturma hatası: {e}")
        userbot_client = None

KONTROL_BILDIRIM_GROUP_ID = -5199864315
ALLOWED_KONTROL_USERS = ["6781642262", "8639720888", "7094870780", "8150494686", "8242824985"]

RULES = [
    "📌Kişisel verilerin ifşası uyarılmaksızın ban sebebidir.",
    "📌Şahısa küfür yasaktır. Onun haricinde küfür serbesttir. Karşılıklı atışmalarda küfür kullanımında her iki taraf da uyarılacaktır.",
    "📌Tartışma yaşadığınız kişiye sizinle muhatap olmamasını söyledikten sonra chatte ya da seste laf atması ve herhangi bir gönderinizi yanıtlaması ve mesajınıza emoji bırakması yasaktır. İhlali durumunda şikayet gerekmeksizin kuralı ihlal eden kişi yönetici olsa dahi uyarı yapılır.",
    "📌Gruba yeni katılan üyelerle henüz gerekli samimiyet oluşmadan; isimleri, kullanıcı adları (nick), profil fotoğrafları veya yaşları gibi kişisel unsurlar üzerinden mizah yapılması, rapor edilmesine gerek duyulmaksızın doğrudan uyarı sebebidir. Bu kural yöneticiler dahil tüm üyeler için istisnasız geçerlidir.",
    "📌Yöneticilere bildirmek istediğiniz bir mesajı alıntılayarak /Report ya da @admin komutunu yazabilirsiniz. Gereksiz kullananlar uyarılacaktır.",
    "📌İftira, milli ve kutsal değerlere hakaret yasaktır. Sohbet akışını bozacak şekilde kişisel tartışmaları devam ettirmek yasaktır.",
    "📌Herhangi bir terör örgütünü, illegal oluşumu vs. övmek uyarılmaksızın ban sebebidir.",
    "📌Pornografik ve ileri şiddet içeren görsel içerikler kesinlikle yasaktır.",
    "📌Çıkmadan önce geçerli bir neden belirtmeksizin gruptan ayrılan üyeler 15 günden önce gruba tekrar dahil olamazlar.",
    "📌Grup üyesi olmayan yanınızdaki arkadaşlarınızın grup seslisindeki sohbete katılması yasaktır.",
    "📌Başka grubun reklamını yapmak ve reklam olabilecek şekilde başka grupla ilgili konuşmak ban sebebi dir.",
]

RULES_SENT_FILE = "rules_sent.json"
KONTROL_FILE = "kontrol_listesi.json"

RECENT_MESSAGE_AUTHORS = OrderedDict()
USERNAME_TO_ID_CACHE = {}
MAX_CACHE_SIZE = 1500

def update_message_cache(message):
    if message and message.from_user:
        user = message.from_user
        RECENT_MESSAGE_AUTHORS[message.message_id] = user.id
        if user.username:
            USERNAME_TO_ID_CACHE[user.username.lower()] = user.id
        if len(RECENT_MESSAGE_AUTHORS) > MAX_CACHE_SIZE:
            RECENT_MESSAGE_AUTHORS.popitem(last=False)

async def cache_message_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        update_message_cache(update.message)
    if update.edited_message:
        update_message_cache(update.edited_message)

def load_rules_sent():
    today_str = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d")
    if os.path.exists(RULES_SENT_FILE):
        try:
            with open(RULES_SENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today_str:
                return set(data.get("sent", []))
        except:
            pass
    return set()

def save_rules_sent(sent_indices):
    today_str = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d")
    data = {"date": today_str, "sent": list(sent_indices)}
    try:
        with open(RULES_SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Rules sent kaydedilemedi: {e}")

async def post_random_rule(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    if not (now.hour >= 8 or now.hour < 1):
        return
    sent = load_rules_sent()
    available = [i for i in range(len(RULES)) if i not in sent]
    if not available:
        return
    idx = random.choice(available)
    rule_text = RULES[idx]
    sent.add(idx)
    save_rules_sent(sent)
    try:
        await context.bot.send_photo(chat_id=ALLOWED_GROUP_ID, photo=RULE_IMAGE_URL, caption=rule_text)
    except Exception as e:
        print(f"Kural gönderme hatası: {e}")

def load_kontrol_listesi():
    if os.path.exists(KONTROL_FILE):
        try:
            with open(KONTROL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"pairs": [], "next_pair_id": 1}

def save_kontrol_listesi(data):
    try:
        with open(KONTROL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Kontrol listesi kaydedilemedi: {e}")

# ==================== PYROGRAM USERBOT İLE WARN ====================
async def send_warn_via_userbot(target_mention: str, reason: str):
    if not userbot_client:
        print("Userbot aktif değil.")
        return False
    try:
        if not userbot_client.is_connected:
            await userbot_client.start()
        warn_command = f"/warn {target_mention} {reason}"
        await userbot_client.send_message(int(ALLOWED_GROUP_ID), warn_command)
        print(f"Userbot ile warn atıldı → {warn_command}")
        return True
    except Exception as e:
        print(f"Userbot warn hatası: {e}")
        return False

# ==================== KONTROL SİSTEMİ ====================

async def kontrolet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return

    text = update.message.text or ""
    mentioned = []

    for entity in (update.message.entities or []):
        if entity.type == "text_mention":
            u = entity.user
            mentioned.append({
                "id": u.id,
                "name": u.first_name or u.username or str(u.id),
                "username": u.username
            })
        elif entity.type == "mention":
            username_part = text[entity.offset:entity.offset + entity.length].lstrip("@")
            found_id = USERNAME_TO_ID_CACHE.get(username_part.lower())
            mentioned.append({
                "id": found_id,
                "name": username_part,
                "username": username_part
            })

    if len(mentioned) < 2:
        await update.message.reply_text("İki üyeyi etiketle. Örnek: /kontrolet @kisi1 @kisi2")
        return

    u1, u2 = mentioned[0], mentioned[1]
    data = load_kontrol_listesi()
    new_pair = {"pair_id": data["next_pair_id"], "user1": u1, "user2": u2}
    data["pairs"].append(new_pair)
    data["next_pair_id"] += 1
    save_kontrol_listesi(data)

    await update.message.reply_text(f"✅ İletişim yasağı eklendi! #{new_pair['pair_id']}")


async def kontrolliste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
    data = load_kontrol_listesi()
    if not data.get("pairs"):
        await update.message.reply_text("Liste boş.")
        return
    lines = [f"#{p['pair_id']} → {p['user1']['name']} × {p['user2']['name']}" for p in data["pairs"]]
    await update.message.reply_text("\n".join(lines))


async def kontrolsil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Kullanım: /kontrolsil 5")
        return
    pid = int(context.args[0])
    data = load_kontrol_listesi()
    data["pairs"] = [p for p in data["pairs"] if p["pair_id"] != pid]
    save_kontrol_listesi(data)
    await update.message.reply_text(f"✅ #{pid} silindi.")


def get_user_mention(user):
    return f"@{user.username}" if user.username else (user.first_name or "Kullanıcı")


async def kontrol_ihlal_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat.id) != ALLOWED_GROUP_ID or not update.message.reply_to_message:
        return

    sender = update.message.from_user
    replied = update.message.reply_to_message.from_user
    if not sender or not replied:
        return

    data = load_kontrol_listesi()
    for pair in data.get("pairs", []):
        u1_id = pair["user1"].get("id")
        u2_id = pair["user2"].get("id")
        if u1_id is None or u2_id is None:
            continue
        if (sender.id == u1_id and replied.id == u2_id) or (sender.id == u2_id and replied.id == u1_id):
            mention = get_user_mention(sender)
            await send_warn_via_userbot(mention, "İletişim yasağı ihlali (Reply)")
            await send_kontrol_bildirim(context, "Reply", mention)
            break


async def kontrol_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction or str(reaction.chat.id) != ALLOWED_GROUP_ID or not reaction.new_reaction:
        return

    reactor = reaction.user
    original_author_id = RECENT_MESSAGE_AUTHORS.get(reaction.message_id)
    if not reactor or not original_author_id:
        return

    data = load_kontrol_listesi()
    for pair in data.get("pairs", []):
        u1_id = pair["user1"].get("id")
        u2_id = pair["user2"].get("id")
        if u1_id is None or u2_id is None:
            continue
        if (reactor.id == u1_id and original_author_id == u2_id) or (reactor.id == u2_id and original_author_id == u1_id):
            mention = get_user_mention(reactor)
            await send_warn_via_userbot(mention, "İletişim yasağı ihlali (Emoji)")
            await send_kontrol_bildirim(context, "Emoji", mention)
            break


async def send_kontrol_bildirim(context, ihlal_tipi, mention):
    try:
        await context.bot.send_message(
            chat_id=KONTROL_BILDIRIM_GROUP_ID,
            text=f"🚨 İletişim Yasağı İhlali ({ihlal_tipi})\nKişi: {mention}"
        )
    except Exception as e:
        print(f"Bildirim hatası: {e}")

# ==================== ANA FONKSİYON ====================
async def start_userbot():
    if userbot_client:
        try:
            await userbot_client.start()
            print("Pyrogram Userbot başarıyla başlatıldı.")
        except Exception as e:
            print(f"Userbot başlatılamadı: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    if userbot_client:
        asyncio.create_task(start_userbot())

    app.add_handler(
        MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)), cache_message_author),
        group=-2
    )

    app.add_handler(CommandHandler("kontrolet", kontrolet))
    app.add_handler(CommandHandler("kontrolliste", kontrolliste))
    app.add_handler(CommandHandler("kontrolsil", kontrolsil))
    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)) & filters.REPLY, kontrol_ihlal_kontrol))
    app.add_handler(MessageReactionHandler(kontrol_reaction))

    if app.job_queue:
        app.job_queue.run_repeating(post_random_rule, interval=155 * 60, first=60)

    print("Bot başlatılıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
