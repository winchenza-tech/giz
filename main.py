import os
import re
import datetime
import pytz
import asyncio
import json
import io
import matplotlib
matplotlib.use('Agg')  # Sunucuda hata vermeden arka planda grafik çizmek için
import matplotlib.pyplot as plt

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters,
    PollAnswerHandler
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

# Duyuru yapabilecek kullanıcı ID'leri
ALLOWED_DUYURU_USERS = ["6781642262", "8639720888", "7094870780","8150494686","8242824985"]

# Duyuru hedef grup ID'si
DUYURU_GROUP_ID = "-1003297262036"


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
    """Belirli kanaldan gelen mesajları diğer gruba kopyalar."""
    try:
        await context.bot.copy_message(
            chat_id="-5199865415",
            from_chat_id=update.channel_post.chat_id,
            message_id=update.channel_post.message_id
        )
    except Exception as e:
        print(f"Kanal mesajı kopyalama hatası: {e}")


async def score_bot_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message Score Bot'un mesajını okuyup grafikli profesyonel rapor gönderir ve mesajını siler."""
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)

    # 00:00 ile 00:30 arasında çalışsın
    if not (now.hour == 0 and 0 <= now.minute <= 30):
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
    
    # Kişi başı ortalama mesajları hesapla
    avg_counts = [round(m / u) if u > 0 else 0 for m, u in zip(m_counts, u_counts)]

    # Grafiği Çiziyoruz
    fig, ax1 = plt.subplots(figsize=(9, 6))
    x = range(len(labels))
    width = 0.25  # 3 sütun olacağı için genişliği biraz daha daralttık

    # İkinci Y eksenini oluşturuyoruz (TwinX)
    ax2 = ax1.twinx()

    # Çubukları oluşturuyoruz
    bars1 = ax1.bar([i - width for i in x], m_counts, width, label='Toplam Mesaj', color='#2C3E50')
    bars2 = ax2.bar([i for i in x], u_counts, width, label='Katılımcı Sayısı', color='#3498DB')
    bars3 = ax2.bar([i + width for i in x], avg_counts, width, label='Ortalama (Kişi Başı)', color='#F1C40F') # Sarı Renk

    # Eksen İsimlendirmeleri
    ax1.set_ylabel('Toplam Mesaj Sayısı (Sol Eksen)', fontsize=11, fontweight='bold', color='#2C3E50')
    ax2.set_ylabel('Katılımcı & Ortalama (Sağ Eksen)', fontsize=11, fontweight='bold')
    ax1.set_title('Grup Günlük Etkileşim Raporu', fontsize=14, fontweight='bold')
    
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=11)
    
    # DİNAMİK Y EKSENLERİ (TwinX ile Ayrıştırılmış)
    max_m = max(m_counts) if m_counts else 10
    ax1.set_ylim(0, max_m + (max_m * 0.15)) # Sol taraf sadece mesajlara odaklı
    
    max_u_avg = max(max(u_counts), max(avg_counts)) if (u_counts or avg_counts) else 10
    ax2.set_ylim(0, max(75, max_u_avg) + 10) # Sağ taraf katılımcı ve ortalamaya odaklı (Max 70 standardına uygun)

    ax1.grid(axis='y', alpha=0.2, linestyle='--')

    # Değerleri sütunların üzerine yazma
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + (max_m * 0.02), str(int(height)), ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 1, str(int(height)), ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars3:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 1, str(int(height)), ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Efsanevi tabloyu (Legend) birleştirme
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=10)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120)
    buf.seek(0)
    plt.close(fig)

    # Profesyonel raporlama promptu — espri veya ucuz motivasyon yok
    report_prompt = (
        f"Bugün grupta {msg_count} mesaj gönderildi ve {user_count} kişi katılım sağladı. Kişi başı ortalama {avg_counts[2]} mesaj düştü. "
        f"Dün {m_counts[1]} mesaj, {u_counts[1]} kişi; geçen hafta aynı gün {m_counts[0]} mesaj, {u_counts[0]} kişi vardı. "
        f"Bu verileri değerlendirerek gruba özel, profesyonel, analitik ve ciddi bir üslupla en fazla 100 kelimelik "
        f"bir günlük değerlendirme raporu yaz. Espri, argo, samimi ifadeler, emoji veya ucuz motivasyon cümleleri kullanma. "
        f"Bir iş ortamına uygun, nesnel ve yapıcı bir dil kullan."
    )
    try:
        report_response = await gemini_client.aio.models.generate_content(model=GEMINI_MODEL, contents=report_prompt)
        report_text = report_response.text
    except:
        report_text = "Günlük grup etkileşim raporu ektedir."

    # Raporu diğer gruba gönder
    try:
        await context.bot.send_photo(
            chat_id="-5199865415",
            photo=buf.getvalue(), 
            caption=report_text
        )
    except Exception as e:
        print(f"Rapor gönderilirken hata oluştu: {e}")

    # İşlem tamamlandığında asıl rapor mesajını sil
    try:
        await update.message.delete()
        print("Rapor başarıyla gönderildi ve 5933486341 ID'li orijinal mesaj silindi.")
    except Exception as e:
        print(f"Orijinal mesaj silinemedi: {e}")


