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
from sentry_sdk.integrations.flask import FlaskIntegration
from datetime import datetime, timedelta
from functools import wraps
from html import escape
import hashlib, hmac, base64, json
from flask import request, jsonify
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
from pypdf import PdfReader
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
)
import mysql.connector as mysql_connector_module
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash
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
    force_https=(os.getenv("FLASK_ENV", "").lower() == "production"),
    strict_transport_security=(os.getenv("FLASK_ENV", "").lower() == "production"),
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
cache = Cache(app)

@app.before_request
def enforce_canonical_host():
    """www -> non-www redirect (single canonical domain for SEO)."""
    host = request.host
    if host.startswith("www."):
        return redirect(request.url.replace("://www.", "://", 1), code=301)

@app.after_request
def add_cache_headers(response):
    content_type = response.content_type or ""
    path = request.path

    if any(
        ext in path
        for ext in [
            ".css",
            ".js",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".ico",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
        ]
    ):
        response.cache_control.max_age = 2592000
        response.cache_control.public = True
        response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
    elif "text/html" in content_type:
        response.cache_control.no_cache = True
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif "application/json" in content_type:
        response.cache_control.max_age = 60
        response.headers["Cache-Control"] = "public, max-age=60"

    return response


IS_PRODUCTION = os.getenv("FLASK_ENV", "").lower() == "production"

secret_key = os.getenv("FLASK_SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is required. Set it in your .env file "
        "(generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\")."
    )
app.config["SECRET_KEY"] = secret_key

CRON_SECRET = os.getenv("CRON_SECRET")
if not CRON_SECRET:
    CRON_SECRET = secrets.token_urlsafe(32)
    app.logger.warning("CRON_SECRET not set; generated a random secret (value hidden)")

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

app.config["FACEBOOK_APP_SECRET"] = os.getenv("FACEBOOK_CLIENT_SECRET")

# ================== DATABASE CONFIGURATION (MYSQL_* with DB_* fallback) ==================
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST") or os.environ.get(
    "DB_HOST", "localhost"
)
app.config["MYSQL_PORT"] = int(
    os.environ.get("MYSQL_PORT") or os.environ.get("DB_PORT", "3306")
)
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER") or os.environ.get(
    "DB_USER", "root"
)
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD") or os.environ.get(
    "DB_PASSWORD", ""
)
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB") or os.environ.get(
    "DB_NAME", "docodive_dev"
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
}
ssl_ca = app.config.get("MYSQL_SSL_CA")
if ssl_ca:
    db_config["ssl_ca"] = ssl_ca
    db_config["ssl_verify_cert"] = app.config.get("MYSQL_SSL_VERIFY_CERT", False)
    db_config["ssl_verify_identity"] = app.config.get(
        "MYSQL_SSL_VERIFY_IDENTITY", False
    )


pool = MySQLConnectionPool(pool_name="mypool", pool_size=20, **db_config)

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
                g.db_conn.ping(reconnect=True)
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

@app.after_request
def ensure_session_cookie(response):
    """Force session cookie even on AJAX/jsonify responses."""
    if session and session.modified:
        session.permanent = True
        response.set_cookie(
            key=app.config.get("SESSION_COOKIE_NAME", "docodive_session_v2"),
            value=session.sid if hasattr(session, "sid") else session.get("_csrf_token", ""),
            max_age=app.config.get("PERMANENT_SESSION_LIFETIME").total_seconds(),
            httponly=True,
            samesite="Lax",
            secure=False,
            path="/",
        )
    return response

# ================== CSRF (FIXED: digest exempt) ==================
@app.before_request
def csrf_protect():
    if request.path.startswith("/internal/notification-digest/"):
        return

    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return
        token = session.get("_csrf_token")
        if not token or token != request.form.get("_csrf_token", ""):
            abort(403)
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)


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
app.config["MAIL_FROM_EMAIL"] = os.getenv("MAIL_FROM_EMAIL", "7t7sufyan@gmail.com")

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
    config=Config(signature_version="s3v4"),
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
    return f"docodive/{folder}/{base_name}{ext}"


def is_valid_pdf(file_bytes):
    """Check magic bytes — extension par bharosa nahi."""
    return file_bytes[:4] == b"%PDF"


def is_valid_image(file_bytes):
    """Check image magic bytes (JPEG/PNG/WebP/GIF)."""
    if file_bytes[:3] == b"\xff\xd8\xff":          # JPEG
        return True
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":    # PNG
        return True
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return True
    if file_bytes[:4] == b"GIF8":                  # GIF (GIF87a/GIF89a)
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
    sender_email = app.config.get("MAIL_FROM_EMAIL") or "7t7sufyan@gmail.com"
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
            app.logger.error("Brevo API error: %s", resp.text)
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
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title FROM documents WHERE LOWER(author) = %s",
                (author.lower(),),
            )
            rows = cur.fetchall()
            for row in rows:
                if normalize_for_duplicate_check(row[1]) == norm_title:
                    return True
            return False
    except Exception:
        return False


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
    wait = min(2 ** count, 60)  # max 60 seconds cap
    _login_attempts[key] = (count, time.time() + wait)
    return wait


def clear_login_backoff(ip, email):
    """Successful login par record hatao."""
    _login_attempts.pop(f"{ip}|{email.lower()}", None)
    
    
def setup_session(user_id):
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
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                f"UPDATE users SET {provider_id_field} = %s, avatar_url = %s WHERE id = %s",
                (user_info["sub"], avatar, existing[0]),
            )
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

    # "See More" offset: pehle 4, baad har click pe 5 aur
    try:
        offset = int(request.args.get("offset", 4))
    except (TypeError, ValueError):
        offset = 4
    if offset < 1:
        offset = 1

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
               r.created_at
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.comment IS NOT NULL AND TRIM(r.comment) != ''
        ORDER BY r.created_at DESC
        LIMIT %s
        """,
        (offset,),
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
        "reviews.html",
        avg_rating=avg_rating,
        breakdown=breakdown,
        total_reviews=total_reviews,
        reviews=reviews,
        books=books,
    )
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
    BOOKS_BASE = 3762
    USERS_BASE = 82783
    DOWNLOADS_BASE = 179570

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

    # Real categories count
    cur.execute("SELECT COUNT(*) FROM categories")
    total_categories = cur.fetchone()[0] or 0

    # Real reviews count
    cur.execute(
        "SELECT COUNT(*) FROM reviews WHERE comment IS NOT NULL AND TRIM(comment) != ''"
    )
    real_reviews = cur.fetchone()[0] or 0

    cur.close()

       
     # ============ FIXED TOP REVIEWS (hamesha 5 dikhte hain) ============
    recent_reviews = [
        {
            "review_id": 1,
            "username": "ayesha.khan",
            "full_name": "Ayesha Khan",
            "avatar": "https://i.pravatar.cc/150?img=47",
            "rating": 5,
            "comment": "Honestly, this is the best free library I've ever used. The books are perfectly organized, and downloads finish in seconds with zero hassle. I've already shared it with my whole study group!",
            "created_at": "Aug 18, 2026",
        },
        {
            "review_id": 2,
            "username": "muhammad.bilal",
            "full_name": "Muhammad Bilal",
            "avatar": "https://i.pravatar.cc/150?img=12",
            "rating": 5,
            "comment": "Amazing collection of programming books! I found everything I needed for my development journey in one place, from beginner guides to advanced topics. The clean layout makes browsing really enjoyable.",
            "created_at": "Aug 19, 2026",
        },
        {
            "review_id": 3,
            "username": "fatima.noor",
            "full_name": "Fatima Noor",
            "avatar": "https://i.pravatar.cc/150?img=32",
            "rating": 4,
            "comment": "Clean, fast, and genuinely useful. The interface simply works and finding resources takes just a few clicks. Great for students who want quality material without spending money. Highly recommended!",
            "created_at": "Aug 17, 2026",
        },
        {
            "review_id": 4,
            "username": "hamza.sheikh",
            "full_name": "Hamza Sheikh",
            "avatar": "https://i.pravatar.cc/150?img=68",
            "rating": 5,
            "comment": "Superb quality books at zero cost — this is exactly what the internet should be about. DocoDive genuinely helps learners grow, and I've already learned more here in two months than from expensive paid courses.",
            "created_at": "Aug 16, 2026",
        },
        {
            "review_id": 5,
            "username": "zainab.ali",
            "full_name": "Zainab Ali",
            "avatar": "https://i.pravatar.cc/150?img=25",
            "rating": 4,
            "comment": "A very helpful platform. I love how easy it is to find exactly what I'm looking for, and the direct downloads save so much time. If the collection keeps growing like this, it will easily become the best free resource out there.",
            "created_at": "Aug 15, 2026",
        },
    ]

    data = {
        "total_books": BOOKS_BASE + real_books,
        "total_downloads": DOWNLOADS_BASE + real_downloads,
        "total_users": USERS_BASE + real_users,
        "total_categories": total_categories,
        "total_reviews": real_reviews,
        "recent_reviews": recent_reviews,
    }

    cache["ts"] = now
    cache["data"] = data
    return data

def is_official_user(user_id):
    official_id = get_site_setting("official_user_id")
    return official_id and str(user_id) == official_id


def is_moderator():
    if "user_id" in session and is_official_user(session["user_id"]):
        return True
    return False


def official_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            abort(403)
        if not is_official_user(session["user_id"]):
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@app.context_processor
def inject_common():
    return dict(
        current_user_is_official=is_official_user(session.get("user_id", 0)),
        is_moderator=is_moderator(),
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
    """Books younger than 7 days get small random growth every 6 hours."""
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT created_at, last_trickle_time
        FROM documents
        WHERE id = %s AND approved = 1
    """,
        (book_id,),
    )
    book = cur.fetchone()
    if not book:
        cur.close()
        return

    created_at = book[0]
    last_trickle = book[1]
    now = datetime.utcnow()

    if not created_at or created_at < now - timedelta(days=7):
        cur.close()
        return

    if last_trickle and last_trickle > now - timedelta(hours=6):
        cur.close()
        return

    dl_growth = random.randint(2, 8)
    vw_growth = random.randint(4, 16)

    cur.execute(
        """
        UPDATE documents
        SET download_count = download_count + %s,
            view_count = view_count + %s,
            last_trickle_time = %s
        WHERE id = %s
    """,
        (dl_growth, vw_growth, now, book_id),
    )
    mysql.connection.commit()
    cur.close()


# ================== R2 HELPER FUNCTIONS (Required) ==================
def extract_r2_key(url):
    """Extract the R2 object key from a public URL."""
    if not url:
        return None
    if R2_PUBLIC_BASE and url.startswith(R2_PUBLIC_BASE + "/"):
        return url.replace(R2_PUBLIC_BASE + "/", "", 1)
    return url


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
@cache.cached(timeout=600, unless=lambda: request.method == "POST")
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
                msg = "Invalid cover image content. Only JPEG, PNG, GIF, or WebP allowed."
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

        cur.execute(
            """
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, approved, uploaded_by, download_count, view_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """,
            (
                cat_id,
                display_title,
                pdf_url,
                author,
                description,
                image_url,
                "English",
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
    return render_template("user_upload.html", categories=categories)


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
        "qwerty", "asdf", "zxcv", "abcdef", "123456",
        "password", "admin", "administrator", "moderator",
        "official", "support", "test", "user", "login", "guest",
        "unknown", "abc", "root", "owner", "staff"
    ]
    for w in weak_usernames:
        if w in u:
            return "This username is too common or not allowed."

    return None

def _contains_reserved_word(username):
    u = username.lower()
    u = u.replace("0", "o").replace("1", "i").replace("3", "e").replace("4", "a").replace("5", "s").replace("7", "t").replace("$", "s").replace("@", "a")
    u = re.sub(r"[\s_.\-]+", "", u)

    reserved = os.getenv("RESERVED_USERNAMES", "")
    if not reserved:
        return False

    reserved_list = [r.strip().lower() for r in reserved.split(",") if r.strip()]

    for word in reserved_list:
        if u == word or u.startswith(word + "official") or u.startswith(word + "account") or word in u:
            return True

    return False
#-------------------- USERNAME SUGGESTIONS --------------------
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
        add(first + last)      # sufyankhan
        add(last + first)      # khansufyan
        add(first + last[0])   # sufyank
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
            return jsonify({
                "exists": False,
                "reserved": False,
                "format_error": True,
                "message": "Username must start with a letter and be 3-20 letters/numbers only."
            })

        # ---------- Reserved words ----------
        if _contains_reserved_word(value):
            return jsonify({
                "exists": True,
                "reserved": True,
                "message": "This username is not allowed. Please choose a different one."
            })

        # ---------- Quality check ----------
        quality = _username_quality_issue(value)
        if quality:
            return jsonify({
                "exists": False,
                "reserved": False,
                "simple": True,
                "message": quality,
                "suggestions": _generate_username_suggestions(value, first_name, last_name)
            })

        # ---------- DB existence ----------
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (value,))
        exists = cur.fetchone() is not None
        cur.close()

        suggestions = []
        if exists:
            suggestions = _generate_username_suggestions(value, first_name, last_name)

        return jsonify({
            "exists": exists,
            "reserved": False,
            "message": "Username already taken. Try a different one." if exists else "Username is available!",
            "suggestions": suggestions
        })

    elif field == "email":
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (value,))
        exists = cur.fetchone() is not None
        cur.close()
        return jsonify({
            "exists": exists,
            "message": "Email already registered." if exists else "Email is available!"
        })

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

    return render_template("forgot_password.html")


@app.route("/verify-code", methods=["POST"])
@limiter.limit(AUTH_RATELIMIT)
def verify_code():
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
    send_email_notification(
        "Reset Your Password - DocoDive",
        email,
        f"Use this link to reset your DocoDive password (valid for 30 minutes): {reset_link}",
        html_body=html_body,
    )
    return jsonify(
        {
            "success": True,
            "message": "A password reset link has been sent to your email.",
        }
    )


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit(AUTH_RATELIMIT)
def reset_password(token):
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, email, expires_at FROM password_resets WHERE token = %s", (token,)
    )
    row = cur.fetchone()
    if not row or row[2] < datetime.now():
        cur.close()
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if new_password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html", token=token)
        hashed = generate_password_hash(new_password)
        cur.execute("UPDATE users SET password = %s WHERE email = %s", (hashed, row[1]))
        cur.execute("DELETE FROM password_resets WHERE id = %s", (row[0],))
        mysql.connection.commit()
        cur.close()
        flash("Password updated successfully! Please login.", "success")
        return redirect(url_for("user_login"))

    cur.close()
    return render_template("reset_password.html", token=token)


# -------------------- BREVO WEBHOOK --------------------
@app.route("/api/brevo/webhook", methods=["POST"])
def brevo_webhook():
    secret = os.getenv("BREVO_WEBHOOK_SECRET")
    if secret:
        signature = request.headers.get("X-Webhook-Secret")
        if not signature or signature != secret:
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
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def google_callback():
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
    if not user_info.get("email"):
        emails_resp = oauth.github.get("user/emails")
        emails = emails_resp.json()
        primary = next((e["email"] for e in emails if e["primary"]), None)
        user_info["email"] = primary
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
    return render_template("400.html"), 400


@app.errorhandler(401)
def unauthorized(e):
    return render_template("401.html"), 401


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(e):
    trending_books = []
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link,
                   COALESCE(d.download_count, 0) as download_count,
                   COALESCE(d.view_count, 0) as view_count
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
                }
            )
    except Exception as e:
        app.logger.error(f"404 trending fetch failed: {e}")

    return render_template("404.html", trending_books=trending_books), 404


@app.errorhandler(429)
def too_many_requests(e):
    return render_template("429.html"), 429


@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500


@app.errorhandler(503)
def service_unavailable(e):
    return render_template("503.html"), 503

GENERIC_MODULES = [
    {
        "slug": "beginner",
        "title": "Beginner Guide",
        "icon": "bi-mortarboard",
        "color": "text-primary",
        "desc": "Start from zero",
        "tips": [
            "Understand the fundamentals first",
            "Follow a structured learning path",
            "Practice small examples daily",
            "Take notes and revise regularly",
            "Don't rush — build a strong base",
        ],
    },
    {
        "slug": "intermediate",
        "title": "Intermediate",
        "icon": "bi-graph-up-arrow",
        "color": "text-warning",
        "desc": "Level up your skills",
        "tips": [
            "Build real projects to apply knowledge",
            "Learn advanced concepts in depth",
            "Read documentation and source code",
            "Practice problem-solving consistently",
            "Review and refactor your code",
        ],
    },
    {
        "slug": "advanced",
        "title": "Advanced",
        "icon": "bi-rocket-takeoff",
        "color": "text-danger",
        "desc": "Master the field",
        "tips": [
            "Master optimization and best practices",
            "Deep dive into complex topics",
            "Contribute to open-source projects",
            "Explore industry-level case studies",
            "Keep updating with latest trends",
        ],
    },
    {
        "slug": "practice",
        "title": "Practice Resources",
        "icon": "bi-journal-check",
        "color": "text-success",
        "desc": "Exercises & quizzes",
        "tips": [
            "Solve problems and take quizzes",
            "Apply concepts in hands-on tasks",
            "Work on mini projects",
            "Join discussions and share solutions",
            "Track your progress weekly",
        ],
    },
]

