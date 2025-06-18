import json
import os

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from db_json import database

# Load .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

IZIN_PATH = "./db_json/izin.json"


# Fungsi /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (
        "Halo! Saya adalah bot untuk mendeteksi kendaraan. Silakan kirimkan nomor plat kendaraan yang ingin didaftarkan. \n"
        "Gunakan perintah /daftar untuk mendaftarkan plat kendaraan Anda.\n\n"
        "Contoh: /daftar B1234ABC\n\n"
        "Setelah mendaftar, Anda akan menerima notifikasi ketika kendaraan Anda ketika terdeteksi oleh camera.\n\n"
        "Gunakan perintah /izinkan untuk mengizinkan kendaraan masuk.\n"
        "Contoh: /izinkan B1234ABC\n\n"
        "Gunakan perintah /tolak untuk menolak kendaraan masuk.\n"
        "Contoh: /tolak B1234ABC"
    )
    await context.bot.send_message(chat_id=chat_id, text=text)


async def daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await context.bot.send_message(chat_id=chat_id, text="Format: /daftar B1234ABC")
        return
    plate = args[0].replace(" ", "").upper()
    name = update.effective_user.full_name
    username = update.effective_user.username  # ambil username telegram
    user = {"name": name, "username": username, "plate": plate, "chat_id": chat_id}
    database.save_user(user)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Plat {plate} berhasil didaftarkan atas nama {name} (@{username}).",
    )


# Fungsi alert kendaraan
def send_telegram_alert(chat_id, plate_number, image_url=None):
    text = f"🚘 Kendaraan dengan plat: *{plate_number}* terdeteksi.\nIzinkan masuk?"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(f"{BOT_URL}/sendMessage", data=payload)

    if image_url:
        img_payload = {"chat_id": chat_id, "photo": image_url}
        requests.post(f"{BOT_URL}/sendPhoto", data=img_payload)


def send_timeout_alert(chat_id, plate_number):
    text = (
        f"⏰ Deteksi plat *{plate_number}* sudah hangus karena tidak ada respon selama 1 menit.\n"
        "Silakan tunggu deteksi berikutnya untuk mengirim feedback."
    )
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(f"{BOT_URL}/sendMessage", data=payload)


async def izinkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Format: /izinkan B1234ABC"
        )
        return
    plate = args[0].replace(" ", "").upper()  # Normalisasi input user

    # Baca izin.json
    if os.path.exists(IZIN_PATH):
        with open(IZIN_PATH, "r") as f:
            izin_data = json.load(f)
    else:
        izin_data = {}

    # Normalisasi semua key di izin_data
    izin_data_normalized = {k.replace(" ", "").upper(): k for k in izin_data.keys()}

    if plate not in izin_data_normalized:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Plat {plate} sudah hangus atau belum terdeteksi. Silakan tunggu deteksi berikutnya.",
        )
        return

    # Update izin_data dengan status baru
    original_key = izin_data_normalized[plate]
    izin_data[original_key] = "allowed"

    with open(IZIN_PATH, "w") as f:
        json.dump(izin_data, f)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Plat {plate} sudah diizinkan masuk.",
    )


async def tolak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Format: /tolak B1234ABC"
        )
        return
    plate = args[0].replace(" ", "").upper()  # Normalisasi input user

    if os.path.exists(IZIN_PATH):
        with open(IZIN_PATH, "r") as f:
            izin_data = json.load(f)
    else:
        izin_data = {}

    izin_data_normalized = {k.replace(" ", "").upper(): k for k in izin_data.keys()}

    if plate not in izin_data_normalized:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Plat {plate} sudah hangus atau belum terdeteksi. Silakan tunggu deteksi berikutnya.",
        )
        return

    original_key = izin_data_normalized[plate]
    izin_data[original_key] = "denied"

    with open(IZIN_PATH, "w") as f:
        json.dump(izin_data, f)
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=f"Plat {plate} ditolak masuk."
    )


# Inisialisasi dan jalankan bot
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        CommandHandler("daftar", daftar)
    )  # Tambahkan handler daftar
    application.add_handler(CommandHandler("izinkan", izinkan))
    application.add_handler(CommandHandler("tolak", tolak))
    print("Bot sedang berjalan...")
    application.run_polling()


if __name__ == "__main__":
    main()
