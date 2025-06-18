import time
import cv2
import easyocr
import numpy as np
import requests
import torch
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort

from utils.utils import is_plate_registered

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return interArea / float(boxAArea + boxBArea - interArea + 1e-6)

def preprocess_crop(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    sharpen_kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
    sharpened = cv2.filter2D(gray, -1, sharpen_kernel)
    _, thresh = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

class PlateDetector:
    def __init__(self, camera_index=0):
        self.reader = easyocr.Reader(['id'], gpu=True)
        self.model = YOLO('./models/PlateDetection.pt')
        self.tracker = DeepSort(max_age=30)
        self.cap = cv2.VideoCapture(camera_index)
        self.ocr_results = {}
        self.ocr_votes = {}
        self.notified_plates = set()
        self.timeout_blacklist = {}

    def notify_plate(self, plate):
        try:
            requests.post("http://localhost:5000/notify", json={"plate": plate})
        except Exception as e:
            print("Notification failed:", e)

    def reset_notified_plate(self, plate):
        self.notified_plates.discard(plate)

    def add_timeout_blacklist(self, plate, duration=30):
        self.timeout_blacklist[plate] = time.time() + duration

    def is_blacklisted(self, plate):
        expire = self.timeout_blacklist.get(plate)
        if expire is None:
            return False
        if time.time() > expire:
            del self.timeout_blacklist[plate]
            return False
        return True

    def vote_ocr_result(self, track_id, plate_text):
        votes = self.ocr_votes.setdefault(track_id, {})
        votes[plate_text] = votes.get(plate_text, 0) + 1
        return max(votes.items(), key=lambda x: x[1])[0]  # return most voted

    def get_frame_and_plate(self):
        ret, frame = self.cap.read()
        if not ret:
            return None, None, None

        results = self.model(frame)[0]
        h, w, _ = frame.shape
        detections, boxes = [], []

        for box in results.boxes.data.tolist():
            x1, y1, x2, y2, score, class_id = box
            if score < 0.7:
                continue
            boxes.append([x1, y1, x2, y2, score])
            detections.append(([x1, y1, x2 - x1, y2 - y1], score, "plate"))

        keep, used = [], [False] * len(boxes)
        for i in range(len(boxes)):
            if used[i]: continue
            keep.append(i)
            for j in range(i + 1, len(boxes)):
                if used[j]: continue
                if iou(boxes[i][:4], boxes[j][:4]) > 0.3:
                    used[j] = True
        detections = [detections[i] for i in keep]

        tracks = self.tracker.update_tracks(detections, frame=frame)
        detected_plate, registered = None, False

        for track in tracks:
            if not track.is_confirmed(): continue
            track_id = track.track_id
            x1, y1, x2, y2 = map(int, track.to_ltrb())

            if track_id not in self.ocr_results:
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0: continue
                crop = cv2.resize(crop, (min(crop.shape[1]*2, 500), min(crop.shape[0]*2, 500)))
                crop = preprocess_crop(crop)
                ocr_dets = self.reader.readtext(crop)
                plate_text = ocr_dets[0][1].upper().replace(" ", "") if ocr_dets else ""
                if plate_text:
                    voted_plate = self.vote_ocr_result(track_id, plate_text)
                    self.ocr_results[track_id] = voted_plate
                    detected_plate = voted_plate

            if track_id in self.ocr_results:
                detected_plate = self.ocr_results[track_id]
                if self.is_blacklisted(detected_plate): continue
                if is_plate_registered(detected_plate):
                    registered = True
                    if detected_plate not in self.notified_plates:
                        self.notify_plate(detected_plate)
                        self.notified_plates.add(detected_plate)
                        self.add_timeout_blacklist(detected_plate)
                else:
                    registered = False

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"ID {track_id}"
            if track_id in self.ocr_results:
                label += f": {self.ocr_results[track_id]}"
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        return frame, detected_plate if registered else None, None
