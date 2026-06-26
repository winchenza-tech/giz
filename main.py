import os
import re
import datetime
import pytz
import asyncio
import json
import io
import matplotlib
matplotlib.use('Agg') # Sunucuda hata vermeden arka planda grafik çizmek için
import matplotlib.pyplot as plt

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters, PollAnswerHandler
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

# Kullanılacak Gemini Modeli
GEMINI_MODEL = "gemini-2.5-flash"

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

WAITING_FOR_TIME = 1
WAITING_FOR_IMPORTANCE = 2
STATS_FILE = "stats.json"

# Duyuru yetkili kullanıcı ID'leri
DUYURU_YETKILI_IDS = [6781642262, 8639720888, 7094870780]
DUYURU_GRUP_ID = "-1003297262036"

# Mesaj silme hedef kullanıcı ve zaman aralığı
SILINECEK_BOT_USER_ID = 5933486341
SILINECEK_GRUP_ID = "-5199865415"

# Duyuru conversation states
WAITING_FOR_DUYURU_TEXT = 10
WAITING_FOR_DUYURU_POLL = 11

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f)

async def send_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    guide = (
        "Es Justo Grup İçinde:\n"
        "/soru [metin] - Yapay zekaya kısa bir soru sorar.\n\n"
        "Özel Mesajda Hatırlatıcı Kurmak:\n"
        "/hatirlat [hatırlatılacak şey] [saat]\n"
        "Örnek: /hatirlat toplantıya katıl 15:40\n\n"
        "/duyuru - Gruba duyuru gönderir ve sabitler (yetkili kullanıcılar).\n\n"
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
    """Belirli kanaldan gelen mesajları diğer gruba kopyalar."""
    try:
        await context.bot.copy_message(
            chat_id="-5199865415",
            from_chat_id=update.channel_post.chat_id,
            message_id=update.channel_post.message_id
        )
    except Exception as e:
        print(f"Kanal mesajı kopyalama hatası: {e}")


# ───────────────────────────────────────────────────────
# DEĞİŞİKLİK 4: 00:00-00:30 arası 5933486341 ID'li
# kullanıcının -5199865415 grubundaki mesajlarını sil
# ───────────────────────────────────────────────────────
async def auto_delete_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saat 00:00-00:30 arasında belirli kullanıcının mesajını anında siler."""
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)

    if not (now.hour == 0 and 0 <= now.minute <= 30):
        return

    if not update.message:
        return

    if update.message.from_user and update.message.from_user.id == SILINECEK_BOT_USER_ID:
        try:
            await update.message.delete()
        except Exception as e:
            print(f"Mesaj silme hatası: {e}")


# ───────────────────────────────────────────────────────
# DEĞİŞİKLİK 1: Profesyonel rapor + grafik Y ekseni max 70
# ───────────────────────────────────────────────────────
async def score_bot_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message Score Bot'un mesajını okuyup grafikli rapor gönderir."""
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    
    # Sadece 00:00 ile 00:25 arasında çalışsın
    if not (now.hour == 0 and 0 <= now.minute <= 25):
        return

    text = update.message.text or update.message.caption
    if not text:
        return

    # İstatistikleri Gemini'ye çektiriyoruz
    extract_prompt = f"Aşağıdaki mesaj istatistiği metninden 'toplam mesaj sayısını' ve 'kullanıcı (çeşitliliği) sayısını' bul. Sadece şu formatta geçerli bir JSON döndür: {{\"msg_count\": 100, \"user_count\": 10}}. Metin: {text}"
    
    try:
        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=extract_prompt
        )
        json_str = response.text.strip().strip('`').replace('json\n', '')
        data = json.loads(json_str)
        msg_count = data.get("msg_count", 0)
        user_count = data.get("user_count", 0)
    except Exception as e:
        print(f"Veri çekilemedi: {e}")
        return

    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    last_week_str = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    stats = load_stats()
    stats[today_str] = {"msg_count": msg_count, "user_count": user_count}
    save_stats(stats)

    labels = ['Geçen Hafta', 'Dün', 'Bugün']
    m_counts = [stats.get(last_week_str, {}).get("msg_count", 0), stats.get(yesterday_str, {}).get("msg_count", 0), msg_count]
    u_counts = [stats.get(last_week_str, {}).get("user_count", 0), stats.get(yesterday_str, {}).get("user_count", 0), user_count]

    # Grafiği Çiziyoruz
    fig, ax1 = plt.subplots(figsize=(8, 5))
    x = range(len(labels))
    width = 0.35

    # Mesaj sayısı barları (sol Y ekseni)
    bars1 = ax1.bar([i - width/2 for i in x], m_counts, width, label='Mesaj Sayısı', color='#4A90E2')
    ax1.set_ylabel('Mesaj Sayısı', color='#4A90E2')
    ax1.tick_params(axis='y', labelcolor='#4A90E2')
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels)

    # Katılımcı sayısı barları (sağ Y ekseni, max 70)
    ax2 = ax1.twinx()
    bars2 = ax2.bar([i + width/2 for i in x], u_counts, width, label='Katılımcı Sayısı', color='#F5A623')
    ax2.set_ylabel('Katılımcı Sayısı', color='#F5A623')
    ax2.tick_params(axis='y', labelcolor='#F5A623')
    ax2.set_ylim(0, 70)

    # Barların üstüne değer yaz
    for bar in bars1:
        height = bar.get_height()
        if height > 0:
            ax1.text(bar.get_x() + bar.get_width() / 2., height, f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars2:
        height = bar.get_height()
        if height > 0:
            ax2.text(bar.get_x() + bar.get_width() / 2., height, f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    fig.suptitle('Grup Günlük Aktiflik Kıyaslaması', fontsize=13, fontweight='bold')
    fig.legend(loc='upper left', bbox_to_anchor=(0.12, 0.92))
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    # Profesyonel rapor prompt'u
    report_prompt = (
        f"Bugün grupta {msg_count} mesaj atıldı ve {user_count} kişi katılım gösterdi. "
        f"Dün {m_counts[1]} mesaj yazılmış ve {u_counts[1]} kişi aktifti. "
        f"Geçen hafta aynı gün ise {m_counts[0]} mesaj ve {u_counts[0]} katılımcı vardı. "
        f"Bu verileri kıyaslayarak kısa, profesyonel ve ciddi bir günlük özet raporu yaz. "
        f"Maksimum 100 kelime. Espri yapma, ucuz motivasyon cümlesi kullanma, emoji kullanma. "
        f"Kurumsal ve düzgün bir Türkçe ile yaz. Verilerdeki artış veya düşüşü net ifade et. "
        f"Rapor bir iş ortamına uygun olsun."
    )
    try:
        report_response = await gemini_client.aio.models.generate_content(model=GEMINI_MODEL, contents=report_prompt)
        report_text = report_response.text
    except:
        report_text = "Günlük grup aktivite raporu ektedir."

    try:
        await context.bot.send_photo(
            chat_id="-5199865415",
            photo=buf,
            caption=report_text
        )
    except Exception as e:
        print(f"Rapor gönderilirken hata oluştu: {e}")


# ───────────────────────────────────────────────────────
# DEĞİŞİKLİK 2 & 3: /soru — token sınırı kaldırıldı,
# görselli mesajlarda caption'dan /soru okunuyor
# ───────────────────────────────────────────────────────
async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        print(f"Gelen Grup ID: {update.message.chat.id} | Beklenen ID: {ALLOWED_GROUP_ID}")

    if update.message.chat.type == "private" or str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    # Soru metni belirleme (Doğrudan mesaj veya caption)
    text = update.message.text or update.message.caption or ""
    question_text = re.sub(r'^/soru\s*', '', text, flags=re.IGNORECASE).strip()

    # Eğer metin yoksa alıntılanan mesajdaki metne bak
    if not question_text and update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        question_text = reply_text.strip()

    # Görsel kontrolü (Mesajın kendisinde veya alıntılanan mesajda)
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

    # Dinamik Samimi Üslup Ayarı
    user_id = str(update.message.from_user.id)
    dynamic_instruction = (
        "Kullanıcının sorusunu maksimum 100 kelime olacak şekilde yanıtla. "
        "Yanıtın en az 5 kelimeden oluşmalı. "
        "Her paragrafın en başına mutlaka uygun bir emoji koy. "
        "Genel olarak ansiklopedik, kaba veya robotik konuşma, samimi ve günlük bir dil kullan. "
        "Uzun cevaplarda paragrafa ayırabilirsin. "
    )

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
        except: pass
            
    animation_task = asyncio.create_task(loading_animation())

    try:
        contents = [question_text] if question_text else []
        if image_data:
            contents.append(image_data)

        # Token sınırı kaldırıldı — 100 kelime sınırı prompt ile sağlanıyor
        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=dynamic_instruction,
                temperature=0.7,
            )
        )
        
        animation_task.cancel()
        try: await status_msg.delete()
        except: pass

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
        try: await status_msg.delete()
        except: pass
        print(f"Gemini Hatası: {e}")
        await update.message.reply_text("Cevap üretilirken bir hata oluştu.")


