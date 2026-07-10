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

# Çevresel Değişkenler
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_GROUP_ID = os.getenv("ALLOWED_GROUP_ID")
if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ALLOWED_GROUP_ID]):
    raise ValueError("Lütfen Railway Variables kısmına TELEGRAM_TOKEN, GEMINI_API_KEY ve ALLOWED_GROUP_ID ekleyin.")

# Kılavuz ve Soru Görsel Linkleri
IMAGE_URL_1 = "https://i.ibb.co/S4yWQrHg/MG-0345.jpg"
IMAGE_URL_2 = "https://i.ibb.co/Y748qgsP/MG-0346.jpg"
SORU_IMAGE_URL = "https://i.ibb.co/5Xcrbv87/MG-0398.jpg"
RULE_IMAGE_URL = "https://i.ibb.co/r2s2dYhb/MG-0987.png"

# Kullanılacak Gemini Modeli
GEMINI_MODEL = "gemini-2.5-flash"
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

WAITING_FOR_TIME = 1
WAITING_FOR_IMPORTANCE = 2

# Duyuru yapabilecek kullanıcı ID'leri
ALLOWED_DUYURU_USERS = ["6781642262", "8639720888", "7094870780", "8150494686", "8242824985"]

# Kontrol yetkili kullanıcı ID'leri
ALLOWED_KONTROL_USERS = ALLOWED_DUYURU_USERS

# Duyuru hedef grup ID'si
DUYURU_GROUP_ID = "-1003297262036"

# İletişim yasağı ihlallerinin bildirileceği grup
KONTROL_BILDIRIM_GROUP_ID = 6781642262

# Kurallar
RULES = [
    """📌Kişisel verilerin ifşası uyarılmaksızın ban sebebidir.""",
    """📌Şahısa küfür yasaktır. Onun haricinde küfür serbesttir. Karşılıklı atışmalarda küfür kullanımında her iki taraf da uyarılacaktır.""",
    """📌Tartışma yaşadığınız kişiye sizinle muhatap olmamasını söyledikten sonra chatte ya da seste laf atması ve herhangi bir gönderinizi yanıtlaması ve mesajınıza emoji bırakması yasaktır. İhlali durumunda şikayet gerekmeksizin kuralı ihlal eden kişi yönetici olsa dahi uyarı yapılır.""",
    """📌Gruba yeni katılan üyelerle henüz gerekli samimiyet oluşmadan; isimleri, kullanıcı adları (nick), profil fotoğrafları veya yaşları gibi kişisel unsurlar üzerinden mizah yapılması, rapor edilmesine gerek duyulmaksızın doğrudan uyarı sebebidir. Bu kural yöneticiler dahil tüm üyeler için istisnasız geçerlidir.""",
    """📌Yöneticilere bildirmek istediğiniz bir mesajı alıntılayarak /Report ya da @ admin komutunu yazabilirsiniz. Gereksiz kullananlar uyarılacaktır.""",
    """📌İftira, milli ve kutsal değerlere hakaret yasaktır. Sohbet akışını bozacak şekilde kişisel tartışmaları devam ettirmek yasaktır.""",
    """📌Herhangi bir terör örgütünü, illegal oluşumu vs. övmek uyarılmaksızın ban sebebidir.""",
    """📌Pornografik ve ileri şiddet içeren görsel içerikler kesinlikle yasaktır.""",
    """📌Çıkmadan önce geçerli bir neden belirtmeksizin gruptan ayrılan üyeler 15 günden önce gruba tekrar dahil olamazlar.""",
    """📌Grup üyesi olmayan yanınızdaki arkadaşlarınızın grup seslisindeki sohbete katılması yasaktır.""",
    """📌Başka grubun reklamını yapmak ve reklam olabilecek şekilde başka grupla ilgili konuşmak ban sebebi dir.""",
]
RULES_SENT_FILE = "rules_sent.json"
KONTROL_FILE = "kontrol_listesi.json"

# Emoji reaction cache
RECENT_MESSAGE_AUTHORS = OrderedDict()
MAX_CACHE_SIZE = 2500


