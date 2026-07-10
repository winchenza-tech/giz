import os
import re
import datetime
import pytz
import asyncio
import json
import random
from collections import OrderedDict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters,
    PollAnswerHandler, MessageReactionHandler
)
from google import genai
from google.genai import types
from pyrogram import Client

# ==================== ÇEVRE DEĞİŞKENLERİ & AYARLAR ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_GROUP_ID = os.getenv("ALLOWED_GROUP_ID")
PYROGRAM_API_ID = os.getenv("PYROGRAM_API_ID")
PYROGRAM_API_HASH = os.getenv("PYROGRAM_API_HASH")
PYROGRAM_SESSION_STRING = os.getenv("PYROGRAM_SESSION_STRING")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ALLOWED_GROUP_ID]):
    raise ValueError("Lütfen Railway Variables kısmına TELEGRAM_TOKEN, GEMINI_API_KEY ve ALLOWED_GROUP_ID ekleyin.")

IMAGE_URL_1 = "https://i.ibb.co/S4yWQrHg/MG-0345.jpg"
IMAGE_URL_2 = "https://i.ibb.co/Y748qgsP/MG-0346.jpg"
SORU_IMAGE_URL = "https://i.ibb.co/5Xcrbv87/MG-0398.jpg"
RULE_IMAGE_URL = "https://i.ibb.co/r2s2dYhb/MG-0987.png"

GEMINI_MODEL = "gemini-2.5-flash"
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

WAITING_FOR_TIME = 1
WAITING_FOR_IMPORTANCE = 2

ALLOWED_DUYURU_USERS = ["6781642262", "8639720888", "7094870780", "8150494686", "8242824985"]
ALLOWED_KONTROL_USERS = ALLOWED_DUYURU_USERS
DUYURU_GROUP_ID = "-1003297262036"
ADMIN_LOG_GROUP_ID = "-5199865414"

RULES_SENT_FILE = "rules_sent.json"
KONTROL_FILE = "kontrol_listesi.json"
FILTRE_FILE = "filtreler.json"

RECENT_MESSAGE_AUTHORS = OrderedDict()
MAX_CACHE_SIZE = 2500

# ==================== PYROGRAM USERBOT ====================
userbot = None
if PYROGRAM_API_ID and PYROGRAM_API_HASH and PYROGRAM_SESSION_STRING:
    userbot = Client(
        "userbot_session",
        api_id=int(PYROGRAM_API_ID),
        api_hash=PYROGRAM_API_HASH,
        session_string=PYROGRAM_SESSION_STRING,
        in_memory=True
    )

async def start_userbot(app: Application):
    if userbot:
        print("Userbot başlatılıyor...")
        await userbot.start()

async def stop_userbot(app: Application):
    if userbot:
        print("Userbot durduruluyor...")
        try:
            if userbot.is_connected:
                await userbot.stop()
        except Exception as e:
            print(f"Userbot kapanırken beklenen bir hata oluştu (yoksayılıyor): {e}")

# ==================== YARDIMCI FONKSİYONLAR ====================
def get_user_mention(user):
    return f"@{user.username}" if user.username else user.first_name

def update_message_cache(message):
    if message and message.from_user:
        RECENT_MESSAGE_AUTHORS[message.message_id] = message.from_user.id
        if len(RECENT_MESSAGE_AUTHORS) > MAX_CACHE_SIZE:
            RECENT_MESSAGE_AUTHORS.popitem(last=False)

async def cache_message_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        update_message_cache(update.message)
    if update.edited_message:
        update_message_cache(update.edited_message)

