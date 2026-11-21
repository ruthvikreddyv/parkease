from pathlib import Path
from parking_lot_status import parking_lot_status


def parking_availability():
    available, occupied = [], []
    lines = Path("parking_area_coordinates.txt").read_text().splitlines()
    for index, line in enumerate(lines):
        box = list(map(int, line.split()))
        state = parking_lot_status(f"parking_lots/{index}.png")
        (available if state == "available" else occupied).append(box)
    return available, occupied
