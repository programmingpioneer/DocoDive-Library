import os
import base64
import io
import re
import json
import random
from collections import defaultdict
import secrets
import socket
import fitz
import requests
import threading
import time
import sentry_sdk
from bs4 import BeautifulSoup
from sentry_sdk.integrations.flask import FlaskIntegration
from datetime import datetime, timedelta, timezone
from functools import wraps
from html import escape
from urllib.parse import quote
import hashlib
import hmac
from jinja2 import TemplateNotFound
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    session,
    abort,
    flash,
    g,
    Response,
)

from PIL import Image
from flask_caching import Cache

import qrcode
from io import BytesIO
from flask import send_file

import boto3
from botocore.config import Config
from pdf_delivery import PDFDeliveryError, open_pdf_object, resolve_r2_key, trusted_public_pdf_url
from pypdf import PdfReader
import mysql.connector as mysql_connector_module
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from password_security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman

# Social login
from authlib.integrations.flask_client import OAuth

load_dotenv()

try:
    import google.genai as genai

    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from flask_mail import Mail, Message

    HAS_MAIL = True
except ImportError:
    HAS_MAIL = False

app = Flask(__name__)
IS_PRODUCTION = os.getenv("FLASK_ENV", "").lower() == "production"


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


# -------------------- SENTRY INITIALIZATION --------------------
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        environment=os.getenv("FLASK_ENV", "development"),
        send_default_pii=False,
    )
    app.logger.info("Sentry initialized")
else:
    app.logger.warning("SENTRY_DSN not set – error tracking disabled")

Talisman(
    app,
    content_security_policy=None,
    force_https=IS_PRODUCTION,
    strict_transport_security=IS_PRODUCTION,
    session_cookie_secure=IS_PRODUCTION,
)

# ---- Rate limiter (thresholds .env se, hardcoded nahi) ----
_ratelimit_day = os.getenv("RATELIMIT_DEFAULT_DAY", "5000 per day")
_ratelimit_hour = os.getenv("RATELIMIT_DEFAULT_HOUR", "500 per hour")
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[_ratelimit_day, _ratelimit_hour],
)

# Tiered limits — env se configurable
AUTH_RATELIMIT = os.getenv("RATELIMIT_AUTH", "5 per minute")
PUBLIC_RATELIMIT = os.getenv("RATELIMIT_PUBLIC", "60 per minute")
USER_ACTION_RATELIMIT = os.getenv("RATELIMIT_USER_ACTION", "20 per minute")

app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 300

# Use HTTPS in production and HTTP for the local development server.
app.config["PREFERRED_URL_SCHEME"] = "https" if IS_PRODUCTION else "http"

cache = Cache(app)


@app.before_request
def enforce_canonical_host():
    """www -> non-www + http -> https redirect (single canonical domain for SEO)."""
    host = request.host
    url = request.url

    # www -> non-www
    if host.startswith("www."):
        url = url.replace("://www.", "://", 1)
        return redirect(url, code=301)

    # http -> https (sirf production me, local dev me nahi)
    if IS_PRODUCTION and request.scheme == "http":
        url = url.replace("http://", "https://", 1)
        return redirect(url, code=301)


@app.after_request
def add_cache_headers(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "private, no-store"

    return response


secret_key = os.getenv("FLASK_SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is required. Set it in your .env file "
        '(generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))").'
    )
app.config["SECRET_KEY"] = secret_key

CRON_SECRET = os.getenv("CRON_SECRET")
if not CRON_SECRET:
    CRON_SECRET = secrets.token_urlsafe(32)
    app.logger.warning("CRON_SECRET not set; generated a random secret (value hidden)")

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

app.config["FACEBOOK_APP_SECRET"] = os.getenv("FACEBOOK_CLIENT_SECRET")

# ================== DATABASE CONFIGURATION (MYSQL_* with DB_* fallback) ==================
app.config["MYSQL_HOST"] = os.environ.get("DB_HOST") or os.environ.get(
    "MYSQL_HOST", "localhost"
)
app.config["MYSQL_PORT"] = int(
    os.environ.get("DB_PORT") or os.environ.get("MYSQL_PORT", "3306")
)
app.config["MYSQL_USER"] = os.environ.get("DB_USER") or os.environ.get(
    "MYSQL_USER", "root"
)
app.config["MYSQL_PASSWORD"] = os.environ.get("DB_PASSWORD") or os.environ.get(
    "MYSQL_PASSWORD", ""
)
app.config["MYSQL_DB"] = os.environ.get("DB_NAME") or os.environ.get(
    "MYSQL_DB", "docodive_dev"
)

app.config["MYSQL_SSL_CA"] = os.environ.get("MYSQL_SSL_CA") or os.path.join(
    os.path.dirname(__file__), "ssl", "isrgrootx.pem"
)
app.config["MYSQL_SSL_VERIFY_CERT"] = _env_bool("MYSQL_SSL_VERIFY_CERT", False)
app.config["MYSQL_SSL_VERIFY_IDENTITY"] = _env_bool("MYSQL_SSL_VERIFY_IDENTITY", False)

from mysql.connector.pooling import MySQLConnectionPool

db_config = {
    "host": app.config["MYSQL_HOST"],
    "user": app.config["MYSQL_USER"],
    "password": app.config["MYSQL_PASSWORD"],
    "database": app.config["MYSQL_DB"],
    "port": app.config["MYSQL_PORT"],
    "use_pure": True,
    "autocommit": True,
    "connection_timeout": 10,
    "read_timeout": 15,
    "write_timeout": 15,
}
ssl_ca = app.config.get("MYSQL_SSL_CA")
if ssl_ca:
    db_config["ssl_ca"] = ssl_ca
    db_config["ssl_verify_cert"] = app.config.get("MYSQL_SSL_VERIFY_CERT", False)
    db_config["ssl_verify_identity"] = app.config.get(
        "MYSQL_SSL_VERIFY_IDENTITY", False
    )


pool = MySQLConnectionPool(
    pool_name="mypool", pool_size=20, pool_reset_session=False, **db_config
)


class MySQLWrapper:
    def __init__(self, app_config):
        self.config = app_config

    @property
    def connection(self):
        if "db_conn" not in g:
            g.db_conn = pool.get_connection()
        else:
            try:
                # Har use se pehle connection zinda hai ya nahi check karo
                g.db_conn.ping(reconnect=False)
            except Exception:
                # Agar connection dead ho gaya to naya le lo
                try:
                    g.db_conn.close()
                except Exception:
                    pass
                g.db_conn = pool.get_connection()
        return g.db_conn

    @property
    def connector(self):
        return self.connection

    @property
    def connector(self):
        return self.connection


@app.teardown_appcontext
def close_db_connection(exception):
    db_conn = g.pop("db_conn", None)
    if db_conn is not None:
        try:
            db_conn.close()
        except Exception:
            pass


mysql = MySQLWrapper(app.config)


@app.before_request
def csrf_protect():
    # External callbacks authenticate with their own signatures, not a browser session.
    if request.path.startswith("/internal/notification-digest/") or request.path in (
        "/api/brevo/webhook",
        "/facebook/data-deletion",
    ):
        return
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        token = session.get("_csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get(
            "_csrf_token", ""
        )
        if (
            not token
            or not supplied
            or not hmac.compare_digest(str(token), str(supplied))
        ):
            abort(403)
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)


# ================== OAuth SETUP ==================
oauth = OAuth(app)

oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    access_token_url="https://accounts.google.com/o/oauth2/token",
    authorize_url="https://accounts.google.com/o/oauth2/auth",
    api_base_url="https://www.googleapis.com/oauth2/v1/",
    client_kwargs={"scope": "openid email profile"},
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
)

oauth.register(
    name="github",
    client_id=os.getenv("GITHUB_CLIENT_ID"),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "user:email"},
)

oauth.register(
    name="facebook",
    client_id=os.getenv("FACEBOOK_CLIENT_ID"),
    client_secret=os.getenv("FACEBOOK_CLIENT_SECRET"),
    access_token_url="https://graph.facebook.com/oauth/access_token",
    authorize_url="https://www.facebook.com/dialog/oauth",
    api_base_url="https://graph.facebook.com/",
    client_kwargs={"scope": "email public_profile"},
)


def compress_image(image_bytes, max_size=(600, 600), quality=85):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail(max_size, Image.LANCZOS)
    output = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def get_book_of_the_day():
    today = datetime.utcnow().date()
    seed = today.toordinal()
    random.seed(seed)
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents WHERE approved = 1")
    total = cur.fetchone()[0]
    if total == 0:
        cur.close()
        return None
    offset = random.randint(0, total - 1)
    cur.execute(
        """
        SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved = 1
        LIMIT 1 OFFSET %s
    """,
        (offset,),
    )
    book = cur.fetchone()
    cur.execute(
        "UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book[0],)
    )
    mysql.connection.commit()
    cur.close()
    random.seed()
    return book


app.config["ADMIN_NOTIFICATION_EMAIL"] = os.getenv("ADMIN_NOTIFICATION_EMAIL")
app.config["SUPPORT_EMAIL"] = os.getenv("SUPPORT_EMAIL", "")
app.config["MAIL_FROM_NAME"] = os.getenv("MAIL_FROM_NAME", "DocoDive")
app.config["MAIL_FROM_EMAIL"] = os.getenv(
    "MAIL_FROM_EMAIL", "noreply@programmingpioneer.com"
)

ALLOWED_EXTENSIONS = {"pdf"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

mail = None
if HAS_MAIL:
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp-relay.brevo.com")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_TIMEOUT"] = int(os.getenv("MAIL_TIMEOUT", "15"))
    if app.config["MAIL_USE_TLS"] and app.config["MAIL_USE_SSL"]:
        raise RuntimeError("Enable only one of MAIL_USE_TLS or MAIL_USE_SSL.")
    app.config["MAIL_DEFAULT_SENDER"] = (
        app.config["MAIL_FROM_NAME"],
        app.config["MAIL_FROM_EMAIL"],
    )
    mail = Mail(app)

genai_client = None
if HAS_GEMINI and os.getenv("GEMINI_API_KEY"):
    genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# -------------------- CLOUDFLARE R2 CLIENT (FIXED) --------------------
r2_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("R2_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=30,
                  retries={"max_attempts": 1, "mode": "standard"}),
    region_name="auto",
)
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "docodive")
R2_PUBLIC_BASE = os.getenv(
    "R2_PUBLIC_DOMAIN", "https://pub-8f5fcc3c01514e53b12396f444c45448.r2.dev"
).rstrip("/")


def upload_to_r2(file_bytes, key, content_type="application/octet-stream"):
    r2_client.put_object(
        Bucket=R2_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
        CacheControl="public, max-age=2592000, immutable",
    )
    if not R2_PUBLIC_BASE:
        return key
    return f"{R2_PUBLIC_BASE}/{key}"


def delete_from_r2(key):
    try:
        r2_client.delete_object(Bucket=R2_BUCKET, Key=key)
    except Exception:
        pass


def generate_r2_key(folder, base_name, ext):
    return f"docodive/{folder}/{base_name}_{secrets.token_hex(16)}{ext}"


def is_valid_pdf(file_bytes):
    """Check magic bytes — extension par bharosa nahi."""
    return file_bytes[:4] == b"%PDF"


def is_valid_image(file_bytes):
    """Check image magic bytes (JPEG/PNG/WebP/GIF)."""
    if file_bytes[:3] == b"\xff\xd8\xff":  # JPEG
        return True
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":  # PNG
        return True
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return True
    if file_bytes[:4] == b"GIF8":  # GIF (GIF87a/GIF89a)
        return True
    return False


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


# -------------------- BREVO API EMAIL SENDING (FIXED) --------------------
def send_email_via_api(subject, recipient, body, html_body=None):
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        app.logger.error("BREVO_API_KEY not set, cannot send via API")
        return False
    sender_email = app.config.get("MAIL_FROM_EMAIL") or "noreply@programmingpioneer.com"
    sender_name = app.config.get("MAIL_FROM_NAME") or "DocoDive"
    try:
        data = {
            "sender": {"email": sender_email, "name": sender_name},
            "to": [{"email": recipient}],
            "subject": subject,
            "htmlContent": html_body or body,
            "textContent": body,
        }
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=data,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 201:
            app.logger.info("Email sent via API to %s", recipient)
            return True
        else:
            app.logger.error("Brevo API delivery failed, status=%s", resp.status_code)
            return False
    except Exception as e:
        app.logger.exception("Brevo API request failed: %s", e)
        return False


def send_email_notification(subject, recipient, body, html_body=None):
    recipient = (recipient or "").strip()
    subject = " ".join((subject or "").splitlines()).strip()
    if not recipient or "\r" in recipient or "\n" in recipient:
        return False
    return send_email_via_api(subject, recipient, body, html_body)


def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        return False
    disposable = [
        "mailinator.com",
        "tempmail.com",
        "throwaway.com",
        "guerrillamail.com",
        "sharklasers.com",
        "10minutemail.com",
        "yopmail.com",
        "trashmail.com",
    ]
    return email.split("@")[1].lower() not in disposable


def sync_brevo_contact(email, first_name="", last_name=""):
    """Create or update a Brevo contact. Non-fatal: logs errors but never crashes."""
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        app.logger.warning("BREVO_API_KEY not set, skipping contact sync")
        return False
    try:
        payload = {
            "email": email,
            "attributes": {"FIRSTNAME": first_name or "", "LASTNAME": last_name or ""},
            "updateEnabled": True,
        }
        resp = requests.post(
            "https://api.brevo.com/v3/contacts",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code in (200, 201, 204):
            app.logger.info("Brevo contact synced: %s", email)
            return True
        app.logger.error("Brevo contact sync failed: %s", resp.text)
        return False
    except Exception as e:
        app.logger.exception("Brevo contact sync error: %s", e)
        return False


def track_download(book_id):
    if "user_id" in session:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
            (session["user_id"], book_id),
        )
        mysql.connection.commit()
        cur.close()


def award_points(user_id, points, book_id=None, action="activity"):
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO user_points (user_id, points, action, book_id) VALUES (%s, %s, %s, %s)",
        (user_id, points, action, book_id),
    )
    mysql.connection.commit()
    cur.close()


def create_notification(user_id, type, message, link=None, metadata=None):
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO notifications (user_id, message, link, type, metadata) VALUES (%s, %s, %s, %s, %s)",
        (user_id, message, link, type, json.dumps(metadata) if metadata else None),
    )
    mysql.connection.commit()
    cur.close()


BANNED_SUBSTRINGS = ["techbymehdi"]