def update_message_cache(message):
    if message and message.from_user:
        RECENT_MESSAGE_AUTHORS[message.message_id] = message.from_user.id
        if len(RECENT_MESSAGE_AUTHORS) > MAX_CACHE_SIZE:
            RECENT_MESSAGE_AUTHORS.popitem(last=False)


def load_rules_sent():
    today_str = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d")
    if os.path.exists(RULES_SENT_FILE):
        try:
            with open(RULES_SENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today_str:
                return set(data.get("sent", []))
        except Exception as e:
            print(f"Rules sent dosyası okunamadı: {e}")
    return set()


def save_rules_sent(sent_indices):
    today_str = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d")
    data = {"date": today_str, "sent": list(sent_indices)}
    try:
        with open(RULES_SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Rules sent dosyası kaydedilemedi: {e}")


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
        await context.bot.send_photo(
            chat_id=ALLOWED_GROUP_ID,
            photo=RULE_IMAGE_URL,
            caption=rule_text
        )
        print(f"Random kural #{idx} gruba gönderildi.")
    except Exception as e:
        print(f"Kural gönderme hatası: {e}")


# ──────────────────────────────── İletişim Kontrol Sistemi (Reply + Emoji + /warn) ────────────────────────────────
async def kontrolet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.message.chat.type
    if chat_type not in ["private", "group", "supergroup"]:
        return
    if chat_type != "private" and str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    user_id = str(update.message.from_user.id)
    if user_id not in ALLOWED_KONTROL_USERS:
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
            mentioned.append({
                "id": None,
                "name": username_part,
                "username": username_part
            })

    if len(mentioned) < 2:
        await update.message.reply_text("İki üyeyi etiketle. Örnek: /kontrolet @ahmet @ayse")
        return

    u1 = mentioned[0]
    u2 = mentioned[1]

    data = load_kontrol_listesi()
    new_pair = {
        "pair_id": data["next_pair_id"],
        "user1": u1,
        "user2": u2
    }
    data["pairs"].append(new_pair)
    data["next_pair_id"] += 1
    save_kontrol_listesi(data)

    await update.message.reply_text(
        f"✅ Madem bu ikisi muhatap olmak istemiyor, iyi... iletişim yasağı eklendi\n"
        f"#{new_pair['pair_id']} → {u1['name']} ↔ {u2['name']}\n"
        f"Bot gözlerini açtı."
    )


async def kontrolliste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.message.chat.type
    if chat_type != "private" and str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    user_id = str(update.message.from_user.id)
    if user_id not in ALLOWED_KONTROL_USERS:
        return

    data = load_kontrol_listesi()
    if not data.get("pairs"):
        await update.message.reply_text("İletişim kontrol listesi şu anda boş.")
        return

    lines = []
    for p in data["pairs"]:
        u1n = p["user1"]["name"]
        u2n = p["user2"]["name"]
        lines.append(f"{p['pair_id']}- {u1n} ve {u2n}")

    text = "📋 **İletişim Yasağı Listesi:**\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


async def kontrolsil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.message.chat.type
    if chat_type != "private" and str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    user_id = str(update.message.from_user.id)
    if user_id not in ALLOWED_KONTROL_USERS:
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Kullanım: /kontrolsil 2")
        return

    pair_id = int(args[0])
    data = load_kontrol_listesi()
    original = len(data["pairs"])
    data["pairs"] = [p for p in data["pairs"] if p["pair_id"] != pair_id]

    if len(data["pairs"]) < original:
        save_kontrol_listesi(data)
        await update.message.reply_text(f"✅ #{pair_id} numaralı yasağı listeden kaldırdın.")
    else:
        await update.message.reply_text(f"#{pair_id} bulunamadı.")


def get_user_mention(user):
    """Kullanıcıyı mention etmek için @username veya isim döndürür"""
    if user.username:
        return f"@{user.username}"
    return user.first_name or "Kullanıcı"


async def kontrol_ihlal_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply ile ihlal tespiti + /warn"""
    if str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return
    if not update.message.reply_to_message:
        return

    sender = update.message.from_user          # İhlal eden
    replied_user = update.message.reply_to_message.from_user

    if not sender or not replied_user:
        return

    data = load_kontrol_listesi()
    for pair in data.get("pairs", []):
        u1_id = pair["user1"].get("id")
        u2_id = pair["user2"].get("id")
        if u1_id is None or u2_id is None:
            continue

        # İhlal eden = sender
        if (sender.id == u1_id and replied_user.id == u2_id) or (sender.id == u2_id and replied_user.id == u1_id):
            mention = get_user_mention(sender)
            warn_text = f"/warn {mention} İletişim yasağı ihlali (yanıt verildi)"

            # İhlal eden kişinin mesajına reply olarak /warn at
            try:
                await update.message.reply_text(warn_text)
            except:
                await context.bot.send_message(chat_id=update.message.chat_id, text=warn_text)

            # Yönetim grubuna bildirim
            await send_kontrol_bildirim(context, "Reply", warn_text, update.message.chat_id)
            break


async def kontrol_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Emoji tepki ile ihlal tespiti + /warn"""
    reaction = update.message_reaction
    if not reaction or str(reaction.chat.id) != ALLOWED_GROUP_ID:
        return
    if not reaction.new_reaction:
        return

    reactor = reaction.user  # İhlal eden
    if not reactor:
        return

    original_author_id = RECENT_MESSAGE_AUTHORS.get(reaction.message_id)
    if not original_author_id:
        return

    data = load_kontrol_listesi()
    for pair in data.get("pairs", []):
        u1_id = pair["user1"].get("id")
        u2_id = pair["user2"].get("id")
        if u1_id is None or u2_id is None:
            continue

        if (reactor.id == u1_id and original_author_id == u2_id) or (reactor.id == u2_id and original_author_id == u1_id):
            mention = get_user_mention(reactor)
            warn_text = f"/warn {mention} İletişim yasağı ihlali (Emoji Tepki)"

            # Emoji atılan mesajı alıntılayarak /warn at
            try:
                await context.bot.send_message(
                    chat_id=reaction.chat.id,
                    text=warn_text,
                    reply_to_message_id=reaction.message_id
                )
            except:
                await context.bot.send_message(chat_id=reaction.chat.id, text=warn_text)

            # Yönetim grubuna bildirim
            await send_kontrol_bildirim(context, "Emoji Tepki", warn_text, reaction.chat.id)
            break


async def send_kontrol_bildirim(context, ihlal_tipi, warn_text, chat_id):
    """Yönetim grubuna (6781642262) bildirim gönderir"""
    try:
        await context.bot.send_message(
            chat_id=KONTROL_BILDIRIM_GROUP_ID,
            text=f"🚨 İletişim Yasağı İhlali ({ihlal_tipi})\n\n{warn_text}\n\nGrup: {chat_id}"
        )
    except Exception as e:
        print(f"Yönetim grubuna bildirim gönderilemedi: {e}")


# ──────────────────────────────── Diğer Fonksiyonlar ────────────────────────────────
async def send_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    guide = (
        "Es Justo Grup İçinde:\n"
        "/soru [metin] - Yapay zekaya kısa bir soru sorar.\n\n"
        "Özel Mesajda Hatırlatıcı Kurmak:\n"
        "/hatirlat [hatırlatılacak şey] [saat]\n"
        "Örnek: /hatirlat toplantıya katıl 15:40\n\n"
        "Özel Mesajda Duyuru:\n"
        "/duyuru [metin] - Gruba duyuru gönderir ve sabitler.\n\n"
        "/yardim veya /start - Bu kılavuzu tekrar gösterir.\n\n"
        "Bu botun bildirim sesini normal mesaj bildirim sesinden farklı yapmanız önerilir."
    )
    await update.message.reply_text(guide)
    try:
        await context.bot.send_photo(chat_id=update.message.chat_id, photo=IMAGE_URL_1, caption="BİLDİRİM SESLERİNİ DEĞİŞTİRME\nAdım 1: Bildirim Menüsü")
        await context.bot.send_photo(chat_id=update.message.chat_id, photo=IMAGE_URL_2, caption="Adım 2: Özel Ses Seçimi")
    except Exception as e:
        await update.message.reply_text("Kılavuzu yükleyemedim tüh.")


async def copy_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.copy_message(
            chat_id="-5199865415",
            from_chat_id=update.channel_post.chat_id,
            message_id=update.channel_post.message_id
        )
    except Exception as e:
        print(f"Kanal mesajı kopyalama hatası: {e}")


async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        return
    if str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    text = update.message.text or update.message.caption or ""
    question_text = re.sub(r'(?i)^/soru\s*', '', text).strip()

    if not question_text and update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        question_text = reply_text.strip()

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
        await update.message.reply_photo(
            photo=SORU_IMAGE_URL,
            caption="Bir soru girsene bu ne böyle şimdi? Örnek: /soru hava durumu nasıl?"
        )
        return

    user_id = str(update.message.from_user.id)
    dynamic_instruction = (
        "Kullanıcının sorusunu maksimum 100 kelime olacak şekilde yanıtla. "
        "Yanıtın en az 5 kelimeden oluşmalı. "
        "Her paragrafın en başına mutlaka uygun bir emoji koy. "
        "Genel olarak ansiklopedik, kaba veya robotik konuşma, samimi ve günlük bir dil kullan. "
        "Uzun cevaplarda paragrafa ayırabilirsin. "
    )
    if image_data:
        dynamic_instruction += "Kullanıcı bir görsel gönderdi. Görseli dikkatlice incele ve soruyu görselin içeriğine göre yanıtla. Görselde ne gördüğünü açıklamayı unutma. "
    if user_id == "8639720888":
        dynamic_instruction += "Lütfen kullanıcıya 'ablam' diye hitap et. Çok saygılı, kız kardeşi gibi sıcak, ablamlı bir dil kullan. "
    elif question_text.endswith("?"):
        dynamic_instruction += "Lütfen kullanıcıya 'güzelim' diye hitap et. Çok samimi, sıcak, sevimli ve flörtöz olmayan tatlı bir üslup kullan. "

    status_msg = await update.message.reply_text("☕ Gizem zihnini açmak için kahvesini yudumluyor...")

    async def loading_animation():
        frames = ["📖 Gizem cevabı düşünüyor...", "✍️ Gizem soruya cevap yazıyor..."]
        try:
            for frame in frames:
                await asyncio.sleep(3)
                await status_msg.edit_text(frame)
        except:
            pass

    animation_task = asyncio.create_task(loading_animation())

    try:
        contents = [question_text] if question_text else []
        if image_data:
            contents.append(image_data)

        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=dynamic_instruction,
                temperature=0.7,
            )
        )
        animation_task.cancel()
        try:
            await status_msg.delete()
        except:
            pass

        if response and response.text:
            clean_response = response.text
            if len(clean_response) <= 1024:
                await update.message.reply_photo(photo=SORU_IMAGE_URL, caption=clean_response)
            else:
                await update.message.reply_photo(photo=SORU_IMAGE_URL)
                await update.message.reply_text(clean_response)
        else:
            await update.message.reply_text("Bu saçma soruyu cevaplayamam.")
    except Exception as e:
        animation_task.cancel()
        try:
            await status_msg.delete()
        except:
            pass
        print(f"Gemini Hatası: {e}")
        await update.message.reply_text("Cevap üretilirken bir hata oluştu.")