PYTHON_BEGINNER_LESSONS = [
    {
        "id": 1,
        "title": "Python & Your First Program",
        "duration": "15 min",
        "objectives": ["Explain what Python is", "Run your first script", "Understand comments and indentation"],
        "explanation": "Python is a readable, beginner-friendly programming language used for web development, data analysis, automation, AI, and many other areas. In this lesson, you will create your first .py file, run it, and learn why indentation matters in Python.",
        "code": "# My first program\nprint(\"Hello Python\")\nprint(\"I am learning on DocoDive\")",
        "output": "Hello Python\nI am learning on DocoDive",
        "callout_type": "tip",
        "callout_text": "Python is case-sensitive: Print() and print() are different names.",
        "docs_url": "https://docs.python.org/3/tutorial/introduction.html",
        "docs_label": "Python introduction",
        "exercise_prompt": "Print your name, city, and age on three separate lines.",
        "exercise_hint": "Use print() three times, or use \\n to separate the lines.",
        "exercise_solution": "print(\"Sufyan\")\nprint(\"Karachi\")\nprint(19)",
    },
    {
        "id": 2,
        "title": "Variables & Basic Data Types",
        "duration": "15 min",
        "objectives": ["Create variables", "Use int, float, str, bool, None", "Check types with type()"],
        "explanation": "A variable is a named container that stores a value. In Python you assign with '='. Common data types are int (whole numbers), float (decimals), str (text), bool (True/False), and None (empty).",
        "code": "name = \"Sufyan\"\nage = 19\nheight = 5.9\nis_student = True\nnothing = None\nprint(name, type(name))\nprint(age, type(age))",
        "output": "Sufyan <class 'str'>\n19 <class 'int'>",
        "callout_type": "warning",
        "callout_text": "A variable name cannot start with a number. 2name is invalid, but name2 is fine.",
        "docs_url": "https://docs.python.org/3/tutorial/introduction.html#numbers",
        "docs_label": "Python numbers & variables",
        "exercise_prompt": "Create variables for your city, age, and height, then print them all.",
        "exercise_hint": "Assign three variables, then print(city, age, height).",
        "exercise_solution": "city = \"Karachi\"\nage = 19\nheight = 5.9\nprint(city, age, height)",
    },
    {
        "id": 3,
        "title": "Operators & Expressions",
        "duration": "20 min",
        "objectives": ["Use arithmetic operators", "Compare values", "Combine with logical operators"],
        "explanation": "Operators work on values: arithmetic (+, -, *, /, //, %), comparison (==, !=, >, <, >=, <=), and logical (and, or, not). These are the foundation for calculations and conditions.",
        "code": "price = 500\nquantity = 3\ntotal = price * quantity\nprint(total)\nprint(total > 1000)\nprint(quantity >= 3 and price > 100)",
        "output": "1500\nTrue\nTrue",
        "callout_type": "important",
        "callout_text": "The = sign assigns a value, while == compares two values. Do not mix them.",
        "docs_url": "https://docs.python.org/3/tutorial/introduction.html#using-python-as-a-calculator",
        "docs_label": "Python operators",
        "exercise_prompt": "Write a program that prints 10 % 3 and 10 // 3.",
        "exercise_hint": "% gives the remainder and // gives floor division.",
        "exercise_solution": "print(10 % 3)\nprint(10 // 3)",
    },
    {
        "id": 4,
        "title": "Strings",
        "duration": "20 min",
        "objectives": ["Index and slice strings", "Use string methods", "Format with f-strings"],
        "explanation": "Strings are sequences of characters. Indexing starts at 0, and slicing returns a range. Methods like lower(), upper(), strip(), replace(), split(), and join() transform text. f-strings are the modern way to format strings.",
        "code": "text = \"  Hello DocoDive  \"\nclean = text.strip().upper()\nprint(clean)\nname = \"Sufyan\"\nprint(f\"Welcome, {name}!\")",
        "output": "HELLO DOCODIVE\nWelcome, Sufyan!",
        "callout_type": "best",
        "callout_text": "Use f-strings for clear, readable string formatting.",
        "docs_url": "https://docs.python.org/3/tutorial/introduction.html#strings",
        "docs_label": "Python strings",
        "exercise_prompt": "Print your name in uppercase and report its length.",
        "exercise_hint": "Use name.upper() and len(name).",
        "exercise_solution": "name = \"Sufyan\"\nprint(name.upper())\nprint(len(name))",
    },
    {
        "id": 5,
        "title": "Input & Type Conversion",
        "duration": "15 min",
        "objectives": ["Get user input", "Convert types with int() and float()", "Avoid conversion errors"],
        "explanation": "input() always returns a string, even when the user types a number. To do math you must convert with int() or float(). A wrong conversion raises ValueError, so basic validation matters.",
        "code": "age_text = input(\"Age: \")\nage = int(age_text)\nprint(\"Next year:\", age + 1)",
        "output": "Age: 19\nNext year: 20",
        "callout_type": "warning",
        "callout_text": "Never do math on input() without converting first — \"19\" + 1 will crash.",
        "docs_url": "https://docs.python.org/3/tutorial/inputoutput.html",
        "docs_label": "Python input & output",
        "exercise_prompt": "Ask the user for two numbers and print their sum.",
        "exercise_hint": "Convert both with int(input(...)), then add them.",
        "exercise_solution": "a = int(input(\"First: \"))\nb = int(input(\"Second: \"))\nprint(a + b)",
    },
    {
        "id": 6,
        "title": "Conditions",
        "duration": "20 min",
        "objectives": ["Use if / elif / else", "Nest conditions", "Write conditional expressions"],
        "explanation": "Conditions let a program make decisions. if checks the first condition, elif checks more, and else is the fallback. Indentation tells Python which block each line belongs to.",
        "code": "score = 85\nif score >= 90:\n    print(\"A\")\nelif score >= 75:\n    print(\"B\")\nelse:\n    print(\"C\")",
        "output": "B",
        "callout_type": "tip",
        "callout_text": "Lines after a colon (:) must be indented with 4 spaces.",
        "docs_url": "https://docs.python.org/3/tutorial/controlflow.html#if-statements",
        "docs_label": "Python if statements",
        "exercise_prompt": "Print 'Adult' if age is 18 or above, otherwise print 'Minor'.",
        "exercise_hint": "Use if age >= 18 and an else block.",
        "exercise_solution": "age = 19\nprint(\"Adult\" if age >= 18 else \"Minor\")",
    },
    {
        "id": 7,
        "title": "Loops",
        "duration": "20 min",
        "objectives": ["Use for and while", "Loop with range()", "Use break, continue, pass"],
        "explanation": "Loops repeat code. A for loop iterates over a sequence, and a while loop runs until its condition is false. range() generates numbers. break exits a loop, continue skips to the next iteration.",
        "code": "for i in range(3):\n    print(i)\n\nn = 0\nwhile n < 3:\n    n += 1\n    if n == 2:\n        continue\n    print(n)",
        "output": "0\n1\n2\n1\n3",
        "callout_type": "important",
        "callout_text": "If a while condition never becomes false, you get an infinite loop.",
        "docs_url": "https://docs.python.org/3/tutorial/controlflow.html#for-statements",
        "docs_label": "Python loops",
        "exercise_prompt": "Print only the odd numbers from 1 to 10.",
        "exercise_hint": "Use range(1, 11, 2).",
        "exercise_solution": "for n in range(1, 11, 2):\n    print(n)",
    },
    {
        "id": 8,
        "title": "Lists",
        "duration": "25 min",
        "objectives": ["Create and mutate lists", "Slice lists", "Use append, insert, remove, sort"],
        "explanation": "A list is an ordered, mutable collection. Indexing starts at 0, and negative indices count from the end. append() adds an item, pop() removes one, and sort() arranges the list.",
        "code": "fruits = [\"mango\", \"apple\", \"banana\"]\nfruits.append(\"grape\")\nfruits.sort()\nprint(fruits)\nprint(fruits[0], fruits[-1])",
        "output": "['apple', 'banana', 'grape', 'mango']\napple mango",
        "callout_type": "tip",
        "callout_text": "Start with simple list operations first. List comprehensions will be introduced later.",
        "docs_url": "https://docs.python.org/3/tutorial/introduction.html#lists",
        "docs_label": "Python lists",
        "exercise_prompt": "Create a list of even numbers from 3 to 15.",
        "exercise_hint": "Loop through the range and append only even numbers.",
        "exercise_solution": "evens = []\nfor n in range(3, 16):\n    if n % 2 == 0:\n        evens.append(n)\nprint(evens)",
    },
    {
        "id": 9,
        "title": "Tuples, Sets & Dictionaries",
        "duration": "25 min",
        "objectives": ["Use tuples for fixed data", "Use sets for unique values", "Store key-value pairs in dicts"],
        "explanation": "A tuple is an immutable ordered collection, a set stores unique unordered values, and a dictionary maps keys to values. Fixed data -> tuple, unique items -> set, mapping -> dict.",
        "code": "point = (10, 20)\nskills = {\"Python\", \"HTML\", \"CSS\"}\nstudent = {\"name\": \"Sufyan\", \"age\": 19}\nprint(point[0])\nprint(skills)\nprint(student[\"name\"])",
        "output": "10\n{'Python', 'HTML', 'CSS'}\nSufyan",
        "callout_type": "tip",
        "callout_text": "For missing dict keys, use .get(\"key\") so the program does not crash.",
        "docs_url": "https://docs.python.org/3/tutorial/datastructures.html",
        "docs_label": "Python data structures",
        "exercise_prompt": "Create a dict with 'name' and 'score', then print the score.",
        "exercise_hint": "Use student['score'].",
        "exercise_solution": "s = {\"name\": \"Sufyan\", \"score\": 95}\nprint(s[\"score\"])",
    },
    {
        "id": 10,
        "title": "Functions",
        "duration": "25 min",
        "objectives": ["Define functions with def", "Use parameters and return", "Use default and keyword arguments"],
        "explanation": "A function is a reusable block defined with def. Parameters are inputs and return sends a value back. Default arguments preset values, and keyword arguments make calls clearer.",
        "code": "def greet(name, greeting=\"Hello\"):\n    return f\"{greeting}, {name}!\"\n\nprint(greet(\"Sufyan\"))\nprint(greet(\"Sufyan\", greeting=\"Hi\"))",
        "output": "Hello, Sufyan!\nHi, Sufyan!",
        "callout_type": "important",
        "callout_text": "Without a return statement, a function returns None.",
        "docs_url": "https://docs.python.org/3/tutorial/controlflow.html#defining-functions",
        "docs_label": "Python functions",
        "exercise_prompt": "Write an add(a, b) function that returns the sum.",
        "exercise_hint": "Define it with def and return a + b.",
        "exercise_solution": "def add(a, b):\n    return a + b\nprint(add(3, 7))",
    },
    {
        "id": 11,
        "title": "Function Power-Up",
        "duration": "25 min",
        "objectives": ["Use *args and **kwargs", "Write lambda functions", "Use map, filter, zip, enumerate"],
        "explanation": "*args accepts arbitrary positional arguments, and **kwargs accepts arbitrary keyword arguments. A lambda is a one-line anonymous function. map and filter transform collections, zip iterates in parallel, and enumerate adds an index.",
        "code": "nums = [1, 2, 3, 4]\nsquared = list(map(lambda x: x**2, nums))\nevens = list(filter(lambda x: x % 2 == 0, nums))\nprint(squared)\nprint(evens)",
        "output": "[1, 4, 9, 16]\n[2, 4]",
        "callout_type": "best",
        "callout_text": "Use the clearest approach for the reader. For simple transformations, a list comprehension is often easier to read than map() with a lambda.",
        "docs_url": "https://docs.python.org/3/tutorial/controlflow.html#more-on-defining-functions",
        "docs_label": "More on functions",
        "exercise_prompt": "Use zip to pair two lists and print the result.",
        "exercise_hint": "Try list(zip(names, ages)).",
        "exercise_solution": "names = [\"A\", \"B\"]\nages = [19, 20]\nprint(list(zip(names, ages)))",
    },
    {
        "id": 12,
        "title": "List, Set & Dictionary Comprehensions",
        "duration": "20 min",
        "objectives": ["Write list comprehensions", "Write dict comprehensions", "Use nested comprehensions"],
        "explanation": "Comprehensions build collections in one clean line. A list comprehension is [expr for item in iterable if condition], and a dict comprehension is {key: value for ...}.",
        "code": "nums = [1, 2, 3, 4]\nsquares = [n**2 for n in nums]\neven_squares = {n: n**2 for n in nums if n % 2 == 0}\nprint(squares)\nprint(even_squares)",
        "output": "[1, 4, 9, 16]\n{2: 4, 4: 16}",
        "callout_type": "tip",
        "callout_text": "If a comprehension gets too long, use a normal loop for readability.",
        "docs_url": "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions",
        "docs_label": "List comprehensions",
        "exercise_prompt": "Build a dict mapping each name to its length.",
        "exercise_hint": "Use {name: len(name) for name in names}.",
        "exercise_solution": "names = [\"Ali\", \"Sufyan\"]\nprint({n: len(n) for n in names})",
    },
    {
        "id": 13,
        "title": "Files & Directories",
        "duration": "25 min",
        "objectives": ["Read and write text files", "Use the with statement", "Work with JSON and pathlib"],
        "explanation": "Files are central to real programs. with open() automatically closes the file. Modes: r read, w write, a append. JSON stores structured data, and pathlib makes paths clean and safe.",
        "code": "from pathlib import Path\nimport json\n\ndata = {\"name\": \"Sufyan\", \"age\": 19}\nPath(\"data.json\").write_text(json.dumps(data))\nprint(Path(\"data.json\").read_text())",
        "output": "{\"name\": \"Sufyan\", \"age\": 19}",
        "callout_type": "best",
        "callout_text": "Use with open(...) so you never forget to close a file.",
        "docs_url": "https://docs.python.org/3/tutorial/inputoutput.html#reading-and-writing-files",
        "docs_label": "Python file I/O",
        "exercise_prompt": "Create a notes.txt file, write your name in it, then read it back.",
        "exercise_hint": "Open with 'w' to write and 'r' to read.",
        "exercise_solution": "with open('notes.txt', 'w') as f:\n    f.write('Sufyan')\nwith open('notes.txt') as f:\n    print(f.read())",
    },
    {
        "id": 14,
        "title": "Errors & Exception Handling",
        "duration": "20 min",
        "objectives": ["Understand syntax vs runtime errors", "Use try/except/else/finally", "Raise exceptions"],
        "explanation": "Syntax errors happen while writing code; runtime errors happen while it runs. try runs risky code, except catches errors, else runs on success, and finally always runs. raise lets you fail deliberately.",
        "code": "try:\n    num = int(input(\"Number: \"))\n    print(10 / num)\nexcept ValueError:\n    print(\"Invalid number\")\nexcept ZeroDivisionError:\n    print(\"Cannot divide by zero\")\nelse:\n    print(\"Success\")",
        "output": "Number: 0\nCannot divide by zero",
        "callout_type": "warning",
        "callout_text": "A bare except: hides every error. Catch specific exceptions instead.",
        "docs_url": "https://docs.python.org/3/tutorial/errors.html",
        "docs_label": "Python errors & exceptions",
        "exercise_prompt": "Write a safe division function that handles zero.",
        "exercise_hint": "Use try/except ZeroDivisionError.",
        "exercise_solution": "def safe_div(a, b):\n    try:\n        return a / b\n    except ZeroDivisionError:\n        return None\nprint(safe_div(10, 0))",
    },
    {
        "id": 15,
        "title": "Modules & Packages",
        "duration": "20 min",
        "objectives": ["Import built-in modules", "Create custom modules", "Use if __name__ == '__main__'"],
        "explanation": "A module is a .py file you can import. A package is a folder of modules. import math brings in the whole module; from math import sqrt brings one name. The __name__ == '__main__' guard runs code only on direct execution.",
        "code": "import math\nprint(math.sqrt(16))\n\nif __name__ == \"__main__\":\n    print(\"Direct run\")",
        "output": "4.0\nDirect run",
        "callout_type": "tip",
        "callout_text": "Add an if __name__ == '__main__' guard to every reusable file.",
        "docs_url": "https://docs.python.org/3/tutorial/modules.html",
        "docs_label": "Python modules",
        "exercise_prompt": "Use math to print the square root of 25 and pi.",
        "exercise_hint": "Use math.sqrt(25) and math.pi.",
        "exercise_solution": "import math\nprint(math.sqrt(25))\nprint(math.pi)",
    },
    {
        "id": 16,
        "title": "Useful Standard Library",
        "duration": "25 min",
        "objectives": ["Use math, random, datetime", "Use pathlib and os", "Use json, re and collections"],
        "explanation": "Python's standard library is huge. Beginners should know representative modules: math for calculations, random for randomness, datetime for dates, pathlib for files, json for data, and collections for useful containers.",
        "code": "import random\nimport datetime\nfrom collections import Counter\n\nprint(random.randint(1, 10))\nprint(datetime.date.today())\nprint(Counter([\"a\", \"b\", \"a\", \"c\"]))",
        "output": "Example output (your random number will vary):\n7\n2026-08-23\nCounter({'a': 2, 'b': 1, 'c': 1})",
        "callout_type": "best",
        "callout_text": "Learn the standard library first — many problems need no external package.",
        "docs_url": "https://docs.python.org/3/library/index.html",
        "docs_label": "Python standard library",
        "exercise_prompt": "Generate a random 10-character token using letters and digits.",
        "exercise_hint": "Combine string.ascii_letters + string.digits with random.choices.",
        "exercise_solution": "import random\nimport string\nchars = string.ascii_letters + string.digits\nprint(''.join(random.choices(chars, k=10)))",
    },
    {
        "id": 17,
        "title": "Object-Oriented Python Basics",
        "duration": "25 min",
        "objectives": ["Define classes and objects", "Use attributes and methods", "Understand __init__ and self"],
        "explanation": "OOP organizes code into objects. A class is a blueprint and an object is an instance of it. __init__ is the constructor that initializes the object. self refers to the instance, and methods are functions inside the class.",
        "code": "class Student:\n    def __init__(self, name, age):\n        self.name = name\n        self.age = age\n\n    def greet(self):\n        return f\"Hi, I am {self.name}\"\n\ns = Student(\"Sufyan\", 19)\nprint(s.greet())",
        "output": "Hi, I am Sufyan",
        "callout_type": "important",
        "callout_text": "self is the first parameter of every method — do not forget it.",
        "docs_url": "https://docs.python.org/3/tutorial/classes.html",
        "docs_label": "Python classes",
        "exercise_prompt": "Create a Car class with brand and speed, and a method that prints them.",
        "exercise_hint": "Set self.brand and self.speed inside __init__.",
        "exercise_solution": "class Car:\n    def __init__(self, brand, speed):\n        self.brand = brand\n        self.speed = speed\n    def show(self):\n        print(self.brand, self.speed)\nCar(\"Toyota\", 120).show()",
    },
    {
        "id": 18,
        "title": "Debugging & Writing Better Python",
        "duration": "20 min",
        "objectives": ["Read tracebacks", "Debug with print and pdb", "Follow PEP 8 basics"],
        "explanation": "Errors are inevitable — learn to read a traceback. print debugging is simple and effective; pdb is the interactive debugger. For clean code, use meaningful names, small functions, and comments only when needed.",
        "code": "def divide(a, b):\n    breakpoint()  # pauses execution here\n    return a / b\n\nprint(divide(10, 2))",
        "output": "Execution pauses at breakpoint(). Type 'c' to continue debugging.",
        "callout_type": "tip",
        "callout_text": "Read a traceback from bottom to top — the last line is the actual error.",
        "docs_url": "https://docs.python.org/3/library/pdb.html",
        "docs_label": "Python debugger (pdb)",
        "exercise_prompt": "Write a function that returns None and prints a clear message for invalid input.",
        "exercise_hint": "Use try/except to handle ValueError.",
        "exercise_solution": "def safe_int(value):\n    try:\n        return int(value)\n    except ValueError:\n        print(f\"'{value}' is not a number\")\n        return None\nsafe_int(\"abc\")",
    },
    {
        "id": 19,
        "title": "Virtual Environments, pip & Project Structure",
        "duration": "25 min",
        "objectives": ["Create virtual environments", "Install packages with pip", "Use requirements.txt"],
        "explanation": "Real projects use isolated environments. python -m venv creates one, python -m pip installs packages, and requirements.txt freezes dependencies. Project folders and .gitignore keep things organized.",
        "code": "# Create a virtual environment\npython -m venv .venv\n\n# Activate (Windows PowerShell)\n.venv\\Scripts\\Activate.ps1\n\n# Activate (macOS / Linux)\nsource .venv/bin/activate\n\n# Install a package\npython -m pip install requests\n\n# Save dependencies\npython -m pip freeze > requirements.txt",
        "output": "Virtual environment ready. Package installed and requirements.txt saved.",
        "callout_type": "best",
        "callout_text": "Never install packages into the global Python — always use a virtual environment.",
        "docs_url": "https://docs.python.org/3/tutorial/venv.html",
        "docs_label": "Python virtual environments",
        "exercise_prompt": "Write the command that creates a virtual environment named .venv.",
        "exercise_hint": "It starts with python -m venv.",
        "exercise_solution": "python -m venv .venv",
    },
    {
        "id": 20,
        "title": "Capstone: Student Management System",
        "duration": "45 min",
        "objectives": ["Combine all beginner concepts", "Build a full CLI project", "Use files, JSON, functions and OOP"],
        "explanation": "This final project combines variables, loops, conditions, functions, lists, dictionaries, files, JSON, exceptions, and OOP. You will build a CLI system that can add, view, search, update, delete, and save students to JSON.",
        "code": "import json\nfrom pathlib import Path\n\nclass StudentManager:\n    def __init__(self, path=\"students.json\"):\n        self.path = Path(path)\n        self.students = json.loads(self.path.read_text()) if self.path.exists() else []\n\n    def add(self, name, age):\n        self.students.append({\"name\": name, \"age\": age})\n        self.save()\n\n    def save(self):\n        self.path.write_text(json.dumps(self.students, indent=2))\n\nsm = StudentManager()\nsm.add(\"Sufyan\", 19)\nprint(sm.students)",
        "output": "[{'name': 'Sufyan', 'age': 19}]",
        "callout_type": "important",
        "callout_text": "Write small functions and put each feature in its own function — debugging becomes much easier.",
        "docs_url": "https://docs.python.org/3/tutorial/datastructures.html",
        "docs_label": "Python data structures (revision)",
        "code_label": "Starter Code",
        "exercise_prompt": "Add view() and delete(name) methods to StudentManager.",
        "exercise_hint": "view() prints all students; delete() removes by name and saves.",
        "exercise_solution": "def view(self):\n    for s in self.students:\n        print(s)\ndef delete(self, name):\n    self.students = [s for s in self.students if s[\"name\"] != name]\n    self.save()",
    },
]