def clean_professional_name(raw_name):
    name = raw_name
    for banned in BANNED_SUBSTRINGS:
        name = re.sub(re.escape(banned), "", name, flags=re.IGNORECASE)
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\{.*?\}", "", name)
    name = re.sub(
        r"\b(version\s?\d+(\.\d+)?|v\d+(\.\d+)?|final|draft)\b", "", name, flags=re.I
    )
    name = re.sub(r"[_\-.]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        name = "Untitled"
    name = name.title()
    name = re.sub(r"[^\w]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if len(name) > 60:
        name = name[:60].rstrip("_")
    return f"{name}_@DocoDive"


def normalize_for_duplicate_check(title):
    t = re.sub(r"\s*\(\d+\)\s*$", "", title)
    t = re.sub(r"\s*-\s*Copy(\s*\(\d+\))?\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*-\s*copy(\s*\(\d+\))?\s*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip().lower()


def is_duplicate(title, author, conn):
    norm_title = normalize_for_duplicate_check(title)
    cur = conn if hasattr(conn, "execute") else conn.cursor()
    try:
        cur.execute(
            "SELECT id, title FROM documents WHERE LOWER(author) = %s",
            (author.lower(),),
        )
        rows = cur.fetchall()
        for row in rows:
            if normalize_for_duplicate_check(row[1]) == norm_title:
                return True
        return False
    finally:
        if cur is not conn:
            cur.close()


KEYWORDS = {
    "Python": [
        "import ",
        "def ",
        "class ",
        "print(",
        "pandas",
        "numpy",
        "python",
        "django",
        "flask",
        "tkinter",
    ],
    "JavaScript": [
        "var ",
        "const ",
        "function",
        "document.",
        "console.log",
        "react",
        "angular",
        "node",
        "express",
    ],
    "Java": ["public class", "system.out", "java", "spring", "hibernate", "swing"],
    "C / C++": [
        "#include",
        "int main",
        "printf",
        "cout",
        "std::",
        "iostream",
        "malloc",
    ],
    "Web Development": [
        "html",
        "css",
        "<div",
        "react",
        "angular",
        "bootstrap",
        "jquery",
        "responsive",
    ],
    "Data Science": [
        "dataframe",
        "scikit",
        "matplotlib",
        "pandas",
        "numpy",
        "seaborn",
        "analytics",
    ],
    "Machine Learning": [
        "model.fit",
        "train_test_split",
        "tensorflow",
        "keras",
        "pytorch",
        "deep learning",
    ],
    "Algorithms": [
        "algorithm",
        "sort",
        "complexity",
        "big o",
        "binary search",
        "graph",
    ],
    "Databases": ["sql", "query", "select *", "mysql", "postgresql", "oracle", "nosql"],
    "Cyber Security": [
        "encrypt",
        "hack",
        "firewall",
        "penetration",
        "malware",
        "sql injection",
    ],
    "Mobile Apps": ["android", "ios", "swift", "kotlin", "flutter", "react native"],
    "DevOps": ["docker", "kubernetes", "ci/cd", "terraform", "jenkins", "ansible"],
}


def extract_text_from_pdf(reader, max_pages=5):
    text = ""
    for page in reader.pages[:max_pages]:
        extracted = page.extract_text()
        if extracted:
            text += extracted
    return text.lower()


def guess_category(text):
    scores = {
        cat: sum(1 for kw in kwds if kw in text) for cat, kwds in KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Others"


def guess_category_intelligent(pdf_text, raw_name):
    combined = pdf_text + " " + raw_name.lower()
    for word in raw_name.lower().split():
        combined += " " + word
    return guess_category(combined)


def ai_enhance_metadata(title, author, text):
    if not genai_client:
        return (
            title,
            author,
            f"A comprehensive resource about '{title}'. Covers essential topics.",
        )
    try:
        prompt = f"""
Improve the following book title, author, and generate a short description.
Title: {title}
Author: {author}
First page text: {text[:2000]}
Return JSON with keys: title, author, description.
"""
        response = genai_client.models.generate_content(
            model="gemini-1.5-flash", contents=prompt
        )
        response_text = response.text
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return (
                data.get("title", title),
                data.get("author", author),
                data.get("description", ""),
            )
    except Exception as e:
        app.logger.error(f"AI metadata failed: {e}")
    return (
        title,
        author,
        f"A comprehensive resource about '{title}'. Covers essential topics.",
    )


# ==================== LOGIN BACKOFF ====================
_login_attempts = {}  # key: "ip|email" -> (fail_count, locked_until)


def check_login_backoff(ip, email):
    """Returns (is_blocked, wait_seconds). Exponential backoff, no hard lockout."""
    key = f"{ip}|{email.lower()}"
    if key in _login_attempts:
        count, locked_until = _login_attempts[key]
        now = time.time()
        if now < locked_until:
            return True, int(locked_until - now)
        # lock expired, reset
        if now - locked_until > 300:
            _login_attempts.pop(key, None)
    return False, 0


def record_login_failure(ip, email):
    """Har fail par backoff double karo: 2s -> 4s -> 8s -> 16s -> 32s."""
    key = f"{ip}|{email.lower()}"
    count, _ = _login_attempts.get(key, (0, 0))
    count += 1
    wait = min(2**count, 60)  # max 60 seconds cap
    _login_attempts[key] = (count, time.time() + wait)
    return wait


def clear_login_backoff(ip, email):
    """Successful login par record hatao."""
    _login_attempts.pop(f"{ip}|{email.lower()}", None)


def setup_session(user_id):
    account_version = app.extensions["account_lifecycle"].on_login(user_id)
    studio_token = session.get("studio_token")
    studio_id = session.get("studio_user_id")
    session.clear()
    if studio_id is not None:
        session["studio_user_id"] = studio_id
        session["studio_token"] = studio_token
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT username, first_name, last_name, avatar_url, email FROM users WHERE id = %s",
        (user_id,),
    )
    user = cur.fetchone()
    cur.close()
    if user:
        session.permanent = True
        session["user_id"] = user_id
        session["account_version"] = account_version
        session["user_name"] = user[0]
        full_name = (user[1] or "") + " " + (user[2] or "")
        session["user_display_name"] = full_name.strip() or user[0]
        session["avatar_url"] = user[3]
        session["email"] = user[4]
        session.modified = True


def handle_social_login(provider_name, user_info):
    provider_id_field = f"{provider_name}_id"
    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("login")
    avatar = user_info.get("picture") or user_info.get("avatar_url")

    if not email:
        email = f"{user_info['sub']}@{provider_name}.local"

    first_name = ""
    last_name = ""
    if name:
        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

    cur = mysql.connection.cursor()

    cur.execute(
        f"SELECT id FROM users WHERE {provider_id_field} = %s", (user_info["sub"],)
    )
    user = cur.fetchone()
    if user:
        cur.close()
        return user[0], False

    if email and "@" in email:
        cur.execute(
            f"SELECT id, {provider_id_field} FROM users WHERE email = %s", (email,)
        )
        existing = cur.fetchone()
        if existing:
            if (
                provider_name not in ("google", "github")
                or user_info.get("email_verified") is not True
                or existing[1]
            ):
                cur.close()
                return None, False
            cur.execute(
                f"UPDATE users SET {provider_id_field} = %s, avatar_url = %s WHERE id = %s AND ({provider_id_field} IS NULL OR {provider_id_field} = '')",
                (user_info["sub"], avatar, existing[0]),
            )
            if cur.rowcount != 1:
                cur.close()
                return None, False
            mysql.connection.commit()
            cur.close()
            return existing[0], False

    username = email.split("@")[0] if email else user_info["sub"]
    base_username = username[:20]
    i = 1
    while True:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if not cur.fetchone():
            break
        username = f"{base_username}{i}"[:20]
        i += 1

    hashed = generate_password_hash(secrets.token_urlsafe(16))

    cur.execute(
        f"""
        INSERT INTO users (username, email, password, verified, verification_token,
                          first_name, last_name, avatar_url, {provider_id_field})
        VALUES (%s, %s, %s, 1, NULL, %s, %s, %s, %s)
    """,
        (username, email, hashed, first_name, last_name, avatar, user_info["sub"]),
    )
    mysql.connection.commit()
    user_id = cur.lastrowid
    cur.close()

    sync_brevo_contact(email, first_name, last_name)

    return user_id, True


# ================== EMAIL TEMPLATES ==================
BRAND_NAME = "DocoDive"
BRAND_COLOR = "#4F46E5"
BRAND_DARK = "#111827"
BRAND_LIGHT = "#EEF2FF"


def _safe(value):
    return escape(str(value or ""))


def _email_button(url, label, color=BRAND_COLOR):
    return f"""
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin:28px 0 8px;">
          <tr><td bgcolor="{color}" style="border-radius:8px;">
            <a href="{_safe(url)}" target="_blank" rel="noopener"
               style="display:inline-block;padding:14px 24px;border-radius:8px;color:#ffffff;
                      font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:700;
                      line-height:20px;text-decoration:none;">{_safe(label)}</a>
          </td></tr>
        </table>
    """


def _email_link(url):
    safe_url = _safe(url)
    return f"""
        <p style="margin:20px 0 0;color:#6B7280;font-size:12px;line-height:18px;">
          Button not working? Copy this link into your browser:<br>
          <a href="{safe_url}" style="color:{BRAND_COLOR};word-break:break-all;">{safe_url}</a>
        </p>
    """


def _email_layout(preheader, label, title, content):
    support_email = _safe(app.config.get("SUPPORT_EMAIL"))
    support = (
        f'Need help? <a href="mailto:{support_email}" style="color:{BRAND_COLOR};text-decoration:none;">Contact DocoDive Support</a>.'
        if support_email
        else "This is an automated account and security email from DocoDive."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{BRAND_NAME}</title>
  <style>
    @media only screen and (max-width:600px) {{
      .card {{ width:100% !important; border-radius:0 !important; }}
      .pad {{ padding:28px 22px !important; }}
      .title {{ font-size:26px !important; line-height:32px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#F3F4F6;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{_safe(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;</div>
  <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="background:#F3F4F6;">
    <tr><td align="center" style="padding:32px 12px;">
      <table role="presentation" class="card" width="600" border="0" cellpadding="0" cellspacing="0"
             style="width:600px;max-width:600px;background:#FFFFFF;border-radius:16px;overflow:hidden;">
        <tr><td style="padding:26px 40px;background:{BRAND_DARK};">
          <table role="presentation" border="0" cellpadding="0" cellspacing="0"><tr>
            <td width="40" height="40" align="center" style="width:40px;height:40px;border-radius:10px;background:{BRAND_COLOR};
                color:#FFFFFF;font:800 23px Arial,Helvetica,sans-serif;">D</td>
            <td style="padding-left:12px;color:#FFFFFF;font-family:Arial,Helvetica,sans-serif;">
              <div style="font-size:19px;font-weight:800;line-height:22px;">{BRAND_NAME}</div>
              <div style="padding-top:3px;color:#C7D2FE;font-size:12px;line-height:16px;">Free knowledge. Built for curious minds.</div>
            </td>
          </tr></table>
        </td></tr>
        <tr><td class="pad" style="padding:40px;color:#374151;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:25px;">
          <div style="color:{BRAND_COLOR};font-size:13px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;">{_safe(label)}</div>
          <h1 class="title" style="margin:10px 0 16px;color:{BRAND_DARK};font-size:30px;line-height:37px;">{_safe(title)}</h1>
          {content}
        </td></tr>
        <tr><td style="padding:24px 40px;background:#F9FAFB;border-top:1px solid #E5E7EB;color:#6B7280;
                       font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:19px;text-align:center;">
          <p style="margin:0 0 8px;">{support}</p>
          <p style="margin:0;">© {datetime.now().year} DocoDive · Free Knowledge, Pure Discipline.</p>
        </td></tr>
      </table>
      <p style="margin:18px 0 0;color:#9CA3AF;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:16px;">
        DocoDive will never ask for your password or verification code by email.
      </p>
    </td></tr>
  </table>
</body>
</html>"""


def make_verification_email(username, verify_link):
    content = f"""
        <p style="margin:0;">Hi {_safe(username)},</p>
        <p style="margin:16px 0 0;">Thanks for joining DocoDive. Confirm your email to activate your account and access the library.</p>
        {_email_button(verify_link, "Verify email address")}
        {_email_link(verify_link)}
        <div style="margin-top:28px;padding:16px;border-left:4px solid {BRAND_COLOR};background:{BRAND_LIGHT};
                    color:#3730A3;font-size:13px;line-height:20px;">
          Didn't create a DocoDive account? You can safely ignore this message.
        </div>
    """
    return _email_layout(
        "Confirm your email to activate your DocoDive account.",
        "Account security",
        "Confirm your email address",
        content,
    )


def make_welcome_email(user_name, provider):
    provider_display = {
        "google": "Google",
        "github": "GitHub",
        "facebook": "Facebook",
    }.get(provider.lower(), provider)
    content = f"""
        <p style="margin:0;">Hi {_safe(user_name)},</p>
        <p style="margin:16px 0 0;">Welcome to <strong>DocoDive</strong> – your gateway to 50,000+ free books &amp; resources!</p>
        <p style="margin:10px 0;">Your account was created via <strong>{provider_display}</strong>. You are now verified and can start exploring the library instantly.</p>
        {_email_button(url_for('home', _external=True), "Explore the Library")}
        <p style="margin-top:24px; font-size:13px; color:#6b7280;">Happy learning!<br>— Team DocoDive</p>
    """
    return _email_layout(
        "Welcome to DocoDive – you're verified!",
        "Welcome aboard",
        f"Hello {_safe(user_name)}!",
        content,
    )


def make_upload_notification_email(title, author, category):
    pending_url = url_for("pending_books", _external=True)
    content = f"""
        <p style="margin:0;">A user submission is waiting for approval.</p>
        <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0"
               style="margin:24px 0;background:#F9FAFB;border:1px solid #E5E7EB;border-radius:10px;">
          <tr><td style="padding:18px;">
            <p style="margin:0 0 10px;color:#6B7280;font-size:12px;font-weight:700;letter-spacing:.7px;">DOCUMENT DETAILS</p>
            <p style="margin:0 0 7px;"><strong style="color:{BRAND_DARK};">Title:</strong> {_safe(title)}</p>
            <p style="margin:0 0 7px;"><strong style="color:{BRAND_DARK};">Author:</strong> {_safe(author)}</p>
            <p style="margin:0;"><strong style="color:{BRAND_DARK};">Category:</strong> {_safe(category)}</p>
          </td></tr>
        </table>
        {_email_button(pending_url, "Review pending documents")}
    """
    return _email_layout(
        "A DocoDive document needs your review.",
        "Admin notification",
        "New document ready for review",
        content,
    )


@app.route("/reviews")
def reviews_page():
    """Public reviews page with rating breakdown, category metrics, and paginated reviews."""
    cur = mysql.connection.cursor()

    # Real review count (sirf non-empty comments)
    cur.execute(
        "SELECT COUNT(*) FROM reviews WHERE comment IS NOT NULL AND TRIM(comment) != ''"
    )
    total_reviews = cur.fetchone()[0] or 0

    # Real breakdown (5 → 1)
    cur.execute("""
        SELECT rating, COUNT(*)
        FROM reviews
        WHERE comment IS NOT NULL AND TRIM(comment) != ''
        GROUP BY rating
        """)
    breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for row in cur.fetchall():
        if row[0] in breakdown:
            breakdown[row[0]] = row[1]

    # Real average rating
    weighted_sum = sum(star * count for star, count in breakdown.items())
    total_count = sum(breakdown.values()) or 1
    avg_rating = round(weighted_sum / total_count, 1)

    page = max(1, request.args.get("page", 1, type=int))
    per_page = 20
    total_pages = max(1, (total_reviews + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    # Recent reviews list (full name + avatar)
    cur.execute(
        """
        SELECT r.id,
               u.username,
               COALESCE(
                   NULLIF(
                       CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')),
                       ' '
                   ),
                   u.username
               ) AS display_name,
               u.avatar_url,
               r.rating,
               r.comment,
               r.created_at,
               r.book_id,
               d.title,
               d.slug
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        LEFT JOIN documents d ON d.id = r.book_id AND d.approved = 1
        WHERE r.comment IS NOT NULL AND TRIM(r.comment) != ''
        ORDER BY r.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (per_page, offset),
    )
    reviews = [
        {
            "review_id": r[0],
            "username": r[1],
            "full_name": r[2],
            "avatar": r[3],
            "rating": r[4] or 0,
            "comment": r[5],
            "created_at": r[6].strftime("%b %d, %Y") if r[6] else "",
            "book_id": r[7],
            "book_title": r[8],
            "book_slug": r[9],
        }
        for r in cur.fetchall()
    ]

    # Books list for Add Review dropdown
    cur.execute(
        "SELECT id, title FROM documents WHERE approved = 1 ORDER BY title LIMIT 100"
    )
    books = [{"id": b[0], "title": b[1]} for b in cur.fetchall()]

    cur.close()

    return render_template(
        "user/reviews.html",
        avg_rating=avg_rating,
        breakdown=breakdown,
        total_reviews=total_reviews,
        reviews=reviews,
        books=books,
        page=page,
        total_pages=total_pages,
    )


@app.route("/api/review-books")
@limiter.limit(PUBLIC_RATELIMIT)
def review_book_search():
    """Search the approved catalog for the optional review book picker."""
    query = request.args.get("q", "").strip()
    if len(query) > 100:
        return jsonify({"error": "Search must be at most 100 characters"}), 400
    # Treat user-entered LIKE metacharacters literally, using a portable escape.
    pattern = "%" + query.replace("=", "==").replace("%", "=%").replace("_", "=_") + "%"
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """
            SELECT id, title, author FROM documents
            WHERE approved = 1
              AND (title LIKE %s ESCAPE '=' OR COALESCE(author, '') LIKE %s ESCAPE '=')
            ORDER BY title, id LIMIT 21
            """,
            (pattern, pattern),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
    return jsonify({
        "books": [{"id": row[0], "title": row[1], "author": row[2]} for row in rows[:20]],
        "has_more": len(rows) > 20,
    })


# _================== REVIEW LIKE TOGGLE API ==================
@app.route("/api/review/<int:review_id>/like", methods=["POST"])
def toggle_review_like(review_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id FROM review_likes WHERE user_id = %s AND review_id = %s",
        (user_id, review_id),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "DELETE FROM review_likes WHERE user_id = %s AND review_id = %s",
            (user_id, review_id),
        )
        liked = False
    else:
        cur.execute(
            "INSERT INTO review_likes (user_id, review_id) VALUES (%s, %s)",
            (user_id, review_id),
        )
        liked = True
    mysql.connection.commit()
    cur.execute("SELECT COUNT(*) FROM review_likes WHERE review_id = %s", (review_id,))
    like_count = cur.fetchone()[0]
    cur.execute(
        "UPDATE reviews SET like_count = %s WHERE id = %s", (like_count, review_id)
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"liked": liked, "like_count": like_count})


def make_code_email(code):
    content = f"""
        <p style="margin:0;">Enter this code in DocoDive to continue resetting your password:</p>
        <div style="margin:26px 0;padding:20px 12px;border:1px solid #C7D2FE;border-radius:12px;background:{BRAND_LIGHT};
                    color:#312E81;font:800 34px Arial,Helvetica,sans-serif;letter-spacing:10px;line-height:40px;text-align:center;">
          {_safe(code)}
        </div>
        <p style="margin:0;color:#4B5563;">This code expires in <strong>10 minutes</strong>. Do not share it with anyone.</p>
    """
    return _email_layout(
        "Your DocoDive password reset code is ready.",
        "Password reset",
        "Use this security code",
        content,
    )


def make_reset_link_email(reset_link):
    content = f"""
        <p style="margin:0;">Your code was confirmed. Use the secure link below to choose a new DocoDive password.</p>
        {_email_button(reset_link, "Reset password")}
        {_email_link(reset_link)}
    """
    return _email_layout(
        "Use this secure link to reset your DocoDive password.",
        "Password reset",
        "Set a new password",
        content,
    )


def make_approval_email(title, status, message):
    approved = status.lower() == "approved"
    status_label = "Approved" if approved else "Not approved"
    color = "#059669" if approved else "#DC2626"
    heading = "Your document is live" if approved else "Your document needs changes"
    action = "Browse the library" if approved else "Visit DocoDive"
    content = f"""
        <p style="margin:0;">{_safe(message)}</p>
        <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0"
               style="margin:24px 0;background:#F9FAFB;border:1px solid #E5E7EB;border-radius:10px;">
          <tr><td style="padding:18px;">
            <p style="margin:0;color:{BRAND_DARK};font-size:16px;font-weight:700;">{_safe(title)}</p>
            <p style="margin:8px 0 0;color:{color};font-size:14px;font-weight:700;">Status: {status_label}</p>
          </td></tr>
        </table>
        {_email_button(url_for('home', _external=True), action, color)}
    """
    return _email_layout(
        f"Your DocoDive submission is {status_label.lower()}.",
        "Document review",
        heading,
        content,
    )


# ================== SITE SETTINGS & OFFICIAL HELPERS ==================
def get_site_setting(key, default=None):
    cur = mysql.connection.cursor()
    cur.execute("SELECT `value` FROM site_settings WHERE `key` = %s", (key,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else default


def set_site_setting(key, value):
    cur = mysql.connection.cursor()
    cur.execute(
        "REPLACE INTO site_settings (`key`, `value`) VALUES (%s, %s)", (key, value)
    )
    mysql.connection.commit()
    cur.close()


# ================== HOME STATS (cached aggregates + recent reviews) ==================
_HOME_STATS_CACHE = {"ts": None, "data": None}


def get_home_stats():
    """Cached homepage aggregates + recent reviews (5 min TTL)."""
    now = datetime.now()
    cache = _HOME_STATS_CACHE
    if cache["ts"] and (now - cache["ts"]).total_seconds() < 300:
        return cache["data"]

    # Baseline counters — real counts inse add honge
    BOOKS_BASE = 0
    USERS_BASE = 0
    DOWNLOADS_BASE = 0

    cur = mysql.connection.cursor()

    # Real books count
    cur.execute("SELECT COUNT(*) FROM documents WHERE approved = 1")
    real_books = cur.fetchone()[0] or 0

    # Real downloads sum
    cur.execute(
        "SELECT COALESCE(SUM(download_count), 0) FROM documents WHERE approved = 1"
    )
    real_downloads = cur.fetchone()[0] or 0

    # Real users count
    cur.execute("SELECT COUNT(*) FROM users")
    real_users = cur.fetchone()[0] or 0
    from public_metrics import monthly_active_members
    from account_store import Store
    try:
        monthly_users = monthly_active_members(Store(mysql))
    except Exception:
        monthly_users = None
        app.logger.warning("Monthly member activity is unavailable; check the activity migration.")

    # Real categories count
    cur.execute("SELECT COUNT(*) FROM categories")
    total_categories = cur.fetchone()[0] or 0

    # Real reviews count
    cur.execute(
        "SELECT COUNT(*) FROM reviews WHERE comment IS NOT NULL AND TRIM(comment) != ''"
    )
    real_reviews = cur.fetchone()[0] or 0

    cur.close()

    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT r.id,u.username,u.first_name,u.last_name,u.avatar_url,r.rating,r.comment,r.created_at FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.comment IS NOT NULL AND TRIM(r.comment) != '' ORDER BY r.created_at DESC LIMIT 5")
        recent_reviews = [dict(review_id=r[0], username=r[1], full_name=((r[2] or '')+' '+(r[3] or '')).strip() or r[1], avatar=r[4] or '', rating=r[5], comment=r[6], created_at=r[7]) for r in cur.fetchall()]
    finally:
        cur.close()

    from public_presentation import community_display_count, homepage_review_cards
    data = {
        "total_books": BOOKS_BASE + real_books,
        "total_downloads": DOWNLOADS_BASE + real_downloads,
        "total_users": USERS_BASE + real_users,
        "monthly_users": monthly_users,
        "total_categories": total_categories,
        "total_reviews": real_reviews,
        "recent_reviews": recent_reviews,
        "community_counter": community_display_count(real_users),
        "review_cards": homepage_review_cards(recent_reviews),
    }

    cache["ts"] = now
    cache["data"] = data
    return data


def is_official_user(user_id):
    if not hasattr(g, "official_user_id"):
        g.official_user_id = get_site_setting("official_user_id")
    return bool(g.official_user_id and str(user_id) == str(g.official_user_id))


def is_moderator():
    from admin.security import is_studio_request

    return is_studio_request()


def official_admin_required(f):
    from admin.security import required

    return required(f)


def slugify(text, max_length=200):
    """SEO-friendly URL slug. 'Automate the Boring Stuff! (2nd Ed.)' -> 'automate-the-boring-stuff-2nd-ed'"""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "-", text)
    text = text.strip("-")
    return text[:max_length].rstrip("-")


def unique_slug(base_slug, cur, exclude_id=None):
    """Agar slug exist karta ho to '-2', '-3' suffix lagao."""
    if not base_slug:
        base_slug = "resource"
    slug = base_slug
    counter = 2
    while True:
        if exclude_id:
            cur.execute(
                "SELECT id FROM documents WHERE slug = %s AND id != %s",
                (slug, exclude_id),
            )
        else:
            cur.execute("SELECT id FROM documents WHERE slug = %s", (slug,))
        if not cur.fetchone():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1
        if counter > 100:
            return f"{base_slug}-{secrets.token_hex(4)}"


def studio_content_setting(key):
    cache_key = "content_" + key
    if not hasattr(g, cache_key):
        try:
            value = json.loads(get_site_setting(key, "{}") or "{}")
        except (ValueError, TypeError):
            value = {}
        setattr(g, cache_key, value if isinstance(value, dict) else {})
    return getattr(g, cache_key)


@app.context_processor
def inject_common():
    # Presentation defaults must remain renderable during an error-page response.
    # Route authorization still uses the original helpers and is not changed here.
    try:
        official = is_official_user(session.get("user_id", 0))
    except Exception:
        official = False
        app.logger.warning("Official display marker unavailable during page rendering")
    try:
        content = studio_content_setting("studio_content")
    except Exception:
        content = {}
        app.logger.warning("Custom display content unavailable during page rendering")
    return dict(
        current_user_is_official=official,
        is_moderator=False,
        site_content=content,
    )


@app.context_processor
def inject_user_logged_in():
    return dict(user_logged_in=bool(session.get("user_id")))


# ================== UTILITY FUNCTIONS ==================
def clean_title_extra(title):
    """Remove @Pdfmatrix, TechByMehdi etc."""
    title = re.sub(r"@pdfmatrix", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[-_]?TechByMehdi", "", title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip()


def extract_cover_from_pdf(pdf_bytes):
    """Generate cover image from the first page of a PDF. Returns compressed PNG bytes."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        cover_bytes = pix.tobytes("png")
        doc.close()
        return compress_image(
            BytesIO(cover_bytes).getvalue(), max_size=(400, 400), quality=75
        )
    except Exception as e:
        app.logger.error(f"Cover extraction failed: {e}")
        return None


def generate_description(title, category):
    """Return a long, professional description based on category."""
    t = title
    templates = {
        "Python": f"Unlock the power of Python with '{t}'. This comprehensive guide takes you from basic syntax to advanced concepts like OOP, data analysis with Pandas, web development with Flask/Django, and task automation. Packed with real-world examples and best practices, it's perfect for beginners and experienced coders.",
        "JavaScript": f"Master JavaScript from the ground up with '{t}'. Explore core language features, DOM manipulation, asynchronous programming, and modern frameworks like React and Node.js.",
        "Java": f"Dive deep into Java with '{t}'. Covering OOP principles, collections, multithreading, and enterprise frameworks like Spring and Hibernate.",
        "C / C++": f"Explore the world of C and C++ with '{t}'. From pointers and memory management to STL and modern C++17/20 features.",
        "Web Development": f"Build stunning, responsive websites with '{t}'. Learn HTML5, CSS3, JavaScript, and popular frameworks like Bootstrap, React, and Angular.",
        "Data Science": f"Discover the art of data science with '{t}'. Learn data wrangling, visualization, statistical modeling, and ML using Pandas, NumPy, and Scikit-learn.",
        "Machine Learning": f"Step into the future with '{t}'. From linear regression to deep neural networks, covers supervised/unsupervised learning and deployment.",
        "Algorithms": f"Sharpen your problem-solving skills with '{t}'. Detailed explanations of sorting, searching, graph algorithms, and dynamic programming.",
        "Databases": f"Master database design and SQL with '{t}'. Covers relational models, normalization, indexing, and query optimization.",
        "Cyber Security": f"Defend the digital world with '{t}'. Learn ethical hacking, penetration testing, network security, and cryptography.",
        "Mobile Apps": f"Create engaging mobile experiences with '{t}'. Covers native Android (Kotlin), iOS (Swift), and Flutter/React Native.",
        "DevOps": f"Transform your workflow with '{t}'. Learn CI/CD pipelines, Docker, Kubernetes, Terraform, and cloud services.",
        "Others": f"An in-depth resource covering '{t}'. Packed with theory, practical examples, and expert insights.",
    }
    return templates.get(
        category, f"An in-depth resource covering '{t}' in the field of {category}."
    )


def guess_category_from_text(pdf_text):
    """Guess category using keyword matching on PDF text. Returns best category or 'Others'."""
    best_category = "Others"
    best_ratio = 0.0
    for category, keywords in KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in pdf_text)
        ratio = hits / len(keywords)
        if ratio > best_ratio:
            best_ratio = ratio
            best_category = category
    if best_ratio < 0.7:
        best_category = "Others"
    return best_category


def guess_category_from_filename(filename):
    """Fallback: guess category from filename keywords."""
    name = filename.lower()
    scores = {}
    for category, keywords in KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in name)
        ratio = hits / len(keywords)
        scores[category] = ratio
    if not scores:
        return "Others"
    best_category = max(scores, key=scores.get)
    best_ratio = scores[best_category]
    if best_ratio < 0.1:
        best_category = "Others"
    return best_category


def lazy_trickle(book_id):
    """Compatibility hook: activity counters are no longer artificially increased."""
    return None


def extract_r2_key(url):
    """Resolve stored keys/known storage URLs without guessing object filenames."""
    return resolve_r2_key(url, public_base=R2_PUBLIC_BASE, bucket=R2_BUCKET,
                          endpoint_url=r2_client.meta.endpoint_url)


def get_presigned_url(key, expiration=300):
    """Generate a presigned URL for an R2 object."""
    try:
        return r2_client.generate_presigned_url(
            "get_object", Params={"Bucket": R2_BUCKET, "Key": key}, ExpiresIn=expiration
        )
    except Exception as e:
        app.logger.error(f"Presigned URL generation failed: {e}")
        return None


# ================== USER UPLOAD (R2) ==================
@app.route("/user/upload", methods=["GET", "POST"])
@limiter.limit(AUTH_RATELIMIT)
def user_upload():
    if "user_id" not in session:
        return redirect(url_for("user_login"))

    if request.method == "POST":
        if "pdf_file" not in request.files:
            msg = "No PDF file selected."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("user_upload"))
        if "pdf_file" not in request.files:
            msg = "No PDF file selected."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("user_upload"))

        file = request.files["pdf_file"]
        if file.filename == "" or not allowed_file(file.filename):
            msg = "Invalid file. Only PDF allowed."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("user_upload"))

        pdf_bytes = file.read()
        # ==== NAYA: Server-side size limit ====
        if len(pdf_bytes) > 500 * 1024 * 1024:  # 500 MB
            msg = "File too large. Maximum 500 MB allowed."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 413
            flash(msg, "danger")
            return redirect(url_for("user_upload"))

        # ==== NAYA: Magic byte content validation ====
        if not is_valid_pdf(pdf_bytes):
            msg = "Invalid PDF content. File is not a real PDF."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("user_upload"))

        reader = PdfReader(io.BytesIO(pdf_bytes))
        meta = reader.metadata
        pdf_title = (meta.title or "").strip() if meta else ""
        author_meta = (meta.author or "").strip() if meta else ""

        raw_name = (
            pdf_title
            if pdf_title and pdf_title.lower() != "unknown"
            else os.path.splitext(file.filename)[0]
        )

        clean_base = clean_professional_name(raw_name)
        display_title = clean_base.replace("_", " ").replace(" @DocoDive", "").strip()
        display_title = clean_title_extra(display_title)
        if not display_title:
            display_title = "Untitled"

        author = (
            author_meta
            if author_meta and author_meta.lower() != "unknown"
            else "Unknown"
        )
        author = author or "Unknown"

        cur = mysql.connection.cursor()
        if is_duplicate(display_title, author, cur):
            cur.close()
            msg = "This book already exists in the library."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("user_upload"))
        cur.close()

        manual_category = request.form.get("category", "").strip()
        if manual_category:
            category = manual_category
        else:
            pdf_text = ""
            try:
                fitz_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for i, page in enumerate(fitz_doc):
                    if i >= 5:
                        break
                    pdf_text += page.get_text()
                fitz_doc.close()
            except Exception:
                try:
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    for page in reader.pages[:5]:
                        extracted = page.extract_text()
                        if extracted:
                            pdf_text += extracted
                except Exception:
                    pass
            pdf_text = pdf_text.lower()
            category = (
                guess_category_from_text(pdf_text)
                if pdf_text
                else guess_category_from_filename(file.filename)
            )

        description = generate_description(display_title, category)

        try:
            pdf_key = generate_r2_key("uploads", clean_base, ".pdf")
            pdf_url = upload_to_r2(pdf_bytes, pdf_key, content_type="application/pdf")
        except Exception as e:
            app.logger.error(f"PDF upload failed: {e}")
            msg = "Failed to upload PDF."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 500
            flash(msg, "danger")
            return redirect(url_for("user_upload"))

        cover_bytes = None
        cover_extension = ".png"
        if (
            "cover_image" in request.files
            and request.files["cover_image"].filename != ""
        ):
            cover_file = request.files["cover_image"]
            if not allowed_image_file(cover_file.filename):
                msg = "Invalid cover image format."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("user_upload"))

            cover_bytes = cover_file.read()
            # Original size check (compress se pehle — memory bachao)
            if len(cover_bytes) > 10 * 1024 * 1024:  # 10 MB raw limit
                msg = "Cover image too large. Maximum 10 MB allowed."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("user_upload"))

            # Magic byte content validation
            if not is_valid_image(cover_bytes):
                msg = (
                    "Invalid cover image content. Only JPEG, PNG, GIF, or WebP allowed."
                )
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("user_upload"))

            # Ab compress karo (valid image confirmed hai)
            cover_bytes = compress_image(cover_bytes, max_size=(400, 400), quality=75)

            # Compressed size check (final)
            if len(cover_bytes) > 2 * 1024 * 1024:
                msg = "Cover image must be less than 2 MB."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("user_upload"))
                return redirect(url_for("user_upload"))
            cover_extension = os.path.splitext(cover_file.filename)[1].lower()
        else:
            cover_bytes = extract_cover_from_pdf(pdf_bytes)
            if not cover_bytes:
                msg = "Could not generate cover from PDF. Please upload a cover image manually."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("user_upload"))

        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime = mime_map.get(cover_extension, "application/octet-stream")
        try:
            cover_key = generate_r2_key("covers", clean_base, cover_extension)
            image_url = upload_to_r2(cover_bytes, cover_key, content_type=mime)
        except Exception as e:
            app.logger.error(f"Cover upload failed: {e}")
            msg = "Failed to upload cover image."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 500
            flash(msg, "danger")
            return redirect(url_for("user_upload"))

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM categories WHERE level = %s", (category,))
        cat = cur.fetchone()
        if not cat:
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (category,))
            cat_id = cur.lastrowid
        else:
            cat_id = cat[0]

        dl_count = random.randint(1000, 3000)
        vw_count = random.randint(2000, 5000)

        new_slug = unique_slug(slugify(display_title), cur)
        cur.execute(
            """
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, slug, approved, uploaded_by, download_count, view_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """,
            (
                cat_id,
                display_title,
                pdf_url,
                author,
                description,
                image_url,
                "English",
                new_slug,
                session["user_id"],
                dl_count,
                vw_count,
            ),
        )
        mysql.connection.commit()
        cur.close()

        award_points(session["user_id"], 10, action="upload")

        html_notification = make_upload_notification_email(
            display_title, author, category
        )
        send_email_notification(
            "New PDF Uploaded by User - Pending Approval",
            app.config["ADMIN_NOTIFICATION_EMAIL"],
            f"A new book '{display_title}' by {author} has been uploaded by a user and is waiting for approval.",
            html_body=html_notification,
        )

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                {
                    "success": True,
                    "message": f"✅ '{display_title}' uploaded successfully! It will appear after admin approval.",
                }
            )

        flash(
            f"✅ '{display_title}' uploaded successfully! It will appear after admin approval.",
            "success",
        )
        return redirect(url_for("user_upload"))

    cur = mysql.connection.cursor()
    cur.execute("SELECT level FROM categories ORDER BY level")
    categories = [row[0] for row in cur.fetchall()]
    cur.close()
    return render_template("user/user_upload.html", categories=categories)


@app.route("/api/user/uploads")
def user_uploads():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, title, author, status, created_at FROM documents WHERE uploaded_by = %s ORDER BY created_at DESC",
        (user_id,),
    )
    books = cur.fetchall()
    cur.close()
    return jsonify(
        [
            {
                "id": b[0],
                "title": b[1],
                "author": b[2],
                "status": b[3],
                "created_at": str(b[4]),
            }
            for b in books
        ]
    )


@app.route("/api/user/pending-uploads")
def user_pending_uploads():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, title, author, created_at FROM documents WHERE uploaded_by = %s AND approved = 0 ORDER BY created_at DESC",
        (user_id,),
    )
    books = cur.fetchall()
    cur.close()
    return jsonify(
        [
            {"id": b[0], "title": b[1], "author": b[2], "created_at": str(b[3])}
            for b in books
        ]
    )


def _username_quality_issue(username):
    u = username.lower()

    if u.isdigit():
        return "Username should not contain only numbers. Mix letters with your name."

    if len(set(u)) <= 2:
        return "Username is too repetitive. Try something more personal."

    weak_usernames = [
        "qwerty",
        "asdf",
        "zxcv",
        "abcdef",
        "123456",
        "password",
        "admin",
        "administrator",
        "moderator",
        "official",
        "support",
        "test",
        "user",
        "login",
        "guest",
        "unknown",
        "abc",
        "root",
        "owner",
        "staff",
    ]
    for w in weak_usernames:
        if w in u:
            return "This username is too common or not allowed."

    return None


def _contains_reserved_word(username):
    u = username.lower()
    u = (
        u.replace("0", "o")
        .replace("1", "i")
        .replace("3", "e")
        .replace("4", "a")
        .replace("5", "s")
        .replace("7", "t")
        .replace("$", "s")
        .replace("@", "a")
    )
    u = re.sub(r"[\s_.\-]+", "", u)

    reserved = os.getenv("RESERVED_USERNAMES", "")
    if not reserved:
        return False

    reserved_list = [r.strip().lower() for r in reserved.split(",") if r.strip()]

    for word in reserved_list:
        if (
            u == word
            or u.startswith(word + "official")
            or u.startswith(word + "account")
            or word in u
        ):
            return True

    return False


# -------------------- USERNAME SUGGESTIONS --------------------
def _generate_username_suggestions(value, first_name, last_name):
    def clean(s):
        return re.sub(r"[^a-zA-Z0-9]", "", s or "").lower()

    first = clean(first_name)
    last = clean(last_name)
    entered = clean(value)

    candidates = []

    def add(c):
        if not c:
            return
        c = c[:20].lower()
        if len(c) < 3:
            return
        if not re.fullmatch(r"[a-z][a-z0-9]{2,19}", c):
            return
        if c not in candidates:
            candidates.append(c)

    # ---------- 1. Full name based (meaningful) ----------
    if first and last:
        add(first + last)  # sufyankhan
        add(last + first)  # khansufyan
        add(first + last[0])  # sufyank
    elif first:
        add(first)
    elif last:
        add(last)

    # ---------- 2. Entered username ke saath mix ----------
    if entered:
        add(entered)
        if first and entered != first:
            add(first + entered)
            add(entered + first)
        if last and entered != last:
            add(last + entered)
            add(entered + last)

    # ---------- 3. Numbers sirf backup ----------
    base_candidates = list(candidates)
    for base in base_candidates[:10]:
        for n in range(1, 10):
            add(base + str(n))

    # ---------- 4. Reserved/taken hatao ----------
    available = []
    cur = mysql.connection.cursor()
    try:
        for c in candidates:
            if _contains_reserved_word(c):
                continue
            cur.execute("SELECT id FROM users WHERE username = %s", (c,))
            if cur.fetchone() is None:
                available.append(c)
            if len(available) >= 6:
                break
    except Exception:
        pass
    finally:
        cur.close()

    return available


# -------------------- API: CHECK USERNAME/EMAIL AVAILABILITY --------------------
@app.route("/api/check-availability")
def check_availability():
    field = request.args.get("field", "")
    value = request.args.get("value", "").strip()
    first_name = request.args.get("first_name", "").strip()
    last_name = request.args.get("last_name", "").strip()

    if not field or not value:
        return jsonify({"error": "Invalid request"}), 400

    if field == "username":
        # ---------- Format check ----------
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,19}", value):
            return jsonify(
                {
                    "exists": False,
                    "reserved": False,
                    "format_error": True,
                    "message": "Username must start with a letter and be 3-20 letters/numbers only.",
                }
            )

        # ---------- Reserved words ----------
        if _contains_reserved_word(value):
            return jsonify(
                {
                    "exists": True,
                    "reserved": True,
                    "message": "This username is not allowed. Please choose a different one.",
                }
            )

        # ---------- Quality check ----------
        quality = _username_quality_issue(value)
        if quality:
            return jsonify(
                {
                    "exists": False,
                    "reserved": False,
                    "simple": True,
                    "message": quality,
                    "suggestions": _generate_username_suggestions(
                        value, first_name, last_name
                    ),
                }
            )

        # ---------- DB existence ----------
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (value,))
        exists = cur.fetchone() is not None
        cur.close()

        suggestions = []
        if exists:
            suggestions = _generate_username_suggestions(value, first_name, last_name)

        return jsonify(
            {
                "exists": exists,
                "reserved": False,
                "message": (
                    "Username already taken. Try a different one."
                    if exists
                    else "Username is available!"
                ),
                "suggestions": suggestions,
            }
        )

    elif field == "email":
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (value,))
        exists = cur.fetchone() is not None
        cur.close()
        return jsonify(
            {
                "exists": exists,
                "message": (
                    "Email already registered." if exists else "Email is available!"
                ),
            }
        )

    return jsonify({"error": "Invalid field"}), 400


# -------------------- FORGOT PASSWORD (AJAX) --------------------
@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit(AUTH_RATELIMIT)
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Please enter your email."}), 400
            flash("Please enter your email.", "danger")
            return redirect(url_for("forgot_password"))

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        if not user:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "No account found with that email."}), 404
            flash("No account found with that email.", "danger")
            return redirect(url_for("forgot_password"))

        code = f"{random.randint(1000, 9999)}"
        expires = datetime.now() + timedelta(minutes=10)
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM password_resets WHERE email = %s", (email,))
        cur.execute(
            "INSERT INTO password_resets (email, code, expires_at) VALUES (%s, %s, %s)",
            (email, code, expires),
        )
        mysql.connection.commit()
        cur.close()

        html_body = make_code_email(code)
        send_email_notification(
            "Password Reset Code - DocoDive",
            email,
            f"Your DocoDive password reset code is {code}. It expires in 10 minutes. Do not share it.",
            html_body=html_body,
        )

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                {"success": True, "message": "Verification code sent to your email."}
            )
        flash("A verification code has been sent to your email.", "success")
        return redirect(url_for("verify_code", email=email))

    return render_template("user/forgot_password.html")


@app.route("/verify-code", methods=["GET", "POST"])
@limiter.limit(AUTH_RATELIMIT)
def verify_code():
    if request.method == "GET":
        email = request.args.get("email", "").strip()
        if not email or len(email) > 254 or "@" not in email:
            return redirect(url_for("forgot_password"))
        return render_template("user/verify_code.html", email=email)

    email = request.form.get("email", "").strip()
    code = request.form.get("code", "").strip()

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, email, code, expires_at FROM password_resets WHERE email = %s AND code = %s",
        (email, code),
    )
    row = cur.fetchone()
    if not row or row[3] < datetime.now():
        cur.close()
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return render_template("user/verify_code.html", email=email, error="This code is invalid or has expired. Request a new code if needed."), 400
        return jsonify({"error": "Invalid or expired code."}), 400

    token = secrets.token_urlsafe(32)
    new_expires = datetime.now() + timedelta(minutes=30)
    cur.execute(
        "UPDATE password_resets SET token = %s, code = NULL, expires_at = %s WHERE id = %s",
        (token, new_expires, row[0]),
    )
    mysql.connection.commit()
    cur.close()

    reset_link = url_for("reset_password", token=token, _external=True)
    html_body = make_reset_link_email(reset_link)
    delivered = send_email_notification(
        "Reset Your Password - DocoDive",
        email,
        f"Use this link to reset your DocoDive password (valid for 30 minutes): {reset_link}",
        html_body=html_body,
    )
    if not delivered:
        message = "The reset email could not be delivered. Please request a new recovery code and try again."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": message}), 503
        return render_template("user/verify_code.html", email=email, error=message), 503
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return render_template("user/password_recovery_sent.html")
    return jsonify(
        {
            "success": True,
            "message": "A password reset link has been sent to your email.",
        }
    )


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit(AUTH_RATELIMIT)
def reset_password(token):
    from studio_auth import AuthError

    settings = app.extensions["reader_settings"]
    if not settings.reset_available(token):
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        try:
            settings.reset_password(token, request.form.get("password", ""), request.form.get("confirm_password", ""))
        except AuthError as error:
            flash(str(error), "danger")
            return render_template("user/reset_password.html", token=token), error.status
        session.clear()
        flash("Password updated. All sessions have been signed out. Please sign in.", "success")
        return redirect(url_for("user_login"))
    return render_template("user/reset_password.html", token=token)


# -------------------- BREVO WEBHOOK --------------------
@app.route("/api/brevo/webhook", methods=["POST"])
def brevo_webhook():
    secret = os.getenv("BREVO_WEBHOOK_SECRET")
    if not secret:
        return "", 503
    signature = request.headers.get("X-Webhook-Secret")
    if not signature or not hmac.compare_digest(signature, secret):
        return "", 403
    data = request.get_json()
    if not data:
        return "", 400
    app.logger.info("Brevo webhook event: %s", json.dumps(data))
    return jsonify({"status": "received"}), 200


# ==================== SOCIAL LOGIN ROUTES ====================
@app.route("/login/google")
@limiter.limit(AUTH_RATELIMIT)
def google_login():
    redirect_uri = url_for("google_callback", _external=True)
    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    return oauth.google.authorize_redirect(redirect_uri, state=state)


@app.route("/auth/google/callback")
def google_callback():
    expected_state = session.pop("google_oauth_state", None)
    returned_state = request.args.get("state", "")
    if not expected_state or not hmac.compare_digest(expected_state, returned_state):
        flash("Login session expired. Please sign in again.", "danger")
        return redirect(url_for("user_login"))
    code = request.args.get("code")
    if not code:
        flash("Missing authorization code.", "danger")
        return redirect(url_for("user_login"))
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": url_for("google_callback", _external=True),
        "grant_type": "authorization_code",
    }
    try:
        token_resp = requests.post(token_url, data=payload, timeout=10)
        token_data = token_resp.json()
    except Exception:
        flash("Login failed. Please try again.", "danger")
        return redirect(url_for("user_login"))
    if "access_token" not in token_data:
        flash("Could not authenticate with Google.", "danger")
        return redirect(url_for("user_login"))
    access_token = token_data["access_token"]
    try:
        user_resp = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        user_info = user_resp.json()
    except Exception:
        flash("Could not retrieve your Google profile.", "danger")
        return redirect(url_for("user_login"))
    user_info["sub"] = user_info.get("id") or user_info.get("sub")
    user_info["picture"] = user_info.get("picture")
    user_info["email"] = user_info.get("email")
    user_info["email_verified"] = user_info.get("verified_email") is True
    user_info["name"] = user_info.get("name")

    uid, is_new = handle_social_login("google", user_info)
    if uid:
        setup_session(uid)
        if is_new:
            try:
                html_body = make_welcome_email(user_info.get("name", "User"), "Google")
                send_email_notification(
                    "Welcome to DocoDive! 🚀",
                    user_info["email"],
                    f"Hi {user_info.get('name', 'User')}, your account has been created via Google.",
                    html_body=html_body,
                )
            except Exception:
                pass
            flash("Account verified! Welcome to DocoDive 🤝", "success")
        else:
            flash("Logged in successfully!", "success")
        return redirect(url_for("home"))
    flash("Google login failed.", "danger")
    return redirect(url_for("user_login"))


@app.route("/login/github")
@limiter.limit(AUTH_RATELIMIT)
def github_login():
    redirect_uri = url_for("github_callback", _external=True)
    return oauth.github.authorize_redirect(redirect_uri)


@app.route("/auth/github/callback")
def github_callback():
    token = oauth.github.authorize_access_token()
    resp = oauth.github.get("user")
    user_info = resp.json()
    try:
        emails_resp = oauth.github.get("user/emails")
        emails = emails_resp.json()
    except Exception:
        emails = []
    if not isinstance(emails, list):
        emails = []
    primary = next(
        (
            e["email"]
            for e in emails
            if isinstance(e, dict)
            and e.get("primary") is True
            and e.get("verified") is True
            and isinstance(e.get("email"), str)
            and e["email"]
        ),
        None,
    )
    user_info["email"] = primary
    user_info["email_verified"] = primary is not None
    user_info["sub"] = str(user_info["id"])
    user_info["name"] = user_info.get("name") or user_info["login"]
    user_info["picture"] = user_info.get("avatar_url")
    uid, is_new = handle_social_login("github", user_info)
    if uid:
        setup_session(uid)
        if is_new:
            try:
                html_body = make_welcome_email(user_info.get("name", "User"), "GitHub")
                send_email_notification(
                    "Welcome to DocoDive! 🚀",
                    user_info["email"],
                    f"Hi {user_info.get('name', 'User')}, your account has been created via GitHub.",
                    html_body=html_body,
                )
            except Exception:
                pass
            flash("Account verified! Welcome to DocoDive 🤝", "success")
        else:
            flash("Logged in successfully!", "success")
        return redirect(url_for("home"))
    flash("GitHub login failed.", "danger")
    return redirect(url_for("user_login"))


@app.route("/login/facebook")
@limiter.limit(AUTH_RATELIMIT)
def facebook_login():
    redirect_uri = url_for("facebook_callback", _external=True)
    return oauth.facebook.authorize_redirect(redirect_uri)


@app.route("/auth/facebook/callback")
def facebook_callback():
    token = oauth.facebook.authorize_access_token()
    resp = oauth.facebook.get("me?fields=id,name,email,picture")
    user_info = resp.json()
    user_info["sub"] = user_info["id"]
    user_info["picture"] = user_info.get("picture", {}).get("data", {}).get("url")
    uid, is_new = handle_social_login("facebook", user_info)
    if uid:
        setup_session(uid)
        if is_new:
            try:
                html_body = make_welcome_email(
                    user_info.get("name", "User"), "Facebook"
                )
                send_email_notification(
                    "Welcome to DocoDive! 🚀",
                    user_info["email"],
                    f"Hi {user_info.get('name', 'User')}, your account has been created via Facebook.",
                    html_body=html_body,
                )
            except Exception:
                pass
            flash("Account verified! Welcome to DocoDive 🤝", "success")
        else:
            flash("Logged in successfully!", "success")
        return redirect(url_for("home"))
    flash("Facebook login failed.", "danger")
    return redirect(url_for("user_login"))


@app.route("/facebook/data-deletion", methods=["POST"])
def facebook_data_deletion():
    signed_request = request.form.get("signed_request")
    if not signed_request:
        return jsonify({"error": "Missing signed request"}), 400
    secret = app.config["FACEBOOK_APP_SECRET"]
    try:
        sig, payload = signed_request.split(".", 1)
        expected_sig = (
            base64.urlsafe_b64encode(
                hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        if not hmac.compare_digest(sig, expected_sig):
            return jsonify({"error": "Invalid signature"}), 403
        data = json.loads(base64.urlsafe_b64decode(payload + "==").decode())
        user_id = data.get("user_id")
        confirmation_code = "abc123"
        return jsonify(
            {
                "url": f"{request.host_url}data-deletion?code={confirmation_code}",
                "confirmation_code": confirmation_code,
            }
        )
    except Exception as e:
        app.logger.error(f"Data deletion request failed: {e}", exc_info=True)
        return jsonify({"error": "Invalid request. Please try again."}), 400


# ================== ERROR HANDLERS ==================
@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    return jsonify({"error": "File size too large. Maximum 500 MB allowed."}), 413


@app.errorhandler(400)
def bad_request(e):
    return render_template("user/400.html"), 400


@app.errorhandler(401)
def unauthorized(e):
    return render_template("user/401.html"), 401


@app.errorhandler(403)
def forbidden(e):
    return render_template("user/403.html"), 403


@app.errorhandler(404)
def not_found(e):
    trending_books = []
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link,
                   COALESCE(d.download_count, 0) as download_count,
                   COALESCE(d.view_count, 0) as view_count,
                   d.slug
            FROM documents d
            JOIN categories c ON d.category_id = c.id
            WHERE d.approved = 1
            ORDER BY d.download_count DESC
            LIMIT 6
        """)
        rows = cur.fetchall()
        cur.close()
        for r in rows:
            trending_books.append(
                {
                    "id": r[0],
                    "title": r[1],
                    "author": r[2],
                    "level": r[3],
                    "image_url": r[4],
                    "link": r[5],
                    "download_count": r[6] or 0,
                    "view_count": r[7] or 0,
                    "slug": r[8],
                }
            )
    except Exception as e:
        app.logger.error(f"404 trending fetch failed: {e}")

    return render_template("user/404.html", trending_books=trending_books), 404


@app.errorhandler(429)
def too_many_requests(e):
    return render_template("user/429.html"), 429


@app.errorhandler(500)
def internal_error(e):
    return render_template("user/500.html"), 500


@app.errorhandler(503)
def service_unavailable(e):
    return render_template("user/503.html"), 503


# Learning data lives in a configuration-free module.
from learning_content import (
    ALGORITHMS_ADVANCED_LESSONS,
    ALGORITHMS_BEGINNER_LESSONS,
    ALGORITHMS_INTERMEDIATE_LESSONS,
    ALGORITHMS_PRACTICE,
    CPP_BEGINNER_LESSONS,
    CPP_INTERMEDIATE_LESSONS,
    CYBERSECURITY_ADVANCED_LESSONS,
    CYBERSECURITY_BEGINNER_LESSONS,
    CYBERSECURITY_INTERMEDIATE_LESSONS,
    CYBERSECURITY_PRACTICE,
    C_BEGINNER_LESSONS,
    C_CPP_ADVANCED_LESSONS,
    C_CPP_PRACTICE,
    C_INTERMEDIATE_LESSONS,
    DATABASES_ADVANCED_LESSONS,
    DATABASES_BEGINNER_LESSONS,
    DATABASES_INTERMEDIATE_LESSONS,
    DATABASES_PRACTICE,
    DATA_SCIENCE_ADVANCED_LESSONS,
    DATA_SCIENCE_BEGINNER_LESSONS,
    DATA_SCIENCE_INTERMEDIATE_LESSONS,
    DATA_SCIENCE_PRACTICE,
    GENERIC_MODULES,
    IELTS_LISTENING_LESSONS,
    IELTS_MODULES,
    IELTS_READING_LESSONS,
    IELTS_SPEAKING_BAND_GUIDE,
    IELTS_SPEAKING_LESSONS,
    IELTS_SPEAKING_MISTAKES,
    IELTS_SPEAKING_PRACTICE,
    IELTS_SPEAKING_TIPS,
    IELTS_TASK2_PRACTICE,
    IELTS_WRITING_LESSONS,
    IELTS_WRITING_LESSONS_TASK1,
    IELTS_WRITING_LESSONS_TASK2,
    IELTS_WRITING_PRACTICE,
    IELTS_WRITING_PRACTICE_P2,
    IELTS_WRITING_PRACTICE_P3,
    IELTS_WRITING_PRACTICE_P4,
    IELTS_WRITING_PRACTICE_P5,
    JAVASCRIPT_ADVANCED_LESSONS,
    JAVASCRIPT_BEGINNER_LESSONS,
    JAVASCRIPT_INTERMEDIATE_LESSONS,
    JAVASCRIPT_PRACTICE,
    JAVA_ADVANCED_LESSONS,
    JAVA_BEGINNER_LESSONS,
    JAVA_INTERMEDIATE_LESSONS,
    JAVA_PRACTICE,
    ML_ADVANCED_LESSONS,
    ML_BEGINNER_LESSONS,
    ML_INTERMEDIATE_LESSONS,
    ML_PRACTICE,
    MOBILE_APPS_ADVANCED_LESSONS,
    MOBILE_APPS_BEGINNER_LESSONS,
    MOBILE_APPS_CAPSTONE,
    MOBILE_APPS_DEBUGGING_CHALLENGES,
    MOBILE_APPS_INTERMEDIATE_LESSONS,
    MOBILE_APPS_PRACTICE_CHALLENGES,
    MOBILE_APPS_PRACTICE_PROJECTS,
    PYTHON_ADVANCED_LESSONS,
    PYTHON_BEGINNER_LESSONS,
    PYTHON_INTERMEDIATE_LESSONS,
    PYTHON_PRACTICE,
    PYTHON_PROJECTS,
    WEB_DEV_ADVANCED_LESSONS,
    WEB_DEV_BEGINNER_LESSONS,
    WEB_DEV_INTERMEDIATE_LESSONS,
    WEB_DEV_PRACTICE,
)


def category_to_slug(category):
    slug = category.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def ensure_default_categories():
    """Ensure all default categories exist in DB (idempotent)."""
    defaults = [
        "Python",
        "JavaScript",
        "Java",
        "C / C++",
        "Web Development",
        "Data Science",
        "Machine Learning",
        "Algorithms",
        "Databases",
        "Cyber Security",
        "Mobile Apps",
        "DevOps",
        "Others",
        "IELTS",
    ]
    cur = mysql.connection.cursor()
    cur.execute("SELECT level FROM categories")
    existing = {row[0] for row in cur.fetchall()}
    missing = [cat for cat in defaults if cat not in existing]
    for cat in missing:
        cur.execute("INSERT INTO categories (level) VALUES (%s)", (cat,))
    if missing:
        mysql.connection.commit()
    cur.close()


def slug_to_category_name(slug, cursor):
    cursor.execute("SELECT level FROM categories ORDER BY level")
    rows = cursor.fetchall()
    for (level,) in rows:
        if category_to_slug(level) == slug:
            return level
    return None


app.jinja_env.filters["slugify"] = category_to_slug


# ================== PUBLIC ROUTES (Home) ==================
@app.route("/")
def home():
    search_query = request.args.get("search_query", "").strip()
    category = request.args.get("category", "").strip()
    author_filter = request.args.get("author", "").strip()
    lang_filter = request.args.get("language", "").strip()

    # ---------- Input length validation (reject, not truncate) ----------
    if len(search_query) > 200:
        abort(400)
    if len(category) > 100:
        abort(400)
    if len(author_filter) > 100:
        abort(400)
    if len(lang_filter) > 50:
        abort(400)

    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(50, request.args.get("per_page", 12, type=int)))
    if per_page < 1:
        per_page = 12
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()
    conditions = ["d.approved = 1", "COALESCE(d.resource_type, 'pdf') = 'pdf'"]
    params = []
    if search_query:
        conditions.append("(d.title LIKE %s OR d.author LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    if category:
        conditions.append("c.level = %s")
        params.append(category)
    if author_filter:
        conditions.append("d.author LIKE %s")
        params.append(f"%{author_filter}%")
    if lang_filter:
        conditions.append("d.language = %s")
        params.append(lang_filter)
    where_clause = " AND ".join(conditions)

    count_query = f"SELECT COUNT(*) FROM documents d JOIN categories c ON d.category_id = c.id WHERE {where_clause}"
    cur.execute(count_query, params)
    total_books = cur.fetchone()[0]
    total_pages = max(1, (total_books + per_page - 1) // per_page)

    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    books_query = f"""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language,
               COALESCE(d.download_count, 0) as download_count,
               COALESCE(d.view_count, 0) as view_count,
               COALESCE(avg_r.avg_rating, 0) as avg_rating,
               d.slug
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        LEFT JOIN (
            SELECT book_id, AVG(rating) as avg_rating FROM reviews GROUP BY book_id
        ) avg_r ON d.id = avg_r.book_id
        WHERE {where_clause} ORDER BY d.id DESC LIMIT %s OFFSET %s
    """
    cur.execute(books_query, params + [per_page, offset])
    books_data = cur.fetchall()

    cur.execute("""
        SELECT c.id, c.level, COUNT(d.id) AS total
        FROM categories c LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1 AND COALESCE(d.resource_type, 'pdf') = 'pdf'
        GROUP BY c.id ORDER BY c.id
    """)
    cat_data = cur.fetchall()
    cur.close()

    real_pdfs = [
        {
            "id": r[0],
            "title": r[1],
            "level": r[2],
            "link": r[3],
            "author": r[4],
            "description": r[5],
            "image_url": r[6],
            "language": r[7],
            "download_count": r[8] or 0,
            "view_count": r[9] or 0,
            "avg_rating": round(float(r[10]), 1) if r[10] else 0,
            "slug": r[11],
        }
        for r in books_data
    ]
    categories = [{"id": r[0], "level": r[1], "count": r[2]} for r in cat_data]

    home_stats = get_home_stats()

    featured_book = get_book_of_the_day()

    streak = longest = 0
    user_downloads = user_favorites = user_reviews = 0
    if "user_id" in session:
        uid = session["user_id"]
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT streak_count, longest_streak FROM user_streaks WHERE user_id = %s",
                (uid,),
            )
            row = cur.fetchone()
            if row:
                streak, longest = row
            cur.execute(
                "SELECT COUNT(*) FROM download_history WHERE user_id = %s", (uid,)
            )
            user_downloads = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id = %s", (uid,))
            user_favorites = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM reviews WHERE user_id = %s", (uid,))
            user_reviews = cur.fetchone()[0] or 0
        finally:
            cur.close()

    recommended_books = []
    if "user_id" in session:
        uid = session["user_id"]
        cur = mysql.connection.cursor()
        cur.execute(
            """
            SELECT DISTINCT d.category_id FROM favorites f
            JOIN documents d ON f.book_id = d.id WHERE f.user_id = %s
            UNION
            SELECT DISTINCT d.category_id FROM download_history h
            JOIN documents d ON h.book_id = d.id WHERE h.user_id = %s
        """,
            (uid, uid),
        )
        cat_ids = [row[0] for row in cur.fetchall()]
        if cat_ids:
            placeholders = ",".join(["%s"] * len(cat_ids))
            cur.execute(
                f"""
                SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link,
                       COALESCE(d.download_count, 0) as download_count,
                       COALESCE(d.view_count, 0) as view_count,
                       COALESCE(avg_r.avg_rating, 0) as avg_rating,
                       d.slug
                FROM documents d
                JOIN categories c ON d.category_id = c.id
                LEFT JOIN (
                    SELECT book_id, AVG(rating) as avg_rating FROM reviews GROUP BY book_id
                ) avg_r ON d.id = avg_r.book_id
                WHERE d.approved = 1 AND d.category_id IN ({placeholders})
                ORDER BY d.created_at DESC LIMIT 10
            """,
                cat_ids,
            )
            rec_rows = cur.fetchall()
            for r in rec_rows:
                recommended_books.append(
                    {
                        "id": r[0],
                        "title": r[1],
                        "author": r[2],
                        "level": r[3],
                        "image_url": r[4],
                        "link": r[5],
                        "download_count": r[6] or 0,
                        "view_count": r[7] or 0,
                        "avg_rating": round(float(r[8]), 1) if r[8] else 0,
                        "slug": r[9],
                    }
                )
        cur.close()

    return render_template(
        "user/index.html",
        pdfs=real_pdfs,
        search_query=search_query,
        category=category,
        author_filter=author_filter,
        lang_filter=lang_filter,
        categories=categories,
        page=page,
        total_pages=total_pages,
        featured_book=featured_book,
        streak=streak,
        longest=longest,
        recommended_books=recommended_books,
        total_books=home_stats["total_books"],
        total_downloads=home_stats["total_downloads"],
        total_users=home_stats["total_users"],
        monthly_users=home_stats["monthly_users"],
        total_categories=home_stats["total_categories"],
        recent_reviews=home_stats["recent_reviews"],
        community_counter=home_stats["community_counter"],
        review_cards=home_stats["review_cards"],
        total_reviews=home_stats["total_reviews"],
        user_downloads=user_downloads,
        user_favorites=user_favorites,
        user_reviews=user_reviews,
    )


# ================== LEARNING HUBS (Category Pages) ==================
@app.route("/learn/<category_slug>")
def learning_hub(category_slug):
    ensure_default_categories()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 24
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()
    category_name = slug_to_category_name(category_slug, cur)

    if category_name is None:
        cur.close()
        abort(404)

    cur.execute(
        """
        SELECT COUNT(*)
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE c.level = %s AND d.approved = 1
    """,
        (category_name,),
    )
    total_books = cur.fetchone()[0]

    total_pages = max(1, (total_books + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    cur.execute(
        """
        SELECT d.id, d.title, d.author, d.image_url, d.telegram_link,
               COALESCE(d.download_count, 0) AS download_count,
               COALESCE(d.view_count, 0) AS view_count,
               c.level,
               COALESCE(avg_r.avg_rating, 0) AS avg_rating,
               d.slug
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        LEFT JOIN (
            SELECT book_id, AVG(rating) AS avg_rating
            FROM reviews
            GROUP BY book_id
        ) avg_r ON d.id = avg_r.book_id
        WHERE c.level = %s AND d.approved = 1
        ORDER BY d.download_count DESC
        LIMIT %s OFFSET %s
    """,
        (category_name, per_page, offset),
    )
    rows = cur.fetchall()

    cur.execute(
        """
        SELECT COALESCE(SUM(d.download_count), 0)
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE c.level = %s AND d.approved = 1
    """,
        (category_name,),
    )
    total_downloads = cur.fetchone()[0]

    cur.execute("""
        SELECT c.level, COUNT(d.id) AS total
        FROM categories c
        LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1 AND COALESCE(d.resource_type, 'pdf') = 'pdf'
        GROUP BY c.id, c.level
        HAVING total > 0
        ORDER BY total DESC
    """)
    all_categories = [
        {"level": r[0], "count": r[1], "slug": category_to_slug(r[0])}
        for r in cur.fetchall()
    ]
    cur.close()

    books = [
        {
            "id": r[0],
            "title": r[1],
            "author": r[2],
            "image_url": r[3],
            "link": r[4],
            "download_count": r[5] or 0,
            "view_count": r[6] or 0,
            "level": r[7],
            "avg_rating": round(float(r[8]), 1) if r[8] else 0,
            "slug": r[9],
        }
        for r in rows
    ]

    hub_content = studio_content_setting("studio_learning").get(category_slug, {})
    if not isinstance(hub_content, dict):
        hub_content = {}
    overrides = hub_content.get("modules", {})
    modules = []
    for original in (IELTS_MODULES if category_name == "IELTS" else GENERIC_MODULES):
        module = dict(original)
        custom = (
            overrides.get(module["slug"], {}) if isinstance(overrides, dict) else {}
        )
        for field in ("title", "desc"):
            if (
                isinstance(custom, dict)
                and isinstance(custom.get(field), str)
                and custom[field].strip()
            ):
                module[field] = custom[field]
        modules.append(module)

    return render_template(
        "user/learning_hub.html",
        category=category_name,
        category_slug=category_slug,
        books=books,
        total_books=total_books,
        total_downloads=total_downloads,
        page=page,
        total_pages=total_pages,
        all_categories=all_categories,
        category_modules=modules,
        hub_content=hub_content,
    )


@app.route("/learn/python/practice")
def python_practice():
    return render_template(
        "user/python/practice.html",
        category="Python",
        category_slug="python",
        info=next(module for module in GENERIC_MODULES if module["slug"] == "practice"),
        lessons=None,
        practice_items=PYTHON_PRACTICE,
        practice_projects=PYTHON_PROJECTS,
    )


# ================== ALL BOOKS (Browse Everything) ==================
@app.route("/books")
@limiter.limit(PUBLIC_RATELIMIT)
def all_books():
    ensure_default_categories()

    q = request.args.get("q", "").strip()
    category_slug = request.args.get("category", "").strip()
    sort = request.args.get("sort", "latest").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 24

    # Input validation
    if len(q) > 200:
        abort(400)
    if len(category_slug) > 100:
        abort(400)

    cur = mysql.connection.cursor()
    try:
        # Resolve category slug -> level (invalid slug = sab books, 404 nahi)
        category_name = (
            slug_to_category_name(category_slug, cur) if category_slug else None
        )
        if category_name:
            category_slug = category_to_slug(category_name)
        else:
            category_slug = ""

        # --- Dynamic WHERE (parameterized, koi user input interpolation nahi) ---
        where_parts = ["d.approved = 1", "COALESCE(d.resource_type, 'pdf') = 'pdf'"]
        params = []

        if q:
            like = f"%{q}%"
            where_parts.append(
                "(d.title LIKE %s OR d.author LIKE %s OR d.description LIKE %s)"
            )
            params.extend([like, like, like])

        if category_name:
            where_parts.append("c.level = %s")
            params.append(category_name)

        where_clause = " AND ".join(where_parts)

        # --- Sort whitelist (invalid -> latest) ---
        sort_map = {
            "latest": "d.created_at DESC",
            "downloads": "d.download_count DESC",
            "views": "d.view_count DESC",
            "rating": "avg_r.avg_rating DESC",
        }
        order_clause = sort_map.get(sort, "d.created_at DESC")

        # --- Total count ---
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM documents d
            JOIN categories c ON d.category_id = c.id
            LEFT JOIN (
                SELECT book_id, AVG(rating) AS avg_rating FROM reviews GROUP BY book_id
            ) avg_r ON d.id = avg_r.book_id
            WHERE {where_clause}
            """,
            tuple(params),
        )
        total_books = cur.fetchone()[0]

        total_pages = max(1, (total_books + per_page - 1) // per_page)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * per_page

        # --- Books fetch ---
        cur.execute(
            f"""
            SELECT d.id, d.title, d.author, d.image_url, d.telegram_link,
                   COALESCE(d.download_count, 0) AS download_count,
                   COALESCE(d.view_count, 0) AS view_count,
                   c.level,
                   COALESCE(avg_r.avg_rating, 0) AS avg_rating,
                   d.slug
            FROM documents d
            JOIN categories c ON d.category_id = c.id
            LEFT JOIN (
                SELECT book_id, AVG(rating) AS avg_rating
                FROM reviews
                GROUP BY book_id
            ) avg_r ON d.id = avg_r.book_id
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
            """,
            tuple(params) + (per_page, offset),
        )
        rows = cur.fetchall()

        # --- Categories with counts (learning_hub jaisa exact) ---
        cur.execute("""
            SELECT c.level, COUNT(d.id) AS total
            FROM categories c
            LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1
            GROUP BY c.id, c.level
            HAVING total > 0
            ORDER BY total DESC
        """)
        all_categories = [
            {"level": r[0], "count": r[1], "slug": category_to_slug(r[0])}
            for r in cur.fetchall()
        ]
    finally:
        cur.close()

    books = [
        {
            "id": r[0],
            "title": r[1],
            "author": r[2],
            "image_url": r[3],
            "link": r[4],
            "download_count": r[5] or 0,
            "view_count": r[6] or 0,
            "level": r[7],
            "avg_rating": round(float(r[8]), 1) if r[8] else 0,
            "slug": r[9],
        }
        for r in rows
    ]

    books_jsonld = [
        {
            "@type": "ListItem",
            "position": i,
            "url": f"{request.host_url}book/{b.get('slug') or b['id']}/{b['id']}",
            "name": b["title"].replace("_", " "),
        }
        for i, b in enumerate(books, 1)
    ]

    return render_template(
        "user/books.html",
        books=books,
        total_books=total_books,
        page=page,
        total_pages=total_pages,
        q=q,
        category_slug=category_slug,
        category_name=category_name or "",
        sort=sort,
        all_categories=all_categories,
        books_jsonld={
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": books_jsonld,
        },
    )


# ================== LEARNING HUB MODULES PYTHON (Category + Module Pages) ==================
@app.route("/learn/<slug>/<module>")
def category_module(slug, module):
    cur = mysql.connection.cursor()
    category = slug_to_category_name(slug, cur)
    cur.close()

    if not category:
        abort(404)

    module_info = next(
        (m for m in GENERIC_MODULES + IELTS_MODULES if m["slug"] == module),
        None,
    )
    if not module_info:
        abort(404)
    folder = category_to_slug(category)
    lessons = None
    writing_practice = None
    task2_practice = None
    practice_items = None
    practice_projects = None
    task1_visuals = None
    task1_structures = None
    band_guide = None
    mistakes = None
    tips = None
    practice = None
    practice_quizzes = None
    debugging_challenges = None
    capstone = None

    if slug == "python" and module == "beginner":
        lessons = PYTHON_BEGINNER_LESSONS
    if slug == "python" and module == "intermediate":
        lessons = PYTHON_INTERMEDIATE_LESSONS
    if slug == "python" and module == "advanced":
        lessons = PYTHON_ADVANCED_LESSONS
    if slug == "python" and module == "practice":
        practice_items = PYTHON_PRACTICE
        practice_projects = PYTHON_PROJECTS
    if slug == "javascript" and module == "beginner":
        lessons = JAVASCRIPT_BEGINNER_LESSONS
    if slug == "javascript" and module == "intermediate":
        lessons = JAVASCRIPT_INTERMEDIATE_LESSONS
    if slug == "javascript" and module == "advanced":
        lessons = JAVASCRIPT_ADVANCED_LESSONS
    if slug == "javascript" and module == "practice":
        practice_items = JAVASCRIPT_PRACTICE
        practice_projects = None
    if slug == "java" and module == "beginner":
        lessons = JAVA_BEGINNER_LESSONS
    if slug == "java" and module == "intermediate":
        lessons = JAVA_INTERMEDIATE_LESSONS
    if slug == "java" and module == "advanced":
        lessons = JAVA_ADVANCED_LESSONS
    if slug == "java" and module == "practice":
        practice_items = JAVA_PRACTICE
        practice_projects = None
    if slug == "c-c" and module == "beginner":
        lessons = C_BEGINNER_LESSONS + CPP_BEGINNER_LESSONS
    if slug == "c-c" and module == "intermediate":
        lessons = C_INTERMEDIATE_LESSONS + CPP_INTERMEDIATE_LESSONS
    if slug == "c-c" and module == "advanced":
        lessons = C_CPP_ADVANCED_LESSONS
    if slug == "c-c" and module == "practice":
        practice_items = C_CPP_PRACTICE
        practice_projects = None
    if slug == "web-development" and module == "beginner":
        lessons = WEB_DEV_BEGINNER_LESSONS
    if slug == "web-development" and module == "intermediate":
        lessons = WEB_DEV_INTERMEDIATE_LESSONS
    if slug == "web-development" and module == "advanced":
        lessons = WEB_DEV_ADVANCED_LESSONS
    if slug == "web-development" and module == "practice":
        practice_items = WEB_DEV_PRACTICE
        practice_projects = None
    if slug == "data-science" and module == "beginner":
        lessons = DATA_SCIENCE_BEGINNER_LESSONS
    if slug == "data-science" and module == "intermediate":
        lessons = DATA_SCIENCE_INTERMEDIATE_LESSONS
    if slug == "data-science" and module == "advanced":
        lessons = DATA_SCIENCE_ADVANCED_LESSONS
    if slug == "data-science" and module == "practice":
        practice_items = DATA_SCIENCE_PRACTICE
        practice_projects = None
    if slug == "machine-learning" and module == "beginner":
        lessons = ML_BEGINNER_LESSONS
    if slug == "machine-learning" and module == "intermediate":
        lessons = ML_INTERMEDIATE_LESSONS
    if slug == "machine-learning" and module == "advanced":
        lessons = ML_ADVANCED_LESSONS
    if slug == "machine-learning" and module == "practice":
        practice_items = ML_PRACTICE
        practice_projects = None
    if slug == "algorithms" and module == "beginner":
        lessons = ALGORITHMS_BEGINNER_LESSONS
    if slug == "algorithms" and module == "intermediate":
        lessons = ALGORITHMS_INTERMEDIATE_LESSONS
    if slug == "algorithms" and module == "advanced":
        lessons = ALGORITHMS_ADVANCED_LESSONS
    if slug == "algorithms" and module == "practice":
        practice_items = ALGORITHMS_PRACTICE
        practice_projects = None
    if slug == "databases" and module == "beginner":
        lessons = DATABASES_BEGINNER_LESSONS
    if slug == "databases" and module == "intermediate":
        lessons = DATABASES_INTERMEDIATE_LESSONS
    if slug == "databases" and module == "advanced":
        lessons = DATABASES_ADVANCED_LESSONS
    if slug == "databases" and module == "practice":
        practice_items = DATABASES_PRACTICE
        practice_projects = None
    if slug == "cyber-security" and module == "beginner":
        lessons = CYBERSECURITY_BEGINNER_LESSONS
    if slug == "cyber-security" and module == "intermediate":
        lessons = CYBERSECURITY_INTERMEDIATE_LESSONS
    if slug == "cyber-security" and module == "advanced":
        lessons = CYBERSECURITY_ADVANCED_LESSONS
    if slug == "cyber-security" and module == "practice":
        practice_items = CYBERSECURITY_PRACTICE
        practice_projects = None
    if slug == "ielts" and module == "listening":
        lessons = IELTS_LISTENING_LESSONS
    if slug == "ielts" and module == "reading":
        lessons = IELTS_READING_LESSONS
    if slug == "ielts" and module == "writing":
        lessons = IELTS_WRITING_LESSONS
        writing_practice = IELTS_WRITING_PRACTICE
        task2_practice = IELTS_TASK2_PRACTICE
    if slug == "ielts" and module == "speaking":
        lessons = IELTS_SPEAKING_LESSONS
        band_guide = IELTS_SPEAKING_BAND_GUIDE
        mistakes = IELTS_SPEAKING_MISTAKES
        tips = IELTS_SPEAKING_TIPS
        practice = IELTS_SPEAKING_PRACTICE
    if slug == "mobile-apps" and module == "beginner":
        lessons = MOBILE_APPS_BEGINNER_LESSONS
    if slug == "mobile-apps" and module == "intermediate":
        lessons = MOBILE_APPS_INTERMEDIATE_LESSONS
    if slug == "mobile-apps" and module == "advanced":
        lessons = MOBILE_APPS_ADVANCED_LESSONS
    if slug == "mobile-apps" and module == "practice":
        practice_items = MOBILE_APPS_PRACTICE_CHALLENGES
        practice_projects = MOBILE_APPS_PRACTICE_PROJECTS
        capstone = MOBILE_APPS_CAPSTONE
    try:
        return render_template(
            f"user/{folder}/{module}.html",
            category=category,
            category_slug=slug,
            lessons=lessons,
            writing_practice=writing_practice,
            practice_items=practice_items,
            practice_projects=practice_projects,
            task1_structures=task1_structures,
            task2_practice=task2_practice,
            band_guide=band_guide,
            mistakes=mistakes,
            tips=tips,
            practice=practice,
            info=module_info,
            practice_quizzes=practice_quizzes,
            debugging_challenges=debugging_challenges,
            capstone=capstone,
        )
    except TemplateNotFound:
        UNIVERSAL = {"beginner", "intermediate", "advanced", "practice"}
        if module in UNIVERSAL:
            return render_template(
                f"user/learn_universal/{module}.html",
                category=category,
                category_slug=slug,
                info=module_info,
            )
        raise


# ================== PRACTICE CHALLENGE API ==================
@app.route("/api/practice/challenges")
def practice_challenges_api():
    level = request.args.get("level", "beginner")
    topic = request.args.get("topic", "")
    challenge_type = request.args.get("type", "")

    filtered = [
        item
        for item in PYTHON_PRACTICE
        if item["level"] == level
        and (not topic or item["topic"].lower() == topic.lower())
        and (not challenge_type or item["type"] == challenge_type)
    ]

    # Return safe data only — answer/solution included for client-side checking
    return jsonify(
        {
            "count": len(filtered),
            "challenges": filtered,
        }
    )


@app.route("/api/practice/next")
def practice_next_challenge():
    level = request.args.get("level", "beginner")
    topic = request.args.get("topic", "")
    exclude_id = request.args.get("exclude", "")

    candidates = [
        item
        for item in PYTHON_PRACTICE
        if item["level"] == level
        and (not topic or item["topic"].lower() == topic.lower())
        and item["id"] != exclude_id
    ]

    if not candidates:
        return jsonify({"challenge": None})

    next_item = random.choice(candidates)
    return jsonify({"challenge": next_item})


# ------IELTS PAGE ROUTE------
@app.route("/ielts")
def ielts_page():
    return redirect(url_for("learning_hub", category_slug="ielts"), code=301)


# -----IELTS MODULE ROUTE-----
@app.route("/ielts/<module>")
def ielts_module(module):
    return redirect(url_for("category_module", slug="ielts", module=module), code=301)


# ================== BOOK DETAIL ==================
@app.route("/book/<int:book_id>")
@app.route("/book/<slug>/<int:book_id>")
def book_detail(book_id, slug=None):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description,
               d.image_url, d.language, d.category_id,
               d.resource_type, d.external_url, d.slug, d.icon_name, d.created_at
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.id = %s AND d.approved = 1
        """,
        (book_id,),
    )
    book = cur.fetchone()

    if not book:
        cur.close()
        abort(404)

    # ========== SLUG + PREFIX REDIRECT LOGIC ==========
    _db_slug_raw = book[11] or ""
    # Corrupt-slug guard: reject control chars, spaces, or absurd length.
    if (
        not _db_slug_raw
        or re.search(r"[\x00-\x1f\x7f]", _db_slug_raw)
        or " " in _db_slug_raw
        or len(_db_slug_raw) > 200
    ):
        db_slug = str(book_id)
    else:
        db_slug = _db_slug_raw
    rtype = book[9] or "pdf"
    expected_prefix = "book"
    current_prefix = request.path.split("/")[1]

    if slug != db_slug or current_prefix != expected_prefix:
        cur.close()
        return redirect(f"/{expected_prefix}/{db_slug}/{book_id}", code=301)
    # ==================================================

    # Increment view count
    cur.execute(
        "UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,)
    )
    mysql.connection.commit()

    # Fetch reviews
    cur.execute(
        """
        SELECT u.username, r.rating, r.comment, r.created_at, u.id, r.id,
               u.avatar_url, u.first_name, u.last_name
        FROM reviews r JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s ORDER BY r.created_at DESC
        """,
        (book_id,),
    )
    reviews_raw = cur.fetchall()

    # Is this resource favorited by current user?
    is_favorite = False
    if session.get("user_id"):
        cur.execute(
            "SELECT id FROM favorites WHERE user_id = %s AND book_id = %s",
            (session["user_id"], book_id),
        )
        is_favorite = cur.fetchone() is not None

    cur.close()

    reviews = []
    for r in reviews_raw:
        display_name = ((r[7] or "") + " " + (r[8] or "")).strip() or r[0]
        reviews.append(
            {
                "id": r[5],
                "username": r[0],
                "rating": r[1],
                "comment": r[2],
                "created_at": r[3],
                "user_id": r[4],
                "is_official": is_official_user(r[4]),
                "avatar": r[6],
                "display_name": display_name,
            }
        )

    lazy_trickle(book_id)

    # Related resources (same category)
    related_books = []
    cat_id = book[8]
    if cat_id:
        cur = mysql.connection.cursor()
        cur.execute(
            """
            SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link,
                   COALESCE(d.download_count, 0), COALESCE(d.view_count, 0),
                   d.resource_type, d.slug
            FROM documents d
            JOIN categories c ON d.category_id = c.id
            WHERE d.approved = 1 AND d.category_id = %s AND d.id != %s
            ORDER BY d.download_count DESC
            LIMIT 4
            """,
            (cat_id, book_id),
        )
        rel_rows = cur.fetchall()
        cur.close()
        for r in rel_rows:
            related_books.append(
                {
                    "id": r[0],
                    "title": r[1],
                    "author": r[2],
                    "level": r[3],
                    "image_url": r[4],
                    "link": r[5],
                    "download_count": r[6] or 0,
                    "view_count": r[7] or 0,
                    "resource_type": r[8] or "pdf",
                    "slug": r[9],
                }
            )

    # PDF-only flow (resource branch removed)
    book_data = {
        "id": book[0],
        "title": book[1],
        "level": book[2],
        "link": book[3],
        "author": book[4],
        "description": book[5],
        "image_url": book[6],
        "language": book[7],
        "slug": book[11],
    }
    return render_template(
        "user/book_detail.html",
        book=book_data,
        reviews=reviews,
        related_books=related_books,
    )


@app.route("/book/<slug>/<int:book_id>/qr")
@app.route("/book/<int:book_id>/qr")
def book_qr(book_id, slug=None):
    """Generate QR code PNG for a book/resource URL."""
    import qrcode
    from io import BytesIO

    # Resolve slug (fallback to id)
    cur = mysql.connection.cursor()
    cur.execute("SELECT slug FROM documents WHERE id = %s AND approved = 1", (book_id,))
    row = cur.fetchone()
    cur.close()
    if not row:
        abort(404)
    db_slug = row[0] or str(book_id)
    qr_url = f"{request.host_url.rstrip(chr(47))}/book/{db_slug}/{book_id}"

    img = qrcode.make(qr_url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/api/book/<int:book_id>/counts")
def book_counts(book_id):
    """Live download/view counts for a book."""
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT COALESCE(download_count, 0), COALESCE(view_count, 0) "
        "FROM documents WHERE id = %s",
        (book_id,),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return jsonify({"download_count": 0, "view_count": 0}), 404
    return jsonify({"download_count": row[0], "view_count": row[1]})


# ================== SEARCH AUTOCOMPLETE ==================
@app.route("/api/search/suggest")
def search_suggest():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, d.author, c.level, d.image_url,
               d.description,
               COALESCE(d.download_count, 0) as download_count,
               COALESCE(d.view_count, 0) as view_count
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE (d.title LIKE %s OR d.author LIKE %s) AND d.approved = 1
        ORDER BY d.title
        LIMIT 12
    """,
        (f"%{q}%", f"%{q}%"),
    )
    results = cur.fetchall()
    cur.close()
    return jsonify(
        [
            {
                "id": r[0],
                "title": r[1],
                "author": r[2],
                "level": r[3],
                "image_url": r[4],
                "description": r[5] or "",
                "download_count": r[6] or 0,
                "view_count": r[7] or 0,
            }
            for r in results
        ]
    )


# ================== API: BOOK DETAIL FOR MODAL ==================
@app.route("/api/book/<int:book_id>")
def api_book_detail(book_id):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language, d.slug
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.id = %s AND d.approved = 1
    """,
        (book_id,),
    )
    book = cur.fetchone()

    if not book:
        cur.close()
        return jsonify({"error": "Book not found"}), 404

    cur.execute(
        "UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,)
    )
    mysql.connection.commit()

    cur.execute(
        """
        SELECT u.username, r.rating, r.comment, r.created_at
        FROM reviews r JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s ORDER BY r.created_at DESC
    """,
        (book_id,),
    )
    reviews = cur.fetchall()

    is_fav = False
    if "user_id" in session:
        cur.execute(
            "SELECT id FROM favorites WHERE user_id = %s AND book_id = %s",
            (session["user_id"], book_id),
        )
        is_fav = cur.fetchone() is not None
    cur.close()

    lazy_trickle(book_id)

    book_data = {
        "id": book[0],
        "title": book[1],
        "level": book[2],
        "link": url_for("download_book", book_id=book[0], slug=book[8]),
        "author": book[4],
        "description": book[5],
        "image_url": book[6],
        "language": book[7],
        "slug": book[8],
        "reviews": [
            {"username": r[0], "rating": r[1], "comment": r[2], "created_at": str(r[3])}
            for r in reviews
        ],
        "is_favorite": is_fav,
        "is_logged_in": "user_id" in session,
    }
    return jsonify(book_data)


# ================== USER ACCOUNTS ==================
@app.route("/user/signup", methods=["GET", "POST"])
@limiter.limit(USER_ACTION_RATELIMIT)
def user_signup():
    if request.method == "POST":
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if len(password) > 128:
            return jsonify(error="Password must be at most 128 characters."), 400
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        # ---------- Required fields ----------
        if not username or not email or not password:
            msg = "All fields are required."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        if not first_name or not last_name:
            msg = "First name and last name are required."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        # ---------- Name length limits ----------
        if len(first_name) > 50 or len(last_name) > 50:
            msg = "Names must be 50 characters or less."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        # ---------- Email format ----------
        if not is_valid_email(email):
            msg = "Please enter a valid email address."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        # ---------- Username format ----------
        if not re.fullmatch(r"[A-Za-z0-9]{3,20}", username):
            msg = (
                "Username must be 3-20 letters and numbers only (no spaces or symbols)."
            )
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        # ---------- Reserved usernames ----------
        reserved = os.getenv("RESERVED_USERNAMES", "")
        if reserved:
            reserved_list = [
                r.strip().lower() for r in reserved.split(",") if r.strip()
            ]
            username_lower = username.lower()
            for word in reserved_list:
                if word in username_lower:
                    msg = "This username is not allowed. Please choose a different one."
                    if is_ajax:
                        return jsonify({"error": msg}), 400
                    return render_template("user/auth.html", mode="signup", error=msg)

        # ---------- Password strength (8+ chars, upper, lower, digit) ----------
        if len(password) < 8:
            msg = "Password must be at least 8 characters."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        if not any(c.isupper() for c in password):
            msg = "Password must contain at least one uppercase letter."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        if not any(c.islower() for c in password):
            msg = "Password must contain at least one lowercase letter."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        if not any(c.isdigit() for c in password):
            msg = "Password must contain at least one number."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("user/auth.html", mode="signup", error=msg)

        # ---------- Duplicate username check ----------
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            msg = "This username is already taken. Try a different one."
            if is_ajax:
                return jsonify({"error": msg}), 409
            return render_template("user/auth.html", mode="signup", error=msg)
        cur.close()

        # ---------- Duplicate email check ----------
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            msg = "This email is already registered. Please login instead."
            if is_ajax:
                return jsonify({"error": msg}), 409
            return render_template("user/auth.html", mode="signup", error=msg)
        cur.close()

        # ---------- Hash + token + insert (validation ke BAAD) ----------
        hashed = generate_password_hash(password)
        token = secrets.token_urlsafe(32)

        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password, verification_token, first_name, last_name) VALUES (%s, %s, %s, %s, %s, %s)",
            (username, email, hashed, token, first_name, last_name),
        )
        new_user_id = cur.lastrowid
        mysql.connection.commit()
        cur.close()
        app.extensions["account_lifecycle"].welcome(new_user_id)

        # ---------- Brevo sync (non-critical) ----------
        try:
            sync_brevo_contact(email, first_name, last_name)
        except Exception as e:
            app.logger.warning(f"Brevo contact sync failed for {email}: {e}")

        # ---------- Verification email ----------
        verify_link = url_for("verify_email", token=token, _external=True)
        html_body = make_verification_email(username, verify_link)
        try:
            send_email_notification(
                "Verify your email - DocoDive",
                email,
                f"Hi {username}, confirm your DocoDive email address: {verify_link}",
                html_body=html_body,
            )
        except Exception:
            pass

        if is_ajax:
            return jsonify(
                {
                    "success": True,
                    "message": "Account created! Please check your email to verify.",
                    "redirect": url_for("user_login"),
                }
            )

        flash("Account created! Please check your email to verify.", "success")
        return redirect(url_for("user_login"))

    return render_template("user/auth.html", mode="signup")


@app.route("/user/login", methods=["GET", "POST"])
@limiter.limit(USER_ACTION_RATELIMIT)
def user_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # ==== Exponential backoff check ====
        client_ip = (
            request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
            .split(",")[0]
            .strip()
        )
        blocked, wait_sec = check_login_backoff(client_ip, email)
        if blocked:
            msg = f"Too many failed attempts. Try again in {wait_sec} seconds."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 429
            flash(msg, "danger")
            return redirect(url_for("user_login"))
        # ==== End backoff check ====

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, username, password, verified, verification_token, first_name, last_name, avatar_url FROM users WHERE email = %s",
            (email,),
        )
        user = cur.fetchone()
        cur.close()

        if not user:
            wait = record_login_failure(client_ip, email)
            app.logger.warning(
                f"Login failure (no account) for {email} from {client_ip}; backoff {wait}s"
            )
            msg = "No account found with this email. Please sign up first."
            if is_ajax:
                return jsonify({"error": msg}), 401
            return render_template("user/auth.html", mode="login", error=msg)

        if not check_password_hash(user[2], password):
            wait = record_login_failure(client_ip, email)
            app.logger.warning(
                f"Login failure (bad password) for {email} from {client_ip}; backoff {wait}s"
            )
            msg = f"Invalid password. Please try again. (Wait {wait}s before retry)"
            if is_ajax:
                return jsonify({"error": msg}), 401
            return render_template("user/auth.html", mode="login", error=msg)

        if not user[3]:
            new_token = secrets.token_urlsafe(32)
            cur = mysql.connection.cursor()
            cur.execute(
                "UPDATE users SET verification_token = %s WHERE id = %s",
                (new_token, user[0]),
            )
            mysql.connection.commit()
            cur.close()
            verify_link = url_for("verify_email", token=new_token, _external=True)
            html_body = make_verification_email(user[1], verify_link)
            try:
                send_email_notification(
                    "Verify your email - DocoDive",
                    email,
                    f"Hi {user[1]}, confirm your DocoDive email address: {verify_link}",
                    html_body=html_body,
                )
            except Exception:
                pass
            msg = "A new verification email has been sent. Please check your inbox."
            if is_ajax:
                return jsonify({"error": msg}), 403
            return render_template("user/auth.html", mode="login", error=msg)

        # ==== Success: clear backoff + set session ====
        clear_login_backoff(client_ip, email)
        session["account_version"] = app.extensions["account_lifecycle"].on_login(
            user[0], password_hash=user[2]
        )

        session.permanent = True
        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["user_display_name"] = user[1]
        session["email"] = email
        session["avatar_url"] = user[6] if len(user) > 6 else None
        # Avatar URL session me set karo (aghar user ne lagayi hai)
        try:
            _cur = mysql.connection.cursor()
            _cur.execute("SELECT avatar_url FROM users WHERE id = %s", (user[0],))
            _avrow = _cur.fetchone()
            session["avatar_url"] = _avrow[0] if _avrow else None
            _cur.close()
        except Exception:
            session["avatar_url"] = None
        session.modified = True

        # Streak updates DB-dependent hain — DB down ho tab bhi login success rahe.
        try:
            today = datetime.utcnow().date()
            cur = mysql.connection.cursor()
            cur.execute(
                "SELECT last_login_date, streak_count, longest_streak FROM user_streaks WHERE user_id = %s",
                (user[0],),
            )
            streak_row = cur.fetchone()
            if streak_row:
                last_date, streak_cnt, long_streak = streak_row
                if last_date == today - timedelta(days=1):
                    streak_cnt += 1
                    award_points(user[0], 1, action="daily_login")
                else:
                    streak_cnt = 1
                long_streak = max(long_streak, streak_cnt)
                cur.execute(
                    "UPDATE user_streaks SET last_login_date=%s, streak_count=%s, longest_streak=%s WHERE user_id=%s",
                    (today, streak_cnt, long_streak, user[0]),
                )
            else:
                cur.execute(
                    "INSERT INTO user_streaks (user_id, last_login_date, streak_count, longest_streak) VALUES (%s, %s, 1, 1)",
                    (user[0], today),
                )
                award_points(user[0], 1, action="daily_login")
            mysql.connection.commit()
            cur.close()
        except Exception:
            app.logger.warning("Streak update skipped due to DB error during login.")

        if is_ajax:
            return jsonify({"success": True, "redirect": url_for("home")})
        return redirect(url_for("home"))

    return render_template("user/auth.html", mode="login")


@app.route("/verify/<token>")
def verify_email(token):
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id FROM users WHERE verification_token = %s AND verified = 0", (token,)
    )
    user = cur.fetchone()
    if user:
        cur.execute(
            "UPDATE users SET verified = 1, verification_token = NULL WHERE id = %s",
            (user[0],),
        )
        mysql.connection.commit()
        cur.close()
        flash("Email verified!", "success")
    else:
        cur.close()
        flash("Invalid or expired verification link.", "danger")
    return redirect(url_for("home"))


@app.route("/user/logout")
def user_logout():
    for key in ("user_id", "user_name", "user_display_name", "avatar_url", "email"):
        session.pop(key, None)
    return redirect(url_for("home"))


# ================== FAVORITES & HISTORY ==================
@app.route("/user/favorites")
def user_favorites():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language, d.slug
        FROM favorites f JOIN documents d ON f.book_id = d.id JOIN categories c ON d.category_id = c.id
        WHERE f.user_id = %s
    """,
        (session["user_id"],),
    )
    books = cur.fetchall()
    cur.close()
    real_pdfs = [
        {
            "id": r[0],
            "title": r[1],
            "level": r[2],
            "link": r[3],
            "author": r[4],
            "description": r[5],
            "image_url": r[6],
            "language": r[7],
            "slug": r[8],
        }
        for r in books
    ]
    return render_template("user/user_favorites.html", pdfs=real_pdfs)


@app.route("/user/favorite/<int:book_id>", methods=["POST"])
def toggle_favorite(book_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id FROM favorites WHERE user_id = %s AND book_id = %s",
        (user_id, book_id),
    )
    if cur.fetchone():
        cur.execute(
            "DELETE FROM favorites WHERE user_id = %s AND book_id = %s",
            (user_id, book_id),
        )
    else:
        cur.execute(
            "INSERT INTO favorites (user_id, book_id) VALUES (%s, %s)",
            (user_id, book_id),
        )
        award_points(user_id, 1, book_id, action="favorite")
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/user/history")
def user_history():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language, h.downloaded_at
        FROM download_history h JOIN documents d ON h.book_id = d.id JOIN categories c ON d.category_id = c.id
        WHERE h.user_id = %s ORDER BY h.downloaded_at DESC
    """,
        (session["user_id"],),
    )
    books = cur.fetchall()
    cur.close()
    real_pdfs = [
        {
            "id": r[0],
            "title": r[1],
            "level": r[2],
            "link": r[3],
            "author": r[4],
            "description": r[5],
            "image_url": r[6],
            "language": r[7],
            "downloaded_at": str(r[8]),
        }
        for r in books
    ]
    return render_template("user/user_history.html", pdfs=real_pdfs)


# ================== DOWNLOAD TRACKING ==================
@app.route("/api/download/<int:book_id>", methods=["POST"])
def track_download_route(book_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
        (session["user_id"], book_id),
    )
    cur.execute(
        "UPDATE documents SET download_count = download_count + 1 WHERE id = %s",
        (book_id,),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


# ================== REVIEWS ==================
@app.route("/api/reviews", methods=["POST"])
@app.route("/book/<int:book_id>/review", methods=["POST"])
@app.route("/book/<slug>/<int:book_id>/review", methods=["POST"])
@limiter.limit(AUTH_RATELIMIT)
def add_review(book_id=None, slug=None):

    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "").strip()
    if not comment and book_id is None:
        return jsonify({"error": "Write a review before posting"}), 400
    if len(comment) > 5000:
        return jsonify({"error": "Review must be at most 5,000 characters"}), 400
    if not rating or rating < 1 or rating > 5:
        return jsonify({"error": "Invalid rating"}), 400
    if book_id is None:
        selected_book = request.form.get("book_id", "").strip()
        if selected_book:
            if (not re.fullmatch(r"[0-9]{1,20}", selected_book)
                    or not 0 < int(selected_book) <= 18446744073709551615):
                return jsonify({"error": "Invalid book selection"}), 400
            book_id = int(selected_book)
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    book_title = None
    if book_id is not None:
        cur.execute("SELECT id, title FROM documents WHERE id=%s AND approved=1", (book_id,))
        book = cur.fetchone()
        if not book:
            cur.close()
            return jsonify({"error": "Book not found"}), 404
        book_title = book[1]
    cur.execute(
        "INSERT INTO reviews (user_id, book_id, rating, comment) VALUES (%s, %s, %s, %s)",
        (user_id, book_id, rating, comment),
    )
    mysql.connection.commit()
    cur.close()
    award_points(user_id, 5, book_id, action="review")
    return jsonify({"success": True, "book_title": book_title})


# -------------------- PROTECTED DOWNLOAD & READ ONLINE --------------------
def _pdf_error_response(status_code=503):
    if status_code == 416:
        return Response(status=416, headers={"Cache-Control": "private, no-store"})
    return render_template("user/pdf_unavailable.html", pdf_error_code=str(status_code)), status_code


def _pdf_filename(title, book_id):
    name = re.sub(r"[\x00-\x1f\x7f/\\]+", "_", str(title or "")).strip(" .")[:150]
    name = name or f"book-{book_id}"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name, secure_filename(name) or f"book-{book_id}.pdf"


def _serve_book_pdf(book_id, slug=None, attachment=False):
    if "user_id" not in session:
        if not attachment or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Login required"}), 401
        flash("Please login to download books.", "danger")
        return redirect(url_for("user_login"))
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT telegram_link, title, slug FROM documents WHERE id = %s AND approved = 1", (book_id,))
        book = cur.fetchone()
    finally:
        cur.close()
    if not book:
        abort(404)
    key = extract_r2_key(book[0])
    if not key or not key.lower().endswith(".pdf") or not key.startswith("docodive/uploads/"):
        return _pdf_error_response(404)
    try:
        resource = open_pdf_object(
            r2_client, R2_BUCKET, key,
            # Serve a full object for If-Range, rather than joining different versions.
            range_header=None if "If-Range" in request.headers else request.headers.get("Range"),
            head=request.method == "HEAD",
            public_url=trusted_public_pdf_url(book[0], R2_PUBLIC_BASE, key),
        )
    except PDFDeliveryError as error:
        app.logger.warning("PDF delivery unavailable for book %s (%s)", book_id, error.category)
        response = app.make_response(_pdf_error_response(error.status_code))
        if error.status_code == 416:
            response.headers.update(error.headers)
        return response

    # Record full download initiations after storage accepts the request.
    # Reader ranges, HEAD checks and failed storage access are not downloads.
    if attachment and request.method == "GET" and not request.headers.get("Range"):
        cur = None
        try:
            cur = mysql.connection.cursor()
            cur.execute("UPDATE documents SET download_count = download_count + 1 WHERE id = %s", (book_id,))
            cur.execute("INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)", (session["user_id"], book_id))
            mysql.connection.commit()
            g.download_recorded = True
        except Exception:
            app.logger.warning("Download activity recording unavailable for book %s", book_id)
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    app.logger.warning("Download activity cursor cleanup unavailable for book %s", book_id)

    name, ascii_name = _pdf_filename(book[1], book_id)
    headers = dict(resource.headers)
    mode = "attachment" if attachment else "inline"
    headers.update({
        "Content-Type": "application/pdf",
        "Content-Disposition": "{}; filename=\"{}\"; filename*=UTF-8''{}".format(mode, ascii_name, quote(name, safe="")),
        "Cache-Control": "private, no-store",
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
    })
    if request.method == "HEAD":
        resource.close()
        response = Response(status=resource.status_code, headers=headers)
    else:
        response = Response(resource.iter_chunks(), status=resource.status_code, headers=headers)
    response.call_on_close(resource.close)
    return response


@app.route("/book/<int:book_id>/download")
@app.route("/book/<slug>/<int:book_id>/download")
def download_book(book_id, slug=None):
    return _serve_book_pdf(book_id, slug, attachment=True)


@app.route("/book/<int:book_id>/pdf", methods=["GET", "HEAD"])
@app.route("/book/<slug>/<int:book_id>/pdf", methods=["GET", "HEAD"])
def book_pdf(book_id, slug=None):
    return _serve_book_pdf(book_id, slug)


@app.route("/book/<int:book_id>/read")
@app.route("/book/<slug>/<int:book_id>/read")
def read_book(book_id, slug=None):
    if "user_id" not in session:
        flash("Please login to read books online.", "danger")
        return redirect(url_for("user_login"))
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT telegram_link, title, slug FROM documents WHERE id = %s AND approved = 1", (book_id,))
        book = cur.fetchone()
        if book and request.method == "GET":
            cur.execute("UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,))
            mysql.connection.commit()
    finally:
        cur.close()
    if not book:
        abort(404)
    return render_template(
        "user/read_online.html", pdf_url=url_for("book_pdf", book_id=book_id),
        book_title=book[1], book_id=book_id, book_slug=book[2],
    )


# ================== OFFICIAL ADMIN ROUTES ==================


@app.route("/api/categories/live-counts")
@cache.cached(timeout=60)
def live_category_counts():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT c.id, c.level, COUNT(d.id) AS total
        FROM categories c LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1 AND COALESCE(d.resource_type, 'pdf') = 'pdf'
        GROUP BY c.id ORDER BY c.id
    """)
    data = cur.fetchall()
    cur.close()
    return jsonify([{"id": r[0], "level": r[1], "count": r[2]} for r in data])


# ================== MODERATION API ==================


# ================== MODERATION PANEL ==================


# ================== FEEDBACK COMMUNITY ==================
@app.route("/feedback", methods=["GET", "POST"])
def user_feedback():
    if request.method == "POST":
        if "user_id" not in session:
            flash("Please login to submit feedback.", "danger")
            return redirect(url_for("user_login"))

        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        if not subject or not message or len(subject) > 200 or len(message) > 5000:
            flash(
                "Enter a subject (up to 200 characters) and message (up to 5,000 characters).",
                "danger",
            )
            return redirect(url_for("user_feedback"))

        user_id = session["user_id"]
        try:
            cur = mysql.connection.cursor()
            cur.execute(
                "INSERT INTO user_feedback (user_id, subject, message) VALUES (%s, %s, %s)",
                (user_id, subject, message),
            )
            mysql.connection.commit()
            cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            user_row = cur.fetchone()
            username = user_row[0] if user_row else "User"
            cur.close()

            if app.config.get("ADMIN_NOTIFICATION_EMAIL"):
                html_body = make_feedback_notification_email(username, subject, message)
                send_email_notification(
                    f"New Feedback - {subject}",
                    app.config["ADMIN_NOTIFICATION_EMAIL"],
                    f"New suggestion from {username}: {subject}",
                    html_body=html_body,
                )
            flash("Your suggestion has been posted!", "success")
        except Exception as e:
            app.logger.error(f"Feedback insert failed: {e}")
            flash("Something went wrong. Please try again.", "danger")
        return redirect(url_for("user_feedback"))

    cur = mysql.connection.cursor()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 30
    cur.execute(
        """
        SELECT f.id, f.subject, f.message, f.created_at, f.like_count, f.official_reply, f.official_replied_at,
               u.username, u.avatar_url, u.id as user_id
        FROM user_feedback f
        LEFT JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC
        LIMIT %s OFFSET %s
    """,
        (per_page + 1, (page - 1) * per_page),
    )
    feedbacks = cur.fetchall()
    has_next = len(feedbacks) > per_page
    feedbacks = feedbacks[:per_page]
    cur.close()

    feedback_list = []
    current_user_id = session.get("user_id")
    liked = set()
    if current_user_id and feedbacks:
        cur = mysql.connection.cursor()
        ids = [row[0] for row in feedbacks]
        cur.execute(
            "SELECT feedback_id FROM feedback_likes WHERE user_id=%s AND feedback_id IN ("
            + ",".join(["%s"] * len(ids))
            + ")",
            (current_user_id, *ids),
        )
        liked = {row[0] for row in cur.fetchall()}
        cur.close()
    for row in feedbacks:
        fid = row[0]
        is_liked = fid in liked
        feedback_list.append(
            {
                "id": fid,
                "subject": row[1],
                "message": row[2],
                "created_at": row[3],
                "like_count": row[4] if row[4] else 0,
                "official_reply": row[5],
                "official_replied_at": row[6],
                "username": row[7] or "Deleted User",
                "avatar_url": row[8] or "",
                "user_id": row[9],
                "is_liked": is_liked,
            }
        )

    return render_template(
        "user/feedback.html", feedbacks=feedback_list, page=page, has_next=has_next
    )


@app.route("/feedback/<int:feedback_id>/like", methods=["POST"])
def toggle_feedback_like(feedback_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT user_id, feedback_id FROM feedback_likes WHERE user_id=%s AND feedback_id=%s",
        (user_id, feedback_id),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "DELETE FROM feedback_likes WHERE user_id=%s AND feedback_id=%s",
            (user_id, feedback_id),
        )
        cur.execute(
            "UPDATE user_feedback SET like_count = like_count - 1 WHERE id=%s",
            (feedback_id,),
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({"liked": False, "count": get_like_count(feedback_id)})
    else:
        cur.execute(
            "INSERT INTO feedback_likes (user_id, feedback_id) VALUES (%s, %s)",
            (user_id, feedback_id),
        )
        cur.execute(
            "UPDATE user_feedback SET like_count = like_count + 1 WHERE id=%s",
            (feedback_id,),
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({"liked": True, "count": get_like_count(feedback_id)})


def get_like_count(feedback_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT like_count FROM user_feedback WHERE id=%s", (feedback_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else 0


@app.route("/feedback/<int:feedback_id>/reply", methods=["POST"])
def add_feedback_reply(feedback_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    message = request.form.get("message", "").strip()
    if not message or len(message) > 5000:
        return jsonify({"error": "Reply must contain 1–5,000 characters"}), 400
    user_id = session["user_id"]
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO feedback_replies (feedback_id, user_id, message) VALUES (%s, %s, %s)",
            (feedback_id, user_id, message),
        )
        mysql.connection.commit()
        reply_id = cur.lastrowid
        cur.close()
        return jsonify({"success": True, "reply_id": reply_id})
    except Exception as e:
        app.logger.error(f"Reply insert failed: {e}")
        return jsonify({"error": "Something went wrong"}), 500


@app.route("/feedback/reply/<int:reply_id>/like", methods=["POST"])
def toggle_reply_like(reply_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT user_id, reply_id FROM reply_likes WHERE user_id=%s AND reply_id=%s",
        (user_id, reply_id),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "DELETE FROM reply_likes WHERE user_id=%s AND reply_id=%s",
            (user_id, reply_id),
        )
        mysql.connection.commit()
        liked = False
    else:
        cur.execute(
            "INSERT INTO reply_likes (user_id, reply_id) VALUES (%s, %s)",
            (user_id, reply_id),
        )
        mysql.connection.commit()
        liked = True
    cur.execute("SELECT COUNT(*) FROM reply_likes WHERE reply_id=%s", (reply_id,))
    count = cur.fetchone()[0]
    cur.close()
    return jsonify({"liked": liked, "count": count})


@app.route("/feedback/<int:feedback_id>/edit", methods=["POST"])
def edit_feedback(feedback_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    new_message = request.form.get("message", "").strip()
    if not new_message or len(new_message) > 5000:
        return jsonify({"error": "Message cannot be empty"}), 400
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM user_feedback WHERE id=%s", (feedback_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Feedback not found"}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({"error": "Unauthorized"}), 403
    cur.execute(
        "UPDATE user_feedback SET message=%s WHERE id=%s", (new_message, feedback_id)
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/feedback/<int:feedback_id>/delete", methods=["POST"])
def delete_feedback(feedback_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM user_feedback WHERE id=%s", (feedback_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Feedback not found"}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({"error": "Unauthorized"}), 403
    cur.execute(
        "DELETE FROM reply_likes WHERE reply_id IN (SELECT id FROM feedback_replies WHERE feedback_id=%s)",
        (feedback_id,),
    )
    cur.execute("DELETE FROM feedback_replies WHERE feedback_id=%s", (feedback_id,))
    cur.execute("DELETE FROM feedback_likes WHERE feedback_id=%s", (feedback_id,))
    cur.execute("DELETE FROM user_feedback WHERE id=%s", (feedback_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/feedback/reply/<int:reply_id>/edit", methods=["POST"])
def edit_reply(reply_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    new_message = request.form.get("message", "").strip()
    if not new_message or len(new_message) > 5000:
        return jsonify({"error": "Message cannot be empty"}), 400
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM feedback_replies WHERE id=%s", (reply_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Reply not found"}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({"error": "Unauthorized"}), 403
    cur.execute(
        "UPDATE feedback_replies SET message=%s WHERE id=%s", (new_message, reply_id)
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/feedback/reply/<int:reply_id>/delete", methods=["POST"])
def delete_reply(reply_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM feedback_replies WHERE id=%s", (reply_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Reply not found"}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({"error": "Unauthorized"}), 403
    cur.execute("DELETE FROM reply_likes WHERE reply_id=%s", (reply_id,))
    cur.execute("DELETE FROM feedback_replies WHERE id=%s", (reply_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/api/feedback/<int:feedback_id>/replies")
def get_feedback_replies(feedback_id):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT r.id, r.message, r.created_at, u.username, u.avatar_url, u.id as user_id,
               (SELECT COUNT(*) FROM reply_likes WHERE reply_id = r.id) as like_count
        FROM feedback_replies r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.feedback_id = %s
        ORDER BY r.created_at ASC
    """,
        (feedback_id,),
    )
    rows = cur.fetchall()
    cur.close()

    current_user_id = session.get("user_id")
    liked = set()
    if current_user_id and rows:
        cur = mysql.connection.cursor()
        ids = [row[0] for row in rows]
        cur.execute(
            "SELECT reply_id FROM reply_likes WHERE user_id=%s AND reply_id IN ("
            + ",".join(["%s"] * len(ids))
            + ")",
            (current_user_id, *ids),
        )
        liked = {row[0] for row in cur.fetchall()}
        cur.close()
    replies = []
    for row in rows:
        rid = row[0]
        is_liked = rid in liked
        replies.append(
            {
                "id": rid,
                "message": row[1],
                "created_at": str(row[2]),
                "username": row[3],
                "avatar_url": row[4],
                "user_id": row[5],
                "like_count": row[6] if row[6] else 0,
                "is_liked": is_liked,
            }
        )
    return jsonify(replies)


# ================== FEEDBACK EMAIL TEMPLATES ==================
def make_feedback_notification_email(username, subject, message):
    feedback_url = url_for("user_feedback", _external=True)
    content = f"""
        <p style="margin:0;">Hi Admin,</p>
        <p style="margin:16px 0 0;">A new suggestion has been submitted on DocoDive:</p>
        <div style="margin:24px 0; background:#F0F4FF; border-left:4px solid #4338ca; border-radius:8px; padding:16px;">
            <p style="margin:0 0 8px; font-weight:700; color:#1e1b4b;">{_safe(subject)}</p>
            <p style="margin:0 0 4px; color:#374151;">by <strong>{_safe(username)}</strong></p>
            <p style="margin:12px 0 0; color:#1e1b4b;">{_safe(message[:200])}</p>
        </div>
        {_email_button(feedback_url, "View All Suggestions")}
        <p style="margin-top:20px; font-size:13px; color:#6b7280;">Stay ahead with the community's voice!</p>
    """
    return _email_layout(
        f"New suggestion from {username}",
        "Community feedback",
        "New suggestion received",
        content,
    )


def make_feedback_reply_email(username, subject, message, official_reply):
    feedback_url = url_for("user_feedback", _external=True)
    content = f"""
        <p style="margin:0;">Hi {_safe(username)},</p>
        <p style="margin:16px 0 0;">The DocoDive team has responded to your suggestion:</p>
        <div style="margin:24px 0; background:#F0F4FF; border-left:4px solid #4338ca; border-radius:8px; padding:16px;">
            <p style="margin:0 0 8px; font-weight:700; color:#1e1b4b;">{_safe(subject)}</p>
            <p style="margin:0 0 12px; color:#374151;">{_safe(message[:200])}</p>
            <div style="background:#ffffff; border-radius:8px; padding:12px; margin-top:12px;">
                <p style="margin:0; color:#4338ca; font-weight:700;">📢 Official Response</p>
                <p style="margin:8px 0 0; color:#1e1b4b;">{_safe(official_reply)}</p>
            </div>
        </div>
        {_email_button(feedback_url, "View Suggestions")}
        <p style="margin-top:20px; font-size:13px; color:#6b7280;">Thank you for helping us improve DocoDive!</p>
    """
    return _email_layout(
        "DocoDive team replied to your suggestion.",
        "Feedback response",
        "We've replied to your idea",
        content,
    )


# ================== NEWSLETTER SUBSCRIBE ==================
def normalize_newsletter_email(raw):
    """Validate the newsletter address and deduplicate its case variants."""
    if not isinstance(raw, str) or any(ord(character) < 32 for character in raw):
        return None
    email = raw.strip().lower()
    if not email or len(email) > 254 or not is_valid_email(email):
        return None
    local, domain = email.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        return None
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
           for label in domain.split(".")):
        return None
    return email


def make_newsletter_welcome_email():
    from newsletter_presentation import build_newsletter_welcome, newsletter_site_base

    base = newsletter_site_base(app.config.get("PUBLIC_SITE_URL"))
    return build_newsletter_welcome(
        base + url_for("all_books"),
        base + url_for("learning_hub", category_slug="python"),
        base + url_for("contact_page"),
        base + url_for("privacy_policy"),
        support_email=app.config.get("SUPPORT_EMAIL"),
    )


def claim_newsletter_welcome(email):
    """Persist the unique welcome attempt before contacting the mail provider."""
    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    connection = mysql.connection
    cur = connection.cursor()
    try:
        cur.execute(
            "INSERT IGNORE INTO newsletter_welcomes (email_key, welcome_status, claimed_at) "
            "VALUES (%s, 'claimed', UTC_TIMESTAMP(6))",
            (email_key,),
        )
        claimed = cur.rowcount == 1
        connection.commit()
        return claimed
    finally:
        cur.close()


def record_newsletter_welcome_result(email, accepted):
    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    connection = mysql.connection
    cur = connection.cursor()
    try:
        cur.execute(
            "UPDATE newsletter_welcomes SET welcome_status=%s, completed_at=UTC_TIMESTAMP(6) "
            "WHERE email_key=%s AND welcome_status='claimed'",
            ("accepted" if accepted else "unconfirmed", email_key),
        )
        connection.commit()
    finally:
        cur.close()


@app.route("/newsletter/subscribe", methods=["POST"])
@limiter.limit(AUTH_RATELIMIT)
def newsletter_subscribe():
    def respond(message, success=False, status=200, welcome=None):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            payload = {"success": True, "message": message, "welcome_email": welcome} if success else {"error": message}
            return jsonify(payload), status
        flash(message, "success" if success else "danger")
        return redirect(url_for("home"))

    raw = request.form.get("email", "")
    if not raw.strip():
        return respond("Please enter your email.", status=400)
    email = normalize_newsletter_email(raw)
    if email is None:
        return respond("Please enter a valid email address.", status=400)

    try:
        # Validate configuration and real route links before provider side effects.
        welcome = make_newsletter_welcome_email()
        # Keep provider suppression settings intact; this upsert does not clear them.
        if sync_brevo_contact(email, "DocoDive", "Subscriber") is not True:
            return respond("Subscription could not be confirmed. Please try again.", status=500)
        claimed = claim_newsletter_welcome(email)
    except Exception:
        app.logger.exception("Newsletter subscription could not be confirmed")
        return respond("Subscription could not be confirmed. Please try again.", status=500)

    if not claimed:
        return respond("You're already subscribed. No additional welcome email was sent.",
                       success=True, welcome="already_requested")

    # An ambiguous timeout can still mean the provider accepted the email. Never
    # automatically repeat a persisted attempt, even if this process stops here.
    accepted = False
    try:
        accepted = send_email_notification(welcome["subject"], email, welcome["text"],
                                           html_body=welcome["html"]) is True
    except Exception:
        app.logger.exception("Newsletter welcome acceptance could not be confirmed")
    try:
        record_newsletter_welcome_result(email, accepted)
    except Exception:
        app.logger.exception("Newsletter welcome result could not be recorded")

    if accepted:
        return respond("You're subscribed! Your welcome email is on its way.",
                       success=True, welcome="accepted")
    return respond("You're subscribed. We couldn't confirm that your welcome email was sent.",
                   success=True, welcome="unconfirmed")


# ================== USER NOTIFICATION PREFERENCES ==================
@app.route("/user/preferences", methods=["GET", "POST"])
def user_preferences():
    if "user_id" not in session:
        return redirect(url_for("user_login"))

    user_id = session["user_id"]

    if request.method == "POST":
        notify_new_books = "1" if request.form.get("notify_new_books") else "0"
        favorite_categories = request.form.getlist("favorite_categories")
        email_frequency = request.form.get("email_frequency", "weekly")

        if email_frequency not in ("daily", "weekly", "off"):
            email_frequency = "weekly"

        categories_json = json.dumps(favorite_categories)

        cur = mysql.connection.cursor()
        cur.execute(
            """
            INSERT INTO user_preferences (user_id, notify_new_books, favorite_categories, email_frequency)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                notify_new_books = VALUES(notify_new_books),
                favorite_categories = VALUES(favorite_categories),
                email_frequency = VALUES(email_frequency)
        """,
            (user_id, notify_new_books, categories_json, email_frequency),
        )
        mysql.connection.commit()
        cur.close()

        flash("✅ Notification preferences saved successfully!", "success")
        return redirect(url_for("user_preferences"))

    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT notify_new_books, favorite_categories, email_frequency
        FROM user_preferences
        WHERE user_id = %s
    """,
        (user_id,),
    )
    row = cur.fetchone()
    cur.close()

    if row:
        pref = {
            "notify_new_books": bool(row[0]),
            "favorite_categories": json.loads(row[1]) if row[1] else [],
            "email_frequency": row[2] or "weekly",
        }
    else:
        pref = {
            "notify_new_books": True,
            "favorite_categories": [],
            "email_frequency": "weekly",
        }

    cur = mysql.connection.cursor()
    cur.execute("SELECT level FROM categories ORDER BY level")
    categories = [r[0] for r in cur.fetchall()]
    cur.close()

    return render_template("user/preferences.html", pref=pref, categories=categories)


# ================== USER PROFILE ==================
@app.route("/user/profile/<username>")
def user_profile(username):
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """
            SELECT id, username, email, verified, created_at, avatar_url, bio, social_links, first_name, last_name, custom_badge
            FROM users WHERE username = %s
        """,
            (username,),
        )
        user = cur.fetchone()
        if not user:
            abort(404)
        uid = user[0]

        activity = {}
        for field, query in (
            ("total_uploads", "SELECT COUNT(*) FROM documents WHERE uploaded_by = %s"),
            ("total_reviews", "SELECT COUNT(*) FROM reviews WHERE user_id = %s"),
            ("total_favorites", "SELECT COUNT(*) FROM favorites WHERE user_id = %s"),
            ("total_points", "SELECT SUM(points) FROM user_points WHERE user_id = %s"),
            ("total_downloads", "SELECT COUNT(*) FROM download_history WHERE user_id = %s"),
        ):
            cur.execute(query, (uid,))
            row = cur.fetchone()
            # An aggregate should return a row even for an empty account. Missing
            # results are unavailable data, not a measured zero or a profile crash.
            if not row:
                activity[field] = None
                app.logger.warning("Profile aggregate returned no row: %s", field)
            else:
                activity[field] = int(row[0] or 0)

        streak = longest = 0
        cur.execute(
            "SELECT streak_count, longest_streak FROM user_streaks WHERE user_id = %s",
            (uid,),
        )
        row = cur.fetchone()
        if row:
            streak, longest = row[0] or 0, row[1] or 0
    finally:
        cur.close()

    # The helper opens another cursor; finish the profile's results first.
    official_user_id = get_site_setting("official_user_id")
    is_official = bool(official_user_id and str(uid) == str(official_user_id))

    social_links_dict = {}
    if user[7]:
        try:
            social_links_dict = json.loads(user[7])
        except Exception:
            pass

    from community_presentation import achievement_summary
    achievement_inputs = (activity["total_downloads"], activity["total_favorites"], activity["total_reviews"], longest)
    profile_achievements = achievement_summary(*achievement_inputs) if all(value is not None for value in achievement_inputs) else None
    stored_badge = user[10] if len(user) > 10 else None
    badge_key = next((b['key'] for b in BADGE_DEFS if b['icon'] == stored_badge), None)
    display_badge = next((b for b in profile_achievements['items'] if b['key'] == badge_key), None) if profile_achievements else None
    return render_template(
        "user/user_profile.html",
        achievements=profile_achievements,
        display_badge=display_badge,
        user=user,
        **activity,
        profile_stats_unavailable=any(value is None for value in activity.values()),
        social_links=social_links_dict,
        is_official=is_official,
        streak=streak,
        longest=longest,
        custom_badge=user[10] if len(user) > 10 else None,
    )


# ================== BADGE DEFINITIONS ==================
BADGE_DEFS = [
    {
        "key": "first_download",
        "name": "First Download",
        "icon": "⬇️",
        "threshold": 1,
        "metric": "downloads",
    },
    {
        "key": "book_collector",
        "name": "Book Collector",
        "icon": "📥",
        "threshold": 10,
        "metric": "downloads",
    },
    {
        "key": "library_hoarder",
        "name": "Library Hoarder",
        "icon": "🏛️",
        "threshold": 50,
        "metric": "downloads",
    },
    {
        "key": "favoriter",
        "name": "Favoriter",
        "icon": "❤️",
        "threshold": 5,
        "metric": "favorites",
    },
    {
        "key": "reviewer",
        "name": "Reviewer",
        "icon": "⭐",
        "threshold": 3,
        "metric": "reviews",
    },
    {
        "key": "book_lover",
        "name": "Book Lover",
        "icon": "🏅",
        "threshold": 7,
        "metric": "longest",
    },
    {
        "key": "avid_reader",
        "name": "Avid Reader",
        "icon": "📚",
        "threshold": 30,
        "metric": "longest",
    },
    {
        "key": "bookworm",
        "name": "Bookworm",
        "icon": "🐛",
        "threshold": 60,
        "metric": "longest",
    },
    {
        "key": "legend",
        "name": "Legend",
        "icon": "👑",
        "threshold": 100,
        "metric": "longest",
    },
]


# ================== USER STATS ==================
@app.route("/user/stats", methods=["GET", "POST"])
def user_stats():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
    uid = session["user_id"]

    cur = mysql.connection.cursor()
    try:
        # Downloads (download_history se)
        cur.execute("SELECT COUNT(*) FROM download_history WHERE user_id = %s", (uid,))
        downloads = cur.fetchone()[0] or 0

        # Favorites
        cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id = %s", (uid,))
        favorites = cur.fetchone()[0] or 0

        # Reviews
        cur.execute("SELECT COUNT(*) FROM reviews WHERE user_id = %s", (uid,))
        reviews = cur.fetchone()[0] or 0

        # Streak + longest
        streak = 0
        longest = 0
        cur.execute(
            "SELECT streak_count, longest_streak FROM user_streaks WHERE user_id = %s",
            (uid,),
        )
        row = cur.fetchone()
        if row:
            streak, longest = row[0] or 0, row[1] or 0

        # Current custom badge
        cur.execute("SELECT custom_badge FROM users WHERE id = %s", (uid,))
        badge_row = cur.fetchone()
        current_badge = badge_row[0] if badge_row else None

        # Unlocked badges compute karo
        metric_map = {
            "downloads": downloads,
            "favorites": favorites,
            "reviews": reviews,
            "longest": longest,
        }
        unlocked_badges = []
        for b in BADGE_DEFS:
            val = metric_map.get(b["metric"], 0)
            if val >= b["threshold"]:
                unlocked_badges.append(
                    {
                        "name": b["name"],
                        "icon": b["icon"],
                        "threshold": b["threshold"],
                        "key": b["key"],
                    }
                )

        # POST — user apna badge select kar raha hai
        if request.method == "POST":
            selected = request.form.get("custom_badge", "").strip()
            valid = any(b["icon"] == selected for b in unlocked_badges)
            if valid:
                cur.execute(
                    "UPDATE users SET custom_badge = %s WHERE id = %s",
                    (selected, uid),
                )
                mysql.connection.commit()
                current_badge = selected
            elif selected == "":
                # Badge remove karo
                cur.execute(
                    "UPDATE users SET custom_badge = NULL WHERE id = %s",
                    (uid,),
                )
                mysql.connection.commit()
                current_badge = None

    finally:
        cur.close()

    from community_presentation import achievement_summary
    return render_template(
        "user/user_stats.html",
        achievements=achievement_summary(downloads, favorites, reviews, longest),
        downloads=downloads,
        favorites=favorites,
        reviews=reviews,
        streak=streak,
        longest=longest,
        unlocked_badges=unlocked_badges,
        current_badge=current_badge,
    )


@app.route("/user/profile/edit", methods=["GET", "POST"])
@limiter.limit(AUTH_RATELIMIT)
def edit_profile():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
    uid = session["user_id"]

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        new_username = request.form.get("username", "").strip()
        bio = request.form.get("bio", "").strip()
        social_links = request.form.get("social_links", "").strip()
        avatar_file = request.files.get("avatar")
        avatar_url = None

        # ---------- Name length limits ----------
        if len(first_name) > 50 or len(last_name) > 50:
            msg = "Names must be 50 characters or less."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("edit_profile"))

        # ---------- Bio length limit ----------
        if len(bio) > 500:
            msg = "Bio must be 500 characters or less."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("edit_profile"))

        # ---------- Social links length limit ----------
        if len(social_links) > 500:
            msg = "Social links must be 500 characters or less."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("edit_profile"))

        # ---------- Username format ----------
        if new_username and not re.fullmatch(r"[A-Za-z0-9]{3,20}", new_username):
            msg = (
                "Username must be 3-20 letters and numbers only (no spaces or symbols)."
            )
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("edit_profile"))

        # ---------- Avatar validation ----------
        if avatar_file and allowed_image_file(avatar_file.filename):
            avatar_data = avatar_file.read()

            # Magic bytes check
            if not is_valid_image(avatar_data):
                msg = "Invalid avatar image. Only JPEG, PNG, GIF, or WebP allowed."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("edit_profile"))

            # Size check (original)
            if len(avatar_data) > 10 * 1024 * 1024:
                msg = "Avatar must be under 10MB."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("edit_profile"))

            # Compress + final size check
            avatar_data = compress_image(avatar_data, max_size=(200, 200), quality=80)
            if len(avatar_data) > 2 * 1024 * 1024:
                msg = "Avatar must be under 2MB after compression."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("edit_profile"))

            avatar_key = generate_r2_key(
                "avatars", f"user_{uid}_{int(datetime.now().timestamp())}", ".jpg"
            )
            try:
                avatar_url = upload_to_r2(
                    avatar_data, avatar_key, content_type="image/jpeg"
                )
            except Exception as e:
                app.logger.error(f"Avatar R2 upload failed: {e}")
                msg = "Avatar upload failed. Please try again."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": msg}), 500
                flash(msg, "danger")
                return redirect(url_for("edit_profile"))

        cur = mysql.connection.cursor()

        # ---------- Username change check ----------
        if new_username and new_username != session.get("user_name"):
            # Duplicate check
            cur.execute(
                "SELECT id FROM users WHERE username = %s AND id != %s",
                (new_username, uid),
            )
            if cur.fetchone():
                cur.close()
                flash("Username already taken. Please choose another.", "danger")
                return redirect(url_for("edit_profile"))

            # 30-day limit
            cur.execute("SELECT username_changed_at FROM users WHERE id = %s", (uid,))
            row = cur.fetchone()
            last_changed = row[0] if row else None
            if last_changed and (datetime.utcnow() - last_changed).days < 30:
                cur.close()
                flash("You can change your username only once every 30 days.", "danger")
                return redirect(url_for("edit_profile"))

            cur.execute(
                "UPDATE users SET username = %s, username_changed_at = NOW() WHERE id = %s",
                (new_username, uid),
            )
            mysql.connection.commit()
            session["user_name"] = new_username

        # ---------- Update profile fields ----------
        cur.execute(
            """
            UPDATE users
            SET first_name = %s, last_name = %s, bio = %s, social_links = %s,
                avatar_url = COALESCE(%s, avatar_url)
            WHERE id = %s
        """,
            (first_name, last_name, bio, social_links, avatar_url, uid),
        )
        mysql.connection.commit()
        cur.close()

        # ---------- Session update (ek hi baar) ----------
        full_name = (first_name + " " + last_name).strip()
        session["user_display_name"] = full_name or session.get("user_name")
        if avatar_url:
            session["avatar_url"] = avatar_url

        msg = "Profile updated successfully!"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                {
                    "success": True,
                    "message": msg,
                    "avatar_url": avatar_url or session.get("avatar_url"),
                }
            )
        flash(msg, "success")
        return redirect(url_for("user_profile", username=session.get("user_name")))

    # ---------- GET: load profile ----------
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT first_name, last_name, bio, social_links, avatar_url, username FROM users WHERE id = %s",
        (uid,),
    )
    row = cur.fetchone()
    cur.close()
    profile = {
        "first_name": row[0] or "",
        "last_name": row[1] or "",
        "bio": row[2] or "",
        "social_links": row[3] or "",
        "avatar_url": row[4] or "",
        "username": row[5] or "",
    }
    return render_template("user/edit_profile.html", profile=profile)


# ================== NOTIFICATIONS PAGE ==================
@app.route("/user/notifications")
def user_notifications():
    if "user_id" not in session:
        return redirect(url_for("user_login"))

    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT id, message, link, is_read, created_at, type, metadata
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
    """,
        (session["user_id"],),
    )
    rows = cur.fetchall()
    cur.close()

    enriched = []
    for row in rows:
        notif = {
            "id": row[0],
            "message": row[1],
            "link": row[2],
            "is_read": row[3],
            "created_at": row[4],
            "type": row[5] or "info",
            "metadata": json.loads(row[6]) if row[6] else {},
        }
        if notif["type"] in ("approval", "rejection"):
            uid = notif["metadata"].get("uploader_id")
            bid = notif["metadata"].get("book_id")
            notif["book_cover"] = None
            notif["actor_name"] = None
            if uid:
                cur = mysql.connection.cursor()
                cur.execute(
                    "SELECT first_name, last_name, username, avatar_url FROM users WHERE id = %s",
                    (uid,),
                )
                u = cur.fetchone()
                cur.close()
                if u:
                    full = f"{(u[0] or chr(32)).strip()} {(u[1] or chr(32)).strip()}".strip()
                    notif["actor_name"] = full or (u[2] or "User")
                    notif["avatar_url"] = u[3]
                else:
                    notif["avatar_url"] = None
                notif["is_official_actor"] = is_official_user(uid)
            else:
                notif["avatar_url"] = None
                notif["is_official_actor"] = False
            if bid:
                cur = mysql.connection.cursor()
                cur.execute("SELECT image_url FROM documents WHERE id = %s", (bid,))
                b = cur.fetchone()
                cur.close()
                notif["book_cover"] = b[0] if b else None
        elif notif["type"] in ("general_comment", "reply"):
            uid = notif["metadata"].get("actor_user_id")
            if uid:
                cur = mysql.connection.cursor()
                cur.execute(
                    "SELECT username, avatar_url FROM users WHERE id = %s", (uid,)
                )
                user = cur.fetchone()
                cur.close()
                notif["actor_name"] = user[0] if user else "Unknown"
                notif["avatar_url"] = user[1] if user else None
                notif["is_official_actor"] = is_official_user(uid)
            else:
                notif["actor_name"] = "Someone"
                notif["avatar_url"] = None
                notif["is_official_actor"] = False
        else:
            notif["avatar_url"] = None
            notif["is_official_actor"] = False

        enriched.append(notif)

    return render_template("user/notifications.html", notifications=enriched)


# ================== NOTIFICATIONS API ==================
@app.route("/api/notifications/unread-count")
def unread_notification_count():
    if "user_id" not in session:
        return jsonify({"count": 0})
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=0",
        (session["user_id"],),
    )
    count = cur.fetchone()[0]
    cur.close()
    return jsonify({"count": count})


