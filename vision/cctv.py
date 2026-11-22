"""Calibrate and monitor a fixed CCTV camera on its own network."""
import argparse
import json
import math
import os
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent


def ordered(points):
    points = np.asarray(points, dtype=np.float32)
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    points = points[np.argsort(angles)]
    return np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)


def valid_quad(points):
    a = np.asarray(points, dtype=np.float32)
    return (a.shape == (4, 2) and np.isfinite(a).all() and (a >= 0).all()
            and (a <= 1).all() and cv2.isContourConvex(a)
            and cv2.contourArea(a) > .0003)


def suggest(frame):
    """Find closed, near-rectangular painted outlines for operator review."""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        polygon = cv2.approxPolyDP(contour, .025 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = ordered(polygon.reshape(4, 2))
        area = cv2.contourArea(points)
        _, sides, _ = cv2.minAreaRect(points)
        if not .002 < area/(w*h) < .13 or min(sides) < 8 or area / math.prod(sides) < .65:
            continue
        if any(cv2.intersectConvexConvex(points, other)[0] > .45 * min(area, cv2.contourArea(other)) for other in candidates):
            continue
        candidates.append(points)
        if len(candidates) >= 100:
            break
    return [(p / [w, h]).tolist() for p in sorted(candidates, key=lambda q: tuple(q.mean(axis=0)[::-1]))]


def open_camera(source):
    if source.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])
    else:
        cap = cv2.VideoCapture(int(source) if source.isdecimal() else source)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("Camera could not be opened. Check connectivity, credentials and codec.")
    return cap


def calibrate(frame, filename):
    h, w = frame.shape[:2]
    config = json.loads(filename.read_text()) if filename.exists() else {
        "entrance": [.5, .97], "bays": [], "revision": ""}
    bays = config["bays"]
    pending, drag = [], None
    entrance_mode = False
    selected = None
    message = "Click four corners per space. A suggests outlines. Save after review."
    def add(points):
        used = {b["id"] for b in bays}
        number = next(i for i in range(1, len(bays)+2) if f"P{i:02}" not in used)
        bays.append({"id": f"P{number:02}", "points": points})

    def mouse(event, x, y, flags, param):
        nonlocal drag, entrance_mode, selected, message
        point = [float(np.clip(x/w, 0, 1)), float(np.clip(y/h, 0, 1))]
        if event == cv2.EVENT_LBUTTONDOWN:
            if entrance_mode:
                config["entrance"] = point
                entrance_mode = False
                return
            for idx, bay in enumerate(bays):
                distances = np.linalg.norm((np.array(bay["points"])-point)*[w,h], axis=1)
                if distances.min() < 9:
                    selected, drag = idx, (idx, int(distances.argmin()))
                    return
                if cv2.pointPolygonTest(np.float32(bay["points"]), tuple(point), False) >= 0:
                    selected = idx
                    return
            pending.append(point)
            if len(pending) == 4:
                p = ordered(pending).tolist()
                if valid_quad(p):
                    add(p)
                    selected = len(bays)-1
                pending.clear()
        elif event == cv2.EVENT_MOUSEMOVE and drag:
            idx, k = drag
            candidate = [v[:] for v in bays[idx]["points"]]
            candidate[k] = point
            if valid_quad(candidate):
                bays[idx]["points"] = candidate
        elif event == cv2.EVENT_LBUTTONUP:
            drag = None

    window = "ParkEase calibration"
    cv2.namedWindow(window)
    cv2.setMouseCallback(window, mouse)
    try:
        while True:
            view = frame.copy()
            for i,bay in enumerate(bays):
                pts = np.int32(np.array(bay["points"])*[w,h])
                color = (40,230,255) if i == selected else (70,240,90)
                cv2.polylines(view,[pts],True,color,2)
                for x,y in pts:
                    cv2.circle(view,(x,y),4,color,-1)
                cv2.putText(view,bay["id"],tuple(pts.mean(axis=0).astype(int)),0,.55,color,2)
            for p in pending:
                cv2.circle(view,tuple(np.int32(np.array(p)*[w,h])),4,(255,180,0),-1)
            cv2.drawMarker(view,tuple(np.int32(np.array(config["entrance"])*[w,h])),(255,220,0))
            cv2.imshow(window, view)
            if message:
                print(message, flush=True)
                message = ""
            key = cv2.waitKey(30) & 255
            if key == 27 or cv2.getWindowProperty(window,cv2.WND_PROP_VISIBLE)<1:
                return
            if key == ord('a') and not bays:
                for p in suggest(frame):
                    add(p)
                message = f"{len(bays)} outlines suggested. Review, adjust or add manually."
            if key == ord('d') and selected is not None:
                bays.pop(selected)
                selected = None
            if key == ord('u') and pending:
                pending.pop()
            if key == ord('e'):
                entrance_mode = True
                message = "Click the entrance."
            if key == ord('s') and bays and not pending and all(valid_quad(b['points']) for b in bays):
                config['revision'] = uuid.uuid4().hex
                config['aspect'] = w / h
                temp = filename.with_suffix('.tmp')
                temp.write_text(json.dumps(config,indent=2))
                temp.replace(filename)
                print("Saved",filename)
                return
    finally:
        cv2.destroyAllWindows()