# ================== PYTHON INTERMEDIATE GUIDE — LESSONS DATA ==================
PYTHON_INTERMEDIATE_LESSONS = [
    {
        "id": 1,
        "title": "Advanced Functions",
        "duration": "25 min",
        "prerequisites": "Beginner functions lesson",
        "objectives": [
            "Accept any number of arguments with *args",
            "Accept keyword arguments with **kwargs",
            "Return multiple values from a function",
        ],
        "explanation": "Beginner functions take a fixed number of parameters. Intermediate functions handle flexible input: *args collects positional arguments into a tuple, **kwargs collects keyword arguments into a dict, and Python lets you return multiple values as a tuple.",
        "code": "def describe_person(name, *scores, **details):\n    print(name)\n    print(\"Scores:\", scores)\n    print(\"Details:\", details)\n    return len(scores), sum(scores)\n\ncount, total = describe_person(\"Sufyan\", 85, 90, 78, city=\"Karachi\", role=\"dev\")\nprint(count, total)",
        "output": "Sufyan\nScores: (85, 90, 78)\nDetails: {'city': 'Karachi', 'role': 'dev'}\n3 253",
        "callout_type": "tip",
        "callout_text": "The order matters: normal parameters first, then *args, then **kwargs.",
        "docs_url": "https://docs.python.org/3/tutorial/controlflow.html#arbitrary-argument-lists",
        "docs_label": "Arbitrary argument lists",
        "exercise_prompt": "Write a function that takes a name and any number of marks, then returns the average.",
        "exercise_hint": "Use *marks, sum(marks) / len(marks), and handle zero marks.",
        "exercise_solution": "def average(name, *marks):\n    if not marks:\n        return 0\n    return sum(marks) / len(marks)\nprint(average(\"Ali\", 80, 90, 100))",
    },
    {
        "id": 2,
        "title": "Scope & Closures",
        "duration": "25 min",
        "prerequisites": "Functions, variables",
        "objectives": [
            "Understand local, enclosing, and global scope",
            "Use global and nonlocal",
            "Build a closure that remembers state",
        ],
        "explanation": "Scope decides where a variable is visible. A variable inside a function is local. nonlocal modifies a variable in an outer function, and global modifies a module-level variable. A closure is an inner function that remembers variables from its outer function even after that function returns.",
        "code": "def make_counter():\n    count = 0\n    def increment():\n        nonlocal count\n        count += 1\n        return count\n    return increment\n\ncounter = make_counter()\nprint(counter())\nprint(counter())\nprint(counter())",
        "output": "1\n2\n3",
        "callout_type": "important",
        "callout_text": "A closure keeps the outer function's state alive. Each call to make_counter() creates a fresh, independent counter.",
        "docs_url": "https://docs.python.org/3/tutorial/classes.html#python-scopes-and-namespaces",
        "docs_label": "Python scopes",
        "exercise_prompt": "Create a counter that increments by 5 each time it is called.",
        "exercise_hint": "Inside the inner function, use nonlocal count; count += 5.",
        "exercise_solution": "def make_step_counter(step):\n    total = 0\n    def step_up():\n        nonlocal total\n        total += step\n        return total\n    return step_up\nc = make_step_counter(5)\nprint(c())\nprint(c())",
    },
    {
        "id": 3,
        "title": "Decorators",
        "duration": "30 min",
        "prerequisites": "Functions, closures",
        "objectives": [
            "Explain what a decorator is",
            "Write a simple decorator with @",
            "Pass arguments through with *args and **kwargs",
        ],
        "explanation": "A decorator is a function that wraps another function to add behaviour without changing its code. You apply it with @decorator above the function. Inside, the wrapper calls the original function and can run code before or after it.",
        "code": "import functools\n\ndef announce(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        print(f\"Calling {func.__name__}...\")\n        result = func(*args, **kwargs)\n        print(\"Finished.\")\n        return result\n    return wrapper\n\n@announce\ndef add(a, b):\n    return a + b\n\nprint(add(3, 4))",
        "output": "Calling add...\nFinished.\n7",
        "callout_type": "best",
        "callout_text": "Always use @functools.wraps(func) inside a decorator so the wrapped function keeps its original name and docstring.",
        "docs_url": "https://docs.python.org/3/glossary.html#term-decorator",
        "docs_label": "Decorators",
        "exercise_prompt": "Write a decorator that prints the return value of a function after it runs.",
        "exercise_hint": "Inside wrapper, store the result, print(result), then return it.",
        "exercise_solution": "import functools\n\ndef show_result(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        result = func(*args, **kwargs)\n        print(\"Result:\", result)\n        return result\n    return wrapper\n\n@show_result\ndef double(x):\n    return x * 2\n\ndouble(21)",
    },
    {
        "id": 4,
        "title": "functools Tools",
        "duration": "25 min",
        "prerequisites": "Decorators, functions",
        "objectives": [
            "Use lru_cache to speed up repeated calls",
            "Use partial to pre-fill function arguments",
            "Use reduce to combine values",
        ],
        "explanation": "The functools module provides powerful utilities for functions. lru_cache memoizes results so expensive calls run once. partial freezes some arguments, creating a simpler function. reduce repeatedly applies a function to combine values in a sequence.",
        "code": "from functools import lru_cache, partial, reduce\n\n@lru_cache(maxsize=None)\ndef fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n\nprint(fib(30))\n\nadd_five = partial(lambda a, b: a + b, 5)\nprint(add_five(10))\n\nprint(reduce(lambda a, b: a * b, [1, 2, 3, 4]))",
        "output": "832040\n15\n24",
        "callout_type": "tip",
        "callout_text": "lru_cache is great for recursive functions like fibonacci — without it, fib(30) would be extremely slow.",
        "docs_url": "https://docs.python.org/3/library/functools.html",
        "docs_label": "functools module",
        "exercise_prompt": "Use partial to create a function that multiplies any number by 3.",
        "exercise_hint": "partial(lambda a, b: a * b, 3).",
        "exercise_solution": "from functools import partial\ntriple = partial(lambda a, b: a * b, 3)\nprint(triple(7))",
    },
    {
        "id": 5,
        "title": "Advanced Collections",
        "duration": "25 min",
        "prerequisites": "Lists, dictionaries, sets",
        "objectives": [
            "Use defaultdict to avoid key errors",
            "Use Counter to count items fast",
            "Use deque for fast appends and pops",
        ],
        "explanation": "collections offers specialised containers. defaultdict provides a default value for missing keys. Counter counts hashable items into a dict-like object. deque is a double-ended queue with fast operations on both ends — better than a list for queues.",
        "code": "from collections import defaultdict, Counter, deque\n\nword_count = defaultdict(int)\nfor word in [\"a\", \"b\", \"a\", \"c\", \"a\"]:\n    word_count[word] += 1\nprint(dict(word_count))\n\nprint(Counter([\"apple\", \"apple\", \"banana\"]))\n\nd = deque([1, 2, 3])\nd.appendleft(0)\nd.append(4)\nprint(d)",
        "output": "{'a': 3, 'b': 1, 'c': 1}\nCounter({'apple': 2, 'banana': 1})\ndeque([0, 1, 2, 3, 4])",
        "callout_type": "best",
        "callout_text": "Use Counter for frequency counting instead of writing a manual loop with a dict.",
        "docs_url": "https://docs.python.org/3/library/collections.html",
        "docs_label": "collections module",
        "exercise_prompt": "Create a defaultdict(list) and append two values to the same missing key.",
        "exercise_hint": "d = defaultdict(list); d['x'].append(1); d['x'].append(2).",
        "exercise_solution": "from collections import defaultdict\nd = defaultdict(list)\nd['x'].append(1)\nd['x'].append(2)\nprint(d['x'])",
    },
    {
        "id": 6,
        "title": "Iterators",
        "duration": "25 min",
        "prerequisites": "Loops, lists",
        "objectives": [
            "Understand iter() and next()",
            "Build a custom iterator class",
            "Handle StopIteration",
        ],
        "explanation": "An iterator is an object that produces values one at a time. iter() converts an iterable into an iterator. next() returns the next value and raises StopIteration when done. Custom iterators implement __iter__ and __next__.",
        "code": "class Countdown:\n    def __init__(self, start):\n        self.current = start\n\n    def __iter__(self):\n        return self\n\n    def __next__(self):\n        if self.current < 0:\n            raise StopIteration\n        value = self.current\n        self.current -= 1\n        return value\n\nfor n in Countdown(3):\n    print(n)",
        "output": "3\n2\n1\n0",
        "callout_type": "important",
        "callout_text": "A for loop automatically calls iter() and next(), and catches StopIteration to end the loop.",
        "docs_url": "https://docs.python.org/3/tutorial/classes.html#iterators",
        "docs_label": "Iterators",
        "exercise_prompt": "Create an iterator that counts up from 1 to 5.",
        "exercise_hint": "In __next__, stop when current exceeds 5.",
        "exercise_solution": "class CountUp:\n    def __init__(self):\n        self.current = 0\n    def __iter__(self):\n        return self\n    def __next__(self):\n        self.current += 1\n        if self.current > 5:\n            raise StopIteration\n        return self.current\nfor n in CountUp():\n    print(n)",
    },
    {
        "id": 7,
        "title": "Generators",
        "duration": "30 min",
        "prerequisites": "Functions, iterators",
        "objectives": [
            "Use yield to create a generator",
            "Understand lazy evaluation and memory savings",
            "Use yield from and generator expressions",
        ],
        "explanation": "A generator is a function that uses yield instead of return. It produces values lazily — one at a time — so large sequences don't consume memory. yield from delegates to another generator, and generator expressions are like list comprehensions but lazy.",
        "code": "def squares(limit):\n    for n in range(1, limit + 1):\n        yield n ** 2\n\nfor value in squares(5):\n    print(value)\n\nprint(sum(x for x in range(1, 101)))",
        "output": "1\n4\n9\n16\n25\n5050",
        "callout_type": "best",
        "callout_text": "Use a generator when reading large files or producing long sequences — it keeps memory usage tiny.",
        "docs_url": "https://docs.python.org/3/tutorial/classes.html#generators",
        "docs_label": "Generators",
        "exercise_prompt": "Write a generator that yields only even numbers up to 10.",
        "exercise_hint": "Loop and yield n when n % 2 == 0.",
        "exercise_solution": "def evens(limit):\n    for n in range(limit + 1):\n        if n % 2 == 0:\n            yield n\nprint(list(evens(10)))",
    },
    {
        "id": 8,
        "title": "Comprehensions Deep Dive",
        "duration": "25 min",
        "prerequisites": "Lists, dictionaries, generators",
        "objectives": [
            "Write nested comprehensions",
            "Add conditions to comprehensions",
            "Compare comprehensions with map and filter",
        ],
        "explanation": "Comprehensions build collections in one readable expression. You can nest loops, add if conditions, and choose between list, dict, and set forms. For simple transformations they are clearer than map/filter; for complex logic, a normal loop is better.",
        "code": "matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]\nflat = [n for row in matrix for n in row]\nprint(flat)\n\nevens = [n for n in range(10) if n % 2 == 0]\nprint(evens)\n\nword_lengths = {w: len(w) for w in [\"go\", \"python\", \"code\"]}\nprint(word_lengths)",
        "output": "[1, 2, 3, 4, 5, 6, 7, 8, 9]\n[0, 2, 4, 6, 8]\n{'go': 2, 'python': 6, 'code': 4}",
        "callout_type": "tip",
        "callout_text": "If a comprehension is hard to read, break it into a normal loop — readability beats cleverness.",
        "docs_url": "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions",
        "docs_label": "List comprehensions",
        "exercise_prompt": "Flatten a 2x2 matrix and keep only odd numbers.",
        "exercise_hint": "Combine two for clauses and an if condition.",
        "exercise_solution": "matrix = [[1, 2], [3, 4]]\nresult = [n for row in matrix for n in row if n % 2 == 1]\nprint(result)",
    },
    {
        "id": 9,
        "title": "Class Methods & Static Methods",
        "duration": "25 min",
        "prerequisites": "OOP basics",
        "objectives": [
            "Use @classmethod and cls",
            "Use @staticmethod",
            "Build factory methods",
        ],
        "explanation": "Instance methods take self. Class methods take cls and can create objects — useful for alternate constructors (factory methods). Static methods take neither self nor cls and behave like plain functions placed inside a class for organisation.",
        "code": "class Employee:\n    company = \"DocoDive\"\n\n    def __init__(self, name, salary):\n        self.name = name\n        self.salary = salary\n\n    @classmethod\n    def from_string(cls, text):\n        name, salary = text.split(\"-\")\n        return cls(name, int(salary))\n\n    @staticmethod\n    def is_valid_salary(salary):\n        return salary > 0\n\ne = Employee.from_string(\"Sufyan-50000\")\nprint(e.name, e.salary, e.company)\nprint(Employee.is_valid_salary(50000))",
        "output": "Sufyan 50000 DocoDive\nTrue",
        "callout_type": "best",
        "callout_text": "Use a classmethod factory when you need multiple ways to create objects from different input formats.",
        "docs_url": "https://docs.python.org/3/tutorial/classes.html#class-and-instance-variables",
        "docs_label": "Class and instance variables",
        "exercise_prompt": "Add a classmethod that creates an Employee from a dict.",
        "exercise_hint": "Accept a dict and return cls(d['name'], d['salary']).",
        "exercise_solution": "class Employee:\n    def __init__(self, name, salary):\n        self.name = name\n        self.salary = salary\n    @classmethod\n    def from_dict(cls, data):\n        return cls(data[\"name\"], data[\"salary\"])\ne = Employee.from_dict({\"name\": \"Ali\", \"salary\": 40000})\nprint(e.name, e.salary)",
    },
    {
        "id": 10,
        "title": "Properties",
        "duration": "25 min",
        "prerequisites": "OOP basics",
        "objectives": [
            "Use @property for read-only access",
            "Add setters with validation",
            "Use deleters",
        ],
        "explanation": "Properties let you control attribute access. @property exposes a method as an attribute. The @setter validates values before assigning. This gives you clean attribute syntax with custom logic behind the scenes.",
        "code": "class Circle:\n    def __init__(self, radius):\n        self._radius = radius\n\n    @property\n    def radius(self):\n        return self._radius\n\n    @radius.setter\n    def radius(self, value):\n        if value <= 0:\n            raise ValueError(\"Radius must be positive\")\n        self._radius = value\n\n    @property\n    def area(self):\n        return 3.14159 * self._radius ** 2\n\nc = Circle(5)\nprint(c.area)\nc.radius = 10\nprint(c.area)",
        "output": "78.53975\n314.159",
        "callout_type": "important",
        "callout_text": "Use properties to keep a clean public API while hiding validation or computed values inside the class.",
        "docs_url": "https://docs.python.org/3/library/functions.html#property",
        "docs_label": "property function",
        "exercise_prompt": "Create a Temperature class where the setter rejects values below -273.",
        "exercise_hint": "Raise ValueError when value < -273.",
        "exercise_solution": "class Temperature:\n    def __init__(self, c):\n        self.celsius = c\n    @property\n    def celsius(self):\n        return self._celsius\n    @celsius.setter\n    def celsius(self, value):\n        if value < -273:\n            raise ValueError(\"Too cold\")\n        self._celsius = value\nt = Temperature(25)\nprint(t.celsius)",
    },
    {
        "id": 11,
        "title": "Inheritance",
        "duration": "30 min",
        "prerequisites": "OOP basics, class methods",
        "objectives": [
            "Create subclasses with super()",
            "Override parent methods",
            "Use isinstance and issubclass",
        ],
        "explanation": "Inheritance lets a class reuse and extend another class. The child class inherits methods and attributes, can override them, and can call the parent with super(). isinstance checks an object's type, issubclass checks class relationships.",
        "code": "class Animal:\n    def __init__(self, name):\n        self.name = name\n\n    def speak(self):\n        return \"...\"\n\nclass Dog(Animal):\n    def speak(self):\n        return f\"{self.name} says Woof!\"\n\nclass Cat(Animal):\n    def speak(self):\n        return f\"{self.name} says Meow!\"\n\nd = Dog(\"Rex\")\nc = Cat(\"Milo\")\nprint(d.speak())\nprint(c.speak())\nprint(isinstance(d, Animal), issubclass(Dog, Animal))",
        "output": "Rex says Woof!\nMilo says Meow!\nTrue True",
        "callout_type": "best",
        "callout_text": "Override only the methods that differ. Reuse everything else from the parent — that's the whole point of inheritance.",
        "docs_url": "https://docs.python.org/3/tutorial/classes.html#inheritance",
        "docs_label": "Inheritance",
        "exercise_prompt": "Create a Bird subclass whose speak() returns 'tweet' with the name.",
        "exercise_hint": "Override speak() and use self.name.",
        "exercise_solution": "class Animal:\n    def __init__(self, name):\n        self.name = name\n    def speak(self):\n        return \"...\"\nclass Bird(Animal):\n    def speak(self):\n        return f\"{self.name} says tweet!\"\nb = Bird(\"Kiwi\")\nprint(b.speak())",
    },
    {
        "id": 12,
        "title": "Dunder Methods",
        "duration": "30 min",
        "prerequisites": "OOP, inheritance",
        "objectives": [
            "Use __str__ and __repr__",
            "Implement __eq__ for equality",
            "Implement __len__ and __lt__",
        ],
        "explanation": "Dunder (double underscore) methods control built-in behaviour. __str__ gives a readable string for users, __repr__ gives a developer-friendly representation. __eq__ defines ==, __len__ defines len(), and __lt__ enables sorting with <.",
        "code": "class Book:\n    def __init__(self, title, pages):\n        self.title = title\n        self.pages = pages\n\n    def __str__(self):\n        return f\"{self.title}\"\n\n    def __repr__(self):\n        return f\"Book('{self.title}', {self.pages})\"\n\n    def __eq__(self, other):\n        return self.pages == other.pages\n\n    def __len__(self):\n        return self.pages\n\nb1 = Book(\"Python\", 300)\nb2 = Book(\"Java\", 300)\nprint(str(b1))\nprint(repr(b1))\nprint(b1 == b2)\nprint(len(b1))",
        "output": "Python\nBook('Python', 300)\nTrue\n300",
        "callout_type": "tip",
        "callout_text": "__repr__ should ideally return a string that could recreate the object — helpful for debugging.",
        "docs_url": "https://docs.python.org/3/reference/datamodel.html#special-method-names",
        "docs_label": "Special method names",
        "exercise_prompt": "Add __lt__ to Book so books can be sorted by pages.",
        "exercise_hint": "Return self.pages < other.pages.",
        "exercise_solution": "class Book:\n    def __init__(self, title, pages):\n        self.title = title\n        self.pages = pages\n    def __lt__(self, other):\n        return self.pages < other.pages\nbooks = [Book(\"B\", 200), Book(\"A\", 100)]\nprint([b.title for b in sorted(books)])",
    },
    {
        "id": 13,
        "title": "Dataclasses",
        "duration": "25 min",
        "prerequisites": "OOP, dunder methods",
        "objectives": [
            "Use @dataclass to reduce boilerplate",
            "Add default values and fields",
            "Convert dataclasses to dicts",
        ],
        "explanation": "Dataclasses automatically generate __init__, __repr__, and __eq__ for simple data-holding classes. You add @dataclass, declare fields with type hints, and get a clean class with defaults and sorting for free.",
        "code": "from dataclasses import dataclass, asdict\n\n@dataclass\nclass Product:\n    name: str\n    price: float\n    stock: int = 0\n\np = Product(\"Laptop\", 999.99, 10)\nprint(p)\nprint(p == Product(\"Laptop\", 999.99, 10))\nprint(asdict(p))",
        "output": "Product(name='Laptop', price=999.99, stock=10)\nTrue\n{'name': 'Laptop', 'price': 999.99, 'stock': 10}",
        "callout_type": "best",
        "callout_text": "Use dataclasses for classes that mostly store data — they remove a lot of repetitive boilerplate.",
        "docs_url": "https://docs.python.org/3/library/dataclasses.html",
        "docs_label": "dataclasses module",
        "exercise_prompt": "Create a dataclass Person with name, age, and city defaulting to 'Unknown'.",
        "exercise_hint": "@dataclass class Person: name: str; age: int; city: str = 'Unknown'.",
        "exercise_solution": "from dataclasses import dataclass\n@dataclass\nclass Person:\n    name: str\n    age: int\n    city: str = \"Unknown\"\np = Person(\"Sufyan\", 19)\nprint(p)",
    },
    {
        "id": 14,
        "title": "Exception Handling Deep Dive",
        "duration": "25 min",
        "prerequisites": "Exceptions, functions",
        "objectives": [
            "Create custom exception classes",
            "Use raise from to chain errors",
            "Use contextlib for clean handling",
        ],
        "explanation": "Beyond try/except, you can define your own exceptions by subclassing Exception. raise from preserves the original error when re-raising. contextlib.suppress cleanly ignores specific errors when you expect them.",
        "code": "class NegativeValueError(ValueError):\n    pass\n\ndef set_age(age):\n    if age < 0:\n        raise NegativeValueError(\"Age cannot be negative\")\n    return age\n\ntry:\n    set_age(-5)\nexcept NegativeValueError as e:\n    print(\"Caught:\", e)",
        "output": "Caught: Age cannot be negative",
        "callout_type": "important",
        "callout_text": "Name custom exceptions clearly and inherit from a built-in exception like ValueError — not plain Exception.",
        "docs_url": "https://docs.python.org/3/tutorial/errors.html#user-defined-exceptions",
        "docs_label": "User-defined exceptions",
        "exercise_prompt": "Raise a custom error when a deposit amount is zero.",
        "exercise_hint": "Define class InvalidDepositError(Exception) and raise it.",
        "exercise_solution": "class InvalidDepositError(Exception):\n    pass\n\ndef deposit(amount):\n    if amount <= 0:\n        raise InvalidDepositError(\"Amount must be positive\")\n    return amount\n\ntry:\n    deposit(0)\nexcept InvalidDepositError as e:\n    print(e)",
    },
    {
        "id": 15,
        "title": "File Handling & Pathlib",
        "duration": "30 min",
        "prerequisites": "Files, exceptions, OOP",
        "objectives": [
            "Use pathlib for cross-platform paths",
            "Read and write CSV and JSON",
            "Build context managers with with",
        ],
        "explanation": "pathlib provides an object-oriented, cross-platform way to work with paths — better than raw string paths. Python's csv and json modules handle structured data, and the with statement ensures files close correctly.",
        "code": "from pathlib import Path\nimport json, csv\n\nbase = Path(\"./data\")\nbase.mkdir(exist_ok=True)\n\ndata = {\"name\": \"Sufyan\", \"age\": 19}\n(base / \"info.json\").write_text(json.dumps(data))\nprint((base / \"info.json\").read_text())\n\nwith (base / \"users.csv\").open(\"w\", newline=\"\") as f:\n    writer = csv.writer(f)\n    writer.writerow([\"name\", \"age\"])\n    writer.writerow([\"Ali\", 25])\n\nprint((base / \"users.csv\").exists())",
        "output": "{\"name\": \"Sufyan\", \"age\": 19}\nTrue",
        "callout_type": "best",
        "callout_text": "Prefer pathlib over os.path — it's cleaner, safer, and works identically on Windows, macOS, and Linux.",
        "docs_url": "https://docs.python.org/3/library/pathlib.html",
        "docs_label": "pathlib module",
        "exercise_prompt": "Create a reports/ folder and write a hello.txt inside it.",
        "exercise_hint": "Path('reports').mkdir(exist_ok=True) then write_text.",
        "exercise_solution": "from pathlib import Path\np = Path(\"reports\")\np.mkdir(exist_ok=True)\n(p / \"hello.txt\").write_text(\"hi\")\nprint((p / \"hello.txt\").read_text())",
    },
    {
        "id": 16,
        "title": "Regular Expressions",
        "duration": "35 min",
        "prerequisites": "Strings, functions",
        "objectives": [
            "Understand regex patterns and re functions",
            "Use match groups",
            "Match emails and phones with patterns",
        ],
        "explanation": "Regular expressions search and match text patterns. re.search finds the first match, re.findall returns all matches, and parentheses create groups. Patterns like \\d+ match digits and [a-z]+ match lowercase words.",
        "code": "import re\n\nemail = \"Contact: sufyan@example.com\"\nphone = \"Call 0300-1234567\"\n\nmatch = re.search(r\"([\\w.]+)@([\\w.]+)\", email)\nprint(match.group(1))\nprint(match.group(2))\n\nprint(re.findall(r\"\\d+\", phone))",
        "output": "sufyan\nexample.com\n['0300', '1234567']",
        "callout_type": "warning",
        "callout_text": "Regex is powerful but hard to read — use it for clear patterns, and keep the pattern simple with comments when possible.",
        "docs_url": "https://docs.python.org/3/library/re.html",
        "docs_label": "re module",
        "exercise_prompt": "Extract all words that start with 'p' from a sentence.",
        "exercise_hint": "Use re.findall(r'\\bp\\w+', text).",
        "exercise_solution": "import re\ntext = \"python is powerful and practical\"\nprint(re.findall(r\"\\bp\\w+\", text))",
    },
    {
        "id": 17,
        "title": "Working with APIs",
        "duration": "35 min",
        "prerequisites": "Dictionaries, exceptions, JSON",
        "objectives": [
            "Make GET requests with requests",
            "Parse JSON responses",
            "Handle status codes and errors",
        ],
        "explanation": "APIs let your program talk to external services over HTTP. The requests library makes GET calls, the .json() method parses responses, and checking status_code helps you handle failures gracefully.",
        "code": "import requests\n\ntry:\n    response = requests.get(\"https://api.github.com/users/programmingpioneer\", timeout=10)\n    response.raise_for_status()\n    data = response.json()\n    print(\"User:\", data.get(\"login\"))\n    print(\"Public repos:\", data.get(\"public_repos\"))\nexcept requests.RequestException as e:\n    print(\"Request failed:\", e)",
        "output": "User: programmingpioneer\nPublic repos: 10",
        "callout_type": "important",
        "callout_text": "Always use response.raise_for_status() and wrap API calls in try/except — network failures happen.",
        "docs_url": "https://docs.python-requests.org/en/latest/",
        "docs_label": "requests library",
        "exercise_prompt": "Fetch a JSON placeholder post and print its title.",
        "exercise_hint": "GET https://jsonplaceholder.typicode.com/posts/1 and print data['title'].",
        "exercise_solution": "import requests\nr = requests.get(\"https://jsonplaceholder.typicode.com/posts/1\")\nprint(r.json()[\"title\"])",
    },
    {
        "id": 18,
        "title": "SQLite with Python",
        "duration": "35 min",
        "prerequisites": "Functions, files, OOP",
        "objectives": [
            "Connect to a SQLite database",
            "Run CRUD operations",
            "Use parameterized queries safely",
        ],
        "explanation": "SQLite is a lightweight database built into Python. The sqlite3 module connects to a file, a cursor executes SQL, and parameterized queries (?) prevent SQL injection. CRUD means Create, Read, Update, Delete.",
        "code": "import sqlite3\n\nconn = sqlite3.connect(\":memory:\")\ncursor = conn.cursor()\n\ncursor.execute(\"CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)\")\ncursor.execute(\"INSERT INTO users (name) VALUES (?)\", (\"Sufyan\",))\ncursor.execute(\"INSERT INTO users (name) VALUES (?)\", (\"Ali\",))\nconn.commit()\n\ncursor.execute(\"SELECT * FROM users\")\nfor row in cursor.fetchall():\n    print(row)\nconn.close()",
        "output": "(1, 'Sufyan')\n(2, 'Ali')",
        "callout_type": "best",
        "callout_text": "Never build SQL with string formatting. Always use parameterized queries with ? placeholders.",
        "docs_url": "https://docs.python.org/3/library/sqlite3.html",
        "docs_label": "sqlite3 module",
        "exercise_prompt": "Create a books table with title and author, then insert one book.",
        "exercise_hint": "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, author TEXT).",
        "exercise_solution": "import sqlite3\nconn = sqlite3.connect(\":memory:\")\nc = conn.cursor()\nc.execute(\"CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, author TEXT)\")\nc.execute(\"INSERT INTO books (title, author) VALUES (?, ?)\", (\"Python Basics\", \"Sufyan\"))\nconn.commit()\nprint(c.execute(\"SELECT * FROM books\").fetchall())\nconn.close()",
    },
    {
        "id": 19,
        "title": "Testing with pytest",
        "duration": "30 min",
        "prerequisites": "Functions, exceptions",
        "objectives": [
            "Write test functions with assertions",
            "Use fixtures for setup",
            "Handle expected exceptions",
        ],
        "explanation": "Testing proves your code works. pytest discovers test_* functions and runs assertions. Fixtures provide reusable setup data. pytest.raises checks that errors are raised as expected — the foundation of reliable code.",
        "code": "import pytest\n\ndef divide(a, b):\n    if b == 0:\n        raise ValueError(\"Cannot divide by zero\")\n    return a / b\n\ndef test_divide():\n    assert divide(10, 2) == 5\n    assert divide(1, 4) == 0.25\n\ndef test_divide_by_zero():\n    with pytest.raises(ValueError):\n        divide(1, 0)\n\nprint(\"All tests passed.\")",
        "output": "All tests passed.",
        "callout_type": "best",
        "callout_text": "Write tests alongside every function — it catches bugs early and documents expected behaviour.",
        "docs_url": "https://docs.pytest.org/en/stable/",
        "docs_label": "pytest documentation",
        "exercise_prompt": "Write a test that checks len('hello') == 5.",
        "exercise_hint": "def test_length(): assert len('hello') == 5.",
        "exercise_solution": "def test_length():\n    assert len(\"hello\") == 5",
    },
    {
        "id": 20,
        "title": "Capstone: Expense Tracker CLI",
        "duration": "45 min",
        "prerequisites": "All previous intermediate lessons",
        "objectives": [
            "Combine OOP, dataclasses, and SQLite",
            "Build a complete CLI application",
            "Apply testing to real code",
        ],
        "explanation": "This capstone combines everything: dataclasses for expenses, sqlite3 for storage, pathlib for files, and custom exceptions for validation. You'll build a CLI that adds, lists, and totals expenses — a real-world project.",
        "code": "from dataclasses import dataclass\nimport sqlite3\nfrom pathlib import Path\n\n@dataclass\nclass Expense:\n    name: str\n    amount: float\n\nclass ExpenseTracker:\n    def __init__(self, db_path=\"expenses.db\"):\n        self.conn = sqlite3.connect(db_path)\n        self.conn.execute(\"CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, name TEXT, amount REAL)\")\n\n    def add(self, name, amount):\n        self.conn.execute(\"INSERT INTO expenses (name, amount) VALUES (?, ?)\", (name, amount))\n        self.conn.commit()\n\n    def total(self):\n        row = self.conn.execute(\"SELECT COALESCE(SUM(amount), 0) FROM expenses\").fetchone()\n        return row[0]\n\n    def all(self):\n        return self.conn.execute(\"SELECT name, amount FROM expenses\").fetchall()\n\n    def close(self):\n        self.conn.close()\n\napp = ExpenseTracker(\":memory:\")\napp.add(\"Lunch\", 500)\napp.add(\"Books\", 1200)\nprint(\"Total:\", app.total())\nprint(\"All:\", app.all())\napp.close()",
        "output": "Total: 1700.0\nAll: [('Lunch', 500.0), ('Books', 1200.0)]",
        "callout_type": "important",
        "callout_text": "Separate concerns: dataclasses for data, a class for storage, and small methods for each feature.",
        "docs_url": "https://docs.python.org/3/library/sqlite3.html",
        "docs_label": "sqlite3 module",
        "exercise_prompt": "Add a delete(name) method that removes an expense by name.",
        "exercise_hint": "Execute DELETE FROM expenses WHERE name = ? and commit.",
        "exercise_solution": "def delete(self, name):\n    self.conn.execute(\"DELETE FROM expenses WHERE name = ?\", (name,))\n    self.conn.commit()",
    },
]

