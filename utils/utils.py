import json


def is_plate_registered(plate_number):
    plate_number = plate_number.replace(" ", "").upper()
    with open("./db_json/users.json") as f:
        data = json.load(f)
    for user in data:
        if user["plate"].replace(" ", "").lower() == plate_number.lower():
            return user
    return None
