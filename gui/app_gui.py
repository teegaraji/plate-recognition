import json
import os
import sys
import threading

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from plate_detector import PlateDetector

USERS_PATH = "./db_json/users.json"
IZIN_PATH = "./db_json/izin.json"


class PlateGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plate Recognition GUI")
        bg_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../static/bg_lite.png")
        )
        self.bg = QPixmap(bg_path)
        if self.bg.isNull():
            print("Gagal load background! Path:", bg_path)
        self.webcam_label = QLabel(self)

        # Kotak plat nomor
        self.plate_label = QLabel(self)
        self.plate_label.setStyleSheet(
            "background-color: white; font-size: 24px; border-radius: 10px;"
        )
        self.plate_label.setAlignment(Qt.AlignCenter)
        self.plate_label.setText("")

        self.feedback_timer = QTimer()
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.clear_plate_box)

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.feedback_timeout)

        # Circle status
        self.circle_left = QLabel(self)
        self.circle_right = QLabel(self)
        self.circle_left.setAutoFillBackground(True)
        self.circle_right.setAutoFillBackground(True)
        self.update_circles(None)

        self.waiting_plate = None  # Tambahkan ini
        self.feedback_waiting = False

        # Thread deteksi plat
        self.detected_plate = None
        self.plate_status = None
        self.detect_thread = threading.Thread(
            target=self.detect_plate_loop, daemon=True
        )
        self.detect_thread.start()

        self.detector = PlateDetector(camera_index=0)
        self.detected_plate = None
        self.plate_status = None
        self.frame = None

        # Timer untuk update webcam
        self.cap = cv2.VideoCapture(0)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    def resizeEvent(self, event):
        win_w = self.width()
        win_h = self.height()

        # Rasio terhadap background asli (7680x4320)
        webcam_x = int(1400 / 7680 * win_w)
        webcam_y = int(560 / 4320 * win_h)
        webcam_w = int(4880 / 7680 * win_w)
        webcam_h = int(2750 / 4320 * win_h)
        self.webcam_label.setGeometry(webcam_x, webcam_y, webcam_w, webcam_h)

        plate_x = int(1200 / 7680 * win_w)
        plate_y = int(3740 / 4320 * win_h)
        plate_w = int(1500 / 7680 * win_w)
        plate_h = int(260 / 4320 * win_h)
        self.plate_label.setGeometry(plate_x, plate_y, plate_w, plate_h)

        circle_left_x = int(5860 / 7680 * win_w)
        circle_left_y = int(3720 / 4320 * win_h)
        circle_right_x = int(6255 / 7680 * win_w)
        circle_right_y = int(3720 / 4320 * win_h)
        circle_size = min(int(300 / 7680 * win_w), int(300 / 4320 * win_h))
        self.circle_left.setGeometry(
            circle_left_x, circle_left_y, circle_size, circle_size
        )
        self.circle_right.setGeometry(
            circle_right_x, circle_right_y, circle_size, circle_size
        )

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        scaled_bg = self.bg.scaled(
            self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        painter.drawPixmap(0, 0, scaled_bg)

    def clear_plate_box(self):
        self.plate_label.setText("")
        self.update_circles(None)
        self.waiting_plate = None
        self.feedback_waiting = False
        self.timeout_timer.stop()

    def update_frame(self):
        frame, plate, status = self.detector.get_frame_and_plate()
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qt_img).scaled(
                self.webcam_label.width(),
                self.webcam_label.height(),
                Qt.IgnoreAspectRatio,
            )
            self.webcam_label.setPixmap(pix)

        # Cek izin.json untuk feedback user
        try:
            with open(IZIN_PATH) as f:
                izin = json.load(f)
        except Exception:
            izin = {}

        # --- LOGIKA BARU ---
        plate_to_show = ""
        circle_status = None

        # Jika ada plat yang sedang menunggu feedback
        if self.waiting_plate:
            feedback = izin.get(self.waiting_plate)
            if feedback in ["allowed", "denied"]:
                plate_to_show = self.waiting_plate
                self.timeout_timer.stop()
                circle_status = feedback

                # Hapus feedback dari izin.json agar tidak langsung allowed/denied pada deteksi berikutnya
                izin.pop(self.waiting_plate, None)
                with open(IZIN_PATH, "w") as f:
                    json.dump(izin, f)

                self.detector.reset_notified_plate(self.waiting_plate)

                # Mulai timer hanya jika belum berjalan
                if not self.feedback_timer.isActive():
                    self.update_circles(circle_status)
                    self.feedback_waiting = True
                    self.feedback_timer.start(3000)  # 3 detik

                # JANGAN set self.waiting_plate = None di sini!
            else:
                plate_to_show = self.waiting_plate
                circle_status = feedback
        elif plate:
            # Plat baru terdeteksi dan terdaftar, tampilkan dan tunggu feedback
            self.waiting_plate = plate
            plate_to_show = plate
            circle_status = izin.get(plate)
            self.timeout_timer.start(60000)
        else:
            # Tidak ada plat yang sedang menunggu dan tidak ada plat baru
            plate_to_show = ""
            circle_status = None

        self.plate_label.setText(plate_to_show)
        if not self.feedback_waiting:
            self.update_circles(circle_status)

    def update_circles(self, status):
        # status: None, "allowed", "denied"
        left_color = "#FBD43A"
        right_color = "#FBD43A"
        if status == "allowed":
            right_color = "#00BEC1"
        elif status == "denied":
            left_color = "#FF2171"
        radius = self.circle_left.width() // 2
        border = "2px solid black"
        self.circle_left.setStyleSheet(
            f"background-color: {left_color}; border-radius: {radius}px; border: {border};"
        )
        self.circle_right.setStyleSheet(
            f"background-color: {right_color}; border-radius: {radius}px; border: {border};"
        )

    def detect_plate_loop(self):
        # Sederhana: polling izin.json dan users.json
        last_plate = ""
        while True:
            try:
                with open(USERS_PATH) as f:
                    users = json.load(f)
                with open(IZIN_PATH) as f:
                    izin = json.load(f)
            except Exception:
                continue

            # Simulasi: ambil plat terakhir yang diizinkan/ditolak
            for plate, status in izin.items():
                user = next(
                    (
                        u
                        for u in users
                        if u["plate"].replace(" ", "").upper()
                        == plate.replace(" ", "").upper()
                    ),
                    None,
                )
                if user:
                    self.detected_plate = plate
                    self.plate_status = status
            # Reset jika tidak ada
            if not izin:
                self.detected_plate = None
                self.plate_status = None

            import time

            time.sleep(1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Q:
            self.close()

    def feedback_timeout(self):
        plate = self.waiting_plate
        self.clear_plate_box()
        # Blacklist plat di detector agar tidak dideteksi ulang selama 1 menit
        if plate:
            self.detector.add_timeout_blacklist(plate, duration=30)
            self.detector.reset_notified_plate(plate)
            import requests

            try:
                requests.post("http://localhost:5000/timeout", json={"plate": plate})
            except Exception as e:
                print("Gagal mengirim notifikasi timeout:", e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = PlateGUI()
    gui.show()
    gui.showFullScreen()
    sys.exit(app.exec_())