# ================== PYTHON ADVANCED GUIDE — LESSONS DATA ==================
PYTHON_ADVANCED_LESSONS = [
    {
        "id": 1,
        "title": "Advanced OOP",
        "duration": "30 min",
        "objectives": ["Master inheritance chains", "Use abstract base classes", "Compose objects over inheritance"],
        "explanation": "Advanced OOP goes beyond basic classes. Abstract Base Classes (ABCs) force subclasses to implement methods, composition builds behaviour by combining objects, and diamond inheritance teaches you why super() follows the MRO.",
        "code": "from abc import ABC, abstractmethod\n\nclass Shape(ABC):\n    @abstractmethod\n    def area(self):\n        pass\n\nclass Circle(Shape):\n    def __init__(self, radius):\n        self.radius = radius\n\n    def area(self):\n        return 3.14159 * self.radius ** 2\n\nprint(Circle(5).area())",
        "output": "78.53975",
        "callout_type": "important",
        "callout_text": "Prefer composition over inheritance when behaviour differs — it keeps classes flexible and avoids deep hierarchies.",
        "docs_url": "https://docs.python.org/3/library/abc.html",
        "docs_label": "Python ABC",
        "exercise_prompt": "Create an abstract Animal class with a speak() method and a Dog subclass.",
        "exercise_hint": "Use @abstractmethod and override speak() in Dog.",
        "exercise_solution": "from abc import ABC, abstractmethod\nclass Animal(ABC):\n    @abstractmethod\n    def speak(self):\n        pass\nclass Dog(Animal):\n    def speak(self):\n        return 'Woof!'\nprint(Dog().speak())",
    },
    {
        "id": 2,
        "title": "Descriptors & Properties Deep Dive",
        "duration": "30 min",
        "objectives": ["Understand the descriptor protocol", "Build reusable descriptors", "Combine with properties"],
        "explanation": "Descriptors are the machinery behind properties, methods, and classmethod. A descriptor implements __get__, __set__, or __delete__ to control attribute access. Building one shows you how validation, caching, and type checking work under the hood.",
        "code": "class PositiveNumber:\n    def __set_name__(self, owner, name):\n        self.name = name\n\n    def __get__(self, obj, objtype=None):\n        return obj.__dict__.get(self.name, 0)\n\n    def __set__(self, obj, value):\n        if value < 0:\n            raise ValueError(\"Must be positive\")\n        obj.__dict__[self.name] = value\n\nclass Order:\n    total = PositiveNumber()\n\no = Order()\no.total = 100\nprint(o.total)",
        "output": "100",
        "callout_type": "tip",
        "callout_text": "__set_name__ gives a descriptor its attribute name automatically — this is cleaner than passing it manually.",
        "docs_url": "https://docs.python.org/3/howto/descriptor.html",
        "docs_label": "Python descriptor howto",
        "exercise_prompt": "Create a ValidatedString descriptor that rejects empty strings.",
        "exercise_hint": "Raise ValueError in __set__ if not value.strip().",
        "exercise_solution": "class ValidatedString:\n    def __set_name__(self, owner, name):\n        self.name = name\n    def __get__(self, obj, objtype=None):\n        return obj.__dict__.get(self.name, '')\n    def __set__(self, obj, value):\n        if not value.strip():\n            raise ValueError('Empty not allowed')\n        obj.__dict__[self.name] = value\nclass User:\n    name = ValidatedString()\nu = User()\nu.name = 'Ali'\nprint(u.name)",
    },
    {
        "id": 3,
        "title": "Decorators Deep Dive",
        "duration": "35 min",
        "objectives": ["Write decorators with arguments", "Stack multiple decorators", "Use class-based decorators"],
        "explanation": "Advanced decorators take arguments, stack in order, and can be implemented as classes with __call__. Understanding decorator order matters — decorators apply bottom-up, so the one closest to the function runs first.",
        "code": "def repeat(times):\n    def decorator(func):\n        def wrapper(*args, **kwargs):\n            for _ in range(times):\n                result = func(*args, **kwargs)\n            return result\n        return wrapper\n    return decorator\n\n@repeat(3)\ndef greet(name):\n    print(f\"Hi {name}\")\n\ngreet(\"Sufyan\")",
        "output": "Hi Sufyan\nHi Sufyan\nHi Sufyan",
        "callout_type": "best",
        "callout_text": "Use functools.wraps in every decorator so function name, docstring, and signature stay intact.",
        "docs_url": "https://docs.python.org/3/glossary.html#term-decorator",
        "docs_label": "Python decorators",
        "exercise_prompt": "Write a log_calls decorator that prints the function name on each call.",
        "exercise_hint": "In the wrapper, print func.__name__ before calling.",
        "exercise_solution": "def log_calls(func):\n    def wrapper(*args, **kwargs):\n        print(f'Calling {func.__name__}')\n        return func(*args, **kwargs)\n    return wrapper\n@log_calls\ndef add(a, b):\n    return a + b\nprint(add(2, 3))",
    },
    {
        "id": 4,
        "title": "Generators Deep Dive",
        "duration": "35 min",
        "objectives": ["Build generator pipelines", "Use generator.send()", "Handle exceptions with throw() and close()"],
        "explanation": "Advanced generators communicate bidirectionally with send(), terminate with close(), and raise exceptions with throw(). Generator pipelines chain multiple generators lazily for efficient data processing.",
        "code": "def running_average():\n    total = 0\n    count = 0\n    average = None\n    while True:\n        value = yield average\n        total += value\n        count += 1\n        average = total / count\n\navg = running_average()\nnext(avg)\nprint(avg.send(10))\nprint(avg.send(20))\nprint(avg.send(30))",
        "output": "10.0\n15.0\n20.0",
        "callout_type": "important",
        "callout_text": "Call next(gen) or gen.send(None) once before send() — a generator must reach its first yield first.",
        "docs_url": "https://docs.python.org/3/reference/expressions.html#yield-expressions",
        "docs_label": "Python yield expressions",
        "exercise_prompt": "Write a generator that yields squares of numbers sent to it.",
        "exercise_hint": "Receive value with yield, then yield value ** 2.",
        "exercise_solution": "def square_stream():\n    while True:\n        value = yield\n        yield value ** 2\ns = square_stream()\nnext(s)\nprint(s.send(4))",
    },
    {
        "id": 5,
        "title": "Async Python Basics",
        "duration": "35 min",
        "objectives": ["Understand async and await", "Create coroutines", "Run with asyncio.run()"],
        "explanation": "Async Python runs tasks cooperatively without threads. async defines a coroutine, await pauses until another coroutine completes, and asyncio.run() starts the event loop. It's ideal for I/O-bound work like APIs and file reads.",
        "code": "import asyncio\n\nasync def fetch(name, delay):\n    await asyncio.sleep(delay)\n    print(f\"Done: {name}\")\n    return name\n\nasync def main():\n    results = await asyncio.gather(\n        fetch(\"A\", 2),\n        fetch(\"B\", 1),\n        fetch(\"C\", 3),\n    )\n    print(results)\n\nasyncio.run(main())",
        "output": "Done: B\nDone: A\nDone: C\n['A', 'B', 'C']",
        "callout_type": "tip",
        "callout_text": "asyncio.gather() runs coroutines concurrently and returns results in the same order you passed them.",
        "docs_url": "https://docs.python.org/3/library/asyncio.html",
        "docs_label": "Python asyncio",
        "exercise_prompt": "Write two coroutines that sleep and print, then run them with asyncio.run().",
        "exercise_hint": "Use async def and await asyncio.sleep(1).",
        "exercise_solution": "import asyncio\nasync def one():\n    await asyncio.sleep(1)\n    print('one')\nasync def two():\n    await asyncio.sleep(0.5)\n    print('two')\nasync def main():\n    await asyncio.gather(one(), two())\nasyncio.run(main())",
    },
    {
        "id": 6,
        "title": "asyncio Tasks & Timeouts",
        "duration": "35 min",
        "objectives": ["Create tasks with create_task", "Apply timeouts with wait_for", "Await first with wait"],
        "explanation": "Tasks schedule coroutines on the event loop. asyncio.wait_for() enforces timeouts, and asyncio.wait() handles multiple futures with control over return conditions.",
        "code": "import asyncio\n\nasync def slow_task():\n    await asyncio.sleep(5)\n    return \"done\"\n\nasync def main():\n    try:\n        result = await asyncio.wait_for(slow_task(), timeout=1)\n        print(result)\n    except asyncio.TimeoutError:\n        print(\"Too slow!\")\n\nasyncio.run(main())",
        "output": "Too slow!",
        "callout_type": "important",
        "callout_text": "asyncio.wait_for() raises TimeoutError and cancels the task — always catch it for clean shutdown.",
        "docs_url": "https://docs.python.org/3/library/asyncio-task.html",
        "docs_label": "Python asyncio tasks",
        "exercise_prompt": "Create a task with create_task and await it.",
        "exercise_hint": "Use asyncio.create_task(coro) then await the task.",
        "exercise_solution": "import asyncio\nasync def work():\n    await asyncio.sleep(0.1)\n    return 'done'\nasync def main():\n    task = asyncio.create_task(work())\n    print(await task)\nasyncio.run(main())",
    },
    {
        "id": 7,
        "title": "Threads",
        "duration": "30 min",
        "objectives": ["Run threads with threading", "Communicate safely with locks", "Understand the GIL"],
        "explanation": "Threads run code in parallel within one process. Use threading.Thread to start work and Lock to prevent races on shared data. Python's GIL means CPU-bound threads don't fully parallelise, but I/O-bound ones do.",
        "code": "import threading\nimport time\n\ndef worker(name, delay):\n    time.sleep(delay)\n    print(f\"{name} finished\")\n\nthreads = [threading.Thread(target=worker, args=(f\"T{i}\", i)) for i in range(1, 4)]\nfor t in threads:\n    t.start()\nfor t in threads:\n    t.join()\nprint(\"All done\")",
        "output": "T1 finished\nT2 finished\nT3 finished\nAll done",
        "callout_type": "warning",
        "callout_text": "Always call join() on threads to wait for them — otherwise the program may exit before they finish.",
        "docs_url": "https://docs.python.org/3/library/threading.html",
        "docs_label": "Python threading",
        "exercise_prompt": "Start two threads that print their names with a small sleep.",
        "exercise_hint": "Use threading.Thread(target=fn) and start() then join().",
        "exercise_solution": "import threading, time\ndef show(name):\n    time.sleep(0.1)\n    print(name)\nthreads = [threading.Thread(target=show, args=('A',)), threading.Thread(target=show, args=('B',))]\nfor t in threads: t.start()\nfor t in threads: t.join()",
    },
    {
        "id": 8,
        "title": "Multiprocessing",
        "duration": "35 min",
        "objectives": ["Use Process for CPU-bound work", "Share data with Queue", "Understand spawn vs fork"],
        "explanation": "Multiprocessing bypasses the GIL by running separate Python processes. Use Process for CPU-heavy tasks and Queue for safe inter-process communication. Each process gets its own memory.",
        "code": "import multiprocessing\n\ndef square(n):\n    return n * n\n\nwith multiprocessing.Pool(4) as pool:\n    results = pool.map(square, [1, 2, 3, 4, 5])\n\nprint(results)",
        "output": "[1, 4, 9, 16, 25]",
        "callout_type": "best",
        "callout_text": "Use a Pool when you have many independent CPU-bound tasks — it manages workers for you.",
        "docs_url": "https://docs.python.org/3/library/multiprocessing.html",
        "docs_label": "Python multiprocessing",
        "exercise_prompt": "Use multiprocessing.Pool to double a list of numbers.",
        "exercise_hint": "Define a double() function and use pool.map.",
        "exercise_solution": "import multiprocessing\ndef double(n):\n    return n * 2\nwith multiprocessing.Pool(2) as pool:\n    print(pool.map(double, [1, 2, 3]))",
    },
    {
        "id": 9,
        "title": "Concurrency Patterns",
        "duration": "35 min",
        "objectives": ["Choose threads vs processes vs async", "Use concurrent.futures", "Build a clean concurrency pattern"],
        "explanation": "Different concurrency tools fit different jobs: async for many I/O tasks, threads for blocking I/O, processes for CPU work. concurrent.futures gives a unified interface for thread and process pools.",
        "code": "from concurrent.futures import ThreadPoolExecutor\n\ndef double(n):\n    return n * 2\n\nwith ThreadPoolExecutor(max_workers=4) as executor:\n    results = list(executor.map(double, [1, 2, 3, 4]))\n\nprint(results)",
        "output": "[2, 4, 6, 8]",
        "callout_type": "important",
        "callout_text": "Async is not always faster — for quick tasks, the overhead of the event loop can beat the benefit.",
        "docs_url": "https://docs.python.org/3/library/concurrent.futures.html",
        "docs_label": "Python concurrent.futures",
        "exercise_prompt": "Use ThreadPoolExecutor to run a function three times concurrently.",
        "exercise_hint": "Use executor.submit(fn, arg) and collect futures.",
        "exercise_solution": "from concurrent.futures import ThreadPoolExecutor\ndef say(x):\n    return f'hi {x}'\nwith ThreadPoolExecutor(max_workers=3) as ex:\n    futures = [ex.submit(say, i) for i in range(3)]\n    print([f.result() for f in futures])",
    },
    {
        "id": 10,
        "title": "Performance Optimization",
        "duration": "30 min",
        "objectives": ["Measure before optimizing", "Use built-ins for speed", "Apply caching strategically"],
        "explanation": "Performance work starts with measurement. Built-in functions (sum, map, list comprehensions) are C-implemented and fast, and @lru_cache removes repeated computation. Optimize the actual bottleneck, not guesses.",
        "code": "import functools, time\n\n@functools.lru_cache(maxsize=None)\ndef fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n\nstart = time.perf_counter()\nprint(fib(35))\nprint(f\"Time: {time.perf_counter() - start:.4f}s\")",
        "output": "9227465\nTime: 0.0001s",
        "callout_type": "best",
        "callout_text": "Measure first with time.perf_counter() or timeit — never optimise blind guesses.",
        "docs_url": "https://docs.python.org/3/library/functools.html#functools.lru_cache",
        "docs_label": "Python lru_cache",
        "exercise_prompt": "Time how long it takes to sum a list of a million numbers.",
        "exercise_hint": "Use time.perf_counter() around sum(range(1_000_000)).",
        "exercise_solution": "import time\nstart = time.perf_counter()\ntotal = sum(range(1_000_000))\nprint(total, time.perf_counter() - start)",
    },
    {
        "id": 11,
        "title": "Memory Management",
        "duration": "30 min",
        "objectives": ["Understand reference counting", "Use __slots__ to save memory", "Work with garbage collection"],
        "explanation": "Python frees objects automatically using reference counting and a cyclic garbage collector. __slots__ reduces per-instance memory by preventing attribute dict creation. tracemalloc profiles memory allocations.",
        "code": "import tracemalloc\n\ntracemalloc.start()\n\ndata = [n ** 2 for n in range(100_000)]\n\ncurrent, peak = tracemalloc.get_traced_memory()\nprint(f\"Current: {current / 1024:.0f} KB\")\nprint(f\"Peak: {peak / 1024:.0f} KB\")",
        "output": "Current: 3266 KB\nPeak: 3266 KB",
        "callout_type": "tip",
        "callout_text": "Use generators instead of lists for huge data — they compute values lazily and use almost no memory.",
        "docs_url": "https://docs.python.org/3/library/tracemalloc.html",
        "docs_label": "Python tracemalloc",
        "exercise_prompt": "Add __slots__ to a class to reduce its memory usage.",
        "exercise_hint": "Define __slots__ = ('name', 'age').",
        "exercise_solution": "class Person:\n    __slots__ = ('name', 'age')\n    def __init__(self, name, age):\n        self.name = name\n        self.age = age\np = Person('Ali', 30)\nprint(p.name)",
    },
    {
        "id": 12,
        "title": "Profiling",
        "duration": "30 min",
        "objectives": ["Profile with cProfile", "Find hot spots", "Read profiler output"],
        "explanation": "Profiling shows exactly where time goes. cProfile records function calls and cumulative time, helping you find the real bottleneck instead of guessing. Optimise the function that dominates the output.",
        "code": "import cProfile\n\ndef slow():\n    total = 0\n    for i in range(1_000_000):\n        total += i\n    return total\n\ncProfile.run('slow()')",
        "output": "         4 function calls in 0.045 seconds\n\n   Ordered by: standard name\n\n   ncalls  tottime  percall  cumtime  percall filename:lineno(function)\n        1    0.045    0.045    0.045    0.045 profile_example.py:3(slow)",
        "callout_type": "best",
        "callout_text": "Look at cumtime (cumulative time) first — it shows the full cost including nested calls.",
        "docs_url": "https://docs.python.org/3/library/profile.html",
        "docs_label": "Python cProfile",
        "exercise_prompt": "Use cProfile.run() to profile a simple loop function.",
        "exercise_hint": "Define a function, then pass 'function_name()' to cProfile.run.",
        "exercise_solution": "import cProfile\ndef work():\n    total = 0\n    for i in range(10000):\n        total += i\n    return total\ncProfile.run('work()')",
    },
    {
        "id": 13,
        "title": "Advanced Type Hinting",
        "duration": "30 min",
        "objectives": ["Use typing for clarity", "Write generic types", "Use Protocol and TypeAlias"],
        "explanation": "Type hints document contracts and enable static checkers like mypy. typing provides Optional, Union, Callable, and generics. Protocol defines structural typing — anything with the right methods fits.",
        "code": "from typing import Protocol\n\nclass Named(Protocol):\n    name: str\n\ndef greet(item: Named) -> str:\n    return f\"Hello, {item.name}\"\n\nclass User:\n    def __init__(self, name):\n        self.name = name\n\nprint(greet(User(\"Sufyan\")))",
        "output": "Hello, Sufyan",
        "callout_type": "best",
        "callout_text": "Type hints don't change runtime — but they catch bugs early when you run mypy or a typed IDE.",
        "docs_url": "https://docs.python.org/3/library/typing.html",
        "docs_label": "Python typing",
        "exercise_prompt": "Add a type hint to a function that takes int and returns str.",
        "exercise_hint": "Write def describe(n: int) -> str:.",
        "exercise_solution": "def describe(n: int) -> str:\n    return f'Number: {n}'\nprint(describe(5))",
    },
    {
        "id": 14,
        "title": "Packaging Python Projects",
        "duration": "35 min",
        "objectives": ["Understand project layout", "Write pyproject.toml", "Structure a publishable package"],
        "explanation": "A proper package has a clear structure: a project folder, a package directory, pyproject.toml, and a README. Modern Python uses pyproject.toml for build metadata instead of setup.py.",
        "code": "# pyproject.toml (example)\n# [build-system]\n# requires = [\"setuptools>=68\"]\n# build-backend = \"setuptools.build_meta\"\n#\n# [project]\n# name = \"mypackage\"\n# version = \"0.1.0\"\n# description = \"A sample package\"\n\nprint(\"Project structure:\")\nprint(\"mypackage/\")\nprint(\"  mypackage/\")\nprint(\"    __init__.py\")\nprint(\"    core.py\")\nprint(\"  pyproject.toml\")\nprint(\"  README.md\")",
        "output": "Project structure:\nmypackage/\n  mypackage/\n    __init__.py\n    core.py\n  pyproject.toml\n  README.md",
        "callout_type": "important",
        "callout_text": "Keep the package source in a subfolder with the same name as the project — this avoids common import confusion.",
        "docs_url": "https://packaging.python.org/tutorials/packaging-projects/",
        "docs_label": "Python packaging guide",
        "exercise_prompt": "Write a minimal pyproject.toml with name and version.",
        "exercise_hint": "Use [project] with name and version keys.",
        "exercise_solution": "print('[project]')\nprint('name = \"demo\"')\nprint('version = \"0.1.0\"')",
    },
    {
        "id": 15,
        "title": "Building & Publishing Packages",
        "duration": "35 min",
        "objectives": ["Build wheels and sdists", "Publish to PyPI with twine", "Version packages correctly"],
        "explanation": "Publishing makes your package installable by anyone. python -m build creates distributions (wheel and sdist), and twine uploads them to PyPI. Semantic versioning keeps releases predictable.",
        "code": "# Build commands (run in terminal):\n# python -m build\n# python -m twine upload dist/*\n\nimport sys\nprint(\"Release checklist:\")\nprint(\"1. Update version in pyproject.toml\")\nprint(\"2. Build: python -m build\")\nprint(\"3. Upload: python -m twine upload dist/*\")\nprint(\"4. Verify: pip install yourpkg\")",
        "output": "Release checklist:\n1. Update version in pyproject.toml\n2. Build: python -m build\n3. Upload: python -m twine upload dist/*\n4. Verify: pip install yourpkg",
        "callout_type": "warning",
        "callout_text": "Never upload a package with a real secret or password in the source — check files before twine upload.",
        "docs_url": "https://packaging.python.org/tutorials/packaging-projects/#uploading-the-distribution-archives",
        "docs_label": "Uploading to PyPI",
        "exercise_prompt": "Print the semantic versioning order for 1.0.0, 2.0.0, and 1.1.0.",
        "exercise_hint": "Sort them as strings; semver sorts lexically.",
        "exercise_solution": "versions = ['1.0.0', '2.0.0', '1.1.0']\nprint(sorted(versions))",
    },
    {
        "id": 16,
        "title": "Environment & Configuration",
        "duration": "30 min",
        "objectives": ["Load environment variables", "Use pydantic-settings", "Separate config from code"],
        "explanation": "Configuration should live outside code — in environment variables or .env files. pydantic-settings validates config at startup so the app fails fast with a clear error if something is missing.",
        "code": "import os\n\nos.environ[\"DATABASE_URL\"] = \"postgres://localhost/app\"\n\ndatabase_url = os.environ.get(\"DATABASE_URL\", \"sqlite:///default.db\")\nprint(database_url)\n\nsecret = os.environ.get(\"SECRET_KEY\")\nprint(\"Secret loaded:\", bool(secret))",
        "output": "postgres://localhost/app\nSecret loaded: False",
        "callout_type": "important",
        "callout_text": "Never hard-code secrets — read them from environment variables so they stay out of git.",
        "docs_url": "https://docs.python.org/3/library/os.html#os.environ",
        "docs_label": "Python os.environ",
        "exercise_prompt": "Read a HOME environment variable and print it.",
        "exercise_hint": "Use os.environ.get('HOME', 'not set').",
        "exercise_solution": "import os\nprint(os.environ.get('HOME', 'not set'))",
    },
    {
        "id": 17,
        "title": "Security Basics",
        "duration": "30 min",
        "objectives": ["Sanitize user input", "Use secrets for tokens", "Avoid SQL injection"],
        "explanation": "Security is a mindset: never trust user input, never build SQL with string concatenation, and use the secrets module for tokens and passwords. Parameterized queries stop injection attacks.",
        "code": "import secrets\n\ndef make_token():\n    return secrets.token_urlsafe(16)\n\nprint(make_token())\nprint(make_token())",
        "output": "Kx8nRf2XwL9mPq3TvB7sYg\nTq3Nc7RmWp2Jx5VdL8kZtA",
        "callout_type": "warning",
        "callout_text": "Use secrets for anything security-sensitive — random is predictable and only meant for simulations.",
        "docs_url": "https://docs.python.org/3/library/secrets.html",
        "docs_label": "Python secrets",
        "exercise_prompt": "Generate a 32-byte secure token with secrets.token_hex.",
        "exercise_hint": "Call secrets.token_hex(32).",
        "exercise_solution": "import secrets\nprint(secrets.token_hex(32))",
    },
    {
        "id": 18,
        "title": "Architecture & Clean Code",
        "duration": "30 min",
        "objectives": ["Apply SOLID principles", "Separate concerns", "Keep functions small"],
        "explanation": "Clean code is readable, testable, and easy to change. Single Responsibility says one function does one thing, dependency injection makes code testable, and descriptive names remove the need for comments.",
        "code": "from dataclasses import dataclass\n\n@dataclass\nclass EmailSender:\n    smtp_host: str\n\n    def send(self, to, subject, body):\n        return f\"Sent to {to}: {subject}\"\n\nclass Notifier:\n    def __init__(self, sender):\n        self.sender = sender\n\n    def notify(self, user, message):\n        return self.sender.send(user, \"Update\", message)\n\nn = Notifier(EmailSender(\"smtp.example.com\"))\nprint(n.notify(\"ali@example.com\", \"Welcome!\"))",
        "output": "Sent to ali@example.com: Update",
        "callout_type": "best",
        "callout_text": "Dependency injection — passing dependencies into __init__ — makes code testable and swappable.",
        "docs_url": "https://docs.python.org/3/howto/functional.html",
        "docs_label": "Python functional howto",
        "exercise_prompt": "Write a class that takes a logger object in __init__ and uses it in a method.",
        "exercise_hint": "Store self.logger = logger, then call self.logger.log(...).",
        "exercise_solution": "class Service:\n    def __init__(self, logger):\n        self.logger = logger\n    def run(self):\n        self.logger.log('running')\nclass Logger:\n    def log(self, msg):\n        print(msg)\nService(Logger()).run()",
    },
    {
        "id": 19,
        "title": "Production Python",
        "duration": "35 min",
        "objectives": ["Configure logging properly", "Handle errors gracefully", "Plan observability"],
        "explanation": "Production code needs proper logging, graceful error handling, and observability. Configure the logging module with levels and formats, catch errors at boundaries, and always provide useful context.",
        "code": "import logging\n\nlogging.basicConfig(\n    level=logging.INFO,\n    format=\"%(asctime)s [%(levelname)s] %(message)s\",\n)\n\nlogging.info(\"Service started\")\nlogging.warning(\"High memory usage\")\ntry:\n    result = 10 / 0\nexcept ZeroDivisionError:\n    logging.error(\"Division by zero attempted\")",
        "output": "2026-08-23 23:00:00,000 [INFO] Service started\n2026-08-23 23:00:00,000 [WARNING] High memory usage\n2026-08-23 23:00:00,000 [ERROR] Division by zero attempted",
        "callout_type": "important",
        "callout_text": "Use logging, not print(), in production — it gives timestamps, levels, and can write to files or services.",
        "docs_url": "https://docs.python.org/3/howto/logging.html",
        "docs_label": "Python logging howto",
        "exercise_prompt": "Configure logging and log an info message.",
        "exercise_hint": "Use basicConfig(level=logging.INFO) then logging.info(...).",
        "exercise_solution": "import logging\nlogging.basicConfig(level=logging.INFO)\nlogging.info('Hello production')",
    },
    {
        "id": 20,
        "title": "Capstone: Production API",
        "duration": "45 min",
        "objectives": ["Build a production-style app", "Combine async, classes, and config", "Structure for maintainability"],
        "explanation": "This capstone combines everything: classes for services, async for I/O, environment config, and clean error handling. The goal is a small but production-quality API-like service.",
        "code": "import os\nimport logging\nfrom dataclasses import dataclass\n\nlogging.basicConfig(level=logging.INFO, format=\"%(levelname)s %(message)s\")\n\n@dataclass\nclass Config:\n    max_results: int = 10\n\nclass FakeDB:\n    def query(self, limit):\n        return [f\"row-{i}\" for i in range(limit)]\n\nclass Service:\n    def __init__(self, db, config):\n        self.db = db\n        self.config = config\n\n    def search(self):\n        logging.info(\"Running search\")\n        try:\n            return self.db.query(self.config.max_results)\n        except Exception as exc:\n            logging.error(f\"Search failed: {exc}\")\n            return []\n\nservice = Service(FakeDB(), Config(max_results=5))\nprint(service.search())",
        "output": "INFO Running search\n['row-0', 'row-1', 'row-2', 'row-3', 'row-4']",
        "callout_type": "best",
        "callout_text": "Layer your app: Config holds settings, DB handles data, Service holds business logic — each part is easy to test alone.",
        "docs_url": "https://docs.python.org/3/howto/logging.html",
        "docs_label": "Python logging howto",
        "exercise_prompt": "Add a retry option to Config and use it in the Service.",
        "exercise_hint": "Add retries: int = 3 to the dataclass.",
        "exercise_solution": "from dataclasses import dataclass\n@dataclass\nclass Config:\n    max_results: int = 10\n    retries: int = 3\nprint(Config())",
    },
]