async def test_rapor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dene komutu ile botun özel mesajından istatistikleri test etmek için."""
    if update.message.chat.type != "private":
        return

    text = update.message.text or update.message.caption or ""
    test_text = re.sub(r'^/dene\s*', '', text, flags=re.IGNORECASE).strip()

    if not test_text:
        await update.message.reply_text("Test edilecek metni eksik girdin. Örnek: /dene Toplam mesaj: 2308 Toplam aktif kullanıcı: 43")
        return

    msg = await update.message.reply_text("Test verisi işleniyor, lütfen bekleyin...")

    extract_prompt = f"Aşağıdaki mesaj istatistiği metninden 'toplam mesaj sayısını' ve 'kullanıcı (çeşitliliği) sayısını' bul. Sadece şu formatta geçerli bir JSON döndür: {{\"msg_count\": 100, \"user_count\": 10}}. Metin: {test_text}"

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
        await msg.edit_text(f"Veri çıkarılırken hata oluştu: {e}")
        return

    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.datetime.now(tz)
    yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    last_week_str = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    # Geçmiş veriler için load yap, test olduğu için kaydetme
    stats = load_stats()
    
    labels = ['Geçen Hafta', 'Dün', 'Bugün (TEST)']
    m_counts = [stats.get(last_week_str, {}).get("msg_count", 0), stats.get(yesterday_str, {}).get("msg_count", 0), msg_count]
    u_counts = [stats.get(last_week_str, {}).get("user_count", 0), stats.get(yesterday_str, {}).get("user_count", 0), user_count]
    
    # Ortalama hesaplama
    avg_counts = [round(m / u) if u > 0 else 0 for m, u in zip(m_counts, u_counts)]

    fig, ax1 = plt.subplots(figsize=(9, 6))
    x = range(len(labels))
    width = 0.25

    ax2 = ax1.twinx()

    bars1 = ax1.bar([i - width for i in x], m_counts, width, label='Toplam Mesaj', color='#2C3E50')
    bars2 = ax2.bar([i for i in x], u_counts, width, label='Katılımcı Sayısı', color='#3498DB')
    bars3 = ax2.bar([i + width for i in x], avg_counts, width, label='Ortalama (Kişi Başı)', color='#F1C40F')

    ax1.set_ylabel('Toplam Mesaj Sayısı (Sol Eksen)', fontsize=11, fontweight='bold', color='#2C3E50')
    ax2.set_ylabel('Katılımcı & Ortalama (Sağ Eksen)', fontsize=11, fontweight='bold')
    ax1.set_title('Grup Günlük Etkileşim Raporu (TEST)', fontsize=14, fontweight='bold')
    
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=11)

    max_m = max(m_counts) if m_counts else 10
    ax1.set_ylim(0, max_m + (max_m * 0.15))
    
    max_u_avg = max(max(u_counts), max(avg_counts)) if (u_counts or avg_counts) else 10
    ax2.set_ylim(0, max(75, max_u_avg) + 10)

    ax1.grid(axis='y', alpha=0.2, linestyle='--')

    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + (max_m * 0.02), str(int(height)), ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 1, str(int(height)), ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars3:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 1, str(int(height)), ha='center', va='bottom', fontsize=9, fontweight='bold')

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=10)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120)
    buf.seek(0)
    plt.close(fig)

    report_prompt = (
        f"Bugün grupta {msg_count} mesaj gönderildi ve {user_count} kişi katılım sağladı. Kişi başı ortalama {avg_counts[2]} mesaj düştü. "
        f"Dün {m_counts[1]} mesaj, {u_counts[1]} kişi; geçen hafta aynı gün {m_counts[0]} mesaj, {u_counts[0]} kişi vardı. "
        f"Bu verileri değerlendirerek gruba özel, profesyonel, analitik ve ciddi bir üslupla en fazla 100 kelimelik "
        f"bir günlük değerlendirme raporu yaz. Espri, argo, samimi ifadeler, emoji veya ucuz motivasyon cümleleri kullanma. "
        f"Bir iş ortamına uygun, nesnel ve yapıcı bir dil kullan.kalın yazmaya çalışma tüm metinler aynı fontta olsun"
    )
    
    try:
        report_response = await gemini_client.aio.models.generate_content(model=GEMINI_MODEL, contents=report_prompt)
        report_text = report_response.text
    except:
        report_text = "Günlük grup etkileşim raporu ektedir."

    try:
        await msg.delete()
        await context.bot.send_photo(
            chat_id=update.message.chat_id,
            photo=buf.getvalue(), 
            caption=f"🧪 **TEST RAPORU:**\n\n{report_text}"
        )
    except Exception as e:
        await context.bot.send_message(chat_id=update.message.chat_id, text=f"Test sırasında hata oluştu: {e}")


async def soru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        return

    if str(update.message.chat.id) != ALLOWED_GROUP_ID:
        return

    # Soru metni belirleme (Doğrudan mesaj veya caption)
    text = update.message.text or update.message.caption or ""
    question_text = re.sub(r'(?i)^/soru\s*', '', text).strip()

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
        await update.message.reply_text("Cevap üretilirken bir hata olutu.")


# ──────────────────────────────── Duyuru Sistemi ────────────────────────────────

async def duyuru_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Özel mesajda /duyuru komutunu işler. Yetkili kullanıcılara anket gönderir."""
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

    # Duyuru metnini sakla
    context.user_data["duyuru_text"] = duyuru_text

    # Anket gönder
    message = await update.message.reply_poll(
        question="Duyuru nasıl paylaşılsın?",
        options=["📢 Bildirimli Sabitle", "📌 Bildirimsiz Sabitle"],
        is_anonymous=False,
    )

    # Anket bilgilerini bot_data'ya kaydet (PollAnswerHandler'dan erişmek için)
    context.bot_data[f"duyuru_poll_{message.poll.id}"] = {
        "chat_id": update.message.chat_id,
        "user_id": user_id,
        "duyuru_text": duyuru_text,
    }