@app.route("/api/notifications")
def get_notifications():
    if "user_id" not in session:
        return jsonify(error="Login required"), 401
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT id, message, link, is_read, created_at, type, metadata
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC LIMIT 20
    """,
        (session["user_id"],),
    )
    rows = cur.fetchall()
    cur.close()

    result = []
    for row in rows:
        notif = {
            "id": row[0],
            "message": row[1],
            "link": row[2],
            "is_read": bool(row[3]),
            "created_at": str(row[4]),
            "type": row[5] or "info",
            "metadata": json.loads(row[6]) if row[6] else {},
        }
        if notif["type"] in ("approval", "rejection"):
            uid = session["user_id"]
            bid = notif["metadata"].get("book_id")
            cur = mysql.connection.cursor()
            cur.execute(
                "SELECT first_name, last_name, username FROM users WHERE id = %s",
                (uid,),
            )
            me = cur.fetchone()
            if me:
                full = (
                    f"{(me[0] or chr(32)).strip()} {(me[1] or chr(32)).strip()}".strip()
                )
                notif["actor_name"] = full or (me[2] or "You")
            else:
                notif["actor_name"] = "You"
            if bid:
                cur.execute("SELECT image_url FROM documents WHERE id = %s", (bid,))
                b = cur.fetchone()
                notif["book_cover"] = b[0] if b else None
            else:
                notif["book_cover"] = None
            cur.close()
            notif["is_official_actor"] = False
        elif notif["type"] in ("general_comment", "reply"):
            actor_id = notif["metadata"].get("actor_user_id")
            if actor_id:
                cur = mysql.connection.cursor()
                cur.execute(
                    "SELECT first_name, last_name, username, avatar_url FROM users WHERE id = %s",
                    (actor_id,),
                )
                user = cur.fetchone()
                cur.close()
                if user:
                    full = f"{(user[0] or chr(32)).strip()} {(user[1] or chr(32)).strip()}".strip()
                    notif["actor_name"] = full or (user[2] or "Someone")
                    notif["actor_avatar"] = user[3]
                else:
                    notif["actor_name"] = "Unknown"
                    notif["actor_avatar"] = None
                notif["is_official_actor"] = is_official_user(actor_id)
            else:
                notif["actor_name"] = "Someone"
                notif["actor_avatar"] = None
                notif["is_official_actor"] = False
        else:
            notif["is_official_actor"] = False

        result.append(notif)

    ids = {n.get("metadata", {}).get("book_id") for n in result}
    ids = [bid for bid in ids if isinstance(bid, int)]
    if ids:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id,title,image_url FROM documents WHERE id IN ("
            + ",".join(["%s"] * len(ids))
            + ")",
            tuple(ids),
        )
        books = {r[0]: r for r in cur.fetchall()}
        cur.close()
        for notification in result:
            book = books.get(notification.get("metadata", {}).get("book_id"))
            if book:
                notification.update(book_title=book[1], book_cover=book[2])
    return jsonify(result)


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def mark_notification_read(notif_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE notifications SET is_read=1 WHERE id=%s AND user_id=%s",
        (notif_id, session["user_id"]),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/api/notifications/<int:notif_id>/delete", methods=["POST"])
def delete_notification(notif_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    cur = mysql.connection.cursor()
    cur.execute(
        "DELETE FROM notifications WHERE id=%s AND user_id=%s",
        (notif_id, session["user_id"]),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/api/notifications/read-all", methods=["POST"])
def mark_all_notifications_read():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE notifications SET is_read=1 WHERE user_id=%s AND is_read=0",
        (session["user_id"],),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


# ================== LEADERBOARD ==================
@app.route("/leaderboard")
def leaderboard():
    from community_presentation import achievement_summary, rank_leaders
    official_user_id = get_site_setting("official_user_id")
    try:
        official_user_id = int(official_user_id) if official_user_id else None
    except (TypeError, ValueError):
        official_user_id = None

    cur = mysql.connection.cursor()
    query = """
        SELECT u.id, u.username, u.first_name, u.last_name, u.avatar_url,
               SUM(up.points) AS total_points,
               (SELECT COUNT(*) FROM download_history dh WHERE dh.user_id = u.id) AS downloads,
               (SELECT COUNT(*) FROM favorites f WHERE f.user_id = u.id) AS favorites,
               (SELECT COUNT(*) FROM reviews r WHERE r.user_id = u.id) AS reviews,
               COALESCE((SELECT longest_streak FROM user_streaks us WHERE us.user_id = u.id), 0) AS longest
        FROM user_points up
        JOIN users u ON up.user_id = u.id
        {exclude}
        GROUP BY u.id, u.username, u.first_name, u.last_name, u.avatar_url
        ORDER BY total_points DESC, u.id ASC
        LIMIT 50
    """
    if official_user_id:
        cur.execute(query.replace("{exclude}", "WHERE u.id != %s"), (official_user_id,))
    else:
        cur.execute(query.replace("{exclude}", ""))
    rows = cur.fetchall()
    cur.close()

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT h.user_id,h.points FROM leaderboard_snapshots h JOIN (SELECT user_id,MAX(snapshot_day) AS latest FROM leaderboard_snapshots WHERE snapshot_day<=DATE_SUB(UTC_DATE(),INTERVAL 7 DAY) GROUP BY user_id) chosen ON chosen.user_id=h.user_id AND chosen.latest=h.snapshot_day"
    )
    previous_scores = dict(cur.fetchall())
    cur.close()
    leaderboard = []
    for row in rows:
        full_name = ((row[2] or "") + " " + (row[3] or "")).strip()
        if not full_name:
            full_name = row[1]

        downloads = row[6] or 0
        favorites = row[7] or 0
        reviews = row[8] or 0
        longest = row[9] or 0

        # Badge emojis compute karo
        badges = []
        if downloads >= 1:
            badges.append("⬇️")
        if downloads >= 10:
            badges.append("📥")
        if favorites >= 5:
            badges.append("❤️")
        if reviews >= 3:
            badges.append("⭐")
        if longest >= 7:
            badges.append("🏅")
        if longest >= 30:
            badges.append("📚")
        if longest >= 100:
            badges.append("👑")

        leaderboard.append(
            {
                "user_id": row[0],
                "username": row[1],
                "name": full_name,
                "avatar_url": row[4],
                "points": row[5],
                "weekly_change": (
                    (row[5] or 0) - previous_scores[row[0]]
                    if row[0] in previous_scores
                    else None
                ),
                "is_official": is_official_user(row[0]),
                "badges": "".join(badges),
                "badge_icon": badges[0] if badges else None,
                "badge_count": achievement_summary(downloads, favorites, reviews, longest)['unlocked_count'],
                "downloads": downloads,
                "favorites": favorites,
                "reviews": reviews,
                "longest": longest,
            }
        )

    current_user_rank = None
    current_user_points = 0
    if "user_id" in session:
        uid = session["user_id"]
        cur = mysql.connection.cursor()
        cur.execute("SELECT SUM(points) FROM user_points WHERE user_id = %s", (uid,))
        total = cur.fetchone()[0] or 0
        current_user_points = total

        if official_user_id and uid != official_user_id:
            cur.execute(
                """
                SELECT COUNT(*) + 1 FROM (
                    SELECT up.user_id, SUM(up.points) AS total
                    FROM user_points up JOIN users u ON u.id = up.user_id
                    WHERE up.user_id != %s
                    GROUP BY up.user_id
                    HAVING SUM(up.points) > %s
                ) AS higher
            """,
                (official_user_id, total),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(*) + 1 FROM (
                    SELECT up.user_id, SUM(up.points) AS total
                    FROM user_points up JOIN users u ON u.id = up.user_id
                    GROUP BY up.user_id
                    HAVING SUM(up.points) > %s
                ) AS higher
            """,
                (total,),
            )
        rank = cur.fetchone()[0]
        current_user_rank = None if uid == official_user_id else rank
        cur.close()

    from community_presentation import rank_leaders
    return render_template(
        "user/leaderboard.html",
        leaderboard=rank_leaders(leaderboard),
        current_user_rank=current_user_rank,
        current_user_points=current_user_points,
    )