# ───────────────────────────────────────────────────────
# DEĞİŞİKLİK 5: /duyuru özelliği
# ───────────────────────────────────────────────────────
async def duyuru_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yetkili kullanıcılar özel mesajda /duyuru yazarak duyuru sürecini başlatır."""
    if update.message.chat.type != "private":
        await update.message.reply_text("Duyuru komutu yalnızca bota özel mesajda kullanılabilir.")
        return ConversationHandler.END

    user_id = update.message.from_user.id
    if user_id not in DUYURU_YETKILI_IDS:
        await update.message.reply_text("Bu komutu kullanma yetkiniz bulunmamaktadır.")
        return ConversationHandler.END

    await update.message.reply_text("Gruba göndermek istediğiniz duyuru metnini yazın:")
    return WAITING_FOR_DUYURU_TEXT


async def duyuru_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Duyuru metnini alır ve bildirim tercihini sorar."""
    duyuru_text = update.message.text.strip()
    if not duyuru_text:
        await update.message.reply_text("Duyuru metni boş olamaz. Lütfen tekrar yazın:")
        return WAITING_FOR_DUYURU_TEXT

    context.user_data["duyuru_text"] = duyuru_text

    # Anket olarak bildirim tercihini sor
    poll_message = await update.message.reply_poll(
        question="Bu duyuru nasıl sabitlensin?",
        options=["Bildirimli sabitle (üyelere bildirim gider)", "Bildirimsiz sabitle (sessiz sabitleme)"],
        is_anonymous=False,
        allows_multiple_answers=False,
    )
    context.user_data["duyuru_poll_id"] = poll_message.poll.id
    context.user_data["duyuru_chat_id"] = update.message.chat_id
    return WAITING_FOR_DUYURU_POLL


