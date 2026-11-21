"""Run from vision/ to export the detector output for the web demo."""
import json
from pathlib import Path
from parking_availability import parking_availability

available, occupied = parking_availability()
labels = Path("parking_labels.txt").read_text().splitlines()
boxes = [list(map(int, line.split())) for line in Path("parking_area_coordinates.txt").read_text().splitlines()]
entrance = list(map(int, Path("parking_entrance_coordinates.txt").read_text().split()))
def center(box):
    x, y, right, bottom = box
    return [x + round((right - x) / 2), y + round((bottom - y) / 2)]

snapshot = {"entrance": center(entrance), "bays": [
    {"label": label, "center": center(box), "occupied": box in occupied}
    for label, box in zip(labels, boxes, strict=True)
]}
Path("../public/snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