async def duyuru_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anket cevabını işler ve duyuruyu gruba gönderir."""
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id

    poll_data = context.bot_data.get(f"duyuru_poll_{poll_id}")
    if not poll_data:
        return

    option_ids = poll_answer.option_ids
    if not option_ids:
        return

    selected = option_ids[0]  # 0 = Bildirimli, 1 = Bildirimsiz
    duyuru_text = poll_data["duyuru_text"]

    try:
        if selected == 0:
            # Bildirimli
            msg = await context.bot.send_message(
                chat_id=DUYURU_GROUP_ID,
                text=f"📢{duyuru_text}",
                disable_notification=False,
            )
        else:
            # Bildirimsiz
            msg = await context.bot.send_message(
                chat_id=DUYURU_GROUP_ID,
                text=f"📢 {duyuru_text}",
                disable_notification=True,
            )

        # Mesajı sabitle
        await msg.pin(disable_notification=True)

        # Yetkiliye bilgi ver
        await context.bot.send_message(
            chat_id=poll_data["chat_id"],
            text="✅ Duyuru gruba gönderildi. Aferin"
        )
    except Exception as e:
        print(f"Duyuru gönderme hatası: {e}")
        await context.bot.send_message(
            chat_id=poll_data["chat_id"],
            text="❌ Duyuru gönderilirken bir hata olutu. ."
        )

    # Temizlik
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


# ──────────────────────────────── Anti Spam (OctopusGame_Bot) ────────────────────────────────

async def anti_spam_octopus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Octopusgame_bot'un reklam ve davet linklerini doğrudan engeller."""
    if not update.message:
        return
        
    user = update.message.from_user
    if not user or not user.username:
        return
        
    if user.username.lower() == "octopusgame_bot":
        text = update.message.text or update.message.caption or ""
        # Türkçe karakter uyumlu (ı/i), boşlukları tolere eden sağlam bir regex
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

    # SPAM KONTROLÜ (En yüksek öncelik ile bağımsız çalışması için group=-1 veriyoruz)
    app.add_handler(MessageHandler(filters.ALL, anti_spam_octopus), group=-1)

    app.add_handler(CommandHandler("start", send_guide))
    app.add_handler(CommandHandler("yardim", send_guide))
    app.add_handler(CommandHandler("iptal", cancel_all))
    
    # Soru Komutu: Artık CommandHandler yerine Regex kullanarak hem salt metin hem de fotoğraflı açıklamaları yakalıyoruz
    app.add_handler(MessageHandler(filters.Regex(r'(?i)^/soru'), soru))
    
    # Test Komutu (Özel mesajda)
    app.add_handler(CommandHandler("dene", test_rapor_command))

    # Duyuru komutu (sadece özel mesajda)
    app.add_handler(CommandHandler("duyuru", duyuru_start))

    # Duyuru anket cevabı dinleyicisi
    app.add_handler(PollAnswerHandler(duyuru_poll_answer))

    # Kanal dinleyicisi (Otomatik mesaj kopyalama)
    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003613910089) & filters.UpdateType.CHANNEL_POST, copy_channel_post))

    # Message Score Bot Dinleyicisi — 00:00-00:30 arası rapor çıkarır ve mesajı siler
    app.add_handler(MessageHandler(filters.Chat(chat_id=-1003297262036) & filters.User(user_id=5933486341), score_bot_listener))

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^read_"))

    print("Bot başlatılıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()
