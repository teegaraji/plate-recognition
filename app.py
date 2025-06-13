from flask import Flask, jsonify, request

from telegram_bot import send_telegram_alert
from utils.utils import is_plate_registered

app = Flask(__name__)


@app.route("/notify", methods=["POST"])
def notify_user():
    data = request.json
    plate_number = data.get("plate")
    snapshot_url = data.get("image_url")

    if not plate_number:
        return jsonify({"status": "error", "message": "No plate number provided"}), 400

    # Cek apakah plat terdaftar
    user = is_plate_registered(plate_number)
    if user:
        send_telegram_alert(user["chat_id"], plate_number, snapshot_url)
        return jsonify({"status": "ok", "message": "Notification sent"})
    else:
        return jsonify({"status": "unknown_plate", "message": "Plate not registered"})


@app.route("/timeout", methods=["POST"])
def timeout_feedback():
    data = request.json
    plate_number = data.get("plate")
    if not plate_number:
        return jsonify({"status": "error", "message": "No plate number provided"}), 400

    user = is_plate_registered(plate_number)
    if user:
        from telegram_bot import send_timeout_alert

        send_timeout_alert(user["chat_id"], plate_number)
        return jsonify({"status": "ok", "message": "Timeout notification sent"})
    else:
        return jsonify({"status": "unknown_plate", "message": "Plate not registered"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