# ================== BOOK COMMENTS ==================
@app.route("/book/<int:book_id>/comments", methods=["GET"])
@app.route("/book/<slug>/<int:book_id>/comments", methods=["GET"])
@limiter.limit(USER_ACTION_RATELIMIT)
def get_comments(book_id, slug=None):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT c.id, c.comment, c.parent_id, c.created_at, u.username, u.avatar_url, u.id
        FROM book_comments c JOIN users u ON c.user_id = u.id
        WHERE c.book_id = %s ORDER BY c.created_at ASC
    """,
        (book_id,),
    )
    comments = cur.fetchall()
    cur.close()
    comment_list = [
        {
            "id": r[0],
            "comment": r[1],
            "parent_id": r[2],
            "created_at": str(r[3]),
            "username": r[4],
            "avatar_url": r[5],
            "user_id": r[6],
            "is_official": is_official_user(r[6]),
        }
        for r in comments
    ]
    return jsonify(comment_list)


@app.route("/book/<int:book_id>/comments", methods=["POST"])
@app.route("/book/<slug>/<int:book_id>/comments", methods=["POST"])
@limiter.limit(USER_ACTION_RATELIMIT)
def add_comment(book_id, slug=None):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("comment"), str):
        return jsonify({"error": "A comment is required"}), 400
    comment = data["comment"].strip()
    parent_id = data.get("parent_id")
    if not 1 <= len(comment) <= 5000:
        return jsonify({"error": "Comment must contain 1–5,000 characters"}), 400
    if parent_id is not None and (type(parent_id) is not int or parent_id < 1):
        return jsonify({"error": "Invalid parent comment"}), 400

    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM documents WHERE id=%s AND approved=1", (book_id,))
    if not cur.fetchone():
        cur.close()
        return jsonify({"error": "Book not found"}), 404
    if parent_id is not None:
        cur.execute(
            "SELECT id FROM book_comments WHERE id=%s AND book_id=%s AND parent_id IS NULL",
            (parent_id, book_id),
        )
        if not cur.fetchone():
            cur.close()
            return jsonify({"error": "Parent comment not found for this book"}), 400
    cur.execute(
        "INSERT INTO book_comments (book_id, user_id, parent_id, comment) VALUES (%s, %s, %s, %s)",
        (book_id, session["user_id"], parent_id, comment),
    )
    mysql.connection.commit()
    new_comment_id = cur.lastrowid
    cur.close()

    award_points(session["user_id"], 2, book_id)

    if not parent_id:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT uploaded_by, title, slug FROM documents WHERE id = %s", (book_id,)
        )
        book_info = cur.fetchone()
        cur.close()
        if book_info and book_info[0] and book_info[0] != session["user_id"]:
            uploader_id = book_info[0]
            book_title = book_info[1]
            book_slug = book_info[2] or str(book_id)
            snippet = comment[:60] + ("..." if len(comment) > 60 else "")
            msg = f'💬 New comment on <em>{book_title}</em><br><small class="text-muted">&ldquo;{snippet}&rdquo;</small>'
            metadata = {
                "book_id": book_id,
                "comment_id": new_comment_id,
                "actor_user_id": session["user_id"],
            }
            create_notification(
                uploader_id,
                "general_comment",
                msg,
                f"/book/{book_slug}/{book_id}#discussion",
                metadata,
            )
    else:
        cur = mysql.connection.cursor()
        cur.execute(
            """
            SELECT c.user_id, d.title, d.slug
            FROM book_comments c
            JOIN documents d ON c.book_id = d.id
            WHERE c.id = %s
        """,
            (parent_id,),
        )
        parent_info = cur.fetchone()
        cur.close()
        if parent_info and parent_info[0] != session["user_id"]:
            parent_author_id = parent_info[0]
            book_title = parent_info[1]
            book_slug = parent_info[2] or str(book_id)
            reply_username = session.get("user_name")
            snippet = comment[:60] + ("..." if len(comment) > 60 else "")
            msg = f'<strong>{reply_username}</strong> replied to your comment on <em>{book_title}</em><br><small class="text-muted">&ldquo;{snippet}&rdquo;</small>'
            metadata = {
                "book_id": book_id,
                "comment_id": new_comment_id,
                "parent_comment_id": parent_id,
                "actor_user_id": session["user_id"],
            }
            create_notification(
                parent_author_id,
                "reply",
                msg,
                url_for(
                    "book_detail", slug=book_slug, book_id=book_id, _anchor="discussion"
                ),
                metadata,
            )

    return jsonify({"success": True})


# ================== NOTIFICATION DIGEST ==================
def _book_matches_categories(book_category, selected_categories):
    if not selected_categories:
        return True
    return book_category in selected_categories


def _send_book_digest_to_user(user, books, digest_type, period_key):
    uid, email = user[0], user[2]
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT favorite_categories FROM user_preferences WHERE user_id = %s", (uid,)
    )
    row = cur.fetchone()
    cur.close()

    selected = []
    if row and row[0]:
        try:
            selected = json.loads(row[0])
            if not isinstance(selected, list):
                selected = []
        except Exception:
            selected = []

    matching = [b for b in books if _book_matches_categories(b[3], selected)]
    if not matching:
        return False

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id FROM notification_digest_log WHERE user_id=%s AND digest_type=%s AND period_key=%s",
        (uid, digest_type, period_key),
    )
    if cur.fetchone():
        cur.close()
        return False

    book_list = [
        {
            "id": b[0],
            "title": b[1],
            "author": b[2],
            "category": b[3],
            "description": b[4],
            "image_url": b[5] if len(b) > 5 else None,
        }
        for b in matching
    ]

    html = make_digest_email(book_list)

    body = "\n".join(f"{b[1]} by {b[2]} ({b[3]})" for b in matching)
    sent = send_email_notification(
        "New books digest - DocoDive", email, body, html_body=html
    )
    if sent:
        cur.execute(
            "INSERT INTO notification_digest_log (user_id, digest_type, period_key) VALUES (%s, %s, %s)",
            (uid, digest_type, period_key),
        )
        mysql.connection.commit()
    cur.close()
    return sent


def send_daily_book_digest():
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    period_key = now.strftime("%Y-%m-%d")

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.id, u.username, u.email
        FROM user_preferences up
        JOIN users u ON u.id = up.user_id
        WHERE up.notify_new_books = '1' AND up.email_frequency = 'daily'
    """)
    users = cur.fetchall()
    cur.execute(
        """
        SELECT d.id, d.title, d.author, c.level, d.description
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved_at >= %s
    """,
        (since,),
    )
    books = cur.fetchall()
    cur.close()

    sent_count = 0
    for user in users:
        if _send_book_digest_to_user(user, books, "daily", period_key):
            sent_count += 1
    return {"success": True, "digest": "daily", "emails_sent": sent_count}