def load_json(file_path, default_val):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_val

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def log_to_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Yönetim log grubuna mesaj gönderir."""
    try:
        await context.bot.send_message(chat_id=int(ADMIN_LOG_GROUP_ID), text=text)
    except Exception as e:
        print(f"Admin log gönderilemedi: {e}")

def load_kontrol_listesi():
    return load_json(KONTROL_FILE, {"pairs": [], "next_pair_id": 1})

def get_violation_pair(user1_id, user2_id):
    """Eğer iki kullanıcı listeyse çifti döndürür, aksi halde None"""
    data = load_kontrol_listesi()
    for pair in data["pairs"]:
        ids = [pair["user1"]["id"], pair["user2"]["id"]]
        if user1_id in ids and user2_id in ids:
            return pair
    return None

async def trigger_userbot_warn(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, p1_name, p2_name, reason):
    """Userbot ile warn atar ve loglar."""
    if userbot and userbot.is_connected:
        try:
            await userbot.send_message(
                chat_id=int(chat_id),
                text=f"/warn İletişim İhlali: Karşılıklı muhatap olmama kararına uyulmadı.\nSebep: {reason}",
                reply_to_message_id=message_id
            )
            await log_to_admin(context, f"⚠️ **İhlal Tespit Edildi ve Warn Atıldı!**\nKişiler: {p1_name} ↔ {p2_name}\nSebep: {reason}\nDurum: Başarılı ✅")
        except Exception as e:
            await log_to_admin(context, f"❌ **İhlal tespit edildi ama Warn ATILAMADI!**\nKişiler: {p1_name} ↔ {p2_name}\nSebep: {reason}\nHata Kodu: {e}\n*Not: Userbot mesajı bulamamış veya grupta yetkisi/oturumu düşmüş olabilir.*")
    else:
        await log_to_admin(context, f"❌ **İhlal tespit edildi ancak Userbot BAĞLI DEĞİL!**\nKişiler: {p1_name} ↔ {p2_name}")

# ==================== KURALLAR (TAM HALİ) ====================
RULES = [
    "📌Kişisel verilerin ifşası uyarılmaksızın ban sebebidir.",
    "📌Şahısa küfür yasaktır. Onun haricinde küfür serbesttir. Karşılıklı atışmalarda küfür kullanımında her iki taraf da uyarılacaktır.",
    "📌Tartışma yaşadığınız kişiye sizinle muhatap olmamasını söyledikten sonra chatte ya da seste laf atması ve herhangi bir gönderinizi yanıtlaması ve mesajınıza emoji bırakması yasaktır. İhlali durumunda şikayet gerekmeksizin kuralı ihlal eden kişi yönetici olsa dahi uyarı yapılır.",
    "📌Gruba yeni katılan üyelerle henüz gerekli samimiyet oluşmadan; isimleri, kullanıcı adları (nick), profil fotoğrafları veya yaşları gibi kişisel unsurlar üzerinden mizah yapılması, rapor edilmesine gerek duyulmaksızın doğrudan uyarı sebebi dir. Bu kural yöneticiler dahil tüm üyeler için istisnasız geçerlidir.",
    "📌Yöneticilere bildirmek istediğiniz bir mesajı alıntılayarak /Report ya da @admin komutunu yazabilirsiniz. Gereksiz kullananlar uyarılacaktır.",
    "📌İftira, milli ve kutsal değerlere hakaret yasaktır. Sohbet akışını bozacak şekilde kişisel tartışmaları devam ettirmek yasaktır.",
    "📌Herhangi bir terör örgütünü, illegal oluşumu vs. övmek uyarılmaksızın ban sebebi dir.",
    "📌Pornografik ve ileri şiddet içeren görsel içerikler kesinlikle yasaktır.",
    "📌Çıkmadan önce geçerli bir neden belirtmeksizin gruptan ayrılan üyeler 15 günden önce gruba tekrar dahil olamazlar.",
    "📌Grup üyesi olmayan yanınızdaki arkadaşlarınızın grup seslisindeki sohbete katılması yasaktır.",
    "📌Başka grubun reklamını yapmak ve reklam olabilecek şekilde başka grupla ilgili konuşmak ban sebebidir.",
]

async def post_random_rule(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    if not (now.hour >= 8 or now.hour < 1):
        return
    
    today_str = now.strftime("%Y-%m-%d")
    data = load_json(RULES_SENT_FILE, {"date": today_str, "sent": []})
    
    if data.get("date") != today_str:
        data = {"date": today_str, "sent": []}
        
    sent = set(data.get("sent", []))
    available = [i for i in range(len(RULES)) if i not in sent]
    
    if not available:
        return
        
    idx = random.choice(available)
    await context.bot.send_photo(chat_id=ALLOWED_GROUP_ID, photo=RULE_IMAGE_URL, caption=RULES[idx])
    
    sent.add(idx)
    data["sent"] = list(sent)
    save_json(RULES_SENT_FILE, data)

# ==================== FİLTRE ÖZELLİĞİ ====================
async def filtreekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Kullanım: /filtreekle kelime @kisi1 @kisi2")
        return
    kelime = args[0].lower()
    kisiler = " ".join(args[1:])
    data = load_json(FILTRE_FILE, {})
    data[kelime] = kisiler
    save_json(FILTRE_FILE, data)
    await update.message.reply_text(f"✅ Filtre başarıyla eklendi.\n'{kelime}' yazıldığında etiketlenecekler: {kisiler}")

async def filtresil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
    if not context.args:
        await update.message.reply_text("Kullanım: /filtresil kelime")
        return
    kelime = context.args[0].lower()
    data = load_json(FILTRE_FILE, {})
    if kelime in data:
        del data[kelime]
        save_json(FILTRE_FILE, data)
        await update.message.reply_text(f"✅ '{kelime}' filtresi başarıyla silindi.")
    else:
        await update.message.reply_text(f"❌ '{kelime}' kelimesine ait filtre bulunamadı.")

async def filtreliste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_json(FILTRE_FILE, {})
    if not data:
        await update.message.reply_text("Aktif filtre bulunmamaktadır.")
        return
    text = "📝 **Aktif Filtreler:**\n\n"
    for k, v in data.items():
        text += f"- **{k}** -> {v}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def filtre_dinleyici(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if str(update.message.chat.id) != ALLOWED_GROUP_ID: return
    
    text = update.message.text.lower()
    data = load_json(FILTRE_FILE, {})
    
    for kelime, kisiler in data.items():
        if re.search(r'\b' + re.escape(kelime) + r'\b', text):
            await update.message.reply_text(kisiler)
            break

# ==================== KONTROL (İLETİŞİM YASAĞI) ====================
MUHATAP_REGEX = re.compile(r'(?i)(muhatap olma|benimle muhatap olma|konuşmayalım|konuşma|muhatap olmayalım)')

async def muhatap_olma_anket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat.id) != ALLOWED_GROUP_ID or not update.message.reply_to_message:
        return

    text = update.message.text or update.message.caption or ""
    if not MUHATAP_REGEX.search(text):
        return

    sender = update.message.from_user
    target = update.message.reply_to_message.from_user
    
    if not sender or not target or sender.id == target.id:
        return

    if get_violation_pair(sender.id, target.id):
        return

    active_polls = context.bot_data.get("active_polls", set())
    pair_key = tuple(sorted([sender.id, target.id]))
    if pair_key in active_polls:
        return

    poll = await context.bot.send_poll(
        chat_id=update.message.chat_id,
        question="Bu kişinin seninle muhatap olmasını istemediğini belirtiyorsun. Aynı şekilde sen de bu kişiye cevap, laf ve hatta emoji dahi atmayacaksın. Kabul ediyor musun?",
        options=["✅ Evet, kabul ediyorum", "❌ Hayır"],
        is_anonymous=False,
        reply_to_message_id=update.message.message_id
    )

    active_polls.add(pair_key)
    context.bot_data["active_polls"] = active_polls

    context.bot_data[f"muhatap_poll_{poll.poll.id}"] = {
        "chat_id": update.message.chat_id,
        "sender_id": sender.id,
        "target_id": target.id,
        "sender_name": get_user_mention(sender),
        "target_name": get_user_mention(target),
        "pair_key": pair_key
    }

async def muhatap_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    poll_data = context.bot_data.get(f"muhatap_poll_{poll_id}")
    
    if not poll_data:
        return
        
    if "active_polls" in context.bot_data:
        context.bot_data["active_polls"].discard(poll_data["pair_key"])

    if poll_answer.user.id != poll_data["sender_id"]:
        return

    if poll_answer.option_ids[0] == 0:  # Evet
        data = load_kontrol_listesi()
        
        if not get_violation_pair(poll_data["sender_id"], poll_data["target_id"]):
            new_pair = {
                "pair_id": data["next_pair_id"],
                "user1": {"id": poll_data["sender_id"], "name": poll_data["sender_name"]},
                "user2": {"id": poll_data["target_id"], "name": poll_data["target_name"]}
            }
            data["pairs"].append(new_pair)
            data["next_pair_id"] += 1
            save_json(KONTROL_FILE, data)

            await context.bot.send_message(
                chat_id=poll_data["chat_id"],
                text=f"✅ İletişim yasağı otomatik eklendi!\n{poll_data['sender_name']} ↔ {poll_data['target_name']}\nArtık birbirinize reply veya emoji atamazsınız."
            )
            await log_to_admin(context, f"✅ **Yeni İletişim Yasağı (Anket ile):**\n{poll_data['sender_name']} ↔ {poll_data['target_name']}")
    
    del context.bot_data[f"muhatap_poll_{poll_id}"]

async def kontrolet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
        
    if len(context.args) < 2 or not userbot:
        await update.message.reply_text("Kullanım: /kontrolet @kisi1 @kisi2")
        return

    try:
        u1 = await userbot.get_users(context.args[0])
        u2 = await userbot.get_users(context.args[1])
        
        data = load_kontrol_listesi()
        if get_violation_pair(u1.id, u2.id):
            await update.message.reply_text("Bu iki kullanıcı zaten listede.")
            return
            
        new_pair = {
            "pair_id": data["next_pair_id"],
            "user1": {"id": u1.id, "name": get_user_mention(u1)},
            "user2": {"id": u2.id, "name": get_user_mention(u2)}
        }
        data["pairs"].append(new_pair)
        data["next_pair_id"] += 1
        save_json(KONTROL_FILE, data)
        
        await update.message.reply_text(f"✅ Liste güncellendi. {get_user_mention(u1)} ↔ {get_user_mention(u2)} artık birbirleriyle muhatap olamazlar.")
        await log_to_admin(context, f"✅ **Yeni İletişim Yasağı (Yönetici komutu ile):**\n{get_user_mention(u1)} ↔ {get_user_mention(u2)}")
    except Exception as e:
        await update.message.reply_text("Kullanıcılar bulunamadı. Lütfen geçerli kullanıcı adları veya ID'ler girin.")

async def kontrolliste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_kontrol_listesi()
    if not data["pairs"]:
        await update.message.reply_text("Kontrol listesi şu an boş.")
        return
        
    text = "🚫 **Muhatap Olmama Listesi**\n\n"
    for p in data["pairs"]:
        text += f"ID: {p['pair_id']} | {p['user1']['name']} ↔ {p['user2']['name']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def kontrolsil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in ALLOWED_KONTROL_USERS:
        return
        
    if not context.args:
        await update.message.reply_text("Kullanım: /kontrolsil <Pair ID>")
        return
        
    try:
        pair_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("Lütfen geçerli bir ID girin.")
        
    data = load_kontrol_listesi()
    original_len = len(data["pairs"])
    data["pairs"] = [p for p in data["pairs"] if p["pair_id"] != pair_id]
    
    if len(data["pairs"]) < original_len:
        save_json(KONTROL_FILE, data)
        await update.message.reply_text(f"✅ {pair_id} ID'li kural başarıyla silindi.")
        await log_to_admin(context, f"🗑️ **İletişim Yasağı Kaldırıldı:** ID {pair_id}")
    else:
        await update.message.reply_text("Belirtilen ID bulunamadı.")

async def kontrol_ihlal_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.reply_to_message: return
        
    sender = msg.from_user
    target = msg.reply_to_message.from_user
    if not sender or not target: return
    
    pair = get_violation_pair(sender.id, target.id)
    if pair:
        await trigger_userbot_warn(
            context,
            msg.chat_id,
            msg.message_id,
            pair["user1"]["name"],
            pair["user2"]["name"],
            "Yasaklı olduğu mesaja Yanıt (Reply) attı."
        )

async def kontrol_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction: return
        
    actor_id = reaction.actor.user.id if reaction.actor and reaction.actor.user else None
    if not actor_id: return
        
    msg_id = reaction.message_id
    author_id = RECENT_MESSAGE_AUTHORS.get(msg_id)
    
    if not author_id or actor_id == author_id: return
        
    pair = get_violation_pair(actor_id, author_id)
    if pair:
        await trigger_userbot_warn(
            context,
            reaction.chat.id,
            msg_id,
            pair["user1"]["name"],
            pair["user2"]["name"],
            "Yasaklı olduğu mesaja Tepki (Emoji) bıraktı."
        )

# ==================== /SORU (TAM ORİJİNAL KOD) ====================
async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private" or str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    text = update.message.text or update.message.caption or ""
    question_text = re.sub(r'(?i)^/soru\s*', '', text).strip()

    if not question_text and update.message.reply_to_message:
        question_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""

    photo_obj = None
    if update.message.photo:
        photo_obj = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo_obj = update.message.reply_to_message.photo[-1]

    image_data = None
    if photo_obj:
        file = await context.bot.get_file(photo_obj.file_id)
        image_bytes = await file.download_as_bytearray()
        image_data = types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')

    if not question_text and not image_data:
        await update.message.reply_photo(photo=SORU_IMAGE_URL, caption="Bir soru girsene.")
        return

    user_id = str(update.message.from_user.id)
    dynamic_instruction = "Kullanıcının sorusunu maksimum 100 kelime ile cevapla. Samimi ol."
    if user_id == "8639720888":
        dynamic_instruction += " Kullanıcıya 'ablam' diye hitap et."

    status_msg = await update.message.reply_text("☕ Cevap hazırlanıyor...")

    try:
        contents = [question_text] if question_text else []
        if image_data:
            contents.append(image_data)

        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL, contents=contents,
            config=types.GenerateContentConfig(system_instruction=dynamic_instruction, temperature=0.7)
        )
        try:
            await status_msg.delete()
        except:
            pass

        if response and response.text:
            await update.message.reply_photo(photo=SORU_IMAGE_URL, caption=response.text)
        else:
            await update.message.reply_text("Cevap üretilemedi.")
    except Exception as e:
        try:
            await status_msg.delete()
        except:
            pass
        await update.message.reply_text("Hata oluştu.")

# ==================== DUYURU (TAM ORİJİNAL KOD) ====================
async def duyuru_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    if str(update.message.from_user.id) not in ALLOWED_DUYURU_USERS:
        await update.message.reply_text("Yetkiniz yok.")
        return

    text = update.message.text or update.message.caption or ""
    duyuru_text = re.sub(r'^/duyuru\s*', '', text, flags=re.IGNORECASE).strip()
    if not duyuru_text:
        await update.message.reply_text("Duyuru metnini yaz.")
        return

    context.user_data["duyuru_text"] = duyuru_text
    message = await update.message.reply_poll(
        question="Duyuru nasıl paylaşılsın?",
        options=["📢 Bildirimli Sabitle", "📌 Bildirimsiz Sabitle"],
        is_anonymous=False,
    )
    context.bot_data[f"duyuru_poll_{message.poll.id}"] = {
        "chat_id": update.message.chat_id,
        "duyuru_text": duyuru_text,
    }

async def duyuru_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    poll_data = context.bot_data.get(f"duyuru_poll_{poll_id}")
    if not poll_data:
        return

    selected = poll_answer.option_ids[0]
    duyuru_text = poll_data["duyuru_text"]

    try:
        msg = await context.bot.send_message(
            chat_id=DUYURU_GROUP_ID,
            text=duyuru_text,
            disable_notification=(selected == 1)
        )
        await msg.pin(disable_notification=True)
        await context.bot.send_message(chat_id=poll_data["chat_id"], text="✅ Duyuru gönderildi.")
    except Exception as e:
        print(f"Duyuru hatası: {e}")

    del context.bot_data[f"duyuru_poll_{poll_id}"]

# ==================== HATIRLATMA (TAM ORİJİNAL KOD) ====================
async def hatirlat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return ConversationHandler.END

    chat_id = update.message.chat_id
    active_reminders = 0
    if context.job_queue:
        for job in context.job_queue.jobs():
            if job.name and f"_{chat_id}_" in job.name:
                active_reminders += 1

    if active_reminders >= 3:
        await update.message.reply_text("Şu anda aktif 3 hatırlatıcın var.")
        return ConversationHandler.END

    args = context.args
    if not args:
        await update.message.reply_text("Örnek: /hatirlat toplantı 15:40")
        return ConversationHandler.END

    possible_time = args[-1]
    if re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", possible_time):
        time_text = possible_time
        reminder_text = " ".join(args[:-1])
        context.user_data["reminder_text"] = reminder_text
        context.user_data["reminder_time"] = time_text
        keyboard = [[InlineKeyboardButton("Çok Önemli", callback_data="imp_high")],
                    [InlineKeyboardButton("Normal", callback_data="imp_normal")]]
        await update.message.reply_text(f"Saat {time_text} için önem?", reply_markup=InlineKeyboardMarkup(keyboard))
        return WAITING_FOR_IMPORTANCE
    else:
        context.user_data["reminder_text"] = " ".join(args)
        await update.message.reply_text("Saati SS:DD formatında gir:")
        return WAITING_FOR_TIME

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()
    if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", time_text):
        await update.message.reply_text("Hatalı format. SS:DD gir.")
        return WAITING_FOR_TIME
    context.user_data["reminder_time"] = time_text
    keyboard = [[InlineKeyboardButton("Çok Önemli", callback_data="imp_high")],
                [InlineKeyboardButton("Normal", callback_data="imp_normal")]]
    await update.message.reply_text("Önem derecesi?", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_FOR_IMPORTANCE

async def receive_importance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    importance = "high" if query.data == "imp_high" else "normal"
    reminder_text = context.user_data.get("reminder_text")
    time_text = context.user_data.get("reminder_time")
    chat_id = query.message.chat_id
    final_text = f"{reminder_text} ({time_text})"

    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    hour, minute = map(int, time_text.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target < now:
        target += datetime.timedelta(days=1)

    delay = (target - now).total_seconds()
    job_data = {"chat_id": chat_id, "text": final_text, "count": 0}
    job_id = f"rem_{chat_id}_{target.timestamp()}"

    if importance == "high":
        context.job_queue.run_repeating(send_high_importance_alert, interval=120, first=delay, data=job_data, name=f"high_{job_id}")
    else:
        context.job_queue.run_repeating(send_normal_importance_alert, interval=300, first=delay, data=job_data, name=f"normal_{job_id}")

    await query.edit_message_text(f"Hatırlatıcı kuruldu! Saat {time_text}")
    return ConversationHandler.END

async def send_high_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    if data["count"] >= 5:
        job.schedule_removal()
        return
    data["count"] += 1
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    await context.bot.send_message(chat_id=data["chat_id"], text=f"Hatırlatma: {data['text']}", reply_markup=InlineKeyboardMarkup(keyboard))

async def send_normal_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    if data["count"] >= 4:
        job.schedule_removal()
        return
    data["count"] += 1
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    await context.bot.send_message(chat_id=data["chat_id"], text=f"Hatırlatma: {data['text']}", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("read_"):
        job_name = query.data.split("read_", 1)[1]
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        await query.edit_message_text("Tamamlandı.")

async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    removed = 0
    for job in context.job_queue.jobs():
        if job.name and f"_{chat_id}_" in job.name:
            job.schedule_removal()
            removed += 1
    await update.message.reply_text(f"{removed} hatırlatıcı silindi." if removed else "Aktif hatırlatıcı yok.")

# ==================== ANTI SPAM (TAM ORİJİNAL KOD) ====================
async def anti_spam_octopus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.message.from_user
    if user and user.username and user.username.lower() == "octopusgame_bot":
        text = update.message.text or update.message.caption or ""
        if re.search(r'(?i)(t\.me|telegram\.me|katıl|aramıza)', text):
            try:
                await update.message.delete()
            except:
                pass

async def send_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot aktif ve çalışıyor.")

# ==================== ANA YAPI ====================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(start_userbot).post_shutdown(stop_userbot).build()

    # Cache mekanizması ve Spam filtresi
    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)), cache_message_author), group=-2)
    app.add_handler(MessageHandler(filters.ALL, anti_spam_octopus), group=-1)

    # Otomatik Kelime/Filtre Dinleyici
    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)) & filters.TEXT & ~filters.COMMAND, filtre_dinleyici), group=3)

    # İletişim İhlali Kontrolleri (Reply ve Reaction)
    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)) & filters.REPLY, kontrol_ihlal_kontrol), group=1)
    app.add_handler(MessageReactionHandler(kontrol_reaction))
    
    # Muhatap Olma Anketi Tetikleyici
    app.add_handler(MessageHandler(filters.Chat(chat_id=int(ALLOWED_GROUP_ID)) & filters.REPLY, muhatap_olma_anket), group=2)
    app.add_handler(PollAnswerHandler(muhatap_poll_answer))

    # Komutlar
    app.add_handler(CommandHandler("start", send_guide))
    app.add_handler(CommandHandler("yardim", send_guide))
    app.add_handler(CommandHandler("iptal", cancel_all))
    app.add_handler(MessageHandler(filters.Regex(r'(?i)^/soru'), soru))
    
    # Filtre Yönetimi Komutları
    app.add_handler(CommandHandler("filtreekle", filtreekle))
    app.add_handler(CommandHandler("filtresil", filtresil))
    app.add_handler(CommandHandler("filtreliste", filtreliste))
    
    # Duyuru Anketi
    app.add_handler(CommandHandler("duyuru", duyuru_start))
    app.add_handler(PollAnswerHandler(duyuru_poll_answer))

    # Kontrol Listesi Yönetimi
    app.add_handler(CommandHandler("kontrolet", kontrolet))
    app.add_handler(CommandHandler("kontrolliste", kontrolliste))
    app.add_handler(CommandHandler("kontrolsil", kontrolsil))

    # Hatırlatıcı Akışı
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("hatirlat", hatirlat_start)],
        states={
            WAITING_FOR_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
            WAITING_FOR_IMPORTANCE: [CallbackQueryHandler(receive_importance, pattern="^imp_")],
        },
        fallbacks=[CommandHandler("iptal", cancel_all)],
        allow_reentry=True
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))

    # 155 Dakikada Bir Rastgele Kural
    if app.job_queue:
        app.job_queue.run_repeating(post_random_rule, interval=155 * 60, first=60)

    print("Bot başlatılıyor...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