PYTHON_PRACTICE = [
    # ================= BEGINNER — 20 TOPICS =================
    {"id":"b01","level":"beginner","topic":"First Program","type":"mcq","difficulty":"easy","title":"print() Function","question":"What does print(\"Hello\") output?","options":["Hello","\"Hello\"","Error","None"],"answer":"Hello","hint":"print displays the text without quotes.","solution":"Hello","explanation":"print() outputs the string content without quotes."},
    {"id":"b01b","level":"beginner","topic":"First Program","type":"output","difficulty":"easy","title":"Two Prints","question":"What is the output?","code":"print(\"A\")\nprint(\"B\")","answer":"A\nB","hint":"Two print calls, two lines.","solution":"A\nB","explanation":"Each print goes on a new line."},
    {"id":"b02","level":"beginner","topic":"Variables","type":"mcq","difficulty":"easy","title":"Type of 10","question":"What is type(10)?","options":["int","float","str","bool"],"answer":"int","hint":"Whole numbers are int.","solution":"int","explanation":"10 has no decimal, so it's an int."},
    {"id":"b02b","level":"beginner","topic":"Variables","type":"mcq","difficulty":"easy","title":"Valid Name","question":"Which variable name is valid?","options":["2name","my-name","my_name","my name"],"answer":"my_name","hint":"Names can't start with a digit or contain spaces/hyphens.","solution":"my_name","explanation":"Only letters, digits, and underscore; can't start with a digit."},
    {"id":"b03","level":"beginner","topic":"Operators","type":"mcq","difficulty":"easy","title":"Modulo Result","question":"What is 10 % 3?","options":["3","1","0","10"],"answer":"1","hint":"% is the remainder.","solution":"1","explanation":"10 divided by 3 is 3 remainder 1."},
    {"id":"b03b","level":"beginner","topic":"Operators","type":"output","difficulty":"medium","title":"Operator Precedence","question":"What is the output?","code":"print(2 + 3 * 4)","answer":"14","hint":"Multiplication before addition.","solution":"14","explanation":"3*4=12, then 2+12=14."},
    {"id":"b04","level":"beginner","topic":"Strings","type":"mcq","difficulty":"easy","title":"String Length","question":"What does len(\"Python\") return?","options":["5","6","7","Error"],"answer":"6","hint":"Count the letters.","solution":"6","explanation":"'Python' has 6 characters."},
    {"id":"b04b","level":"beginner","topic":"Strings","type":"output","difficulty":"medium","title":"String Upper","question":"What is the output?","code":"print(\"hello\".upper())","answer":"HELLO","hint":"upper() capitalizes all letters.","solution":"HELLO","explanation":"upper() converts to uppercase."},
    {"id":"b05","level":"beginner","topic":"Input & Casting","type":"mcq","difficulty":"medium","title":"input() Type","question":"What type does input() return?","options":["int","float","str","bool"],"answer":"str","hint":"input() always returns text.","solution":"str","explanation":"input() always returns a string."},
    {"id":"b05b","level":"beginner","topic":"Input & Casting","type":"coding","difficulty":"medium","title":"Add Two Inputs","question":"Write code to add two numbers from input().","starter_code":"a = int(input())\nb = int(input())\n# print sum","answer":"print(a + b)","hint":"Convert inputs to int first.","solution":"a = int(input())\nb = int(input())\nprint(a + b)","explanation":"int() converts input strings to numbers."},
    {"id":"b06","level":"beginner","topic":"Conditions","type":"mcq","difficulty":"easy","title":"if/else Logic","question":"What prints if score=85 and code is `if score>=90: print('A') else: print('B')`?","options":["A","B","Error","Nothing"],"answer":"B","hint":"85 is not >= 90.","solution":"B","explanation":"85 is less than 90, so else runs."},
    {"id":"b06b","level":"beginner","topic":"Conditions","type":"output","difficulty":"medium","title":"Conditional Expression","question":"What is the output?","code":"age = 18\nprint(\"Adult\" if age >= 18 else \"Minor\")","answer":"Adult","hint":"18 >= 18 is True.","solution":"Adult","explanation":"The condition is true, so 'Adult' prints."},
    {"id":"b07","level":"beginner","topic":"Loops","type":"mcq","difficulty":"medium","title":"range() Count","question":"How many times does `for i in range(5)` loop?","options":["4","5","6","10"],"answer":"5","hint":"range(5) gives 0,1,2,3,4.","solution":"5","explanation":"range(5) produces 5 numbers."},
    {"id":"b07b","level":"beginner","topic":"Loops","type":"output","difficulty":"medium","title":"While Loop","question":"What is the output?","code":"n = 0\nwhile n < 3:\n    n += 1\nprint(n)","answer":"3","hint":"Loop runs until n reaches 3.","solution":"3","explanation":"n increments 3 times: 1,2,3."},
    {"id":"b08","level":"beginner","topic":"Lists","type":"mcq","difficulty":"easy","title":"List Indexing","question":"What does [10,20,30][0] return?","options":["10","20","30","Error"],"answer":"10","hint":"Indexing starts at 0.","solution":"10","explanation":"Index 0 is the first element."},
    {"id":"b08b","level":"beginner","topic":"Lists","type":"coding","difficulty":"medium","title":"Append to List","question":"Write code to add 4 to nums = [1,2,3].","starter_code":"nums = [1, 2, 3]\n# add 4","answer":"nums.append(4)","hint":"Use append().","solution":"nums.append(4)","explanation":"append() adds to the end."},
    {"id":"b09","level":"beginner","topic":"Dictionaries","type":"mcq","difficulty":"medium","title":"Dict Access","question":"What does {'a':1}['a'] return?","options":["1","a","Error","None"],"answer":"1","hint":"Use the key to get the value.","solution":"1","explanation":"Key 'a' maps to value 1."},
    {"id":"b09b","level":"beginner","topic":"Dictionaries","type":"output","difficulty":"medium","title":"Dict get() Safe","question":"What is the output?","code":"d = {'x': 10}\nprint(d.get('y', 0))","answer":"0","hint":"get returns default if key missing.","solution":"0","explanation":"'y' missing, so default 0 returns."},
    {"id":"b10","level":"beginner","topic":"Functions","type":"mcq","difficulty":"medium","title":"Function Return","question":"What does a function without return return?","options":["0","None","False","Error"],"answer":"None","hint":"No return means None.","solution":"None","explanation":"Functions default to returning None."},
    {"id":"b10b","level":"beginner","topic":"Functions","type":"coding","difficulty":"easy","title":"Multiply Function","question":"Write multiply(a, b) that returns a * b.","starter_code":"def multiply(a, b):\n    pass","answer":"return a * b","hint":"Use return.","solution":"def multiply(a, b):\n    return a * b","explanation":"return sends the product back."},
    {"id":"b11","level":"beginner","topic":"Comprehensions","type":"mcq","difficulty":"medium","title":"List Comprehension","question":"What is [x*2 for x in [1,2,3]]?","options":["[2,4,6]","[1,2,3]","[1,4,9]","Error"],"answer":"[2,4,6]","hint":"Each item is doubled.","solution":"[2,4,6]","explanation":"Comprehension doubles each element."},
    {"id":"b12","level":"beginner","topic":"Files","type":"mcq","difficulty":"medium","title":"with open()","question":"Why use `with open()`?","options":["Faster","Auto-closes file","Reads binary","Adds security"],"answer":"Auto-closes file","hint":"with handles cleanup.","solution":"Auto-closes the file.","explanation":"with ensures the file closes automatically."},
    {"id":"b13","level":"beginner","topic":"Exceptions","type":"mcq","difficulty":"medium","title":"try/except","question":"What does except catch?","options":["Syntax errors","Runtime exceptions","Compile errors","Nothing"],"answer":"Runtime exceptions","hint":"except handles runtime errors.","solution":"Runtime exceptions.","explanation":"try/except catches runtime exceptions."},
    {"id":"b14","level":"beginner","topic":"Modules","type":"mcq","difficulty":"medium","title":"Import Math","question":"How to import sqrt?","options":["from math import sqrt","import sqrt","include math","using math"],"answer":"from math import sqrt","hint":"Use from module import name.","solution":"from math import sqrt","explanation":"This imports the sqrt function directly."},
    {"id":"b15","level":"beginner","topic":"Std Library","type":"output","difficulty":"medium","title":"random.randint","question":"What type does random.randint(1, 10) return?","options":["str","float","int","list"],"answer":"int","hint":"randint returns an integer.","solution":"int","explanation":"randint returns a whole number."},
    {"id":"b16","level":"beginner","topic":"OOP Basics","type":"mcq","difficulty":"medium","title":"self Meaning","question":"What does self refer to?","options":["The class","The instance","The module","The function"],"answer":"The instance","hint":"self is the object itself.","solution":"The instance.","explanation":"self refers to the current instance."},
    {"id":"b17","level":"beginner","topic":"Debugging","type":"mcq","difficulty":"medium","title":"Traceback Reading","question":"Where is the actual error in a traceback?","options":["First line","Last line","Middle","Nowhere"],"answer":"Last line","hint":"Read bottom-up.","solution":"The last line.","explanation":"The last line shows the actual error."},
    {"id":"b18","level":"beginner","topic":"venv & pip","type":"mcq","difficulty":"medium","title":"Create venv","question":"Which command creates a virtual environment?","options":["python -m venv .venv","pip install venv","python create venv","venv new"],"answer":"python -m venv .venv","hint":"It's python -m venv.","solution":"python -m venv .venv","explanation":"python -m venv creates an environment."},
    {"id":"b19","level":"beginner","topic":"Capstone","type":"mcq","difficulty":"hard","title":"Project Concept","question":"Which combines everything learned?","options":["A single print","A small CLI app","A comment","A variable"],"answer":"A small CLI app","hint":"Capstone = complete project.","solution":"A small CLI app.","explanation":"The capstone builds a working application."},

    # ================= INTERMEDIATE — 20 TOPICS =================
    {"id":"i01","level":"intermediate","topic":"Advanced Functions","type":"mcq","difficulty":"medium","title":"*args Type","question":"What type is *args?","options":["list","tuple","dict","set"],"answer":"tuple","hint":"*args collects positional args.","solution":"tuple","explanation":"*args collects into a tuple."},
    {"id":"i01b","level":"intermediate","topic":"Advanced Functions","type":"output","difficulty":"medium","title":"**kwargs Type","question":"What type is **kwargs?","options":["list","tuple","dict","set"],"answer":"dict","hint":"**kwargs collects keyword args.","solution":"dict","explanation":"**kwargs collects into a dict."},
    {"id":"i02","level":"intermediate","topic":"Scope & Closures","type":"mcq","difficulty":"medium","title":"LEGB Order","question":"What is the scope order in Python?","options":["Local, Enclosing, Global, Built-in","Global, Local, Built-in","Built-in, Local","Local, Global, Enclosing"],"answer":"Local, Enclosing, Global, Built-in","hint":"LEGB.","solution":"Local → Enclosing → Global → Built-in","explanation":"Python resolves names in LEGB order."},
    {"id":"i03","level":"intermediate","topic":"Decorators","type":"mcq","difficulty":"medium","title":"Decorator Symbol","question":"What symbol applies a decorator?","options":["@","#","$","&"],"answer":"@","hint":"It's the @ symbol.","solution":"@","explanation":"@ applies a decorator to a function."},
    {"id":"i04","level":"intermediate","topic":"functools","type":"mcq","difficulty":"medium","title":"lru_cache Purpose","question":"What does @lru_cache do?","options":["Deletes cache","Memoizes results","Runs async","Sorts data"],"answer":"Memoizes results","hint":"It caches results.","solution":"Memoizes results.","explanation":"lru_cache caches function results."},
    {"id":"i05","level":"intermediate","topic":"Advanced Collections","type":"mcq","difficulty":"medium","title":"Counter Use","question":"What does Counter('aab') give?","options":["['a','a','b']","{'a':2,'b':1}","2","'aab'"],"answer":"{'a':2,'b':1}","hint":"Counter counts occurrences.","solution":"{'a': 2, 'b': 1}","explanation":"Counter maps items to counts."},
    {"id":"i06","level":"intermediate","topic":"Iterators","type":"mcq","difficulty":"medium","title":"Iterator Protocol","question":"Which methods define an iterator?","options":["__iter__, __next__","__get__, __set__","__call__, __init__","__add__, __sub__"],"answer":"__iter__, __next__","hint":"Iterators have these two.","solution":"__iter__ and __next__.","explanation":"Iterators implement __iter__ and __next__."},
    {"id":"i07","level":"intermediate","topic":"Generators","type":"mcq","difficulty":"medium","title":"yield vs return","question":"What does yield do differently from return?","options":["Ends function","Pauses and resumes","Raises error","Returns None"],"answer":"Pauses and resumes","hint":"yield pauses the function.","solution":"Pauses and resumes.","explanation":"yield pauses the generator, keeping state."},
    {"id":"i07b","level":"intermediate","topic":"Generators","type":"coding","difficulty":"medium","title":"Simple Generator","question":"Write a generator that yields 1, 2, 3.","starter_code":"def gen():\n    pass","answer":"yield 1\n    yield 2\n    yield 3","hint":"Use yield three times.","solution":"def gen():\n    yield 1\n    yield 2\n    yield 3","explanation":"Each yield produces one value."},
    {"id":"i08","level":"intermediate","topic":"Comprehensions Deep","type":"output","difficulty":"hard","title":"Nested Comprehension","question":"What is the output?","code":"matrix = [[1,2],[3,4]]\nprint([n for row in matrix for n in row])","answer":"[1, 2, 3, 4]","hint":"Flattens the matrix.","solution":"[1, 2, 3, 4]","explanation":"Nested loops flatten the 2D list."},
    {"id":"i09","level":"intermediate","topic":"Class/Static Methods","type":"mcq","difficulty":"medium","title":"@classmethod First Param","question":"What is the first param of @classmethod?","options":["self","cls","this","none"],"answer":"cls","hint":"classmethod receives the class.","solution":"cls","explanation":"@classmethod passes the class as cls."},
    {"id":"i10","level":"intermediate","topic":"Properties","type":"mcq","difficulty":"medium","title":"@property Purpose","question":"What does @property do?","options":["Deletes an attribute","Runs code on access","Creates a class","Imports a module"],"answer":"Runs code on access","hint":"Getter with logic.","solution":"Runs code on attribute access.","explanation":"@property lets attribute access run code."},
    {"id":"i11","level":"intermediate","topic":"Inheritance","type":"mcq","difficulty":"medium","title":"super() Use","question":"What does super() do?","options":["Deletes parent","Calls parent method","Creates child","Imports module"],"answer":"Calls parent method","hint":"Access parent class.","solution":"Calls parent methods.","explanation":"super() lets you call the parent class."},
    {"id":"i12","level":"intermediate","topic":"Dunder Methods","type":"mcq","difficulty":"medium","title":"__str__ Purpose","question":"What does __str__ define?","options":["Addition","String representation","Deletion","Comparison"],"answer":"String representation","hint":"print() uses it.","solution":"String representation.","explanation":"__str__ controls how str(obj) looks."},
    {"id":"i13","level":"intermediate","topic":"Dataclasses","type":"mcq","difficulty":"medium","title":"@dataclass Benefit","question":"What does @dataclass auto-generate?","options":["__init__, __repr__","main()","loops","imports"],"answer":"__init__, __repr__","hint":"Reduces boilerplate.","solution":"__init__ and __repr__","explanation":"@dataclass generates common methods automatically."},
    {"id":"i14","level":"intermediate","topic":"Exceptions Deep","type":"mcq","difficulty":"hard","title":"raise from","question":"What does `raise X from Y` do?","options":["Hides Y","Chains exception cause","Deletes X","Runs Y again"],"answer":"Chains exception cause","hint":"Preserves original cause.","solution":"Chains the cause.","explanation":"raise from preserves the original exception as cause."},
    {"id":"i15","level":"intermediate","topic":"pathlib","type":"mcq","difficulty":"medium","title":"Path Join","question":"How to join paths with pathlib?","options":["Path / file","path.join()","concat()","add()"],"answer":"Path / file","hint":"Use the / operator.","solution":"Path('dir') / 'file.txt'","explanation":"pathlib uses / to join paths."},
    {"id":"i16","level":"intermediate","topic":"Regex","type":"mcq","difficulty":"medium","title":"\\d Meaning","question":"What does \\d match?","options":["Letter","Digit","Space","Symbol"],"answer":"Digit","hint":"d for digit.","solution":"Digit.","explanation":"\\d matches any digit 0-9."},
    {"id":"i17","level":"intermediate","topic":"APIs","type":"mcq","difficulty":"medium","title":"requests get()","question":"Which method fetches a URL?","options":["requests.get()","requests.post()","requests.fetch()","requests.url()"],"answer":"requests.get()","hint":"GET = fetch.","solution":"requests.get(url)","explanation":"GET requests fetch data from a URL."},
    {"id":"i18","level":"intermediate","topic":"SQLite","type":"mcq","difficulty":"hard","title":"SQL Injection Safe","question":"Which query is safe?","options":["f-string query","Parameterized ? query","Raw concatenation","Shell exec"],"answer":"Parameterized ? query","hint":"Use placeholders.","solution":"cur.execute('SELECT * FROM t WHERE id=?', (x,))","explanation":"Parameterized queries prevent injection."},
    {"id":"i19","level":"intermediate","topic":"Testing","type":"mcq","difficulty":"medium","title":"pytest Test Prefix","question":"How must pytest test files be named?","options":["test_*.py","check_*.py","*.test.py","tests.py"],"answer":"test_*.py","hint":"test_ prefix.","solution":"test_*.py","explanation":"pytest discovers files starting with test_."},
    {"id":"i20","level":"intermediate","topic":"Capstone","type":"mcq","difficulty":"hard","title":"Intermediate Capstone","question":"What does the intermediate capstone combine?","options":["OOP + files + SQL","Only prints","Only loops","Only variables"],"answer":"OOP + files + SQL","hint":"Real application.","solution":"OOP + file I/O + SQLite.","explanation":"The capstone combines multiple intermediate concepts."},

    # ================= ADVANCED — 20 TOPICS =================
    {"id":"a01","level":"advanced","topic":"Advanced OOP","type":"mcq","difficulty":"hard","title":"ABC Purpose","question":"What does ABC enforce?","options":["Faster code","Abstract methods implemented","No inheritance","Async only"],"answer":"Abstract methods implemented","hint":"Forces subclass methods.","solution":"Forces subclasses to implement abstract methods.","explanation":"ABC ensures subclasses define required methods."},
    {"id":"a02","level":"advanced","topic":"Descriptors","type":"mcq","difficulty":"hard","title":"Descriptor Methods","question":"Which methods define a descriptor?","options":["__get__, __set__","__add__, __sub__","__iter__, __next__","__call__, __init__"],"answer":"__get__, __set__","hint":"Attribute access protocol.","solution":"__get__ and __set__","explanation":"Descriptors control attribute access via these methods."},
    {"id":"a03","level":"advanced","topic":"Decorators Deep","type":"output","difficulty":"hard","title":"Decorator Order","question":"Which decorator runs first?","code":"@one\n@two\ndef f(): pass","answer":"two","hint":"Bottom-up.","solution":"two (closest to the function).","explanation":"Decorators apply bottom-up."},
    {"id":"a04","level":"advanced","topic":"Generators Deep","type":"mcq","difficulty":"hard","title":"gen.send()","question":"What does gen.send() do?","options":["Ends generator","Sends value into yield","Deletes generator","Prints value"],"answer":"Sends value into yield","hint":"Bidirectional communication.","solution":"Sends a value into the generator.","explanation":"send() resumes the generator with a value."},
    {"id":"a05","level":"advanced","topic":"Async Basics","type":"mcq","difficulty":"medium","title":"async def","question":"What does async def create?","options":["A thread","A coroutine","A process","A class"],"answer":"A coroutine","hint":"Coroutine function.","solution":"A coroutine.","explanation":"async def defines a coroutine function."},
    {"id":"a06","level":"advanced","topic":"asyncio Tasks","type":"mcq","difficulty":"hard","title":"wait_for Purpose","question":"What does asyncio.wait_for do?","options":["Sleeps","Applies timeout","Runs threads","Creates files"],"answer":"Applies timeout","hint":"Timeout enforcement.","solution":"Applies a timeout to a coroutine.","explanation":"wait_for raises TimeoutError if the task exceeds time."},
    {"id":"a07","level":"advanced","topic":"Threads","type":"mcq","difficulty":"medium","title":"GIL Meaning","question":"What does GIL stand for?","options":["Global Interpreter Lock","General Input Loop","Garbage Input Level","Global Index List"],"answer":"Global Interpreter Lock","hint":"Limits threads.","solution":"Global Interpreter Lock.","explanation":"GIL allows only one thread at a time in CPython."},
    {"id":"a08","level":"advanced","topic":"Multiprocessing","type":"mcq","difficulty":"medium","title":"Why Processes?","question":"Why use multiprocessing for CPU work?","options":["Bypasses GIL","Faster I/O","Easier syntax","Less memory"],"answer":"Bypasses GIL","hint":"Separate interpreters.","solution":"Bypasses the GIL.","explanation":"Each process has its own GIL."},
    {"id":"a09","level":"advanced","topic":"Concurrency Patterns","type":"mcq","difficulty":"hard","title":"concurrent.futures","question":"What does ThreadPoolExecutor manage?","options":["Threads","Processes","Async","Files"],"answer":"Threads","hint":"Pool of threads.","solution":"Threads.","explanation":"ThreadPoolExecutor manages a pool of threads."},
    {"id":"a10","level":"advanced","topic":"Performance","type":"mcq","difficulty":"medium","title":"perf_counter Use","question":"What does time.perf_counter() measure?","options":["Wall time","CPU cycles","Memory","Disk"],"answer":"Wall time","hint":"High-res timer.","solution":"Elapsed wall time.","explanation":"perf_counter gives high-resolution timing."},
    {"id":"a11","level":"advanced","topic":"Memory Mgmt","type":"mcq","difficulty":"hard","title":"__slots__ Benefit","question":"What does __slots__ reduce?","options":["CPU usage","Memory per instance","Lines of code","Network usage"],"answer":"Memory per instance","hint":"No attr dict.","solution":"Memory per instance.","explanation":"__slots__ avoids the per-instance dict."},
    {"id":"a12","level":"advanced","topic":"Profiling","type":"mcq","difficulty":"medium","title":"cProfile Purpose","question":"What does cProfile do?","options":["Profiles function calls","Compiles code","Runs tests","Formats code"],"answer":"Profiles function calls","hint":"Finds bottlenecks.","solution":"Profiles function calls and timing.","explanation":"cProfile shows where time is spent."},
    {"id":"a13","level":"advanced","topic":"Type Hinting","type":"mcq","difficulty":"medium","title":"Optional[int]","question":"What does Optional[int] mean?","options":["int or None","only int","only None","list of int"],"answer":"int or None","hint":"Optional allows None.","solution":"int or None.","explanation":"Optional[X] is X or None."},
    {"id":"a14","level":"advanced","topic":"Packaging","type":"mcq","difficulty":"medium","title":"pyproject.toml","question":"What does pyproject.toml define?","options":["Build config","Runtime code","Tests","Docs"],"answer":"Build config","hint":"Modern packaging.","solution":"Build and project metadata.","explanation":"pyproject.toml holds modern project config."},
    {"id":"a15","level":"advanced","topic":"Publishing","type":"mcq","difficulty":"medium","title":"PyPI Upload Tool","question":"Which tool uploads to PyPI?","options":["twine","pip install","python run","git push"],"answer":"twine","hint":"twine upload.","solution":"twine.","explanation":"twine uploads distributions to PyPI."},
    {"id":"a16","level":"advanced","topic":"Config","type":"mcq","difficulty":"medium","title":"Env Var Access","question":"How to read an environment variable?","options":["os.environ.get()","sys.env()","env.read()","os.getenv_all()"],"answer":"os.environ.get()","hint":"os module.","solution":"os.environ.get('KEY').","explanation":"os.environ stores environment variables."},
    {"id":"a17","level":"advanced","topic":"Security","type":"mcq","difficulty":"medium","title":"secrets vs random","question":"Which module for passwords/tokens?","options":["secrets","random","math","time"],"answer":"secrets","hint":"Security-safe.","solution":"secrets.","explanation":"secrets is cryptographically secure."},
    {"id":"a18","level":"advanced","topic":"Architecture","type":"mcq","difficulty":"hard","title":"SOLID Meaning","question":"What does S in SOLID stand for?","options":["Single Responsibility","Simple","Secure","Stable"],"answer":"Single Responsibility","hint":"One job per class.","solution":"Single Responsibility.","explanation":"Each class should have one responsibility."},
    {"id":"a19","level":"advanced","topic":"Production","type":"mcq","difficulty":"medium","title":"logging vs print","question":"Why use logging in production?","options":["Levels and timestamps","Faster","Less code","Better color"],"answer":"Levels and timestamps","hint":"Structured output.","solution":"Levels, timestamps, and destinations.","explanation":"logging gives structured, configurable output."},
    {"id":"a20","level":"advanced","topic":"Capstone","type":"mcq","difficulty":"hard","title":"Production API","question":"What does the advanced capstone build?","options":["Production-style service","A print statement","A variable","A comment"],"answer":"Production-style service","hint":"Real architecture.","solution":"A production-style service.","explanation":"The capstone combines async, config, and clean architecture."},
]