# ──────────────────────────────── Duyuru Sistemi ────────────────────────────────
async def duyuru_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = str(update.message.from_user.id)
    if user_id not in ALLOWED_DUYURU_USERS:
        await update.message.reply_text("Bu komutu kullanma yetkiniz bulunmuyor.")
        return

    text = update.message.text or update.message.caption or ""
    duyuru_text = re.sub(r'^/duyuru\s*', '', text, flags=re.IGNORECASE).strip()

    if not duyuru_text:
        await update.message.reply_text("Duyuru metnini yazmalısın. Örnek: /duyuru Yarın saat 14:00'te Zenithar'a ibadet var.")
        return

    context.user_data["duyuru_text"] = duyuru_text

    message = await update.message.reply_poll(
        question="Duyuru nasıl paylaşılsın?",
        options=["📢 Bildirimli Sabitle", "📌 Bildirimsiz Sabitle"],
        is_anonymous=False,
    )

    context.bot_data[f"duyuru_poll_{message.poll.id}"] = {
        "chat_id": update.message.chat_id,
        "user_id": user_id,
        "duyuru_text": duyuru_text,
    }


async def duyuru_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    poll_data = context.bot_data.get(f"duyuru_poll_{poll_id}")
    if not poll_data:
        return

    option_ids = poll_answer.option_ids
    if not option_ids:
        return

    selected = option_ids[0]
    duyuru_text = poll_data["duyuru_text"]

    try:
        if selected == 0:
            msg = await context.bot.send_message(
                chat_id=DUYURU_GROUP_ID,
                text=duyuru_text,
                disable_notification=False,
            )
        else:
            msg = await context.bot.send_message(
                chat_id=DUYURU_GROUP_ID,
                text=duyuru_text,
                disable_notification=True,
            )

        await msg.pin(disable_notification=True)

        await context.bot.send_message(
            chat_id=poll_data["chat_id"],
            text="✅ Duyuru gruba gönderildi ve sabitlendi."
        )
    except Exception as e:
        print(f"Duyuru gönderme hatası: {e}")
        await context.bot.send_message(
            chat_id=poll_data["chat_id"],
            text="❌ Duyuru gönderilirken bir hata oluştu."
        )

    del context.bot_data[f"duyuru_poll_{poll_id}"]


