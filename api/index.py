"""ParkEase API. A single locked lot row serializes bookings and camera updates."""
import hashlib
import hmac
import math
import os
import re
import secrets
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, request, send_from_directory
from sqlalchemy import (JSON, Column, Float, ForeignKey, Integer, MetaData, String, Table,
                        create_engine, delete, insert, select, update)
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 100_000
schema = MetaData()
drivers = Table("pe_driver", schema, Column("id", Integer, primary_key=True),
                Column("name", String(40), unique=True, nullable=False), Column("password", String(256), nullable=False))
profiles = Table("pe_driver_profile", schema,
                 Column("driver", Integer, ForeignKey("pe_driver.id"), primary_key=True),
                 Column("full_name", String(100), nullable=False),
                 Column("contact", String(16), nullable=False))
sessions = Table("pe_session", schema, Column("digest", String(64), primary_key=True),
                 Column("driver", Integer, nullable=False), Column("expires", Float, nullable=False))
lots = Table("pe_lot", schema, Column("id", Integer, primary_key=True), Column("snapshot", JSON, nullable=False))
holds = Table("pe_hold", schema, Column("bay", String(30), primary_key=True),
              Column("driver", Integer, unique=True, nullable=False), Column("expires", Float, nullable=False))
database = os.getenv("PARKEASE_DATABASE_URL")
if database and database.startswith(("postgres://", "postgresql://")):
    database = "postgresql+psycopg://" + database.split("://", 1)[1]
if not database and not os.getenv("VERCEL"):
    database = "sqlite:///" + str(ROOT / "parkease.local.sqlite3")
engine = create_engine(database, pool_pre_ping=True) if database else None
COOKIE = "parkease_session"
HOLD_SECONDS = 900
STALE_SECONDS = 20


def initialize():
    if engine is None:
        raise RuntimeError("Configure PARKEASE_DATABASE_URL first.")
    schema.create_all(engine)
    try:
        with engine.begin() as conn:
            conn.execute(insert(lots).values(id=1, snapshot={}))
    except IntegrityError:
        pass


@contextmanager
def transaction(write=False):
    if engine is None: abort(503, "Booking service awaits database setup.")
    with engine.connect() as conn:
        if write and engine.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def lot(conn, lock=False):
    query = select(lots.c.snapshot).where(lots.c.id == 1)
    return conn.execute(query.with_for_update() if lock else query).scalar_one()


def user(conn):
    token = request.cookies.get(COOKIE, "")
    if not token: return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    return conn.execute(select(drivers.c.id, drivers.c.name).join(sessions, sessions.c.driver == drivers.c.id)
                        .where(sessions.c.digest == digest, sessions.c.expires > time.time())).first()


@app.before_request
def check_origin():
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host: abort(403, "Origin rejected.")
        if not request.is_json: abort(415, "JSON required.")


@app.after_request
def headers(response):
    if request.path.startswith("/api/"): response.headers["Cache-Control"] = "private, no-store"
    return response


@app.errorhandler(HTTPException)
def problem(error):
    return jsonify(error=error.description), error.code


@app.post("/api/<action>")
def account(action):
    if action not in {"login", "signup", "logout"}: abort(404)
    data = request.get_json()
    if not isinstance(data, dict): abort(400, "Invalid request.")
    with transaction(True) as conn:
        if action == "logout":
            digest = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
            conn.execute(delete(sessions).where(sessions.c.digest == digest))
            result = jsonify(ok=True)
            result.delete_cookie(COOKIE, path="/")
            return result
        name, password = data.get("username"), data.get("password")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{3,40}", name):
            abort(400, "Use a username with 3–40 letters, numbers, dots, underscores or dashes.")
        if not isinstance(password, str) or not 1 <= len(password) <= 128: abort(400, "Invalid password.")
        name = name.lower()
        if action == "signup":
            if len(password)<12: abort(400, "Use at least 12 characters for your password.")
            if data.get("confirm_password") != password:
                abort(400, "Passwords do not match.")
            full_name = data.get("full_name")
            if not isinstance(full_name, str) or not 1 <= len(full_name.strip()) <= 100 or not full_name.strip().isprintable():
                abort(400, "Enter your full name (up to 100 characters).")
            contact = data.get("contact")
            if not isinstance(contact, str) or len(contact) > 32:
                abort(400, "Enter a valid contact number.")
            contact = re.sub(r"[ ()-]", "", contact)
            if not re.fullmatch(r"\+?[0-9]{7,15}", contact):
                abort(400, "Enter a contact number with 7–15 digits.")
            try:
                driver = conn.execute(insert(drivers).values(name=name,password=generate_password_hash(password))).inserted_primary_key[0]
            except IntegrityError:
                abort(409, "Username unavailable.")
            conn.execute(insert(profiles).values(driver=driver, full_name=full_name.strip(), contact=contact))
        else:
            row = conn.execute(select(drivers).where(drivers.c.name == name)).first()
            if not row or not check_password_hash(row.password, password): abort(401, "Invalid username or password.")
            driver = row.id
        token = secrets.token_urlsafe(32)
        conn.execute(delete(sessions).where(sessions.c.expires <= time.time()))
        conn.execute(insert(sessions).values(digest=hashlib.sha256(token.encode()).hexdigest(), driver=driver, expires=time.time()+86400))
    result = jsonify(username=name)
    result.set_cookie(COOKIE, token, max_age=86400, httponly=True, secure=bool(os.getenv("VERCEL")) or request.is_secure, samesite="Lax", path="/")
    return result