async def duyuru_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anket yanıtını alır, duyuruyu gruba gönderir ve sabitler."""
    poll_answer = update.poll_answer
    user_id = poll_answer.user.id

    if user_id not in DUYURU_YETKILI_IDS:
        return

    # user_data'ya erişmek için chat_id gerekli
    chat_data_key = f"duyuru_{user_id}"

    # Poll answer handler'da context.user_data doğrudan erişilemez,
    # bu yüzden bot_data üzerinden geçici veri saklıyoruz.
    bot_data = context.bot_data
    duyuru_info = bot_data.get(chat_data_key)

    if not duyuru_info:
        return

    duyuru_text = duyuru_info.get("duyuru_text", "")
    chat_id = duyuru_info.get("duyuru_chat_id")

    if not duyuru_text:
        return

    # Seçilen şık: 0 = bildirimli, 1 = bildirimsiz
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else 1
    disable_notification = (selected_option == 1)

    try:
        # Duyuruyu gruba gönder
        sent_message = await context.bot.send_message(
            chat_id=DUYURU_GRUP_ID,
            text=duyuru_text,
            disable_notification=disable_notification
        )
        # Mesajı sabitle
        await context.bot.pin_chat_message(
            chat_id=DUYURU_GRUP_ID,
            message_id=sent_message.message_id,
            disable_notification=disable_notification
        )
        # Kullanıcıya bilgi ver
        bildirim_durumu = "bildirimli" if not disable_notification else "bildirimsiz"
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Duyuru başarıyla gruba gönderildi ve {bildirim_durumu} olarak sabitlendi."
        )
    except Exception as e:
        print(f"Duyuru gönderme hatası: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Duyuru gönderilirken bir hata oluştu: {e}"
        )

    # Geçici veriyi temizle
    bot_data.pop(chat_data_key, None)


async def duyuru_save_to_bot_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Duyuru metnini alır, bot_data'ya kaydeder ve anketi gönderir."""
    duyuru_text = update.message.text.strip()
    if not duyuru_text:
        await update.message.reply_text("Duyuru metni boş olamaz. Lütfen tekrar yazın:")
        return WAITING_FOR_DUYURU_TEXT

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    # bot_data'ya kaydet (poll_answer handler'dan erişilebilsin)
    chat_data_key = f"duyuru_{user_id}"
    context.bot_data[chat_data_key] = {
        "duyuru_text": duyuru_text,
        "duyuru_chat_id": chat_id,
    }

    # Anket olarak bildirim tercihini sor
    await update.message.reply_poll(
        question="Bu duyuru nasıl sabitlensin?",
        options=["Bildirimli sabitle (üyelere bildirim gider)", "Bildirimsiz sabitle (sessiz sabitleme)"],
        is_anonymous=False,
        allows_multiple_answers=False,
    )
    return ConversationHandler.END


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
        await update.message.reply_text("Şu anda aktif 3 adet hatırlatıcın bulunuyor. Daha fazla ekleyebilmek için mevcut olanlardan birinin tamamlanmasını bekl veya /iptal komutu ile hepsini silebilirsin.")
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
        await update.message.reply_text("Hatalı format. Bunu çocuk bile becerebilir de neyse saati 15:40 formatında gir:")
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
    if target_time < now: target_time += datetime.timedelta(days=1)
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
    if data["count"] >= 5: job.schedule_removal(); return
    data["count"] += 1
    keyboard = [[InlineKeyboardButton("Okudum", callback_data=f"read_{job.name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=f"Hatırlatma: {data['text']}", reply_markup=reply_markup)

async def send_normal_importance_alert(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    if data["count"] >= 4: job.schedule_removal(); return
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
        for job in current_jobs: job.schedule_removal()
        await query.edit_message_text(f"Görev tamamlandı.")

async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    removed_count = 0
    if context.job_queue:
        for job in context.job_queue.jobs():
            if job.name and f"_{chat_id}_" in job.name:
                job.schedule_removal()
                removed_count += 1
    if removed_count > 0: await update.message.reply_text(f"İşlem iptal edildi ve sana ait aktif {removed_count} hatırlatıcı tamamen silindi.")
    else: await update.message.reply_text("İşlem iptal edildi. (Zaten aktif bir hatırlatıcın bulunmuyordu.)")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Hatırlatıcı conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("hatirlat", hatirlat_start)],
        states={
            WAITING_FOR_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
            WAITING_FOR_IMPORTANCE: [CallbackQueryHandler(receive_importance, pattern="^imp_")],
        },
        fallbacks=[CommandHandler("iptal", cancel_all)],
        allow_reentry=True
    )

    # Duyuru conversation handler
    duyuru_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("duyuru", duyuru_start)],
        states={
            WAITING_FOR_DUYURU_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, duyuru_save_to_bot_data)],
        },
        fallbacks=[CommandHandler("iptal", cancel_all)],
        allow_reentry=True
    )
    
    app.add_handler(CommandHandler("start", send_guide))
    app.add_handler(CommandHandler("yardim", send_guide))
    app.add_handler(CommandHandler("iptal", cancel_all))
    app.add_handler(CommandHandler("soru", soru))

    # Görselli /soru mesajları için: caption'da /soru geçen fotoğraf mesajları
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r'^/soru') & filters.Chat(chat_id=int(ALLOWED_GROUP_ID)),
        soru
    ))
    
    # Kanal dinleyicisi (Otomatik mesaj kopyalama)
    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003613910089) & filters.UpdateType.CHANNEL_POST, copy_channel_post))
    
    # Message Score Bot Dinleyicisi
    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003297262036) & filters.User(user_id=5933486341), score_bot_listener))

    # Mesaj silme dinleyicisi: -5199865415 grubunda 5933486341 ID'li kullanıcının mesajları
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=int(SILINECEK_GRUP_ID)) & filters.User(user_id=SILINECEK_BOT_USER_ID),
        auto_delete_listener
    ))

    app.add_handler(conv_handler)
    app.add_handler(duyuru_conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))

    # Duyuru anket yanıt handler'ı
    app.add_handler(PollAnswerHandler(duyuru_poll_answer))
    
    print("Bot başlatılıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