# ──────────────────────────────── Hatırlatıcı Sistemi ────────────────────────────────
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
        await update.message.reply_text("Şu anda aktif 3 adet hatırlatıcın bulunuyor. Daha fazla ekleyebilmek için mevcut olanlardan birinin tamamlanmasını bekle veya /iptal komutu ile hepsini silebilirsin.")
        return ConversationHandler.END

    args = context.args
    if not args:
        await update.message.reply_text("Hatırlatılacak o çok önemli şeyi yaz. Örnek: /hatirlat toplantıya katıl 15:40")
        return ConversationHandler.END

    possible_time = args[-1]
    if re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", possible_time):
        time_text = possible_time
        reminder_text = " ".join(args[:-1])
        if not reminder_text:
            await update.message.reply_text("Hatırlatılacak o dünya önemlisi şeyi de söyle. Örnek: /hatirlat toplantı 15:40")
            return ConversationHandler.END
        context.user_data["reminder_text"] = reminder_text
        context.user_data["reminder_time"] = time_text
        keyboard = [[InlineKeyboardButton("Çok Önemli", callback_data="imp_high")], [InlineKeyboardButton("Normal", callback_data="imp_normal")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Saat {time_text} için '{reminder_text}' hatırlatıcısının önem derecesi nedir?", reply_markup=reply_markup)
        return WAITING_FOR_IMPORTANCE
    else:
        reminder_text = " ".join(args)
        context.user_data["reminder_text"] = reminder_text
        await update.message.reply_text("Hatırlatma saatini SS:DD formatında gir (Örneğin 15:40):")
        return WAITING_FOR_TIME


async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()
    if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", time_text):
        await update.message.reply_text("Hatalı format. Saati 15:40 formatında gir:")
        return WAITING_FOR_TIME
    context.user_data["reminder_time"] = time_text
    keyboard = [[InlineKeyboardButton("Çok Önemli", callback_data="imp_high")], [InlineKeyboardButton("Normal", callback_data="imp_normal")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bu hatırlatıcının önem derecesi nedir?", reply_markup=reply_markup)
    return WAITING_FOR_IMPORTANCE


async def receive_importance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    importance = "high" if query.data == "imp_high" else "normal"
    reminder_text = context.user_data.get("reminder_text")
    time_text = context.user_data.get("reminder_time")
    chat_id = query.message.chat_id
    final_reminder_text = f"{reminder_text} ({time_text})"

    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    hour, minute = map(int, time_text.split(":"))
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_time < now:
        target_time += datetime.timedelta(days=1)

    delay_seconds = (target_time - now).total_seconds()
    job_data = {"chat_id": chat_id, "text": final_reminder_text, "count": 0}
    job_id = f"rem_{chat_id}_{target_time.timestamp()}"

    if importance == "high":
        context.job_queue.run_repeating(send_high_importance_alert, interval=120, first=delay_seconds, data=job_data, name=f"high_loop_{job_id}")
    else:
        context.job_queue.run_repeating(send_normal_importance_alert, interval=300, first=delay_seconds, data=job_data, name=f"normal_loop_{job_id}")

    await query.edit_message_text(f"Hatırlatıcı kuruldu! Saat {time_text} geldiğinde bildirim alacaksın.")
    return ConversationHandler.END


async def send_high_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    if data["count"] >= 5:
        job.schedule_removal()
        return
    data["count"] += 1
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=f"Hatırlatma: {data['text']}", reply_markup=reply_markup)


async def send_normal_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    if data["count"] >= 4:
        job.schedule_removal()
        return
    data["count"] += 1
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=f"Hatırlatma: {data['text']}", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("read_"):
        job_name = query.data.split("read_", 1)[1]
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
        await query.edit_message_text("Görev tamamlandı.")


async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    removed_count = 0
    if context.job_queue:
        for job in context.job_queue.jobs():
            if job.name and f"_{chat_id}_" in job.name:
                job.schedule_removal()
                removed_count += 1
    if removed_count > 0:
        await update.message.reply_text(f"İşlem iptal edildi ve sana ait aktif {removed_count} hatırlatıcı tamamen silindi.")
    else:
        await update.message.reply_text("İşlem iptal edildi. (Zaten aktif bir hatırlatıcın bulunmuyordu.)")
    return ConversationHandler.END


# ──────────────────────────────── Anti Spam ────────────────────────────────
async def anti_spam_octopus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.message.from_user
    if not user or not user.username:
        return
    if user.username.lower() == "octopusgame_bot":
        text = update.message.text or update.message.caption or ""
        spam_pattern = r'(?i)(t\.me/?|telegram\.me/?|aram[ıi]za|kat[ıi]l|grubumuza)'
        if re.search(spam_pattern, text):
            try:
                await update.message.delete()
                print("OctopusGame spamı başarıyla silindi.")
            except Exception as e:
                print(f"Spam mesaj silinemedi: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("hatirlat", hatirlat_start)],
        states={
            WAITING_FOR_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
            WAITING_FOR_IMPORTANCE: [CallbackQueryHandler(receive_importance, pattern="^imp_")],
        },
        fallbacks=[CommandHandler("iptal", cancel_all)],
        allow_reentry=True
    )

    # Cache handler (emoji için)
    app.add_handler(
        MessageHandler(
            filters.Chat(chat_id=int(ALLOWED_GROUP_ID)),
            cache_message_author
        ),
        group=-2
    )

    # SPAM KONTROLÜ
    app.add_handler(MessageHandler(filters.ALL, anti_spam_octopus), group=-1)

    app.add_handler(CommandHandler("start", send_guide))
    app.add_handler(CommandHandler("yardim", send_guide))
    app.add_handler(CommandHandler("iptal", cancel_all))

    app.add_handler(MessageHandler(filters.Regex(r'(?i)^/soru'), soru))

    app.add_handler(CommandHandler("duyuru", duyuru_start))
    app.add_handler(PollAnswerHandler(duyuru_poll_answer))

    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003613910089) & filters.UpdateType.CHANNEL_POST, copy_channel_post))

    # Kontrol komutları
    app.add_handler(CommandHandler("kontrolet", kontrolet))
    app.add_handler(CommandHandler("kontrolliste", kontrolliste))
    app.add_handler(CommandHandler("kontrolsil", kontrolsil))

    # Reply ihlal + /warn
    app.add_handler(
        MessageHandler(
            filters.Chat(chat_id=int(ALLOWED_GROUP_ID)) & filters.REPLY,
            kontrol_ihlal_kontrol
        )
    )

    # Emoji tepki ihlal + /warn
    app.add_handler(MessageReactionHandler(kontrol_reaction))

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))

    if app.job_queue:
        app.job_queue.run_repeating(
            post_random_rule,
            interval=155 * 60,
            first=60,
            name="random_rule_poster"
        )

    print("Bot başlatılıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()