def number(x):
    return type(x) in (int, float) and math.isfinite(x)


def point(p):
    return isinstance(p, list) and len(p)==2 and all(number(x) and 0<=x<=1 for x in p)


@app.post("/api/telemetry")
def telemetry():
    token = os.getenv("PARKEASE_CAMERA_TOKEN")
    if not token or not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer "+token):
        abort(403, "Camera authorization required.")
    data = request.get_json()
    if not isinstance(data,dict): abort(400)
    ts, bays = data.get("observed"), data.get("bays")
    if not number(ts) or not time.time()-STALE_SECONDS < ts < time.time()+3: abort(400, "Expired observation.")
    if not (isinstance(data.get("revision"),str) and re.fullmatch("[0-9a-f]{32}",data["revision"]) and point(data.get("entrance")) and number(data.get("aspect")) and .1<data["aspect"]<10 and isinstance(bays,list) and 1<=len(bays)<=100): abort(400,"Invalid layout.")
    ids=set()
    for bay in bays:
        if not isinstance(bay,dict): abort(400)
        label=bay.get("id")
        if not (isinstance(label,str) and re.fullmatch(r"[A-Za-z0-9_-]{1,30}",label) and label not in ids and type(bay.get("occupied")) is bool and isinstance(bay.get("points"),list) and len(bay["points"])==4 and all(point(p) for p in bay["points"])): abort(400,"Invalid bay.")
        ids.add(label)
    with transaction(True) as conn:
        previous = lot(conn,True)
        if previous.get("observed",0)>=ts: abort(409,"Out-of-order observation.")
        if previous and previous["revision"]!=data["revision"] and conn.execute(select(holds.c.bay).where(holds.c.expires>time.time()).limit(1)).first():
            abort(409,"Layout change requires active reservations to finish.")
        conn.execute(update(lots).where(lots.c.id==1).values(snapshot=data))
    return jsonify(ok=True)


@app.get("/api/state")
def state():
    if engine is None: return jsonify(snapshot={}, holds=[], mine=None, username=None, fresh=False, configured=False)
    with transaction() as conn:
        current = user(conn)
        data = lot(conn)
        active = conn.execute(select(holds).where(holds.c.expires>time.time())).all()
    mine = next(({"bay":h.bay,"expires":h.expires} for h in active if current and h.driver==current.id),None)
    return jsonify(snapshot=data,holds=[h.bay for h in active],mine=mine,
                   username=current.name if current else None,fresh=time.time()-data.get("observed",0)<STALE_SECONDS,configured=True)


@app.post("/api/book")
def book():
    if not request.cookies.get(COOKIE): abort(401,"Log in to reserve a bay.")
    data = request.get_json()
    if not isinstance(data,dict): abort(400)
    with transaction(True) as conn:
        current=user(conn)
        if not current: abort(401,"Log in to reserve a bay.")
        snapshot=lot(conn,True)
        now=time.time()
        if now-snapshot.get("observed",0)>=STALE_SECONDS: abort(409,"Waiting for fresh CCTV data.")
        if snapshot.get("revision")!=data.get("revision"): abort(409,"Layout changed. Select the bay again.")
        bay=next((b for b in snapshot["bays"] if b["id"]==data.get("bay")),None)
        if not bay or bay["occupied"]: abort(409,"Bay is unavailable.")
        conn.execute(delete(holds).where(holds.c.expires<=now))
        try:
            conn.execute(insert(holds).values(bay=bay["id"], driver=current.id, expires=now+HOLD_SECONDS))
        except IntegrityError: abort(409,"Bay already reserved or you already have an active reservation.")
    return jsonify(bay=bay["id"], expires=now+HOLD_SECONDS),201


@app.post("/api/cancel")
def cancel():
    with transaction(True) as conn:
        current=user(conn)
        if not current: abort(401)
        lot(conn,True)
        conn.execute(delete(holds).where(holds.c.driver==current.id))
    return jsonify(ok=True)


@app.get("/")
@app.get("/<path:path>")
def frontend(path=""):
    if path.startswith("api/"): abort(404)
    return send_from_directory(ROOT/"public",path+"index.html" if not path or path.endswith("/") else path)


if __name__ == "__main__":
    initialize()
    app.run(port=8000)