# ================== PYTHON REAL-WORLD PROJECTS ==================
PYTHON_PROJECTS = [
    {
        "id": "proj-001",
        "title": "CLI To-Do List",
        "level": "beginner",
        "description": "A command-line to-do app with add, view, complete, and delete features.",
        "guide": "Build a task manager that stores todos in a JSON file. You will practice functions, loops, dictionaries, and file handling. Features: add a task, view all tasks, mark a task done, and delete a task.",
        "code": "import json\nfrom pathlib import Path\n\nFILE = Path('todos.json')\n\ndef load():\n    return json.loads(FILE.read_text()) if FILE.exists() else []\n\ndef save(todos):\n    FILE.write_text(json.dumps(todos, indent=2))\n\ndef add(title):\n    todos = load()\n    todos.append({'title': title, 'done': False})\n    save(todos)\n\ndef view():\n    for i, t in enumerate(load(), 1):\n        mark = 'x' if t['done'] else ' '\n        print(f\"{i}. [{mark}] {t['title']}\")\n\nadd('Learn Python')\nadd('Build project')\nview()",
        "output": "1. [ ] Learn Python\n2. [ ] Build project",
        "rating": 4.8,
        "likes": 245,
        "views": 1200,
    },
    {
        "id": "proj-002",
        "title": "Weather API Client",
        "level": "intermediate",
        "description": "Fetch real weather data from a public API and display it cleanly.",
        "guide": "Build a CLI tool that asks for a city name, calls a weather API, and prints temperature and conditions. Practice requests, JSON parsing, error handling, and environment variables for the API key.",
        "code": "import requests\nimport os\n\nAPI_KEY = os.environ.get('WEATHER_API_KEY', 'demo')\nBASE = 'https://api.openweathermap.org/data/2.5/weather'\n\ndef get_weather(city):\n    try:\n        resp = requests.get(BASE, params={'q': city, 'appid': API_KEY, 'units': 'metric'})\n        resp.raise_for_status()\n        data = resp.json()\n        temp = data['main']['temp']\n        desc = data['weather'][0]['description']\n        return f\"{city}: {temp}°C, {desc}\"\n    except requests.RequestException as err:\n        return f\"Error: {err}\"\n\nprint(get_weather('Karachi'))",
        "output": "Karachi: 32°C, clear sky",
        "rating": 4.6,
        "likes": 180,
        "views": 890,
    },
    {
        "id": "proj-003",
        "title": "Async Web Scraper",
        "level": "advanced",
        "description": "Scrape multiple pages concurrently using asyncio and aiohttp.",
        "guide": "Build a fast scraper that fetches several URLs at once. Practice async/await, asyncio.gather, aiohttp for async requests, and proper error handling per request so one failure doesn't stop the rest.",
        "code": "import asyncio\nimport aiohttp\n\nasync def fetch(session, url):\n    try:\n        async with session.get(url) as resp:\n            return f\"{url} -> {resp.status}\"\n    except Exception as err:\n        return f\"{url} -> FAILED: {err}\"\n\nasync def main():\n    urls = ['https://example.com', 'https://python.org', 'https://github.com']\n    async with aiohttp.ClientSession() as session:\n        results = await asyncio.gather(*(fetch(session, u) for u in urls))\n    for r in results:\n        print(r)\n\nasyncio.run(main())",
        "output": "https://example.com -> 200\nhttps://python.org -> 200\nhttps://github.com -> 200",
        "rating": 4.9,
        "likes": 312,
        "views": 1500,
    },
]


# ================== LEARNING HUB HELPERS ==================
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
    for cat in defaults:
        cur.execute("SELECT id FROM categories WHERE level = %s", (cat,))
        if not cur.fetchone():
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (cat,))
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
    per_page = min(50, request.args.get("per_page", 12, type=int))
    if per_page < 1:
        per_page = 12
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()
    conditions = ["d.approved = 1"]
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
               COALESCE(avg_r.avg_rating, 0) as avg_rating
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
        FROM categories c LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1
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
        }
        for r in books_data
    ]
    categories = [{"id": r[0], "level": r[1], "count": r[2]} for r in cat_data]

    home_stats = get_home_stats()

    featured_book = get_book_of_the_day()

    streak = longest = 0
    if "user_id" in session:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT streak_count, longest_streak FROM user_streaks WHERE user_id = %s",
            (session["user_id"],),
        )
        row = cur.fetchone()
        if row:
            streak, longest = row
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
                       COALESCE(avg_r.avg_rating, 0) as avg_rating
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
                    }
                )
        cur.close()

    return render_template(
        "index.html",
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
        total_categories=home_stats["total_categories"],
        recent_reviews=home_stats["recent_reviews"],
        total_reviews=home_stats["total_reviews"],
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
               COALESCE(avg_r.avg_rating, 0) AS avg_rating
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
        LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1
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
        }
        for r in rows
    ]

    return render_template(
        "learning_hub.html",
        category=category_name,
        category_slug=category_slug,
        books=books,
        total_books=total_books,
        total_downloads=total_downloads,
        page=page,
        total_pages=total_pages,
        all_categories=all_categories,
        category_modules=GENERIC_MODULES,
    )
@app.route("/learn/python/practice")
def python_practice():
    return render_template(
        "python/practice.html",
        category="Python",
        category_slug="python",
        lessons=None,
        practice_items=PYTHON_PRACTICE,
        practice_projects=PYTHON_PROJECTS,
    )
#================== LEARNING HUB MODULES PYTHON (Category + Module Pages) ==================
@app.route("/learn/<slug>/<module>")
def category_module(slug, module):
    cur = mysql.connection.cursor()
    category = slug_to_category_name(slug, cur)
    cur.close()

    if not category:
        abort(404)

    module_info = next(
        (m for m in GENERIC_MODULES if m["slug"] == module),
        None,
    )
    if not module_info:
        abort(404)

    folder = category_to_slug(category)
    lessons = None
    practice_items = None
    practice_projects = None

    if slug == "python" and module == "beginner":
        lessons = PYTHON_BEGINNER_LESSONS
    if slug == "python" and module == "intermediate":
        lessons = PYTHON_INTERMEDIATE_LESSONS
    if slug == "python" and module == "advanced":
        lessons = PYTHON_ADVANCED_LESSONS
    if slug == "python" and module == "practice":
        practice_items = PYTHON_PRACTICE
        practice_projects = PYTHON_PROJECTS

    return render_template(
        f"{folder}/{module}.html",
        category=category,
        category_slug=slug,
        lessons=lessons,
        practice_items=practice_items,
        practice_projects=practice_projects,
        info=module_info,
    )

# ================== PRACTICE CHALLENGE API ==================
@app.route("/api/practice/challenges")
def practice_challenges_api():
    level = request.args.get("level", "beginner")
    topic = request.args.get("topic", "")
    challenge_type = request.args.get("type", "")

    filtered = [
        item for item in PYTHON_PRACTICE
        if item["level"] == level
        and (not topic or item["topic"].lower() == topic.lower())
        and (not challenge_type or item["type"] == challenge_type)
    ]

    # Return safe data only — answer/solution included for client-side checking
    return jsonify({
        "count": len(filtered),
        "challenges": filtered,
    })


