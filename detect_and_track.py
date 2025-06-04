import cv2
import torch
from ultralytics import YOLO
import easyocr
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

# ========== Inisialisasi Model ========== #
reader = easyocr.Reader(["id"], gpu=True)
model = YOLO("./models/PlateDetection.pt")  # Path ke model YOLO kamu
tracker = DeepSort(max_age=30)

# Untuk simpan hasil OCR yang sudah pernah dibaca
ocr_results = {}


# Fungsi normalisasi teks OCR
def fix_plate_smart(plate):
    replacements = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
    fixed = ""
    for char in plate:
        if char.isalpha():
            fixed += char.upper()
        elif char.isdigit():
            fixed += char
        else:
            fixed += replacements.get(char, char)
    return fixed


# Ambil teks utama dari hasil OCR
def extract_main_line_text(detections):
    if not detections:
        return "", 0.0
    y_positions = [bbox[0][1] for bbox, _, _ in detections]
    avg_y = np.mean(y_positions)
    main_line = [
        (bbox, text, score)
        for (bbox, text, score) in detections
        if bbox[0][1] < avg_y + 20
    ]
    main_line.sort(key=lambda item: item[0][0][0])

    combined_text = ""
    total_score = 0
    count = 0
    for _, text, score in main_line:
        if score > 0.3:
            cleaned = text.upper().replace(" ", "")
            cleaned = fix_plate_smart(cleaned)
            combined_text += cleaned + " "
            total_score += score
            count += 1
    avg_conf = total_score / count if count > 0 else 0
    return combined_text.strip(), round(avg_conf, 2)


# ========== Stream dari Webcam ========== #
cap = cv2.VideoCapture(0)  # 0 = default webcam

while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame)[0]
    detections = []

    h, w, _ = frame.shape
    for box in results.boxes.data.tolist():
        x1, y1, x2, y2, score, class_id = box
        detections.append(([x1, y1, x2 - x1, y2 - y1], score, "plate"))

    tracks = tracker.update_tracks(detections, frame=frame)

    for track in tracks:
        if not track.is_confirmed():
            continue
        track_id = track.track_id
        ltrb = track.to_ltrb()
        x1, y1, x2, y2 = map(int, ltrb)

        # Kalau ID belum pernah di-OCR
        if track_id not in ocr_results:
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crop = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2))

            ocr_dets = reader.readtext(crop)
            plate_text, avg_conf = extract_main_line_text(ocr_dets)

            if plate_text:
                ocr_results[track_id] = (plate_text, avg_conf)

        # Gambar bounding box dan text
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"ID {track_id}"
        if track_id in ocr_results:
            label += f": {ocr_results[track_id][0]}"
        cv2.putText(
            frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2
        )

    cv2.imshow("Webcam Plate Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
