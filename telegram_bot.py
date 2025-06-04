import os
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import CommandHandler, ApplicationBuilder, ContextTypes
from db_json import database

# Load .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


# Fungsi /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = "Halo! Saya adalah bot untuk mendeteksi kendaraan. Silakan kirimkan nomor plat kendaraan yang ingin didaftarkan."
    await context.bot.send_message(chat_id=chat_id, text=text)


async def daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await context.bot.send_message(chat_id=chat_id, text="Format: /daftar B1234ABC")
        return
    plate = args[0]
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


# Inisialisasi dan jalankan bot
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        CommandHandler("daftar", daftar)
    )  # Tambahkan handler daftar
    print("Bot sedang berjalan...")
    application.run_polling()


if __name__ == "__main__":
    main()