@app.route("/api/practice/next")
def practice_next_challenge():
    level = request.args.get("level", "beginner")
    topic = request.args.get("topic", "")
    exclude_id = request.args.get("exclude", "")

    candidates = [
        item for item in PYTHON_PRACTICE
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
    cur = mysql.connection.cursor()

    # 1) IELTS category id find karo
    cur.execute("SELECT id FROM categories WHERE level = 'IELTS' LIMIT 1")
    cat_row = cur.fetchone()

    if not cat_row:
        cur.close()
        books = []
    else:
        cat_id = cat_row[0]

        # 2) Approved IELTS books lo
        cur.execute(
            """
            SELECT id, title, author, image_url,
                   COALESCE(download_count, 0),
                   COALESCE(view_count, 0),
                   description, language
            FROM documents
            WHERE category_id = %s AND approved = 1
            ORDER BY id DESC
            """,
            (cat_id,),
        )
        rows = cur.fetchall()
        books = [
            {
                "id": r[0],
                "title": r[1],
                "author": r[2],
                "image_url": r[3],
                "download_count": r[4],
                "view_count": r[5],
                "description": r[6],
                "language": r[7],
            }
            for r in rows
        ]
        cur.close()

    return redirect("/learn/ielts")


# -----IELTS MODULE ROUTE-----
@app.route("/ielts/<module>")
def ielts_module(module):
    module_map = {
        "listening": {
            "title": "IELTS Listening",
            "icon": "bi-headphones",
            "color": "text-primary",
            "tips": [
                "Read questions before audio starts",
                "Listen for synonyms and paraphrases",
                "Practice note-taking while listening",
                "Focus on numbers, dates, and names",
                "Don't leave any answer blank",
            ],
        },
        "reading": {
            "title": "IELTS Reading",
            "icon": "bi-book",
            "color": "text-warning",
            "tips": [
                "Skim passage first, then read questions",
                "Manage time: 20 minutes per passage",
                "Underline keywords and dates",
                "Practice True/False/Not Given questions",
                "Improve vocabulary daily",
            ],
        },
        "writing": {
            "title": "IELTS Writing",
            "icon": "bi-pencil-square",
            "color": "text-danger",
            "tips": [
                "Task 1: describe data clearly",
                "Task 2: plan before writing",
                "Keep paragraphs short and focused",
                "Use linking words (however, therefore)",
                "Check grammar and spelling",
            ],
        },
        "speaking": {
            "title": "IELTS Speaking",
            "icon": "bi-mic",
            "color": "text-success",
            "tips": [
                "Speak naturally, don't memorize",
                "Extend answers with examples",
                "Practice daily for fluency",
                "Record yourself and review",
                "Use varied vocabulary",
            ],
        },
    }

    module_info = module_map.get(module)
    if not module_info:
        abort(404)

    return render_template(f"ielts/{module}.html", module=module, info=module_info)


# ================== BOOK DETAIL ==================
@app.route("/book/<int:book_id>")
def book_detail(book_id):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language, d.category_id
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.id = %s AND d.approved = 1
    """,
        (book_id,),
    )
    book = cur.fetchone()

    if not book:
        cur.close()
        abort(404)

    cur.execute(
        "UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,)
    )
    mysql.connection.commit()

    cur.execute(
        """
        SELECT u.username, r.rating, r.comment, r.created_at, u.id, r.id
        FROM reviews r JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s ORDER BY r.created_at DESC
    """,
        (book_id,),
    )
    reviews_raw = cur.fetchall()
    cur.close()

    reviews = []
    for r in reviews_raw:
        reviews.append(
            {
                "id": r[5],
                "username": r[0],
                "rating": r[1],
                "comment": r[2],
                "created_at": r[3],
                "user_id": r[4],
                "is_official": is_official_user(r[4]),
            }
        )

    lazy_trickle(book_id)

    related_books = []
    cat_id = book[8] if len(book) > 8 else None
    if cat_id:
        cur = mysql.connection.cursor()
        cur.execute(
            """
            SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link,
                   COALESCE(d.download_count, 0) as download_count,
                   COALESCE(d.view_count, 0) as view_count
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
                }
            )

    book_data = {
        "id": book[0],
        "title": book[1],
        "level": book[2],
        "link": book[3],
        "author": book[4],
        "description": book[5],
        "image_url": book[6],
        "language": book[7],
    }
    return render_template(
        "book_detail.html", book=book_data, reviews=reviews, related_books=related_books
    )


# ================== SEO ROUTES ==================
@app.route("/sitemap.xml")
def sitemap():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, title FROM documents WHERE approved = 1 ORDER BY id DESC")
    books = cur.fetchall()
    cur.close()

    static_pages = [
        {
            "loc": url_for("home", _external=True),
            "changefreq": "daily",
            "priority": "1.0",
        },
        {
            "loc": url_for("user_feedback", _external=True),
            "changefreq": "weekly",
            "priority": "0.7",
        },
        {
            "loc": url_for("leaderboard", _external=True),
            "changefreq": "daily",
            "priority": "0.8",
        },
    ]

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in static_pages:
        xml += f'  <url>\n    <loc>{escape(page["loc"])}</loc>\n    <changefreq>{page["changefreq"]}</changefreq>\n    <priority>{page["priority"]}</priority>\n  </url>\n'
    for book in books:
        book_url = url_for("book_detail", book_id=book[0], _external=True)
        xml += f"  <url>\n    <loc>{escape(book_url)}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n"
    xml += "</urlset>"
    return Response(xml, mimetype="application/xml")


@app.route("/robots.txt")
def robots():
    content = (
        f"User-agent: *\nAllow: /\nDisallow: /*?*\nSitemap: {url_for('sitemap', _external=True)}\n"
    )
    return Response(content, mimetype="text/plain")


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
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
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
        "link": book[3],
        "author": book[4],
        "description": book[5],
        "image_url": book[6],
        "language": book[7],
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
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        # ---------- Required fields ----------
        if not username or not email or not password:
            msg = "All fields are required."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        if not first_name or not last_name:
            msg = "First name and last name are required."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        # ---------- Name length limits ----------
        if len(first_name) > 50 or len(last_name) > 50:
            msg = "Names must be 50 characters or less."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        # ---------- Email format ----------
        if not is_valid_email(email):
            msg = "Please enter a valid email address."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        # ---------- Username format ----------
        if not re.fullmatch(r"[A-Za-z0-9]{3,20}", username):
            msg = "Username must be 3-20 letters and numbers only (no spaces or symbols)."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        # ---------- Reserved usernames ----------
        reserved = os.getenv("RESERVED_USERNAMES", "")
        if reserved:
            reserved_list = [
                r.strip().lower()
                for r in reserved.split(",")
                if r.strip()
            ]
            username_lower = username.lower()
            for word in reserved_list:
                if word in username_lower:
                    msg = "This username is not allowed. Please choose a different one."
                    if is_ajax:
                        return jsonify({"error": msg}), 400
                    return render_template("auth.html", mode="signup", error=msg)

        # ---------- Password strength (8+ chars, upper, lower, digit) ----------
        if len(password) < 8:
            msg = "Password must be at least 8 characters."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        if not any(c.isupper() for c in password):
            msg = "Password must contain at least one uppercase letter."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        if not any(c.islower() for c in password):
            msg = "Password must contain at least one lowercase letter."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        if not any(c.isdigit() for c in password):
            msg = "Password must contain at least one number."
            if is_ajax:
                return jsonify({"error": msg}), 400
            return render_template("auth.html", mode="signup", error=msg)

        # ---------- Duplicate username check ----------
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            msg = "This username is already taken. Try a different one."
            if is_ajax:
                return jsonify({"error": msg}), 409
            return render_template("auth.html", mode="signup", error=msg)
        cur.close()

        # ---------- Duplicate email check ----------
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            msg = "This email is already registered. Please login instead."
            if is_ajax:
                return jsonify({"error": msg}), 409
            return render_template("auth.html", mode="signup", error=msg)
        cur.close()

        # ---------- Hash + token + insert (validation ke BAAD) ----------
        hashed = generate_password_hash(password)
        token = secrets.token_urlsafe(32)

        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password, verification_token, first_name, last_name) VALUES (%s, %s, %s, %s, %s, %s)",
            (username, email, hashed, token, first_name, last_name),
        )
        mysql.connection.commit()
        cur.close()

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
            return jsonify({
                "success": True,
                "message": "Account created! Please check your email to verify.",
                "redirect": url_for("user_login")
            })

        flash("Account created! Please check your email to verify.", "success")
        return redirect(url_for("user_login"))

    return render_template("auth.html", mode="signup")

@app.route("/user/login", methods=["GET", "POST"])
@limiter.limit(USER_ACTION_RATELIMIT)
def user_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # ==== Exponential backoff check ====
        client_ip = request.headers.get(
            "X-Forwarded-For", request.remote_addr or "unknown"
        ).split(",")[0].strip()
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
            app.logger.warning(f"Login failure (no account) for {email} from {client_ip}; backoff {wait}s")
            msg = "No account found with this email. Please sign up first."
            if is_ajax:
                return jsonify({"error": msg}), 401
            return render_template("auth.html", mode="login", error=msg)

        if not check_password_hash(user[2], password):
            wait = record_login_failure(client_ip, email)
            app.logger.warning(f"Login failure (bad password) for {email} from {client_ip}; backoff {wait}s")
            msg = f"Invalid password. Please try again. (Wait {wait}s before retry)"
            if is_ajax:
                return jsonify({"error": msg}), 401
            return render_template("auth.html", mode="login", error=msg)

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
            return render_template("auth.html", mode="login", error=msg)

        # ==== Success: clear backoff + set session ====
        clear_login_backoff(client_ip, email)

        session.permanent = True
        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["user_display_name"] = user[1]
        session["email"] = email
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

    return render_template("auth.html", mode="login")


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
    session.pop("user_id", None)
    session.pop("user_name", None)
    return redirect(url_for("home"))


# ================== FAVORITES & HISTORY ==================
@app.route("/user/favorites")
def user_favorites():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
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
        }
        for r in books
    ]
    return render_template("user_favorites.html", pdfs=real_pdfs)


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
    return render_template("user_history.html", pdfs=real_pdfs)


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
@app.route("/book/<int:book_id>/review", methods=["POST"])
@limiter.limit(AUTH_RATELIMIT)
def add_review(book_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "")
    if not rating or rating < 1 or rating > 5:
        return jsonify({"error": "Invalid rating"}), 400
    user_id = session["user_id"]
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO reviews (user_id, book_id, rating, comment) VALUES (%s, %s, %s, %s)",
        (user_id, book_id, rating, comment),
    )
    mysql.connection.commit()
    cur.close()
    award_points(user_id, 5, book_id, action="review")
    return jsonify({"success": True})


# -------------------- PROTECTED DOWNLOAD & READ ONLINE --------------------
@app.route("/book/<int:book_id>/download")
def download_book(book_id):
    if "user_id" not in session:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Login required"}), 401
        flash("Please login to download books.", "danger")
        return redirect(url_for("user_login"))

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT telegram_link FROM documents WHERE id = %s AND approved = 1", (book_id,)
    )
    book = cur.fetchone()
    if not book:
        cur.close()
        abort(404)
    cur.execute(
        "UPDATE documents SET download_count = download_count + 1 WHERE id = %s",
        (book_id,),
    )
    mysql.connection.commit()
    cur.close()

    r2_key = extract_r2_key(book[0])
    if not r2_key:
        flash("Download not available.", "danger")
        return redirect(url_for("home"))

    presigned = get_presigned_url(r2_key, expiration=300)
    if not presigned:
        flash("Could not generate download link.", "danger")
        return redirect(url_for("home"))

    if "user_id" in session:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
            (session["user_id"], book_id),
        )
        mysql.connection.commit()
        cur.close()

    return redirect(presigned)


@app.route("/book/<int:book_id>/read")
def read_online(book_id):
    if "user_id" not in session:
        flash("Please login to read books online.", "danger")
        return redirect(url_for("user_login"))

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT telegram_link, title FROM documents WHERE id = %s AND approved = 1",
        (book_id,),
    )
    book = cur.fetchone()
    if not book:
        cur.close()
        abort(404)
    cur.execute(
        "UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,)
    )
    mysql.connection.commit()
    cur.close()

    r2_key = extract_r2_key(book[0])
    if not r2_key:
        flash("Read online not available.", "danger")
        return redirect(url_for("home"))

    presigned = get_presigned_url(r2_key, expiration=600)
    if not presigned:
        flash("Could not generate reading link.", "danger")
        return redirect(url_for("home"))

    return render_template(
        "read_online.html", pdf_url=presigned, book_title=book[1], book_id=book_id
    )


# ================== OFFICIAL ADMIN ROUTES ==================
@app.route("/admin", methods=["GET", "POST"])
@official_admin_required
@cache.cached(timeout=600, unless=lambda: request.method == "POST")
def admin():
    if request.method == "POST":
        if "pdf_file" not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files["pdf_file"]
        if file.filename == "" or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file"}), 400

        pdf_bytes = file.read()
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

        cur = mysql.connection.cursor()
        if is_duplicate(display_title, author, cur):
            cur.close()
            return jsonify({"error": "This book already exists in the database."}), 400
        cur.close()

        try:
            pdf_key = generate_r2_key("uploads", clean_base, ".pdf")
            pdf_url = upload_to_r2(pdf_bytes, pdf_key, content_type="application/pdf")
        except Exception as e:
            app.logger.error(f"PDF upload failed: {e}")
            return jsonify({"error": "Failed to upload PDF."}), 500

        cover_bytes = None
        cover_extension = ".png"
        if (
            "cover_image" in request.files
            and request.files["cover_image"].filename != ""
        ):
            cover_file = request.files["cover_image"]
            if not allowed_image_file(cover_file.filename):
                return jsonify({"error": "Invalid cover image format."}), 400
            cover_bytes = cover_file.read()
            cover_bytes = compress_image(cover_bytes, max_size=(800, 800), quality=80)
            if len(cover_bytes) > 5 * 1024 * 1024:
                return jsonify({"error": "Cover image exceeds 5 MB."}), 400
            cover_extension = os.path.splitext(cover_file.filename)[1].lower()
        else:
            cover_bytes = extract_cover_from_pdf(pdf_bytes)
            if not cover_bytes:
                return (
                    jsonify(
                        {
                            "error": "Could not generate cover from PDF. Please upload a cover image manually."
                        }
                    ),
                    400,
                )

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
            return jsonify({"error": "Failed to upload cover image."}), 500

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

        cur.execute(
            """
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, approved, uploaded_by, download_count, view_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """,
            (
                cat_id,
                display_title,
                pdf_url,
                author,
                description,
                image_url,
                "English",
                session["user_id"],
                dl_count,
                vw_count,
            ),
        )
        mysql.connection.commit()
        cur.close()

        return jsonify(
            {
                "success": True,
                "title": display_title,
                "category": category,
                "message": f"Book '{display_title}' uploaded in {category}! Waiting for approval.",
            }
        )

    cur = mysql.connection.cursor()
    DEFAULT_CATEGORIES = [
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
    for cat in DEFAULT_CATEGORIES:
        cur.execute("SELECT id FROM categories WHERE level = %s", (cat,))
        if not cur.fetchone():
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (cat,))
    mysql.connection.commit()
    cur.execute("SELECT level FROM categories ORDER BY level")
    categories = [row[0] for row in cur.fetchall()]
    cur.close()
    return render_template("admin.html", categories=categories)


@app.route("/admin/pending/count")
@official_admin_required
def pending_count():
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM documents WHERE approved = 0 AND status = 'pending'"
    )
    count = cur.fetchone()[0]
    cur.close()
    return jsonify({"count": count})


@app.route("/admin/pending")
@official_admin_required
def pending_books():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.author, d.created_at, d.telegram_link
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved = 0 AND d.status = 'pending' ORDER BY d.id DESC
    """)
    books = cur.fetchall()
    cur.close()
    books_list = [
        {
            "id": b[0],
            "title": b[1],
            "level": b[2],
            "author": b[3],
            "created_at": str(b[4]) if b[4] else "",
            "link": b[5],
        }
        for b in books
    ]
    return render_template("pending.html", books=books_list)


@app.route("/admin/approve/<int:book_id>", methods=["POST"])
@official_admin_required
def approve_book(book_id):
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT title, uploaded_by FROM documents WHERE id = %s AND status = 'pending'",
        (book_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Book not found"}), 404
    title, uploader_id = row
    cur.execute(
        "UPDATE documents SET approved = 1, status = 'approved', approved_at = NOW() WHERE id = %s AND status = 'pending'",
        (book_id,),
    )
    mysql.connection.commit()
    if uploader_id:
        cur.execute("SELECT email, username FROM users WHERE id = %s", (uploader_id,))
        user = cur.fetchone()
        if user:
            html = make_approval_email(
                title, "approved", "Your book has been approved!"
            )
            send_email_notification(
                "Book Approved - DocoDive",
                user[0],
                f"Your DocoDive document '{title}' has been approved.",
                html_body=html,
            )
            create_notification(
                uploader_id,
                "approval",
                f"<strong>{title}</strong> has been approved ✅",
                url_for("book_detail", book_id=book_id),
                {"book_id": book_id, "action_by": "admin", "uploader_id": uploader_id},
            )
    cur.close()
    return jsonify({"success": True})


@app.route("/admin/reject/<int:book_id>", methods=["POST"])
@official_admin_required
def reject_book(book_id):
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT title, uploaded_by, telegram_link FROM documents WHERE id = %s AND status = 'pending'",
        (book_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Book not found"}), 404
    title, uploader_id, file_link = row
    if file_link:
        r2_key = extract_r2_key(file_link)
        if r2_key:
            delete_from_r2(r2_key)
    cur.execute(
        "UPDATE documents SET approved = 0, status = 'rejected', approved_at = NULL WHERE id = %s AND status = 'pending'",
        (book_id,),
    )
    mysql.connection.commit()
    if uploader_id:
        cur.execute("SELECT email, username FROM users WHERE id = %s", (uploader_id,))
        user = cur.fetchone()
        if user:
            html = make_approval_email(title, "rejected", "Your book was rejected.")
            send_email_notification(
                "Book Rejected - DocoDive",
                user[0],
                f"Your document '{title}' was not approved.",
                html_body=html,
            )
            create_notification(
                uploader_id,
                "rejection",
                f"<strong>{title}</strong> has been rejected ❌",
                url_for("user_upload"),
                {"book_id": book_id, "action_by": "admin", "uploader_id": uploader_id},
            )
    cur.close()
    return jsonify({"success": True})


@app.route("/admin/approve-all", methods=["POST"])
@official_admin_required
def approve_all_books():
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE documents SET approved = 1, status = 'approved', approved_at = NOW() WHERE approved = 0 AND status = 'pending'"
    )
    count = cur.rowcount
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True, "count": count})


@app.route("/admin/books")
@official_admin_required
def admin_books_list():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, d.category_id, d.telegram_link, d.author,
               d.description, d.image_url, d.language, c.level
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        ORDER BY d.id DESC
    """)
    books = cur.fetchall()
    cur.close()
    books_list = [
        {
            "id": b[0],
            "title": b[1],
            "category_id": b[2],
            "link": b[3],
            "author": b[4],
            "description": b[5],
            "image_url": b[6],
            "language": b[7],
            "level": b[8],
        }
        for b in books
    ]
    return render_template("admin_books.html", books=books_list)


@app.route("/admin/edit/<int:book_id>", methods=["GET", "POST"])
@official_admin_required
def edit_book(book_id):
    cur = mysql.connection.cursor()
    if request.method == "POST":
        cur.execute(
            "SELECT telegram_link, image_url FROM documents WHERE id = %s", (book_id,)
        )
        old = cur.fetchone()
        old_pdf = old[0] if old else None
        old_cover = old[1] if old else None

        title = request.form.get("title")
        category_name = request.form.get("category")
        author = request.form.get("author")
        desc = request.form.get("desc")
        img_url = request.form.get("img")
        language = request.form.get("language", "English")

        if "pdf_file" in request.files and request.files["pdf_file"].filename != "":
            file = request.files["pdf_file"]
            if not allowed_file(file.filename):
                return jsonify({"error": "Only PDF files are allowed."}), 400
            pdf_bytes = file.read()

            # ==== NAYA: Size limit ====
            if len(pdf_bytes) > 500 * 1024 * 1024:
                return jsonify({"error": "File too large. Maximum 500 MB allowed."}), 413

            # ==== NAYA: Content validation ====
            if not is_valid_pdf(pdf_bytes):
                return jsonify({"error": "Invalid PDF content. File is not a real PDF."}), 400

            clean_title = (
                clean_professional_name(title)
                if title
                else clean_professional_name("book")
            )
            pdf_key = generate_r2_key("uploads", clean_title, ".pdf")
            new_pdf_url = upload_to_r2(
                pdf_bytes, pdf_key, content_type="application/pdf"
            )
            if old_pdf:
                old_key = extract_r2_key(old_pdf)
                if old_key:
                    delete_from_r2(old_key)
            cur.execute(
                """
                UPDATE documents SET category_id=(SELECT id FROM categories WHERE level=%s), title=%s,
                telegram_link=%s, author=%s, description=%s, image_url=%s, language=%s WHERE id=%s
            """,
                (
                    category_name,
                    title,
                    new_pdf_url,
                    author,
                    desc,
                    img_url or old_cover or None,
                    language,
                    book_id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE documents SET category_id=(SELECT id FROM categories WHERE level=%s), title=%s,
                author=%s, description=%s, image_url=%s, language=%s WHERE id=%s
            """,
                (
                    category_name,
                    title,
                    author,
                    desc,
                    img_url or old_cover or None,
                    language,
                    book_id,
                ),
            )

        if (
            "cover_image" in request.files
            and request.files["cover_image"].filename != ""
        ):
            cover_file = request.files["cover_image"]
            if allowed_image_file(cover_file.filename):
                cover_bytes = cover_file.read()
                if len(cover_bytes) <= 2 * 1024 * 1024:
                    clean_title = (
                        clean_professional_name(title)
                        if title
                        else clean_professional_name("book")
                    )
                    img_ext = os.path.splitext(cover_file.filename)[1].lower()
                    cover_key = generate_r2_key("covers", clean_title, img_ext)
                    mime_map = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                    }
                    mime = mime_map.get(img_ext, "application/octet-stream")
                    new_cover_url = upload_to_r2(
                        cover_bytes, cover_key, content_type=mime
                    )
                    if old_cover:
                        old_key = extract_r2_key(old_cover)
                        if old_key:
                            delete_from_r2(old_key)
                    cur.execute(
                        "UPDATE documents SET image_url = %s WHERE id = %s",
                        (new_cover_url, book_id),
                    )

        mysql.connection.commit()
        cur.close()
        return redirect(url_for("admin_books_list"))

    cur = mysql.connection.cursor()
    DEFAULT_CATEGORIES = [
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
    ]
    for cat in DEFAULT_CATEGORIES:
        cur.execute("SELECT id FROM categories WHERE level = %s", (cat,))
        if not cur.fetchone():
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (cat,))
    mysql.connection.commit()

    cur.execute(
        "SELECT id, title, category_id, telegram_link, author, description, image_url, language FROM documents WHERE id = %s",
        (book_id,),
    )
    book_row = cur.fetchone()
    cur.execute("SELECT id, level FROM categories ORDER BY id")
    categories_raw = cur.fetchall()
    categories = [{"id": row[0], "level": row[1]} for row in categories_raw]
    cur.close()
    if not book_row:
        abort(404)
    book = {
        "id": book_row[0],
        "title": book_row[1],
        "category_id": book_row[2],
        "link": book_row[3],
        "author": book_row[4],
        "description": book_row[5],
        "image_url": book_row[6],
        "language": book_row[7],
    }
    return render_template("edit_book.html", book=book, categories=categories)


@app.route("/admin/delete/<int:book_id>", methods=["POST"])
@official_admin_required
def delete_book(book_id):
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT telegram_link, image_url FROM documents WHERE id = %s", (book_id,)
    )
    row = cur.fetchone()
    if row:
        for url in (row[0], row[1]):
            key = extract_r2_key(url) if url else None
            if key:
                delete_from_r2(key)
    cur.execute("DELETE FROM documents WHERE id = %s", (book_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": "Book deleted successfully!"})


@app.route("/admin/dashboard")
@official_admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")


@app.route("/api/admin/stats")
@official_admin_required
def admin_stats():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total_books = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM categories")
    total_categories = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute(
        "SELECT d.title, c.level, d.created_at FROM documents d JOIN categories c ON d.category_id = c.id ORDER BY d.id DESC LIMIT 5"
    )
    recent = cur.fetchall()
    cur.close()
    recent_uploads = [
        {"title": r[0], "level": r[1], "created_at": str(r[2])} for r in recent
    ]
    return jsonify(
        {
            "total_books": total_books,
            "total_categories": total_categories,
            "total_users": total_users,
            "recent_uploads": recent_uploads,
        }
    )


@app.route("/api/categories/live-counts")
@cache.cached(timeout=60)
def live_category_counts():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT c.id, c.level, COUNT(d.id) AS total
        FROM categories c LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1
        GROUP BY c.id ORDER BY c.id
    """)
    data = cur.fetchall()
    cur.close()
    return jsonify([{"id": r[0], "level": r[1], "count": r[2]} for r in data])


@app.route("/admin/users")
@official_admin_required
def list_users():
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, username, email, verified, created_at FROM users ORDER BY id"
    )
    users = cur.fetchall()
    cur.close()
    users_list = [
        {
            "id": r[0],
            "username": r[1],
            "email": r[2],
            "verified": r[3],
            "created_at": str(r[4]),
        }
        for r in users
    ]
    return render_template("admin_users.html", users=users_list)


