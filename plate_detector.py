import time

import cv2
import easyocr
import numpy as np
import requests
import torch
from deep_sort_realtime.deepsort_tracker import DeepSort
from ultralytics import YOLO

from utils.utils import is_plate_registered


def iou(boxA, boxB):
    # box: [x1, y1, x2, y2]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou


class PlateDetector:
    def __init__(self, camera_index=0):
        self.reader = easyocr.Reader(["id"], gpu=True)
        self.model = YOLO("./models/PlateDetection.pt")
        self.tracker = DeepSort(max_age=30)
        self.cap = cv2.VideoCapture(camera_index)
        self.ocr_results = {}
        self.notified_plates = set()
        self.timeout_blacklist = {}  # Untuk menyimpan plat yang timeout

    def notify_plate(self, plate, image_url=None):
        payload = {"plate": plate}
        if image_url:
            payload["image_url"] = image_url
        try:
            requests.post("http://localhost:5000/notify", json=payload)
        except Exception as e:
            print("Gagal mengirim notifikasi:", e)

    def reset_notified_plate(self, plate):
        self.notified_plates.discard(plate)

    def add_timeout_blacklist(self, plate, duration=30):
        # Tambahkan plat ke blacklist selama 'duration' detik
        self.timeout_blacklist[plate] = time.time() + duration

    def is_blacklisted(self, plate):
        # Cek apakah plat masih dalam masa blacklist
        expire = self.timeout_blacklist.get(plate)
        if expire is None:
            return False
        if time.time() > expire:
            del self.timeout_blacklist[plate]
            return False
        return True

    def get_frame_and_plate(self):
        ret, frame = self.cap.read()
        if not ret:
            return None, None, None
        results = self.model(frame)[0]
        detections = []
        h, w, _ = frame.shape
        score_threshold = 0.7
        boxes = []
        for box in results.boxes.data.tolist():
            x1, y1, x2, y2, score, class_id = box
            if score < score_threshold:
                continue
            boxes.append([x1, y1, x2, y2, score])
            detections.append(([x1, y1, x2 - x1, y2 - y1], score, "plate"))

        # Manual NMS
        keep = []
        used = [False] * len(boxes)
        iou_threshold = 0.3
        for i in range(len(boxes)):
            if used[i]:
                continue
            keep.append(i)
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                if iou(boxes[i][:4], boxes[j][:4]) > iou_threshold:
                    used[j] = True
        detections = [detections[i] for i in keep]

        tracks = self.tracker.update_tracks(detections, frame=frame)
        detected_plate = None
        registered = False
        for track in tracks:
            if not track.is_confirmed():
                continue
            track_id = track.track_id
            ltrb = track.to_ltrb()
            x1, y1, x2, y2 = map(int, ltrb)
            if track_id not in self.ocr_results:
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                crop = cv2.resize(
                    crop,
                    (min(crop.shape[1] * 2, 500), min(crop.shape[0] * 2, 500)),
                )
                ocr_dets = self.reader.readtext(crop)
                plate_text = ""
                if ocr_dets:
                    plate_text = ocr_dets[0][1].upper().replace(" ", "")
                if plate_text:
                    self.ocr_results[track_id] = plate_text
                    detected_plate = plate_text
            if track_id in self.ocr_results:
                detected_plate = self.ocr_results[track_id]
                if self.is_blacklisted(detected_plate):
                    continue  # Skip plat yang sedang di-blacklist
                # Cek apakah terdaftar
                if is_plate_registered(detected_plate):
                    registered = True
                    if detected_plate not in self.notified_plates:
                        self.notify_plate(detected_plate)
                        self.notified_plates.add(detected_plate)
                else:
                    registered = False
            # Draw bounding box and label
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"ID {track_id}"
            if track_id in self.ocr_results:
                label += f": {self.ocr_results[track_id]}"
            cv2.putText(
                frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 0),
                2,
            )
        return frame, detected_plate if registered else None, None
