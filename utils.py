import json


def is_plate_registered(plate_number):
    with open("db_json") as f:
        data = json.load(f)
    for user in data["users"]:
        if user["plate"].lower() == plate_number.lower():
            return user
    return None
