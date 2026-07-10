import os
import datetime
import pytz
import json
import random
import asyncio
from collections import OrderedDict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters,
    PollAnswerHandler, MessageReactionHandler
)
from google import genai
from google.genai import types

from telethon import TelegramClient
from telethon.sessions import StringSession

# ==================== ENV & AYARLAR ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_GROUP_ID = os.getenv("ALLOWED_GROUP_ID")

# Userbot ayarları
USERBOT_API_ID = int(os.getenv("USERBOT_API_ID", 0))
USERBOT_API_HASH = os.getenv("USERBOT_API_HASH")
USERBOT_SESSION_STRING = os.getenv("USERBOT_SESSION_STRING")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ALLOWED_GROUP_ID]):
    raise ValueError("TELEGRAM_TOKEN, GEMINI_API_KEY ve ALLOWED_GROUP_ID zorunlu!")

# Userbot client
userbot_client = None
if USERBOT_API_ID and USERBOT_API_HASH and USERBOT_SESSION_STRING:
    userbot_client = TelegramClient(
        StringSession(USERBOT_SESSION_STRING),
        USERBOT_API_ID,
        USERBOT_API_HASH
    )

IMAGE_URL_1 = "https://i.ibb.co/S4yWQrHg/MG-0345.jpg"
IMAGE_URL_2 = "https://i.ibb.co/Y748qgsP/MG-0346.jpg"
RULE_IMAGE_URL = "https://i.ibb.co/r2s2dYhb/MG-0987.png"

ALLOWED_DUYURU_USERS = ["6781642262", "8639720888", "7094870780", "8150494686", "8242824985"]
ALLOWED_KONTROL_USERS = ALLOWED_DUYURU_USERS

KONTROL_BILDIRIM_GROUP_ID = -5199864315   # <-- YENİ GRUP ID

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

# Anket takibi (sadece anket sahibi cevabı geçerli olsun diye)
PENDING_MUHATAP_POLL = {}   # poll_id -> {"requester_id": int, "target_user": dict}

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

# ==================== USERBOT İLE WARN ATMA ====================
async def send_warn_via_userbot(target_mention: str, reason: str):
    """Userbot üzerinden /warn komutu atar"""
    if not userbot_client:
        print("Userbot client başlatılamadı!")
        return False
    try:
        if not userbot_client.is_connected():
            await userbot_client.connect()
        
        warn_command = f"/warn {target_mention} {reason}"
        await userbot_client.send_message(int(ALLOWED_GROUP_ID), warn_command)
        return True
    except Exception as e:
        print(f"Userbot warn hatası: {e}")
        return False

# ==================== KONTROL SİSTEMİ ====================

async def kontrolet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (önceki kontrolet fonksiyonu aynen kalabilir, kısaltmak için buraya koymuyorum)
    # İstersen önceki mesajımdaki kontrolet fonksiyonunu buraya yapıştır
    pass

# ==================== YENİ: ALINTI İLE MUHATAP OLMA ANKETİ ====================

async def muhatap_olma_anket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Birisi mesajı alıntılayarak 'benimle muhatap olma' yazarsa anket oluşturur"""
    if str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return
    if not update.message.reply_to_message:
        return

    text = (update.message.text or "").lower().strip()
    if "benimle muhatap olma" not in text and "muhatap olma" not in text:
        return

    replied_user = update.message.reply_to_message.from_user
    requester = update.message.from_user

    if not replied_user or not requester:
        return

    # Anket oluştur
    question = (
        f"Bu kişinin ({replied_user.first_name or replied_user.username}) seninle herhangi bir iletişime geçmemesini istiyorsun. "
        "Senin de onunla aynı şekilde iletişim kurmaman, laf atmaman gerekiyor. Onaylıyor musun?"
    )

    try:
        poll_message = await context.bot.send_poll(
            chat_id=update.message.chat_id,
            question=question,
            options=["Evet", "Hayır"],
            is_anonymous=False,
            reply_to_message_id=update.message.reply_to_message.message_id
        )

        # Anketi takip et (sadece anket sahibi cevabı geçerli olsun)
        PENDING_MUHATAP_POLL[poll_message.poll.id] = {
            "requester_id": requester.id,
            "target_user": {
                "id": replied_user.id,
                "name": replied_user.first_name or replied_user.username or str(replied_user.id),
                "username": replied_user.username
            }
        }

    except Exception as e:
        print(f"Anket oluşturma hatası: {e}")


async def muhatap_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sadece anketi oluşturan kişinin cevabını değerlendirir"""
    poll_answer = update.poll_answer
    if not poll_answer:
        return

    poll_id = poll_answer.poll_id
    if poll_id not in PENDING_MUHATAP_POLL:
        return

    data = PENDING_MUHATAP_POLL[poll_id]
    if poll_answer.user.id != data["requester_id"]:
        return  # Başkası tıkladıysa dikkate alma

    answer = poll_answer.option_ids[0]  # 0 = Evet, 1 = Hayır

    target = data["target_user"]
    requester_id = data["requester_id"]

    if answer == 0:  # Evet
        # Otomatik olarak iletişim yasağı ekle
        pair_data = load_kontrol_listesi()
        new_pair = {
            "pair_id": pair_data["next_pair_id"],
            "user1": {"id": requester_id, "name": "İstek Sahibi", "username": None},
            "user2": target
        }
        pair_data["pairs"].append(new_pair)
        pair_data["next_pair_id"] += 1
        save_kontrol_listesi(pair_data)

        await context.bot.send_message(
            chat_id=ALLOWED_GROUP_ID,
            text=f"✅ İletişim yasağı eklendi! #{new_pair['pair_id']}"
        )

    # Anketi temizle
    del PENDING_MUHATAP_POLL[poll_id]

# ==================== İHLAL KONTROL (Userbot ile warn) ====================

async def kontrol_ihlal_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (önceki kod)
    # İhlal olduğunda:
    # await send_warn_via_userbot(mention, "İletişim yasağı ihlali (Reply)")
    pass

# Benzer şekilde kontrol_reaction da güncellenecek

# ==================== ANA FONKSİYON ====================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Userbot'u başlat
    if userbot_client:
        asyncio.get_event_loop().create_task(userbot_client.start())

    # Cache
    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)), cache_message_author), group=-2)

    # Yeni anket sistemi
    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)) & filters.REPLY, muhatap_olma_anket))
    app.add_handler(PollAnswerHandler(muhatap_poll_answer))

    # Kontrol komutları
    app.add_handler(CommandHandler("kontrolet", kontrolet))
    app.add_handler(CommandHandler("kontrolliste", kontrolliste))
    app.add_handler(CommandHandler("kontrolsil", kontrolsil))

    # Diğer handler'lar...
    app.add_handler(CommandHandler("start", send_guide))
    # ... (diğer komutlar)

    if app.job_queue:
        app.job_queue.run_repeating(post_random_rule, interval=155 * 60, first=60, name="random_rule_poster")

    print("Bot başlatılıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