def send_weekly_book_digest():
    now = datetime.utcnow()
    since = now - timedelta(days=7)
    period_key = now.strftime("%Y-%W")

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.id, u.username, u.email
        FROM user_preferences up
        JOIN users u ON u.id = up.user_id
        WHERE up.notify_new_books = '1' AND up.email_frequency = 'weekly'
    """)
    users = cur.fetchall()
    cur.execute(
        """
        SELECT d.id, d.title, d.author, c.level, d.description
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved_at >= %s
    """,
        (since,),
    )
    books = cur.fetchall()
    cur.close()

    sent_count = 0
    for user in users:
        if _send_book_digest_to_user(user, books, "weekly", period_key):
            sent_count += 1
    return {"success": True, "digest": "weekly", "emails_sent": sent_count}


@app.route("/internal/notification-digest/<digest_type>", methods=["POST"])
def notification_digest(digest_type):
    provided = request.headers.get("X-Cron-Secret", "")
    if (
        not CRON_SECRET
        or not provided
        or not hmac.compare_digest(str(CRON_SECRET), str(provided))
    ):
        return jsonify({"error": "Unauthorized"}), 401

    if digest_type == "daily":
        return jsonify(send_daily_book_digest())
    if digest_type == "weekly":
        return jsonify(send_weekly_book_digest())
    return jsonify({"error": "Invalid digest type"}), 400


def make_digest_email(books):
    """Build a DocoDive-styled new-books digest email (HTML string)."""

    book_cards = ""
    for book in books:
        image_url = book.get("image_url") or ""
        image_tag = ""
        if image_url:
            image_tag = f"""
                <img src="{_safe(image_url)}" alt="{_safe(book.get('title', 'Book'))}"
                     style="display:block;width:56px;height:70px;object-fit:cover;border-radius:8px;margin-right:14px;" />
            """

        book_cards += f"""
            <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0"
                   style="width:100%;margin-bottom:16px;border:1px solid #E5E7EB;border-left:5px solid {BRAND_COLOR};border-radius:14px;background:#FFFFFF;">
              <tr>
                <td style="padding:18px 20px;">
                  <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0">
                    <tr>
                      <td valign="top" width="70" style="width:70px;">
                        {image_tag}
                      </td>
                      <td valign="top" style="padding-left:{'0' if image_url else '0'};">
                        <span style="display:inline-block;padding:5px 10px;border-radius:999px;color:{BRAND_COLOR};background:{BRAND_LIGHT};font-size:10px;line-height:14px;font-weight:800;letter-spacing:.7px;text-transform:uppercase;">
                          {_safe(book.get('category', ''))}
                        </span>
                        <div style="margin-top:9px;color:{BRAND_DARK};font-size:17px;line-height:23px;font-weight:800;">
                          {_safe(book.get('title', ''))}
                        </div>
                        <div style="margin-top:4px;color:#9CA3AF;font-size:12px;line-height:18px;">
                          By {_safe(book.get('author', ''))}
                        </div>
                        <p style="margin:10px 0 0;color:#4B5563;font-size:13px;line-height:20px;">
                          {_safe(book.get('description', ''))}
                        </p>
                        <a href="{f"{request.host_url.rstrip('/')}/book/{book.get('slug') or book.get('id')}/{book.get('id')}"}"
                           style="display:inline-block;margin-top:14px;padding:11px 18px;background:{BRAND_COLOR};color:#FFFFFF;border-radius:9px;text-decoration:none;font-size:12px;line-height:16px;font-weight:800;">
                          Explore Book →
                        </a>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
        """

    return f"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>DocoDive — New Books</title>
        </head>
        <body style="margin:0;padding:0;background:#EEF2FF;font-family:Arial,Helvetica,sans-serif;color:#111827;">
          <div style="display:none;max-height:0;overflow:hidden;opacity:0;">Fresh books and resources have been added to DocoDive.</div>
          <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="width:100%;background:#EEF2FF;">
            <tr>
              <td align="center" style="padding:34px 12px;">
                <table role="presentation" width="600" border="0" cellpadding="0" cellspacing="0"
                       style="width:600px;max-width:600px;background:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 16px 48px rgba(79,70,229,0.15);">
                  <tr>
                    <td style="padding:30px 40px;background:#111827;">
                      <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0">
                        <tr>
                          <td width="48" valign="middle" style="width:48px;">
                            <div style="width:48px;height:48px;line-height:48px;text-align:center;border-radius:14px;background:#6366F1;color:#FFFFFF;font-size:24px;font-weight:900;">D</div>
                          </td>
                          <td valign="middle" style="padding-left:14px;">
                            <div style="color:#FFFFFF;font-size:22px;line-height:26px;font-weight:900;">DocoDive</div>
                            <div style="margin-top:4px;color:#C7D2FE;font-size:12px;line-height:17px;">Free knowledge. Endless discovery.</div>
                          </td>
                          <td align="right" valign="middle">
                            <span style="display:inline-block;padding:7px 12px;border-radius:999px;background:#312E81;color:#FFFFFF;font-size:11px;font-weight:800;">📚 NEW</span>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:40px 40px 34px;">
                      <span style="display:inline-block;padding:7px 12px;border-radius:999px;background:#EEF2FF;color:#4F46E5;font-size:11px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;">✨ Fresh Arrivals</span>
                      <h1 style="margin:16px 0 10px;color:#111827;font-size:30px;line-height:38px;font-weight:900;">New books are here.</h1>
                      <p style="margin:0 0 28px;color:#6B7280;font-size:15px;line-height:24px;">We've added new books based on your selected categories.</p>
                      {book_cards}
                      <div style="margin-top:30px;padding-top:24px;border-top:1px solid #E5E7EB;text-align:center;">
                        <div style="color:#111827;font-size:15px;font-weight:800;">Ready to explore more?</div>
                        <a href="{url_for('home', _external=True)}" style="display:inline-block;margin-top:14px;padding:13px 22px;background:#111827;color:#FFFFFF;border-radius:10px;text-decoration:none;font-size:13px;font-weight:800;">Visit DocoDive</a>
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:22px 40px;background:#F9FAFB;border-top:1px solid #E5E7EB;text-align:center;">
                      <div style="color:#374151;font-size:12px;font-weight:700;">DocoDive</div>
                      <div style="margin-top:4px;color:#9CA3AF;font-size:11px;">Free knowledge. Built for curious minds.</div>
                      <div style="margin-top:8px;color:#C7C9CE;font-size:10px;">© 2026 DocoDive. All rights reserved.</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </body>
        </html>
    """