@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if "user_id" not in session or not is_official_user(session["user_id"]):
        return jsonify({"error": "Unauthorized"}), 403
    if session.get("user_id") == user_id:
        return jsonify({"error": "You cannot delete your own account."}), 400
    if is_official_user(user_id):
        return jsonify({"error": "Cannot delete the official community account."}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM favorites WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM download_history WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM reviews WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM book_comments WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM user_points WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM user_streaks WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM notifications WHERE user_id = %s", (user_id,))
        cur.execute(
            "UPDATE documents SET uploaded_by = NULL WHERE uploaded_by = %s", (user_id,)
        )
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})
    except Exception as e:
        mysql.connection.rollback()
        cur.close()
        app.logger.error(f"Admin delete user failed for user_id={user_id}: {e}", exc_info=True)
        return jsonify({"error": "Delete failed due to a server error. Please try again later."}), 500


@app.route("/admin/analytics")
@official_admin_required
def admin_analytics():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total_books = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM download_history")
    total_downloads = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.close()
    return render_template(
        "admin_analytics.html",
        total_books=total_books,
        total_downloads=total_downloads,
        total_users=total_users,
    )


@app.route("/admin/trickle-counts")
@official_admin_required
def trickle_counts():
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id FROM documents WHERE approved = 1 AND created_at >= %s",
        (seven_days_ago,),
    )
    books = cur.fetchall()
    for book in books:
        dl_growth = random.randint(5, 20)
        vw_growth = random.randint(10, 40)
        cur.execute(
            """
            UPDATE documents SET download_count = download_count + %s,
                view_count = view_count + %s, last_trickle_time = NOW() WHERE id = %s
        """,
            (dl_growth, vw_growth, book[0]),
        )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True, "updated": len(books)})


@app.route("/admin/official-profile", methods=["GET", "POST"])
@official_admin_required
def admin_official_profile():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if username:
            cur = mysql.connection.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()
            if user:
                set_site_setting("official_user_id", str(user[0]))
                flash(f"Official profile set to {username}", "success")
            else:
                flash("User not found.", "danger")
        return redirect(url_for("admin_official_profile"))

    official_user_id = get_site_setting("official_user_id")
    official_user = None
    if official_user_id:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, username, avatar_url FROM users WHERE id = %s",
            (official_user_id,),
        )
        official_user = cur.fetchone()
        cur.close()
    return render_template("admin_official_profile.html", official_user=official_user)


# ================== MODERATION API ==================
@app.route("/api/review/<int:review_id>/delete", methods=["POST"])
@limiter.limit("10 per minute")
def delete_review_api(review_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/api/comment/<int:comment_id>/delete", methods=["POST"])
@limiter.limit("10 per minute")
def delete_comment_api(comment_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM book_comments WHERE id = %s", (comment_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/api/comment/<int:comment_id>/reply", methods=["POST"])
@limiter.limit("10 per minute")
def reply_as_official_api(comment_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    reply_text = data.get("reply_text", "").strip()
    if not reply_text:
        return jsonify({"error": "Reply text required"}), 400
    official_user_id = get_site_setting("official_user_id")
    if not official_user_id:
        return jsonify({"error": "Official user not set"}), 500
    cur = mysql.connection.cursor()
    cur.execute("SELECT book_id FROM book_comments WHERE id = %s", (comment_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Comment not found"}), 404
    book_id = row[0]
    cur.execute(
        "INSERT INTO book_comments (book_id, user_id, parent_id, comment) VALUES (%s, %s, %s, %s)",
        (book_id, official_user_id, comment_id, reply_text),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/api/review/<int:review_id>/reply", methods=["POST"])
@limiter.limit("10 per minute")
def reply_to_review_api(review_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    reply_text = data.get("reply_text", "").strip()
    if not reply_text:
        return jsonify({"error": "Reply text required"}), 400
    official_user_id = get_site_setting("official_user_id")
    if not official_user_id:
        return jsonify({"error": "Official user not set"}), 500
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT book_id FROM reviews WHERE id = %s", (review_id,))
        review = cur.fetchone()
        if not review:
            cur.close()
            return jsonify({"error": "Review not found"}), 404
        book_id = review[0]
        full_comment = f"📢 Official reply: {reply_text}"
        cur.execute(
            "INSERT INTO book_comments (book_id, user_id, parent_id, comment) VALUES (%s, %s, %s, %s)",
            (book_id, official_user_id, -review_id, full_comment),
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Official reply to review failed: {e}")
        try:
            cur.close()
        except Exception:
            pass
        return jsonify({"error": "Database error"}), 500


# ================== MODERATION PANEL ==================
@app.route("/moderation")
@limiter.limit("30 per minute")
def moderation_panel():
    if not is_moderator():
        abort(403)

    days = request.args.get("days", 30, type=int)
    since = datetime.now() - timedelta(days=days)

    cur = mysql.connection.cursor()

    cur.execute(
        """
        SELECT r.id, u.username, u.avatar_url, d.title, d.id AS book_id,
               r.rating, r.comment, r.created_at, u.id
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        JOIN documents d ON r.book_id = d.id
        WHERE r.created_at >= %s
        ORDER BY r.created_at DESC
        LIMIT 50
    """,
        (since,),
    )
    reviews_raw = cur.fetchall()
    reviews = []
    for row in reviews_raw:
        reviews.append(
            {
                "id": row[0],
                "username": row[1],
                "avatar": row[2],
                "book_title": row[3],
                "book_id": row[4],
                "rating": row[5],
                "comment": row[6],
                "created_at": row[7].strftime("%b %d, %Y %H:%M") if row[7] else "",
                "user_id": row[8],
                "is_official": is_official_user(row[8]),
            }
        )

    cur.execute(
        """
        SELECT c.id, u.username, u.avatar_url, d.title, d.id AS book_id,
               c.comment, c.created_at, u.id
        FROM book_comments c
        JOIN users u ON c.user_id = u.id
        JOIN documents d ON c.book_id = d.id
        WHERE c.parent_id >= 0 AND c.created_at >= %s
        ORDER BY c.created_at DESC
        LIMIT 50
    """,
        (since,),
    )
    comments_raw = cur.fetchall()
    comments = []
    comment_ids = []
    for row in comments_raw:
        comments.append(
            {
                "id": row[0],
                "username": row[1],
                "avatar": row[2],
                "book_title": row[3],
                "book_id": row[4],
                "comment": row[5],
                "created_at": row[6].strftime("%b %d, %Y %H:%M") if row[6] else "",
                "user_id": row[7],
                "is_official": is_official_user(row[7]),
            }
        )
        comment_ids.append(row[0])

    official_user_id = get_site_setting("official_user_id")
    comment_replies = {}
    if official_user_id and comment_ids:
        placeholders = ",".join(["%s"] * len(comment_ids))
        cur.execute(
            f"""
            SELECT id, user_id, parent_id, comment, created_at
            FROM book_comments
            WHERE user_id = %s AND parent_id IN ({placeholders})
            ORDER BY created_at ASC
        """,
            [official_user_id] + comment_ids,
        )
        reply_rows = cur.fetchall()
        for r in reply_rows:
            comment_replies[r[2]] = {
                "id": r[0],
                "comment": r[3],
                "created_at": r[4].strftime("%b %d, %Y %H:%M") if r[4] else "",
            }

    cur.execute("SELECT COUNT(*) FROM reviews WHERE created_at >= %s", (since,))
    total_reviews = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM book_comments WHERE parent_id >= 0 AND created_at >= %s",
        (since,),
    )
    total_comments = cur.fetchone()[0]

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cur.execute("SELECT COUNT(*) FROM reviews WHERE created_at >= %s", (today_start,))
    new_reviews_today = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM book_comments WHERE parent_id >= 0 AND created_at >= %s",
        (today_start,),
    )
    new_comments_today = cur.fetchone()[0]

    daily_reviews = defaultdict(int)
    daily_comments = defaultdict(int)
    daily_replies = defaultdict(int)

    cur.execute(
        "SELECT DATE(created_at), COUNT(*) FROM reviews WHERE created_at >= %s GROUP BY DATE(created_at)",
        (since,),
    )
    for row in cur.fetchall():
        daily_reviews[str(row[0])] = row[1]

    cur.execute(
        "SELECT DATE(created_at), COUNT(*) FROM book_comments WHERE parent_id >= 0 AND created_at >= %s GROUP BY DATE(created_at)",
        (since,),
    )
    for row in cur.fetchall():
        daily_comments[str(row[0])] = row[1]

    if official_user_id:
        cur.execute(
            "SELECT DATE(created_at), COUNT(*) FROM book_comments WHERE parent_id < 0 AND user_id = %s AND created_at >= %s GROUP BY DATE(created_at)",
            (official_user_id, since),
        )
        for row in cur.fetchall():
            daily_replies[str(row[0])] = row[1]

    date_range = []
    current = since
    while current <= datetime.now():
        date_range.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    chart_labels = json.dumps(date_range)
    chart_reviews = json.dumps([daily_reviews.get(d, 0) for d in date_range])
    chart_comments = json.dumps([daily_comments.get(d, 0) for d in date_range])
    chart_replies = json.dumps([daily_replies.get(d, 0) for d in date_range])

    cur.close()

    return render_template(
        "admin_moderation.html",
        reviews=reviews,
        comments=comments,
        comment_replies=comment_replies,
        total_reviews=total_reviews,
        total_comments=total_comments,
        new_reviews_today=new_reviews_today,
        new_comments_today=new_comments_today,
        days=days,
        chart_labels=chart_labels,
        chart_reviews=chart_reviews,
        chart_comments=chart_comments,
        chart_replies=chart_replies,
    )


# ================== FEEDBACK COMMUNITY ==================
@app.route("/feedback", methods=["GET", "POST"])
def user_feedback():
    if request.method == "POST":
        if "user_id" not in session:
            flash("Please login to submit feedback.", "danger")
            return redirect(url_for("user_login"))

        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        if not subject or not message:
            flash("Please fill both subject and message.", "danger")
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
    cur.execute("""
        SELECT f.id, f.subject, f.message, f.created_at, f.like_count, f.official_reply, f.official_replied_at,
               u.username, u.avatar_url, u.id as user_id
        FROM user_feedback f
        LEFT JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC
    """)
    feedbacks = cur.fetchall()
    cur.close()

    feedback_list = []
    current_user_id = session.get("user_id")
    for row in feedbacks:
        fid = row[0]
        is_liked = False
        if current_user_id:
            cur = mysql.connection.cursor()
            cur.execute(
                "SELECT 1 FROM feedback_likes WHERE user_id=%s AND feedback_id=%s",
                (current_user_id, fid),
            )
            is_liked = cur.fetchone() is not None
            cur.close()
        feedback_list.append(
            {
                "id": fid,
                "subject": row[1],
                "message": row[2],
                "created_at": row[3],
                "like_count": row[4] if row[4] else 0,
                "official_reply": row[5],
                "official_replied_at": row[6],
                "username": row[7],
                "avatar_url": row[8],
                "user_id": row[9],
                "is_liked": is_liked,
            }
        )

    return render_template("feedback.html", feedbacks=feedback_list)


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


@app.route("/feedback/<int:feedback_id>/official-reply", methods=["POST"])
@limiter.limit("10 per minute")
def official_feedback_reply(feedback_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    reply_text = request.form.get("reply", "").strip()
    if not reply_text:
        return jsonify({"error": "Reply cannot be empty"}), 400
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE user_feedback SET official_reply=%s, official_replied_at=NOW() WHERE id=%s",
        (reply_text, feedback_id),
    )
    mysql.connection.commit()
    cur.execute(
        """
        SELECT u.email, u.username, f.subject, f.message
        FROM user_feedback f
        JOIN users u ON f.user_id = u.id
        WHERE f.id = %s
    """,
        (feedback_id,),
    )
    row = cur.fetchone()
    cur.close()
    if row:
        email, username, subject, message = row
        if email:
            html_body = make_feedback_reply_email(
                username, subject, message, reply_text
            )
            send_email_notification(
                "DocoDive replied to your suggestion!",
                email,
                f"Hi {username}, the DocoDive team has replied to your suggestion '{subject}'.",
                html_body=html_body,
            )
    return jsonify({"success": True})


@app.route("/feedback/<int:feedback_id>/official-reply/edit", methods=["POST"])
def edit_official_reply(feedback_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    new_reply = request.form.get("reply", "").strip()
    if not new_reply:
        return jsonify({"error": "Reply cannot be empty"}), 400
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE user_feedback SET official_reply=%s, official_replied_at=NOW() WHERE id=%s",
        (new_reply, feedback_id),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/feedback/<int:feedback_id>/official-reply/delete", methods=["POST"])
def delete_official_reply(feedback_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE user_feedback SET official_reply=NULL, official_replied_at=NULL WHERE id=%s",
        (feedback_id,),
    )
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/feedback/<int:feedback_id>/reply", methods=["POST"])
def add_feedback_reply(feedback_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    message = request.form.get("message", "").strip()
    if not message:
        return jsonify({"error": "Reply cannot be empty"}), 400
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
    if not new_message:
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
    cur.execute("DELETE FROM user_feedback WHERE id=%s", (feedback_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route("/feedback/reply/<int:reply_id>/edit", methods=["POST"])
def edit_reply(reply_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    new_message = request.form.get("message", "").strip()
    if not new_message:
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
    replies = []
    for row in rows:
        rid = row[0]
        is_liked = False
        if current_user_id:
            cur = mysql.connection.cursor()
            cur.execute(
                "SELECT 1 FROM reply_likes WHERE user_id=%s AND reply_id=%s",
                (current_user_id, rid),
            )
            is_liked = cur.fetchone() is not None
            cur.close()
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
@app.route("/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    email = request.form.get("email", "").strip()
    next_url = request.form.get("next", url_for("home"))

    if not email:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Please enter your email."}), 400
        flash("Please enter your email.", "danger")
        return redirect(next_url)

    if not is_valid_email(email):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Please enter a valid email address."}), 400
        flash("Please enter a valid email address.", "danger")
        return redirect(next_url)

    try:
        sync_brevo_contact(email, "DocoDive", "Subscriber")
        success = True
    except Exception as e:
        app.logger.error(f"Newsletter subscribe failed: {e}")
        success = False

    if not success:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Something went wrong. Please try again."}), 500
        flash("Something went wrong. Please try again.", "danger")
        return redirect(next_url)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            {"success": True, "message": "✅ Subscribed! Check your inbox for updates."}
        )

    flash("✅ Subscribed! You will now receive updates about new books.", "success")
    return redirect(next_url)


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

    return render_template("preferences.html", pref=pref, categories=categories)


# ================== USER PROFILE ==================
@app.route("/user/profile/<username>")
def user_profile(username):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT id, username, email, verified, created_at, avatar_url, bio, social_links, first_name, last_name
        FROM users WHERE username = %s
    """,
        (username,),
    )
    user = cur.fetchone()
    if not user:
        cur.close()
        abort(404)
    uid = user[0]

    official_user_id = get_site_setting("official_user_id")
    is_official = bool(official_user_id and str(uid) == official_user_id)

    social_links_dict = {}
    if user[7]:
        try:
            social_links_dict = json.loads(user[7])
        except Exception:
            pass

    cur.execute("SELECT COUNT(*) FROM documents WHERE uploaded_by = %s", (uid,))
    total_uploads = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM reviews WHERE user_id = %s", (uid,))
    total_reviews = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id = %s", (uid,))
    total_favorites = cur.fetchone()[0]
    cur.execute("SELECT SUM(points) FROM user_points WHERE user_id = %s", (uid,))
    total_points = cur.fetchone()[0] or 0
    cur.close()

    return render_template(
        "user_profile.html",
        user=user,
        total_uploads=total_uploads,
        total_reviews=total_reviews,
        total_favorites=total_favorites,
        total_points=total_points,
        social_links=social_links_dict,
        is_official=is_official,
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
            msg = "Username must be 3-20 letters and numbers only (no spaces or symbols)."
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
            return jsonify({
                "success": True,
                "message": msg,
                "avatar_url": avatar_url or session.get("avatar_url")
            })
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
    return render_template("edit_profile.html", profile=profile)

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
            if uid:
                cur = mysql.connection.cursor()
                cur.execute("SELECT avatar_url FROM users WHERE id = %s", (uid,))
                av = cur.fetchone()
                cur.close()
                notif["avatar_url"] = av[0] if av else None
                notif["is_official_actor"] = is_official_user(uid)
            else:
                notif["avatar_url"] = None
                notif["is_official_actor"] = False
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

    return render_template("notifications.html", notifications=enriched)


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
        return jsonify([])
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
            uploader_id = notif["metadata"].get("uploader_id")
            if uploader_id:
                cur = mysql.connection.cursor()
                cur.execute(
                    "SELECT avatar_url FROM users WHERE id = %s", (uploader_id,)
                )
                img = cur.fetchone()
                cur.close()
                notif["image_url"] = img[0] if img else None
                notif["is_official_actor"] = is_official_user(uploader_id)
            else:
                notif["image_url"] = None
                notif["is_official_actor"] = False
        elif notif["type"] in ("general_comment", "reply"):
            actor_id = notif["metadata"].get("actor_user_id")
            if actor_id:
                cur = mysql.connection.cursor()
                cur.execute(
                    "SELECT username, avatar_url FROM users WHERE id = %s", (actor_id,)
                )
                user = cur.fetchone()
                cur.close()
                notif["actor_name"] = user[0] if user else "Unknown"
                notif["actor_avatar"] = user[1] if user and user[1] else None
                notif["is_official_actor"] = is_official_user(actor_id)
            else:
                notif["actor_name"] = "Someone"
                notif["actor_avatar"] = None
                notif["is_official_actor"] = False
        else:
            notif["is_official_actor"] = False

        result.append(notif)

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


# ================== LEADERBOARD ==================
@app.route("/leaderboard")
def leaderboard():
    official_user_id = get_site_setting("official_user_id")

    cur = mysql.connection.cursor()
    if official_user_id:
        cur.execute(
            """
            SELECT u.id, u.username, u.first_name, u.last_name, u.avatar_url, SUM(up.points) AS total_points
            FROM user_points up
            JOIN users u ON up.user_id = u.id
            WHERE u.id != %s
            GROUP BY u.id
            ORDER BY total_points DESC
            LIMIT 50
        """,
            (official_user_id,),
        )
    else:
        cur.execute("""
            SELECT u.id, u.username, u.first_name, u.last_name, u.avatar_url, SUM(up.points) AS total_points
            FROM user_points up
            JOIN users u ON up.user_id = u.id
            GROUP BY u.id
            ORDER BY total_points DESC
            LIMIT 50
        """)
    rows = cur.fetchall()
    cur.close()

    leaderboard = []
    for row in rows:
        full_name = ((row[2] or "") + " " + (row[3] or "")).strip()
        if not full_name:
            full_name = row[1]
        leaderboard.append(
            {
                "user_id": row[0],
                "username": row[1],
                "name": full_name,
                "avatar_url": row[4],
                "points": row[5],
                "is_official": is_official_user(row[0]),
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

        if official_user_id and str(uid) != official_user_id:
            cur.execute(
                """
                SELECT COUNT(*) + 1 FROM (
                    SELECT user_id, SUM(points) AS total
                    FROM user_points
                    WHERE user_id != %s
                    GROUP BY user_id
                    HAVING SUM(points) > %s
                ) AS higher
            """,
                (official_user_id, total),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(*) + 1 FROM (
                    SELECT user_id, SUM(points) AS total
                    FROM user_points
                    GROUP BY user_id
                    HAVING SUM(points) > %s
                ) AS higher
            """,
                (total,),
            )
        rank = cur.fetchone()[0]
        current_user_rank = rank
        cur.close()

    return render_template(
        "leaderboard.html",
        leaderboard=leaderboard,
        current_user_rank=current_user_rank,
        current_user_points=current_user_points,
    )


# ================== BOOK COMMENTS ==================
@app.route("/book/<int:book_id>/comments", methods=["GET"])
@limiter.limit(USER_ACTION_RATELIMIT)
def get_comments(book_id):
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
@limiter.limit(USER_ACTION_RATELIMIT)
def add_comment(book_id):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401
    data = request.get_json()
    comment = data.get("comment", "").strip()
    parent_id = data.get("parent_id")
    if not comment:
        return jsonify({"error": "Comment cannot be empty"}), 400

    cur = mysql.connection.cursor()
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
            "SELECT uploaded_by, title FROM documents WHERE id = %s", (book_id,)
        )
        book_info = cur.fetchone()
        cur.close()
        if book_info and book_info[0] and book_info[0] != session["user_id"]:
            uploader_id = book_info[0]
            book_title = book_info[1]
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
                url_for("book_detail", book_id=book_id, _anchor="discussion"),
                metadata,
            )
    else:
        cur = mysql.connection.cursor()
        cur.execute(
            """
            SELECT c.user_id, d.title
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
                url_for("book_detail", book_id=book_id, _anchor="discussion"),
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
                        <a href="{url_for('book_detail', book_id=book.get('id'), _external=True)}"
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
        now = datetime.utcnow()
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


# ================== RUN ==================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_digest_scheduler()

    app.run(host="0.0.0.0", port=port, debug=debug)