def occupied(frame, points, detector):
    h,w = frame.shape[:2]
    quad = ordered(np.float32(points)*[w,h])
    x,y,bw,bh = cv2.boundingRect(quad)
    crop = frame[y:y+bh,x:x+bw]
    q = np.int32(quad-[x,y])
    mask = np.zeros(crop.shape[:2],np.uint8)
    cv2.fillConvexPoly(mask,q,255)
    gray = cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    hits = detector.detectMultiScale(cv2.bitwise_and(gray,gray,mask=mask),1.1,1)
    return any(cv2.pointPolygonTest(q,(float(cx+cw/2),float(cy+ch/2)),False)>=0 for cx,cy,cw,ch in hits)


def publish(url, token, data):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
        raise ValueError("Use HTTPS for the ParkEase endpoint.")
    req = Request(url.rstrip('/')+'/api/telemetry',data=json.dumps(data).encode(),
                  headers={'Content-Type':'application/json','Authorization':'Bearer '+token},method='POST')
    with urlopen(req,timeout=8) as result:
        result.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["calibrate","monitor"])
    parser.add_argument("--source",default=os.getenv("PARKEASE_CAMERA_SOURCE","0"),help="Device index, RTSP/HTTP stream or local video")
    parser.add_argument("--layout",type=Path,default=Path("camera-layout.json"))
    parser.add_argument("--server",default=os.getenv("PARKEASE_SERVER"))
    args=parser.parse_args()
    camera=open_camera(args.source)
    try:
        if args.mode=="calibrate":
            ok,frame=camera.read()
            if not ok: raise RuntimeError("No video frame received")
            calibrate(frame,args.layout)
            return
        layout=json.loads(args.layout.read_text())
        if not layout["bays"] or not all(valid_quad(b["points"]) for b in layout["bays"]):
            raise ValueError("Recalibrate the camera before monitoring.")
        token=os.getenv("PARKEASE_CAMERA_TOKEN","")
        if not token or not args.server: raise ValueError("Set PARKEASE_SERVER and PARKEASE_CAMERA_TOKEN.")
        detector=cv2.CascadeClassifier(str(ROOT/'cars.xml'))
        if detector.empty(): raise RuntimeError("Car classifier unavailable")
        history={b["id"]:deque(maxlen=3) for b in layout["bays"]}
        recorded = not args.source.isdecimal() and "://" not in args.source
        fps = camera.get(cv2.CAP_PROP_FPS) if recorded else 0
        last=0
        while True:
            ok, frame=camera.read()
            if not ok:
                if recorded: break
                camera.release()
                for votes in history.values(): votes.clear()
                while True:
                    time.sleep(2)
                    try:
                        camera = open_camera(args.source)
                        break
                    except RuntimeError:
                        print("Waiting for camera connection.", flush=True)
                continue
            if recorded: time.sleep(1 / (fps if 0 < fps < 240 else 25))
            if time.monotonic()-last < 1: continue
            last=time.monotonic()
            timestamp=time.time()
            height,width=frame.shape[:2]
            if abs(width/height-layout["aspect"])>.03: raise ValueError("Camera aspect changed. Recalibrate.")
            states=[]
            for b in layout["bays"]:
                votes=history[b["id"]]
                votes.append(occupied(frame,b["points"],detector))
                states.append({"id":b["id"],"points":b["points"],"occupied":sum(votes)>=2})
            if min(map(len,history.values()))<3: continue
            try:
                publish(args.server,token,{"revision":layout["revision"],"observed":timestamp,
                       "entrance":layout["entrance"],"aspect":layout["aspect"],"bays":states})
            except OSError as err:
                print("Telemetry update failed:",type(err).__name__,getattr(err,"code",""),flush=True)
    finally:
        camera.release()

if __name__=="__main__":
    main()