def _digest_scheduler_loop():
    """Background scheduler: daily 8 PM PKT, weekly Sunday 8 PM PKT."""
    while True:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if now.hour == 15 and now.minute == 0:
            try:
                with app.app_context():
                    send_daily_book_digest()
                    if now.weekday() == 6:
                        send_weekly_book_digest()
            except Exception as e:
                app.logger.exception("Scheduled digest failed: %s", e)
            time.sleep(60)
        time.sleep(20)


def start_digest_scheduler():
    thread = threading.Thread(target=_digest_scheduler_loop, daemon=True)
    thread.start()
    app.logger.info("Digest scheduler started")


# ================== LEGAL PAGES ==================
@app.route("/cookies")
def cookies_policy():
    return render_template("user/cookies.html")


@app.route("/contact")
def contact_page():
    return render_template("user/contact.html")


@app.route("/community-guidelines")
def community_guidelines():
    return render_template("user/community_guidelines.html")


@app.route("/accessibility")
def accessibility_page():
    return render_template("user/accessibility.html")


@app.route("/privacy")
def privacy_policy():
    return render_template("user/privacy.html")


@app.route("/terms")
def terms_of_service():
    return render_template("user/terms.html")


@app.route("/data-deletion")
def data_deletion():
    return render_template("user/data_deletion.html")


# ================== RUN ==================
@app.before_request
def redirect_legacy_resources():
    """301: legacy /resources/* URLs -> /book/* (SEO canonical)."""
    p = request.path
    if p != "/resources" and not p.startswith("/resources/"):
        return
    tail = p[len("/resources") :]
    if tail.startswith("/"):
        segs = tail.lstrip("/").split("/", 2)
        if len(segs) >= 2 and segs[1].isdigit():
            rest = ("/" + segs[2]) if len(segs) == 3 else ""
            new_url = f"/book/{segs[0]}/{segs[1]}{rest}"
            if request.query_string:
                new_url += "?" + request.query_string.decode()
            return redirect(new_url, code=301)
    return redirect("/books", code=301)


# Register after public routes; new services perform no startup database writes.
from account_routes import register_accounts, start_account_scheduler

register_accounts(app, globals())

# Register after user routes so legacy endpoint names remain available.
from admin.admin_routes import register_admin

register_admin(app, globals())

from seo import register_seo

app.config["PUBLIC_SITE_URL"] = os.getenv("PUBLIC_SITE_URL", "")
register_seo(app, globals())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_digest_scheduler()
        start_account_scheduler(app)

    app.run(host="0.0.0.0", port=port, debug=debug)
