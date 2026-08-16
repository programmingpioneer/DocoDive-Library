import os
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
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, abort, flash, g, Response

from PIL import Image
from flask_caching import Cache

import qrcode
from io import BytesIO
from flask import send_file

import boto3
from botocore.config import Config
from PyPDF2 import PdfReader
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, abort, flash, g
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
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes', 'on')

# -------------------- SENTRY INITIALIZATION --------------------
sentry_dsn = os.getenv('SENTRY_DSN')
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        environment=os.getenv('FLASK_ENV', 'development'),
        send_default_pii=False
    )
    app.logger.info("Sentry initialized")
else:
    app.logger.warning("SENTRY_DSN not set – error tracking disabled")

Talisman(app, content_security_policy=None)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["5000 per day", "500 per hour"]
)

app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 300
cache = Cache(app)

@app.after_request
def add_cache_headers(response):
    content_type = response.content_type or ''
    path = request.path

    if any(ext in path for ext in ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot']):
        response.cache_control.max_age = 2592000
        response.cache_control.public = True
        response.headers['Cache-Control'] = 'public, max-age=2592000, immutable'
    elif 'text/html' in content_type:
        response.cache_control.no_cache = True
        response.headers['Cache-Control'] = 'no-cache, must-revalidate'
    elif 'application/json' in content_type:
        response.cache_control.max_age = 60
        response.headers['Cache-Control'] = 'public, max-age=60'

    return response

IS_PRODUCTION = os.getenv("FLASK_ENV", "").lower() == "production"

secret_key = os.getenv("FLASK_SECRET_KEY")
if not secret_key:
    if IS_PRODUCTION:
        raise RuntimeError("FLASK_SECRET_KEY must be set in production.")
    secret_key = "local-development-only-change-me"
    app.logger.warning("Using local dev secret key. Set FLASK_SECRET_KEY before deployment.")
app.config["SECRET_KEY"] = secret_key

CRON_SECRET = os.getenv('CRON_SECRET')
if not CRON_SECRET:
    CRON_SECRET = secrets.token_urlsafe(32)
    app.logger.warning("CRON_SECRET not set; generated random secret: %s", CRON_SECRET)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

app.config['FACEBOOK_APP_SECRET'] = os.getenv('FACEBOOK_CLIENT_SECRET')

# ================== DATABASE CONFIGURATION (MYSQL_* with DB_* fallback) ==================
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST') or os.environ.get('DB_HOST', 'localhost')
app.config['MYSQL_PORT'] = int(os.environ.get('MYSQL_PORT') or os.environ.get('DB_PORT', '3306'))
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER') or os.environ.get('DB_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD') or os.environ.get('DB_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB') or os.environ.get('DB_NAME', 'docodive_dev')

app.config['MYSQL_SSL_CA'] = (
    os.environ.get('MYSQL_SSL_CA')
    or os.path.join(os.path.dirname(__file__), 'ssl', 'isrgrootx.pem')
)
app.config['MYSQL_SSL_VERIFY_CERT'] = _env_bool('MYSQL_SSL_VERIFY_CERT', False)
app.config['MYSQL_SSL_VERIFY_IDENTITY'] = _env_bool('MYSQL_SSL_VERIFY_IDENTITY', False)

from mysql.connector.pooling import MySQLConnectionPool

db_config = {
    'host': app.config['MYSQL_HOST'],
    'user': app.config['MYSQL_USER'],
    'password': app.config['MYSQL_PASSWORD'],
    'database': app.config['MYSQL_DB'],
    'port': app.config['MYSQL_PORT'],
    'use_pure': True,
    'autocommit': True,
}

ssl_ca = app.config.get('MYSQL_SSL_CA')
if ssl_ca:
    db_config['ssl_ca'] = ssl_ca
    db_config['ssl_verify_cert'] = app.config.get('MYSQL_SSL_VERIFY_CERT', False)
    db_config['ssl_verify_identity'] = app.config.get('MYSQL_SSL_VERIFY_IDENTITY', False)

pool = MySQLConnectionPool(pool_name="mypool", pool_size=20, **db_config)

class MySQLWrapper:
    def __init__(self, app_config):
        self.config = app_config

    @property
    def connection(self):
        if 'db_conn' not in g:
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

@app.teardown_appcontext
def close_db_connection(exception):
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        try:
            db_conn.close()
        except Exception:
            pass

mysql = MySQLWrapper(app.config)

# ================== CSRF (FIXED: digest exempt) ==================
@app.before_request
def csrf_protect():
    if request.path.startswith('/internal/notification-digest/'):
        return

    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return
        token = session.get('_csrf_token')
        if not token or token != request.form.get('_csrf_token', ''):
            abort(403)
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)

# ================== OAuth SETUP ==================
oauth = OAuth(app)

oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={'scope': 'openid email profile'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

oauth.register(
    name='github',
    client_id=os.getenv('GITHUB_CLIENT_ID'),
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)

oauth.register(
    name='facebook',
    client_id=os.getenv('FACEBOOK_CLIENT_ID'),
    client_secret=os.getenv('FACEBOOK_CLIENT_SECRET'),
    access_token_url='https://graph.facebook.com/oauth/access_token',
    authorize_url='https://www.facebook.com/dialog/oauth',
    api_base_url='https://graph.facebook.com/',
    client_kwargs={'scope': 'email public_profile'},
)

def is_valid_pdf(file_bytes):
    return file_bytes[:5] == b'%PDF-'

def compress_image(image_bytes, max_size=(600, 600), quality=85):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail(max_size, Image.LANCZOS)
    output = io.BytesIO()
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.save(output, format='JPEG', quality=quality, optimize=True)
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
    cur.execute("""
        SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved = 1
        LIMIT 1 OFFSET %s
    """, (offset,))
    book = cur.fetchone()
    cur.execute("UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book[0],))
    mysql.connection.commit()
    cur.close()
    random.seed()
    return book

app.config['ADMIN_NOTIFICATION_EMAIL'] = os.getenv('ADMIN_NOTIFICATION_EMAIL')
app.config['SUPPORT_EMAIL'] = os.getenv('SUPPORT_EMAIL', '')
app.config['MAIL_FROM_NAME'] = os.getenv('MAIL_FROM_NAME', 'DocoDive')
app.config['MAIL_FROM_EMAIL'] = os.getenv('MAIL_FROM_EMAIL', '7t7sufyan@gmail.com')

ALLOWED_EXTENSIONS = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

mail = None
if HAS_MAIL:
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp-relay.brevo.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '587'))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'false').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_TIMEOUT'] = int(os.getenv('MAIL_TIMEOUT', '15'))
    if app.config['MAIL_USE_TLS'] and app.config['MAIL_USE_SSL']:
        raise RuntimeError("Enable only one of MAIL_USE_TLS or MAIL_USE_SSL.")
    app.config['MAIL_DEFAULT_SENDER'] = (app.config['MAIL_FROM_NAME'], app.config['MAIL_FROM_EMAIL'])
    mail = Mail(app)

genai_client = None
if HAS_GEMINI and os.getenv('GEMINI_API_KEY'):
    genai_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# -------------------- CLOUDFLARE R2 CLIENT (FIXED) --------------------
r2_client = boto3.client(
    's3',
    endpoint_url=os.getenv('R2_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    config=Config(signature_version='s3v4'),
    region_name='auto'
)
R2_BUCKET = os.getenv('R2_BUCKET_NAME', 'docodive')
R2_PUBLIC_BASE = os.getenv('R2_PUBLIC_DOMAIN', 'https://pub-8f5fcc3c01514e53b12396f444c45448.r2.dev').rstrip('/')

def upload_to_r2(file_bytes, key, content_type='application/octet-stream'):
    r2_client.put_object(
        Bucket=R2_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
        CacheControl='public, max-age=2592000, immutable'
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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

#-------------------- BREVO API EMAIL SENDING (FIXED) --------------------
def send_email_via_api(subject, recipient, body, html_body=None):
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        app.logger.error("BREVO_API_KEY not set, cannot send via API")
        return False
    sender_email = app.config.get('MAIL_FROM_EMAIL') or "7t7sufyan@gmail.com"
    sender_name = app.config.get('MAIL_FROM_NAME') or "DocoDive"
    try:
        data = {
            "sender": {"email": sender_email, "name": sender_name},
            "to": [{"email": recipient}],
            "subject": subject,
            "htmlContent": html_body or body,
            "textContent": body
        }
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=data,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=10
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

def send_email_via_api(subject, recipient, body, html_body=None):
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        app.logger.error("BREVO_API_KEY not set, cannot send via API")
        return False
    sender_email = app.config.get('MAIL_FROM_EMAIL') or "7t7sufyan@gmail.com"
    sender_name = app.config.get('MAIL_FROM_NAME') or "DocoDive"
    try:
        data = {
    "sender": {"email": sender_email, "name": sender_name},
    "to": [{"email": recipient}],
    "subject": subject,
    "htmlContent": html_body or body,
    "textContent": body
    }
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=data,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=10
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
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    disposable = ['mailinator.com', 'tempmail.com', 'throwaway.com', 'guerrillamail.com',
                  'sharklasers.com', '10minutemail.com', 'yopmail.com', 'trashmail.com']
    return email.split('@')[1].lower() not in disposable

def sync_brevo_contact(email, first_name='', last_name=''):
    """Create or update a Brevo contact. Non-fatal: logs errors but never crashes."""
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        app.logger.warning("BREVO_API_KEY not set, skipping contact sync")
        return False
    try:
        payload = {
            "email": email,
            "attributes": {
                "FIRSTNAME": first_name or "",
                "LASTNAME": last_name or ""
            },
            "updateEnabled": True
        }
        resp = requests.post(
            "https://api.brevo.com/v3/contacts",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=10
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
    if 'user_id' in session:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
                    (session['user_id'], book_id))
        mysql.connection.commit()
        cur.close()

def award_points(user_id, points, book_id=None, action='activity'):
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO user_points (user_id, points, action, book_id) VALUES (%s, %s, %s, %s)",
                (user_id, points, action, book_id))
    mysql.connection.commit()
    cur.close()

def create_notification(user_id, type, message, link=None, metadata=None):
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO notifications (user_id, message, link, type, metadata) VALUES (%s, %s, %s, %s, %s)",
        (user_id, message, link, type, json.dumps(metadata) if metadata else None)
    )
    mysql.connection.commit()
    cur.close()

BANNED_SUBSTRINGS = ['techbymehdi']

def clean_professional_name(raw_name):
    name = raw_name
    for banned in BANNED_SUBSTRINGS:
        name = re.sub(re.escape(banned), '', name, flags=re.IGNORECASE)
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\{.*?\}', '', name)
    name = re.sub(r'\b(version\s?\d+(\.\d+)?|v\d+(\.\d+)?|final|draft)\b', '', name, flags=re.I)
    name = re.sub(r'[_\-.]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    if not name:
        name = 'Untitled'
    name = name.title()
    name = re.sub(r'[^\w]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    if len(name) > 60:
        name = name[:60].rstrip('_')
    return f"{name}_@DocoDive"

def normalize_for_duplicate_check(title):
    t = re.sub(r'\s*\(\d+\)\s*$', '', title)
    t = re.sub(r'\s*-\s*Copy(\s*\(\d+\))?\s*$', '', t, flags=re.I)
    t = re.sub(r'\s*-\s*copy(\s*\(\d+\))?\s*$', '', t, flags=re.I)
    return re.sub(r'\s+', ' ', t).strip().lower()

def is_duplicate(title, author, conn):
    norm_title = normalize_for_duplicate_check(title)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title FROM documents WHERE LOWER(author) = %s", (author.lower(),))
            rows = cur.fetchall()
            for row in rows:
                if normalize_for_duplicate_check(row[1]) == norm_title:
                    return True
            return False
    except Exception:
        return False

KEYWORDS = {
    'Python': ['import ', 'def ', 'class ', 'print(', 'pandas', 'numpy', 'python', 'django', 'flask', 'tkinter'],
    'JavaScript': ['var ', 'const ', 'function', 'document.', 'console.log', 'react', 'angular', 'node', 'express'],
    'Java': ['public class', 'system.out', 'java', 'spring', 'hibernate', 'swing'],
    'C / C++': ['#include', 'int main', 'printf', 'cout', 'std::', 'iostream', 'malloc'],
    'Web Development': ['html', 'css', '<div', 'react', 'angular', 'bootstrap', 'jquery', 'responsive'],
    'Data Science': ['dataframe', 'scikit', 'matplotlib', 'pandas', 'numpy', 'seaborn', 'analytics'],
    'Machine Learning': ['model.fit', 'train_test_split', 'tensorflow', 'keras', 'pytorch', 'deep learning'],
    'Algorithms': ['algorithm', 'sort', 'complexity', 'big o', 'binary search', 'graph'],
    'Databases': ['sql', 'query', 'select *', 'mysql', 'postgresql', 'oracle', 'nosql'],
    'Cyber Security': ['encrypt', 'hack', 'firewall', 'penetration', 'malware', 'sql injection'],
    'Mobile Apps': ['android', 'ios', 'swift', 'kotlin', 'flutter', 'react native'],
    'DevOps': ['docker', 'kubernetes', 'ci/cd', 'terraform', 'jenkins', 'ansible']
}

def extract_text_from_pdf(reader, max_pages=5):
    text = ''
    for page in reader.pages[:max_pages]:
        extracted = page.extract_text()
        if extracted:
            text += extracted
    return text.lower()

def guess_category(text):
    scores = {cat: sum(1 for kw in kwds if kw in text) for cat, kwds in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'Others'

def guess_category_intelligent(pdf_text, raw_name):
    combined = pdf_text + ' ' + raw_name.lower()
    for word in raw_name.lower().split():
        combined += ' ' + word
    return guess_category(combined)

def ai_enhance_metadata(title, author, text):
    if not genai_client:
        return title, author, f"A comprehensive resource about '{title}'. Covers essential topics."
    try:
        prompt = f"""
Improve the following book title, author, and generate a short description.
Title: {title}
Author: {author}
First page text: {text[:2000]}
Return JSON with keys: title, author, description.
"""
        response = genai_client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
        response_text = response.text
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get('title', title), data.get('author', author), data.get('description', '')
    except Exception as e:
        app.logger.error(f"AI metadata failed: {e}")
    return title, author, f"A comprehensive resource about '{title}'. Covers essential topics."

def setup_session(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, first_name, last_name, avatar_url, email FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    if user:
        session['user_id'] = user_id
        session['user_name'] = user[0]
        full_name = (user[1] or '') + ' ' + (user[2] or '')
        session['user_display_name'] = full_name.strip() or user[0]
        session['avatar_url'] = user[3]
        session['email'] = user[4]

def handle_social_login(provider_name, user_info):
    provider_id_field = f'{provider_name}_id'
    email = user_info.get('email')
    name = user_info.get('name') or user_info.get('login')
    avatar = user_info.get('picture') or user_info.get('avatar_url')

    if not email:
        email = f"{user_info['sub']}@{provider_name}.local"

    first_name = ''
    last_name = ''
    if name:
        parts = name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''

    cur = mysql.connection.cursor()

    cur.execute(f"SELECT id FROM users WHERE {provider_id_field} = %s", (user_info['sub'],))
    user = cur.fetchone()
    if user:
        cur.close()
        return user[0], False

    if email and '@' in email:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing = cur.fetchone()
        if existing:
            cur.execute(f"UPDATE users SET {provider_id_field} = %s, avatar_url = %s WHERE id = %s",
                        (user_info['sub'], avatar, existing[0]))
            mysql.connection.commit()
            cur.close()
            return existing[0], False

    username = email.split('@')[0] if email else user_info['sub']
    base_username = username[:20]
    i = 1
    while True:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if not cur.fetchone():
            break
        username = f"{base_username}{i}"[:20]
        i += 1

    hashed = generate_password_hash(secrets.token_urlsafe(16))

    cur.execute(f"""
        INSERT INTO users (username, email, password, verified, verification_token,
                          first_name, last_name, avatar_url, {provider_id_field})
        VALUES (%s, %s, %s, 1, NULL, %s, %s, %s, %s)
    """, (username, email, hashed, first_name, last_name, avatar, user_info['sub']))
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
        if support_email else "This is an automated account and security email from DocoDive."
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
    return _email_layout("Confirm your email to activate your DocoDive account.", "Account security", "Confirm your email address", content)

def make_welcome_email(user_name, provider):
    provider_display = {'google': 'Google', 'github': 'GitHub', 'facebook': 'Facebook'}.get(provider.lower(), provider)
    content = f"""
        <p style="margin:0;">Hi {_safe(user_name)},</p>
        <p style="margin:16px 0 0;">Welcome to <strong>DocoDive</strong> – your gateway to 50,000+ free books &amp; resources!</p>
        <p style="margin:10px 0;">Your account was created via <strong>{provider_display}</strong>. You are now verified and can start exploring the library instantly.</p>
        {_email_button(url_for('home', _external=True), "Explore the Library")}
        <p style="margin-top:24px; font-size:13px; color:#6b7280;">Happy learning!<br>— Team DocoDive</p>
    """
    return _email_layout("Welcome to DocoDive – you're verified!", "Welcome aboard", f"Hello {_safe(user_name)}!", content)

def make_upload_notification_email(title, author, category):
    pending_url = url_for('pending_books', _external=True)
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
    return _email_layout("A DocoDive document needs your review.", "Admin notification", "New document ready for review", content)

def make_code_email(code):
    content = f"""
        <p style="margin:0;">Enter this code in DocoDive to continue resetting your password:</p>
        <div style="margin:26px 0;padding:20px 12px;border:1px solid #C7D2FE;border-radius:12px;background:{BRAND_LIGHT};
                    color:#312E81;font:800 34px Arial,Helvetica,sans-serif;letter-spacing:10px;line-height:40px;text-align:center;">
          {_safe(code)}
        </div>
        <p style="margin:0;color:#4B5563;">This code expires in <strong>10 minutes</strong>. Do not share it with anyone.</p>
    """
    return _email_layout("Your DocoDive password reset code is ready.", "Password reset", "Use this security code", content)

def make_reset_link_email(reset_link):
    content = f"""
        <p style="margin:0;">Your code was confirmed. Use the secure link below to choose a new DocoDive password.</p>
        {_email_button(reset_link, "Reset password")}
        {_email_link(reset_link)}
    """
    return _email_layout("Use this secure link to reset your DocoDive password.", "Password reset", "Set a new password", content)

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
    return _email_layout(f"Your DocoDive submission is {status_label.lower()}.", "Document review", heading, content)

# ================== SITE SETTINGS & OFFICIAL HELPERS ==================
def get_site_setting(key, default=None):
    cur = mysql.connection.cursor()
    cur.execute("SELECT `value` FROM site_settings WHERE `key` = %s", (key,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else default


def set_site_setting(key, value):
    cur = mysql.connection.cursor()
    cur.execute("REPLACE INTO site_settings (`key`, `value`) VALUES (%s, %s)", (key, value))
    mysql.connection.commit()
    cur.close()


def is_official_user(user_id):
    official_id = get_site_setting('official_user_id')
    return official_id and str(user_id) == official_id


def is_moderator():
    if 'user_id' in session and is_official_user(session['user_id']):
        return True
    return False


def official_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            abort(403)
        if not is_official_user(session['user_id']):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_common():
    return dict(
        current_user_is_official=is_official_user(session.get('user_id', 0)),
        is_moderator=is_moderator()
    )


@app.context_processor
def inject_user_logged_in():
    return dict(user_logged_in=bool(session.get('user_id')))


# ================== UTILITY FUNCTIONS ==================
def clean_title_extra(title):
    """Remove @Pdfmatrix, TechByMehdi etc."""
    title = re.sub(r'@pdfmatrix', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[-_]?TechByMehdi', '', title, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', title).strip()


def extract_cover_from_pdf(pdf_bytes):
    """Generate cover image from the first page of a PDF. Returns compressed PNG bytes."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        cover_bytes = pix.tobytes("png")
        doc.close()
        return compress_image(BytesIO(cover_bytes).getvalue(), max_size=(400, 400), quality=75)
    except Exception as e:
        app.logger.error(f"Cover extraction failed: {e}")
        return None


def generate_description(title, category):
    """Return a long, professional description based on category."""
    t = title
    templates = {
        'Python': f"Unlock the power of Python with '{t}'. This comprehensive guide takes you from basic syntax to advanced concepts like OOP, data analysis with Pandas, web development with Flask/Django, and task automation. Packed with real-world examples and best practices, it's perfect for beginners and experienced coders.",
        'JavaScript': f"Master JavaScript from the ground up with '{t}'. Explore core language features, DOM manipulation, asynchronous programming, and modern frameworks like React and Node.js.",
        'Java': f"Dive deep into Java with '{t}'. Covering OOP principles, collections, multithreading, and enterprise frameworks like Spring and Hibernate.",
        'C / C++': f"Explore the world of C and C++ with '{t}'. From pointers and memory management to STL and modern C++17/20 features.",
        'Web Development': f"Build stunning, responsive websites with '{t}'. Learn HTML5, CSS3, JavaScript, and popular frameworks like Bootstrap, React, and Angular.",
        'Data Science': f"Discover the art of data science with '{t}'. Learn data wrangling, visualization, statistical modeling, and ML using Pandas, NumPy, and Scikit-learn.",
        'Machine Learning': f"Step into the future with '{t}'. From linear regression to deep neural networks, covers supervised/unsupervised learning and deployment.",
        'Algorithms': f"Sharpen your problem-solving skills with '{t}'. Detailed explanations of sorting, searching, graph algorithms, and dynamic programming.",
        'Databases': f"Master database design and SQL with '{t}'. Covers relational models, normalization, indexing, and query optimization.",
        'Cyber Security': f"Defend the digital world with '{t}'. Learn ethical hacking, penetration testing, network security, and cryptography.",
        'Mobile Apps': f"Create engaging mobile experiences with '{t}'. Covers native Android (Kotlin), iOS (Swift), and Flutter/React Native.",
        'DevOps': f"Transform your workflow with '{t}'. Learn CI/CD pipelines, Docker, Kubernetes, Terraform, and cloud services.",
        'Others': f"An in-depth resource covering '{t}'. Packed with theory, practical examples, and expert insights."
    }
    return templates.get(category, f"An in-depth resource covering '{t}' in the field of {category}.")


def guess_category_from_text(pdf_text):
    """Guess category using keyword matching on PDF text. Returns best category or 'Others'."""
    best_category = 'Others'
    best_ratio = 0.0
    for category, keywords in KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in pdf_text)
        ratio = hits / len(keywords)
        if ratio > best_ratio:
            best_ratio = ratio
            best_category = category
    if best_ratio < 0.7:
        best_category = 'Others'
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
        return 'Others'
    best_category = max(scores, key=scores.get)
    best_ratio = scores[best_category]
    if best_ratio < 0.1:
        best_category = 'Others'
    return best_category


def lazy_trickle(book_id):
    """Books younger than 7 days get small random growth every 6 hours."""
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT created_at, last_trickle_time
        FROM documents
        WHERE id = %s AND approved = 1
    """, (book_id,))
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

    cur.execute("""
        UPDATE documents
        SET download_count = download_count + %s,
            view_count = view_count + %s,
            last_trickle_time = %s
        WHERE id = %s
    """, (dl_growth, vw_growth, now, book_id))
    mysql.connection.commit()
    cur.close()


# ================== R2 HELPER FUNCTIONS (Required) ==================
def extract_r2_key(url):
    """Extract the R2 object key from a public URL."""
    if not url:
        return None
    if R2_PUBLIC_BASE and url.startswith(R2_PUBLIC_BASE + '/'):
        return url.replace(R2_PUBLIC_BASE + '/', '', 1)
    return url


def get_presigned_url(key, expiration=300):
    """Generate a presigned URL for an R2 object."""
    try:
        return r2_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET, 'Key': key},
            ExpiresIn=expiration
        )
    except Exception as e:
        app.logger.error(f"Presigned URL generation failed: {e}")
        return None


# ================== USER UPLOAD (R2) ==================
@app.route('/user/upload', methods=['GET', 'POST'])
@cache.cached(timeout=600, unless=lambda: request.method == 'POST')
def user_upload():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            msg = 'No PDF file selected.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('user_upload'))

        file = request.files['pdf_file']
        if file.filename == '' or not allowed_file(file.filename):
            msg = 'Invalid file. Only PDF allowed.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('user_upload'))

        pdf_bytes = file.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        meta = reader.metadata
        pdf_title = (meta.title or '').strip() if meta else ''
        author_meta = (meta.author or '').strip() if meta else ''

        raw_name = pdf_title if pdf_title and pdf_title.lower() != 'unknown' else os.path.splitext(file.filename)[0]

        clean_base = clean_professional_name(raw_name)
        display_title = clean_base.replace('_', ' ').replace(' @DocoDive', '').strip()
        display_title = clean_title_extra(display_title)
        if not display_title:
            display_title = 'Untitled'

        author = author_meta if author_meta and author_meta.lower() != 'unknown' else 'Unknown'
        author = author or 'Unknown'

        cur = mysql.connection.cursor()
        if is_duplicate(display_title, author, cur):
            cur.close()
            msg = 'This book already exists in the library.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('user_upload'))
        cur.close()

        manual_category = request.form.get('category', '').strip()
        if manual_category:
            category = manual_category
        else:
            pdf_text = ''
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
            category = guess_category_from_text(pdf_text) if pdf_text else guess_category_from_filename(file.filename)

        description = generate_description(display_title, category)

        try:
            pdf_key = generate_r2_key('uploads', clean_base, '.pdf')
            pdf_url = upload_to_r2(pdf_bytes, pdf_key, content_type='application/pdf')
        except Exception as e:
            app.logger.error(f"PDF upload failed: {e}")
            msg = 'Failed to upload PDF.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': msg}), 500
            flash(msg, 'danger')
            return redirect(url_for('user_upload'))

        cover_bytes = None
        cover_extension = '.png'
        if 'cover_image' in request.files and request.files['cover_image'].filename != '':
            cover_file = request.files['cover_image']
            if not allowed_image_file(cover_file.filename):
                msg = 'Invalid cover image format.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': msg}), 400
                flash(msg, 'danger')
                return redirect(url_for('user_upload'))
            cover_bytes = cover_file.read()
            cover_bytes = compress_image(cover_bytes, max_size=(400, 400), quality=75)
            if len(cover_bytes) > 2 * 1024 * 1024:
                msg = 'Cover image must be less than 2 MB.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': msg}), 400
                flash(msg, 'danger')
                return redirect(url_for('user_upload'))
            cover_extension = os.path.splitext(cover_file.filename)[1].lower()
        else:
            cover_bytes = extract_cover_from_pdf(pdf_bytes)
            if not cover_bytes:
                msg = 'Could not generate cover from PDF. Please upload a cover image manually.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': msg}), 400
                flash(msg, 'danger')
                return redirect(url_for('user_upload'))

        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
        mime = mime_map.get(cover_extension, 'application/octet-stream')
        try:
            cover_key = generate_r2_key('covers', clean_base, cover_extension)
            image_url = upload_to_r2(cover_bytes, cover_key, content_type=mime)
        except Exception as e:
            app.logger.error(f"Cover upload failed: {e}")
            msg = 'Failed to upload cover image.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': msg}), 500
            flash(msg, 'danger')
            return redirect(url_for('user_upload'))

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

        cur.execute("""
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, approved, uploaded_by, download_count, view_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """, (cat_id, display_title, pdf_url, author, description, image_url, 'English', session['user_id'], dl_count, vw_count))
        mysql.connection.commit()
        cur.close()

        award_points(session['user_id'], 10, action='upload')

        html_notification = make_upload_notification_email(display_title, author, category)
        send_email_notification(
            "New PDF Uploaded by User - Pending Approval",
            app.config['ADMIN_NOTIFICATION_EMAIL'],
            f"A new book '{display_title}' by {author} has been uploaded by a user and is waiting for approval.",
            html_body=html_notification
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': f"✅ '{display_title}' uploaded successfully! It will appear after admin approval."})

        flash(f"✅ '{display_title}' uploaded successfully! It will appear after admin approval.", 'success')
        return redirect(url_for('user_upload'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT level FROM categories ORDER BY level")
    categories = [row[0] for row in cur.fetchall()]
    cur.close()
    return render_template('user_upload.html', categories=categories)


@app.route('/api/user/uploads')
def user_uploads():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, title, author, status, created_at FROM documents WHERE uploaded_by = %s ORDER BY created_at DESC", (user_id,))
    books = cur.fetchall()
    cur.close()
    return jsonify([{"id": b[0], "title": b[1], "author": b[2], "status": b[3], "created_at": str(b[4])} for b in books])


@app.route('/api/user/pending-uploads')
def user_pending_uploads():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, title, author, created_at FROM documents WHERE uploaded_by = %s AND approved = 0 ORDER BY created_at DESC", (user_id,))
    books = cur.fetchall()
    cur.close()
    return jsonify([{"id": b[0], "title": b[1], "author": b[2], "created_at": str(b[3])} for b in books])


# -------------------- API: CHECK USERNAME/EMAIL AVAILABILITY --------------------
@app.route('/api/check-availability')
def check_availability():
    field = request.args.get('field', '')
    value = request.args.get('value', '').strip()
    if not field or not value:
        return jsonify({'error': 'Invalid request'}), 400

    if field == 'username':
        reserved = os.getenv('RESERVED_USERNAMES', '')
        if reserved:
            reserved_list = [r.strip().lower() for r in reserved.split(',') if r.strip()]
            username_lower = value.lower()
            for word in reserved_list:
                if word in username_lower:
                    return jsonify({'exists': True, 'reserved': True, 'message': 'This username contains a reserved word.'})
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (value,))
        exists = cur.fetchone() is not None
        cur.close()
        return jsonify({'exists': exists, 'message': 'Username already taken.' if exists else 'Username is available!'})

    elif field == 'email':
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (value,))
        exists = cur.fetchone() is not None
        cur.close()
        return jsonify({'exists': exists, 'message': 'Email already registered.' if exists else 'Email is available.'})

    return jsonify({'error': 'Invalid field'}), 400


# -------------------- FORGOT PASSWORD (AJAX) --------------------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Please enter your email.'}), 400
            flash('Please enter your email.', 'danger')
            return redirect(url_for('forgot_password'))

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        if not user:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'No account found with that email.'}), 404
            flash('No account found with that email.', 'danger')
            return redirect(url_for('forgot_password'))

        code = f"{random.randint(1000, 9999)}"
        expires = datetime.now() + timedelta(minutes=10)
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM password_resets WHERE email = %s", (email,))
        cur.execute("INSERT INTO password_resets (email, code, expires_at) VALUES (%s, %s, %s)", (email, code, expires))
        mysql.connection.commit()
        cur.close()

        html_body = make_code_email(code)
        send_email_notification("Password Reset Code - DocoDive", email,
                                f"Your DocoDive password reset code is {code}. It expires in 10 minutes. Do not share it.",
                                html_body=html_body)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Verification code sent to your email.'})
        flash('A verification code has been sent to your email.', 'success')
        return redirect(url_for('verify_code', email=email))

    return render_template('forgot_password.html')


@app.route('/verify-code', methods=['POST'])
def verify_code():
    email = request.form.get('email', '').strip()
    code = request.form.get('code', '').strip()

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, email, code, expires_at FROM password_resets WHERE email = %s AND code = %s", (email, code))
    row = cur.fetchone()
    if not row or row[3] < datetime.now():
        cur.close()
        return jsonify({'error': 'Invalid or expired code.'}), 400

    token = secrets.token_urlsafe(32)
    new_expires = datetime.now() + timedelta(minutes=30)
    cur.execute("UPDATE password_resets SET token = %s, code = NULL, expires_at = %s WHERE id = %s", (token, new_expires, row[0]))
    mysql.connection.commit()
    cur.close()

    reset_link = url_for('reset_password', token=token, _external=True)
    html_body = make_reset_link_email(reset_link)
    send_email_notification("Reset Your Password - DocoDive", email,
                            f"Use this link to reset your DocoDive password (valid for 30 minutes): {reset_link}",
                            html_body=html_body)
    return jsonify({'success': True, 'message': 'A password reset link has been sent to your email.'})


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, email, expires_at FROM password_resets WHERE token = %s", (token,))
    row = cur.fetchone()
    if not row or row[2] < datetime.now():
        cur.close()
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if new_password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        hashed = generate_password_hash(new_password)
        cur.execute("UPDATE users SET password = %s WHERE email = %s", (hashed, row[1]))
        cur.execute("DELETE FROM password_resets WHERE id = %s", (row[0],))
        mysql.connection.commit()
        cur.close()
        flash('Password updated successfully! Please login.', 'success')
        return redirect(url_for('user_login'))

    cur.close()
    return render_template('reset_password.html', token=token)


# -------------------- BREVO WEBHOOK --------------------
@app.route('/api/brevo/webhook', methods=['POST'])
def brevo_webhook():
    secret = os.getenv('BREVO_WEBHOOK_SECRET')
    if secret:
        signature = request.headers.get('X-Webhook-Secret')
        if not signature or signature != secret:
            return '', 403
    data = request.get_json()
    if not data:
        return '', 400
    app.logger.info("Brevo webhook event: %s", json.dumps(data))
    return jsonify({"status": "received"}), 200


# ==================== SOCIAL LOGIN ROUTES ====================
@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def google_callback():
    code = request.args.get('code')
    if not code:
        flash('Missing authorization code.', 'danger')
        return redirect(url_for('user_login'))
    token_url = 'https://oauth2.googleapis.com/token'
    payload = {
        'code': code,
        'client_id': os.getenv('GOOGLE_CLIENT_ID'),
        'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
        'redirect_uri': url_for('google_callback', _external=True),
        'grant_type': 'authorization_code'
    }
    try:
        token_resp = requests.post(token_url, data=payload, timeout=10)
        token_data = token_resp.json()
    except Exception:
        flash('Login failed. Please try again.', 'danger')
        return redirect(url_for('user_login'))
    if 'access_token' not in token_data:
        flash('Could not authenticate with Google.', 'danger')
        return redirect(url_for('user_login'))
    access_token = token_data['access_token']
    try:
        user_resp = requests.get('https://www.googleapis.com/oauth2/v1/userinfo?alt=json',
                                 headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
        user_info = user_resp.json()
    except Exception:
        flash('Could not retrieve your Google profile.', 'danger')
        return redirect(url_for('user_login'))
    user_info['sub'] = user_info.get('id') or user_info.get('sub')
    user_info['picture'] = user_info.get('picture')
    user_info['email'] = user_info.get('email')
    user_info['name'] = user_info.get('name')

    uid, is_new = handle_social_login('google', user_info)
    if uid:
        setup_session(uid)
        if is_new:
            try:
                html_body = make_welcome_email(user_info.get('name', 'User'), 'Google')
                send_email_notification("Welcome to DocoDive! 🚀", user_info['email'],
                                        f"Hi {user_info.get('name', 'User')}, your account has been created via Google.",
                                        html_body=html_body)
            except Exception:
                pass
            flash('Account verified! Welcome to DocoDive 🤝', 'success')
        else:
            flash('Logged in successfully!', 'success')
        return redirect(url_for('home'))
    flash('Google login failed.', 'danger')
    return redirect(url_for('user_login'))


@app.route('/login/github')
def github_login():
    redirect_uri = url_for('github_callback', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)


@app.route('/auth/github/callback')
def github_callback():
    token = oauth.github.authorize_access_token()
    resp = oauth.github.get('user')
    user_info = resp.json()
    if not user_info.get('email'):
        emails_resp = oauth.github.get('user/emails')
        emails = emails_resp.json()
        primary = next((e['email'] for e in emails if e['primary']), None)
        user_info['email'] = primary
    user_info['sub'] = str(user_info['id'])
    user_info['name'] = user_info.get('name') or user_info['login']
    user_info['picture'] = user_info.get('avatar_url')
    uid, is_new = handle_social_login('github', user_info)
    if uid:
        setup_session(uid)
        if is_new:
            try:
                html_body = make_welcome_email(user_info.get('name', 'User'), 'GitHub')
                send_email_notification("Welcome to DocoDive! 🚀", user_info['email'],
                                        f"Hi {user_info.get('name', 'User')}, your account has been created via GitHub.",
                                        html_body=html_body)
            except Exception:
                pass
            flash('Account verified! Welcome to DocoDive 🤝', 'success')
        else:
            flash('Logged in successfully!', 'success')
        return redirect(url_for('home'))
    flash('GitHub login failed.', 'danger')
    return redirect(url_for('user_login'))


@app.route('/login/facebook')
def facebook_login():
    redirect_uri = url_for('facebook_callback', _external=True)
    return oauth.facebook.authorize_redirect(redirect_uri)


@app.route('/auth/facebook/callback')
def facebook_callback():
    token = oauth.facebook.authorize_access_token()
    resp = oauth.facebook.get('me?fields=id,name,email,picture')
    user_info = resp.json()
    user_info['sub'] = user_info['id']
    user_info['picture'] = user_info.get('picture', {}).get('data', {}).get('url')
    uid, is_new = handle_social_login('facebook', user_info)
    if uid:
        setup_session(uid)
        if is_new:
            try:
                html_body = make_welcome_email(user_info.get('name', 'User'), 'Facebook')
                send_email_notification("Welcome to DocoDive! 🚀", user_info['email'],
                                        f"Hi {user_info.get('name', 'User')}, your account has been created via Facebook.",
                                        html_body=html_body)
            except Exception:
                pass
            flash('Account verified! Welcome to DocoDive 🤝', 'success')
        else:
            flash('Logged in successfully!', 'success')
        return redirect(url_for('home'))
    flash('Facebook login failed.', 'danger')
    return redirect(url_for('user_login'))


@app.route('/facebook/data-deletion', methods=['POST'])
def facebook_data_deletion():
    signed_request = request.form.get('signed_request')
    if not signed_request:
        return jsonify({'error': 'Missing signed request'}), 400
    secret = app.config['FACEBOOK_APP_SECRET']
    try:
        sig, payload = signed_request.split('.', 1)
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        ).rstrip(b'=').decode()
        if not hmac.compare_digest(sig, expected_sig):
            return jsonify({'error': 'Invalid signature'}), 403
        data = json.loads(base64.urlsafe_b64decode(payload + '==').decode())
        user_id = data.get('user_id')
        confirmation_code = 'abc123'
        return jsonify({
            'url': f'{request.host_url}data-deletion?code={confirmation_code}',
            'confirmation_code': confirmation_code
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ================== ERROR HANDLERS ==================
@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    return jsonify({"error": "File size too large. Maximum 500 MB allowed."}), 413


@app.errorhandler(400)
def bad_request(e):
    return render_template('400.html'), 400


@app.errorhandler(401)
def unauthorized(e):
    return render_template('401.html'), 401


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


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
            trending_books.append({
                "id": r[0], "title": r[1], "author": r[2], "level": r[3],
                "image_url": r[4], "link": r[5],
                "download_count": r[6] or 0, "view_count": r[7] or 0
            })
    except Exception as e:
        app.logger.error(f"404 trending fetch failed: {e}")

    return render_template('404.html', trending_books=trending_books), 404


@app.errorhandler(429)
def too_many_requests(e):
    return render_template('429.html'), 429


@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500


@app.errorhandler(503)
def service_unavailable(e):
    return render_template('503.html'), 503


# ================== LEARNING HUB HELPERS ==================
def category_to_slug(category):
    slug = category.strip().lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def slug_to_category_name(slug, cursor):
    cursor.execute("SELECT level FROM categories ORDER BY level")
    rows = cursor.fetchall()
    for (level,) in rows:
        if category_to_slug(level) == slug:
            return level
    return None


app.jinja_env.filters['slugify'] = category_to_slug


# ================== PUBLIC ROUTES (Home) ==================
@app.route('/')
def home():
    search_query = request.args.get('search_query', '').strip()
    category = request.args.get('category', '').strip()
    author_filter = request.args.get('author', '').strip()
    lang_filter = request.args.get('language', '').strip()

    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(50, request.args.get('per_page', 12, type=int))
    if per_page < 1:
        per_page = 12
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()
    conditions = ["d.approved = 1"]
    params = []
    if search_query:
        conditions.append("(d.title LIKE %s OR d.author LIKE %s)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if category:
        conditions.append("c.level = %s")
        params.append(category)
    if author_filter:
        conditions.append("d.author LIKE %s")
        params.append(f'%{author_filter}%')
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

    real_pdfs = [{"id": r[0], "title": r[1], "level": r[2], "link": r[3],
                  "author": r[4], "description": r[5], "image_url": r[6], "language": r[7],
                  "download_count": r[8] or 0, "view_count": r[9] or 0,
                  "avg_rating": round(float(r[10]), 1) if r[10] else 0} for r in books_data]
    categories = [{"id": r[0], "level": r[1], "count": r[2]} for r in cat_data]

    featured_book = get_book_of_the_day()

    streak = longest = 0
    if 'user_id' in session:
        cur = mysql.connection.cursor()
        cur.execute("SELECT streak_count, longest_streak FROM user_streaks WHERE user_id = %s", (session['user_id'],))
        row = cur.fetchone()
        if row:
            streak, longest = row
        cur.close()

    recommended_books = []
    if 'user_id' in session:
        uid = session['user_id']
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT DISTINCT d.category_id FROM favorites f
            JOIN documents d ON f.book_id = d.id WHERE f.user_id = %s
            UNION
            SELECT DISTINCT d.category_id FROM download_history h
            JOIN documents d ON h.book_id = d.id WHERE h.user_id = %s
        """, (uid, uid))
        cat_ids = [row[0] for row in cur.fetchall()]
        if cat_ids:
            placeholders = ','.join(['%s'] * len(cat_ids))
            cur.execute(f"""
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
            """, cat_ids)
            rec_rows = cur.fetchall()
            for r in rec_rows:
                recommended_books.append({
                    "id": r[0], "title": r[1], "author": r[2], "level": r[3],
                    "image_url": r[4], "link": r[5],
                    "download_count": r[6] or 0, "view_count": r[7] or 0,
                    "avg_rating": round(float(r[8]), 1) if r[8] else 0
                })
        cur.close()

    return render_template('index.html',
                           pdfs=real_pdfs, search_query=search_query, category=category,
                           author_filter=author_filter, lang_filter=lang_filter,
                           categories=categories, page=page, total_pages=total_pages,
                           featured_book=featured_book, streak=streak, longest=longest,
                           recommended_books=recommended_books)


# ================== LEARNING HUBS (Category Pages) ==================
@app.route('/learn/<category_slug>')
def learning_hub(category_slug):
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 24
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()
    category_name = slug_to_category_name(category_slug, cur)

    if category_name is None:
        cur.close()
        abort(404)

    cur.execute("""
        SELECT COUNT(*)
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE c.level = %s AND d.approved = 1
    """, (category_name,))
    total_books = cur.fetchone()[0]

    total_pages = max(1, (total_books + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    cur.execute("""
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
    """, (category_name, per_page, offset))
    rows = cur.fetchall()

    cur.execute("""
        SELECT COALESCE(SUM(d.download_count), 0)
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE c.level = %s AND d.approved = 1
    """, (category_name,))
    total_downloads = cur.fetchone()[0]

    cur.execute("""
        SELECT c.level, COUNT(d.id) AS total
        FROM categories c
        LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1
        GROUP BY c.id, c.level
        HAVING total > 0
        ORDER BY total DESC
    """)
    all_categories = [{"level": r[0], "count": r[1], "slug": category_to_slug(r[0])}
                      for r in cur.fetchall()]
    cur.close()

    books = [{
        "id": r[0],
        "title": r[1],
        "author": r[2],
        "image_url": r[3],
        "link": r[4],
        "download_count": r[5] or 0,
        "view_count": r[6] or 0,
        "level": r[7],
        "avg_rating": round(float(r[8]), 1) if r[8] else 0,
    } for r in rows]

    return render_template(
        'learning_hub.html',
        category=category_name,
        category_slug=category_slug,
        books=books,
        total_books=total_books,
        total_downloads=total_downloads,
        page=page,
        total_pages=total_pages,
        all_categories=all_categories,
    )


# ================== BOOK DETAIL ==================
@app.route('/book/<int:book_id>')
def book_detail(book_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language, d.category_id
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.id = %s AND d.approved = 1
    """, (book_id,))
    book = cur.fetchone()

    if not book:
        cur.close()
        abort(404)

    cur.execute("UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,))
    mysql.connection.commit()

    cur.execute("""
        SELECT u.username, r.rating, r.comment, r.created_at, u.id, r.id
        FROM reviews r JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s ORDER BY r.created_at DESC
    """, (book_id,))
    reviews_raw = cur.fetchall()
    cur.close()

    reviews = []
    for r in reviews_raw:
        reviews.append({
            'id': r[5], 'username': r[0], 'rating': r[1], 'comment': r[2],
            'created_at': r[3], 'user_id': r[4], 'is_official': is_official_user(r[4])
        })

    lazy_trickle(book_id)

    related_books = []
    cat_id = book[8] if len(book) > 8 else None
    if cat_id:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT d.id, d.title, d.author, c.level, d.image_url, d.telegram_link,
                   COALESCE(d.download_count, 0) as download_count,
                   COALESCE(d.view_count, 0) as view_count
            FROM documents d
            JOIN categories c ON d.category_id = c.id
            WHERE d.approved = 1 AND d.category_id = %s AND d.id != %s
            ORDER BY d.download_count DESC
            LIMIT 4
        """, (cat_id, book_id))
        rel_rows = cur.fetchall()
        cur.close()
        for r in rel_rows:
            related_books.append({
                "id": r[0], "title": r[1], "author": r[2], "level": r[3],
                "image_url": r[4], "link": r[5],
                "download_count": r[6] or 0, "view_count": r[7] or 0
            })

    book_data = {"id": book[0], "title": book[1], "level": book[2], "link": book[3],
                 "author": book[4], "description": book[5], "image_url": book[6], "language": book[7]}
    return render_template('book_detail.html', book=book_data, reviews=reviews, related_books=related_books)


# ================== SEO ROUTES ==================
@app.route('/sitemap.xml')
def sitemap():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, title FROM documents WHERE approved = 1 ORDER BY id DESC")
    books = cur.fetchall()
    cur.close()

    static_pages = [
        {'loc': url_for('home', _external=True), 'changefreq': 'daily', 'priority': '1.0'},
        {'loc': url_for('user_login', _external=True), 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': url_for('user_signup', _external=True), 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': url_for('forgot_password', _external=True), 'changefreq': 'monthly', 'priority': '0.3'},
        {'loc': url_for('user_favorites', _external=True), 'changefreq': 'weekly', 'priority': '0.4'},
        {'loc': url_for('user_history', _external=True), 'changefreq': 'weekly', 'priority': '0.4'},
    ]

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in static_pages:
        xml += f'  <url>\n    <loc>{escape(page["loc"])}</loc>\n    <changefreq>{page["changefreq"]}</changefreq>\n    <priority>{page["priority"]}</priority>\n  </url>\n'
    for book in books:
        book_url = url_for('book_detail', book_id=book[0], _external=True)
        xml += f'  <url>\n    <loc>{escape(book_url)}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
    xml += '</urlset>'
    return Response(xml, mimetype='application/xml')


@app.route('/robots.txt')
def robots():
    content = f"User-agent: *\nAllow: /\nSitemap: {url_for('sitemap', _external=True)}\n"
    return Response(content, mimetype='text/plain')


# ================== SEARCH AUTOCOMPLETE ==================
@app.route('/api/search/suggest')
def search_suggest():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, d.author, c.level, d.image_url,
               COALESCE(d.download_count, 0) as download_count,
               COALESCE(d.view_count, 0) as view_count
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE d.title LIKE %s AND d.approved = 1
        ORDER BY d.title
        LIMIT 8
    """, (f'%{q}%',))
    results = cur.fetchall()
    cur.close()
    return jsonify([{
        "id": r[0], "title": r[1], "author": r[2], "level": r[3], "image_url": r[4],
        "download_count": r[5] or 0, "view_count": r[6] or 0
    } for r in results])


# ================== API: BOOK DETAIL FOR MODAL ==================
@app.route('/api/book/<int:book_id>')
def api_book_detail(book_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.id = %s AND d.approved = 1
    """, (book_id,))
    book = cur.fetchone()

    if not book:
        cur.close()
        return jsonify({"error": "Book not found"}), 404

    cur.execute("UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,))
    mysql.connection.commit()

    cur.execute("""
        SELECT u.username, r.rating, r.comment, r.created_at
        FROM reviews r JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s ORDER BY r.created_at DESC
    """, (book_id,))
    reviews = cur.fetchall()

    is_fav = False
    if 'user_id' in session:
        cur.execute("SELECT id FROM favorites WHERE user_id = %s AND book_id = %s", (session['user_id'], book_id))
        is_fav = cur.fetchone() is not None
    cur.close()

    lazy_trickle(book_id)

    book_data = {
        "id": book[0], "title": book[1], "level": book[2], "link": book[3],
        "author": book[4], "description": book[5], "image_url": book[6], "language": book[7],
        "reviews": [{"username": r[0], "rating": r[1], "comment": r[2], "created_at": str(r[3])} for r in reviews],
        "is_favorite": is_fav, "is_logged_in": 'user_id' in session
    }
    return jsonify(book_data)


# ================== USER ACCOUNTS ==================
@app.route('/user/signup', methods=['GET', 'POST'])
def user_signup():
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()

        if not username or not email or not password:
            msg = 'All fields are required.'
            if is_ajax:
                return jsonify({'error': msg}), 400
            return render_template('auth.html', mode='signup', error=msg)
        if not is_valid_email(email):
            msg = 'Please enter a valid email address.'
            if is_ajax:
                return jsonify({'error': msg}), 400
            return render_template('auth.html', mode='signup', error=msg)
        if len(username) < 3 or len(username) > 20 or not username.isalnum():
            msg = 'Username must be 3-20 letters and numbers only.'
            if is_ajax:
                return jsonify({'error': msg}), 400
            return render_template('auth.html', mode='signup', error=msg)
        if len(password) < 6:
            msg = 'Password must be at least 6 characters.'
            if is_ajax:
                return jsonify({'error': msg}), 400
            return render_template('auth.html', mode='signup', error=msg)

        hashed = generate_password_hash(password)
        token = secrets.token_urlsafe(32)

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cur.fetchone():
            cur.close()
            msg = 'Username or email already exists.'
            if is_ajax:
                return jsonify({'error': msg}), 409
            return render_template('auth.html', mode='signup', error=msg)

        cur.execute("INSERT INTO users (username, email, password, verification_token, first_name, last_name) VALUES (%s, %s, %s, %s, %s, %s)",
                    (username, email, hashed, token, first_name, last_name))
        mysql.connection.commit()
        cur.close()

        sync_brevo_contact(email, first_name, last_name)

        verify_link = url_for('verify_email', token=token, _external=True)
        html_body = make_verification_email(username, verify_link)
        try:
            send_email_notification("Verify your email - DocoDive", email,
                                    f"Hi {username}, confirm your DocoDive email address: {verify_link}",
                                    html_body=html_body)
        except Exception:
            pass

        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for('home')})
        flash('Account created! Please check your email to verify.', 'success')
        return redirect(url_for('user_login'))

    return render_template('auth.html', mode='signup')


@app.route('/user/login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        email = request.form.get('email')
        password = request.form.get('password')
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, password, verified, verification_token FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

        if not user:
            msg = 'No account found with this email. Please sign up first.'
            if is_ajax:
                return jsonify({'error': msg}), 401
            return render_template('auth.html', mode='login', error=msg)
        if not check_password_hash(user[2], password):
            msg = 'Invalid password. Please try again.'
            if is_ajax:
                return jsonify({'error': msg}), 401
            return render_template('auth.html', mode='login', error=msg)
        if not user[3]:
            new_token = secrets.token_urlsafe(32)
            cur = mysql.connection.cursor()
            cur.execute("UPDATE users SET verification_token = %s WHERE id = %s", (new_token, user[0]))
            mysql.connection.commit()
            cur.close()
            verify_link = url_for('verify_email', token=new_token, _external=True)
            html_body = make_verification_email(user[1], verify_link)
            try:
                send_email_notification("Verify your email - DocoDive", email,
                                        f"Hi {user[1]}, confirm your DocoDive email address: {verify_link}",
                                        html_body=html_body)
            except Exception:
                pass
            msg = 'A new verification email has been sent. Please check your inbox.'
            if is_ajax:
                return jsonify({'error': msg}), 403
            return render_template('auth.html', mode='login', error=msg)

        setup_session(user[0])

        today = datetime.utcnow().date()
        cur = mysql.connection.cursor()
        cur.execute("SELECT last_login_date, streak_count, longest_streak FROM user_streaks WHERE user_id = %s", (user[0],))
        streak_row = cur.fetchone()
        if streak_row:
            last_date, streak_cnt, long_streak = streak_row
            if last_date == today - timedelta(days=1):
                streak_cnt += 1
                award_points(user[0], 1, action='daily_login')
            else:
                streak_cnt = 1
            long_streak = max(long_streak, streak_cnt)
            cur.execute("UPDATE user_streaks SET last_login_date=%s, streak_count=%s, longest_streak=%s WHERE user_id=%s",
                        (today, streak_cnt, long_streak, user[0]))
        else:
            cur.execute("INSERT INTO user_streaks (user_id, last_login_date, streak_count, longest_streak) VALUES (%s, %s, 1, 1)",
                        (user[0], today))
            award_points(user[0], 1, action='daily_login')
        mysql.connection.commit()
        cur.close()

        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for('home')})
        return redirect(url_for('home'))

    return render_template('auth.html', mode='login')


@app.route('/verify/<token>')
def verify_email(token):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM users WHERE verification_token = %s AND verified = 0", (token,))
    user = cur.fetchone()
    if user:
        cur.execute("UPDATE users SET verified = 1, verification_token = NULL WHERE id = %s", (user[0],))
        mysql.connection.commit()
        cur.close()
        flash('Email verified! You can now login.', 'success')
    else:
        cur.close()
        flash('Invalid or expired verification link.', 'danger')
    return redirect(url_for('user_login'))


@app.route('/user/logout')
def user_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    return redirect(url_for('home'))


# ================== FAVORITES & HISTORY ==================
@app.route('/user/favorites')
def user_favorites():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
        FROM favorites f JOIN documents d ON f.book_id = d.id JOIN categories c ON d.category_id = c.id
        WHERE f.user_id = %s
    """, (session['user_id'],))
    books = cur.fetchall()
    cur.close()
    real_pdfs = [{"id": r[0], "title": r[1], "level": r[2], "link": r[3],
                   "author": r[4], "description": r[5], "image_url": r[6], "language": r[7]} for r in books]
    return render_template('user_favorites.html', pdfs=real_pdfs)


@app.route('/user/favorite/<int:book_id>', methods=['POST'])
def toggle_favorite(book_id):
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM favorites WHERE user_id = %s AND book_id = %s", (user_id, book_id))
    if cur.fetchone():
        cur.execute("DELETE FROM favorites WHERE user_id = %s AND book_id = %s", (user_id, book_id))
    else:
        cur.execute("INSERT INTO favorites (user_id, book_id) VALUES (%s, %s)", (user_id, book_id))
        award_points(user_id, 1, book_id, action='favorite')
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route('/user/history')
def user_history():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language, h.downloaded_at
        FROM download_history h JOIN documents d ON h.book_id = d.id JOIN categories c ON d.category_id = c.id
        WHERE h.user_id = %s ORDER BY h.downloaded_at DESC
    """, (session['user_id'],))
    books = cur.fetchall()
    cur.close()
    real_pdfs = [{"id": r[0], "title": r[1], "level": r[2], "link": r[3],
                   "author": r[4], "description": r[5], "image_url": r[6], "language": r[7],
                   "downloaded_at": str(r[8])} for r in books]
    return render_template('user_history.html', pdfs=real_pdfs)


# ================== DOWNLOAD TRACKING ==================
@app.route('/api/download/<int:book_id>', methods=['POST'])
def track_download_route(book_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
                (session['user_id'], book_id))
    cur.execute("UPDATE documents SET download_count = download_count + 1 WHERE id = %s",
                (book_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})


# ================== REVIEWS ==================
@app.route('/book/<int:book_id>/review', methods=['POST'])
def add_review(book_id):
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '')
    if not rating or rating < 1 or rating > 5:
        return jsonify({"error": "Invalid rating"}), 400
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO reviews (user_id, book_id, rating, comment) VALUES (%s, %s, %s, %s)",
                (user_id, book_id, rating, comment))
    mysql.connection.commit()
    cur.close()
    award_points(user_id, 5, book_id, action='review')
    return jsonify({"success": True})


# -------------------- PROTECTED DOWNLOAD & READ ONLINE --------------------
@app.route('/book/<int:book_id>/download')
def download_book(book_id):
    if 'user_id' not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Login required'}), 401
        flash('Please login to download books.', 'danger')
        return redirect(url_for('user_login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT telegram_link FROM documents WHERE id = %s AND approved = 1", (book_id,))
    book = cur.fetchone()
    if not book:
        cur.close()
        abort(404)
    cur.execute("UPDATE documents SET download_count = download_count + 1 WHERE id = %s", (book_id,))
    mysql.connection.commit()
    cur.close()

    r2_key = extract_r2_key(book[0])
    if not r2_key:
        flash('Download not available.', 'danger')
        return redirect(url_for('home'))

    presigned = get_presigned_url(r2_key, expiration=300)
    if not presigned:
        flash('Could not generate download link.', 'danger')
        return redirect(url_for('home'))

    if 'user_id' in session:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
                    (session['user_id'], book_id))
        mysql.connection.commit()
        cur.close()

    return redirect(presigned)


@app.route('/book/<int:book_id>/read')
def read_online(book_id):
    if 'user_id' not in session:
        flash('Please login to read books online.', 'danger')
        return redirect(url_for('user_login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT telegram_link, title FROM documents WHERE id = %s AND approved = 1", (book_id,))
    book = cur.fetchone()
    if not book:
        cur.close()
        abort(404)
    cur.execute("UPDATE documents SET view_count = view_count + 1 WHERE id = %s", (book_id,))
    mysql.connection.commit()
    cur.close()

    r2_key = extract_r2_key(book[0])
    if not r2_key:
        flash('Read online not available.', 'danger')
        return redirect(url_for('home'))

    presigned = get_presigned_url(r2_key, expiration=600)
    if not presigned:
        flash('Could not generate reading link.', 'danger')
        return redirect(url_for('home'))

    return render_template('read_online.html', pdf_url=presigned, book_title=book[1], book_id=book_id)

# ================== OFFICIAL ADMIN ROUTES ==================
@app.route('/admin', methods=['GET', 'POST'])
@official_admin_required
@cache.cached(timeout=600, unless=lambda: request.method == 'POST')
def admin():
    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['pdf_file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file"}), 400

        pdf_bytes = file.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        meta = reader.metadata
        pdf_title = (meta.title or '').strip() if meta else ''
        author_meta = (meta.author or '').strip() if meta else ''
        raw_name = pdf_title if pdf_title and pdf_title.lower() != 'unknown' else os.path.splitext(file.filename)[0]
        clean_base = clean_professional_name(raw_name)
        display_title = clean_base.replace('_', ' ').replace(' @DocoDive', '').strip()
        display_title = clean_title_extra(display_title)
        if not display_title:
            display_title = 'Untitled'
        author = author_meta if author_meta and author_meta.lower() != 'unknown' else 'Unknown'
        author = author or 'Unknown'

        manual_category = request.form.get('category', '').strip()
        if manual_category:
            category = manual_category
        else:
            pdf_text = ''
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
            category = guess_category_from_text(pdf_text) if pdf_text else guess_category_from_filename(file.filename)

        description = generate_description(display_title, category)

        cur = mysql.connection.cursor()
        if is_duplicate(display_title, author, cur):
            cur.close()
            return jsonify({"error": "This book already exists in the database."}), 400
        cur.close()

        try:
            pdf_key = generate_r2_key('uploads', clean_base, '.pdf')
            pdf_url = upload_to_r2(pdf_bytes, pdf_key, content_type='application/pdf')
        except Exception as e:
            app.logger.error(f"PDF upload failed: {e}")
            return jsonify({"error": "Failed to upload PDF."}), 500

        cover_bytes = None
        cover_extension = '.png'
        if 'cover_image' in request.files and request.files['cover_image'].filename != '':
            cover_file = request.files['cover_image']
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
                return jsonify({"error": "Could not generate cover from PDF. Please upload a cover image manually."}), 400

        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
        mime = mime_map.get(cover_extension, 'application/octet-stream')
        try:
            cover_key = generate_r2_key('covers', clean_base, cover_extension)
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

        cur.execute("""
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, approved, uploaded_by, download_count, view_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """, (cat_id, display_title, pdf_url, author, description, image_url, 'English', session['user_id'], dl_count, vw_count))
        mysql.connection.commit()
        cur.close()

        return jsonify({"success": True, "title": display_title, "category": category,
                        "message": f"Book '{display_title}' uploaded in {category}! Waiting for approval."})

    cur = mysql.connection.cursor()
    DEFAULT_CATEGORIES = ['Python', 'JavaScript', 'Java', 'C / C++', 'Web Development', 'Data Science',
                          'Machine Learning', 'Algorithms', 'Databases', 'Cyber Security', 'Mobile Apps', 'DevOps', 'Others']
    for cat in DEFAULT_CATEGORIES:
        cur.execute("SELECT id FROM categories WHERE level = %s", (cat,))
        if not cur.fetchone():
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (cat,))
    mysql.connection.commit()
    cur.execute("SELECT level FROM categories ORDER BY level")
    categories = [row[0] for row in cur.fetchall()]
    cur.close()
    return render_template('admin.html', categories=categories)


@app.route('/admin/pending/count')
@official_admin_required
def pending_count():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents WHERE approved = 0")
    count = cur.fetchone()[0]
    cur.close()
    return jsonify({'count': count})


@app.route('/admin/pending')
@official_admin_required
def pending_books():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.author, d.created_at, d.telegram_link
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved = 0 ORDER BY d.id DESC
    """)
    books = cur.fetchall()
    cur.close()
    books_list = [{"id": b[0], "title": b[1], "level": b[2], "author": b[3],
                   "created_at": str(b[4]) if b[4] else '', "link": b[5]} for b in books]
    return render_template('pending.html', books=books_list)


@app.route('/admin/approve/<int:book_id>', methods=['POST'])
@official_admin_required
def approve_book(book_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT title, uploaded_by FROM documents WHERE id = %s", (book_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Book not found"}), 404
    title, uploader_id = row
    cur.execute("UPDATE documents SET approved = 1, status = 'approved', approved_at = NOW() WHERE id = %s", (book_id,))
    mysql.connection.commit()
    if uploader_id:
        cur.execute("SELECT email, username FROM users WHERE id = %s", (uploader_id,))
        user = cur.fetchone()
        if user:
            html = make_approval_email(title, "approved", "Your book has been approved!")
            send_email_notification("Book Approved - DocoDive", user[0],
                                    f"Your DocoDive document '{title}' has been approved.", html_body=html)
            create_notification(uploader_id, 'approval', f"<strong>{title}</strong> has been approved ✅",
                                url_for('book_detail', book_id=book_id),
                                {"book_id": book_id, "action_by": "admin", "uploader_id": uploader_id})
    cur.close()
    return jsonify({"success": True})


@app.route('/admin/reject/<int:book_id>', methods=['POST'])
@official_admin_required
def reject_book(book_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT title, uploaded_by, telegram_link FROM documents WHERE id = %s", (book_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Book not found"}), 404
    title, uploader_id, file_link = row
    if file_link:
        r2_key = extract_r2_key(file_link)
        if r2_key:
            delete_from_r2(r2_key)
    cur.execute("UPDATE documents SET approved = 0, status = 'rejected', approved_at = NULL WHERE id = %s", (book_id,))
    mysql.connection.commit()
    if uploader_id:
        cur.execute("SELECT email, username FROM users WHERE id = %s", (uploader_id,))
        user = cur.fetchone()
        if user:
            html = make_approval_email(title, "rejected", "Your book was rejected.")
            send_email_notification("Book Rejected - DocoDive", user[0],
                                    f"Your document '{title}' was not approved.", html_body=html)
            create_notification(uploader_id, 'rejection', f"<strong>{title}</strong> has been rejected ❌",
                                url_for('user_upload'),
                                {"book_id": book_id, "action_by": "admin", "uploader_id": uploader_id})
    cur.close()
    return jsonify({"success": True})


@app.route('/admin/approve-all', methods=['POST'])
@official_admin_required
def approve_all_books():
    cur = mysql.connection.cursor()
    cur.execute("UPDATE documents SET approved = 1, status = 'approved', approved_at = NOW() WHERE approved = 0")
    count = cur.rowcount
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True, "count": count})


@app.route('/admin/books')
@official_admin_required
def admin_books_list():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, d.category_id, d.telegram_link, d.author, d.description, d.image_url, d.language, c.level
        FROM documents d JOIN categories c ON d.category_id = c.id ORDER BY d.id DESC
    """)
    books = cur.fetchall()
    cur.close()
    books_list = [{"id": b[0], "title": b[1], "category_id": b[2], "link": b[3],
                   "author": b[4], "description": b[5], "image_url": b[6], "language": b[7], "level": b[8]} for b in books]
    return render_template('admin_books.html', books=books_list)


@app.route('/admin/edit/<int:book_id>', methods=['GET', 'POST'])
@official_admin_required
def edit_book(book_id):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        cur.execute("SELECT telegram_link, image_url FROM documents WHERE id = %s", (book_id,))
        old = cur.fetchone()
        old_pdf = old[0] if old else None
        old_cover = old[1] if old else None

        title = request.form.get('title')
        category_name = request.form.get('category')
        author = request.form.get('author')
        desc = request.form.get('desc')
        img_url = request.form.get('img')
        language = request.form.get('language', 'English')

        if 'pdf_file' in request.files and request.files['pdf_file'].filename != '':
            file = request.files['pdf_file']
            if not allowed_file(file.filename):
                return jsonify({"error": "Only PDF files are allowed."}), 400
            pdf_bytes = file.read()
            clean_title = clean_professional_name(title) if title else clean_professional_name("book")
            pdf_key = generate_r2_key('uploads', clean_title, '.pdf')
            new_pdf_url = upload_to_r2(pdf_bytes, pdf_key, content_type='application/pdf')
            if old_pdf:
                old_key = extract_r2_key(old_pdf)
                if old_key:
                    delete_from_r2(old_key)
            cur.execute("""
                UPDATE documents SET category_id=(SELECT id FROM categories WHERE level=%s), title=%s,
                telegram_link=%s, author=%s, description=%s, image_url=%s, language=%s WHERE id=%s
            """, (category_name, title, new_pdf_url, author, desc, img_url or old_cover or None, language, book_id))
        else:
            cur.execute("""
                UPDATE documents SET category_id=(SELECT id FROM categories WHERE level=%s), title=%s,
                author=%s, description=%s, image_url=%s, language=%s WHERE id=%s
            """, (category_name, title, author, desc, img_url or old_cover or None, language, book_id))

        if 'cover_image' in request.files and request.files['cover_image'].filename != '':
            cover_file = request.files['cover_image']
            if allowed_image_file(cover_file.filename):
                cover_bytes = cover_file.read()
                if len(cover_bytes) <= 2 * 1024 * 1024:
                    clean_title = clean_professional_name(title) if title else clean_professional_name("book")
                    img_ext = os.path.splitext(cover_file.filename)[1].lower()
                    cover_key = generate_r2_key('covers', clean_title, img_ext)
                    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
                    mime = mime_map.get(img_ext, 'application/octet-stream')
                    new_cover_url = upload_to_r2(cover_bytes, cover_key, content_type=mime)
                    if old_cover:
                        old_key = extract_r2_key(old_cover)
                        if old_key:
                            delete_from_r2(old_key)
                    cur.execute("UPDATE documents SET image_url = %s WHERE id = %s", (new_cover_url, book_id))

        mysql.connection.commit()
        cur.close()
        return redirect(url_for('admin_books_list'))

    cur = mysql.connection.cursor()
    DEFAULT_CATEGORIES = ['Python', 'JavaScript', 'Java', 'C / C++', 'Web Development', 'Data Science',
                          'Machine Learning', 'Algorithms', 'Databases', 'Cyber Security', 'Mobile Apps', 'DevOps', 'Others']
    for cat in DEFAULT_CATEGORIES:
        cur.execute("SELECT id FROM categories WHERE level = %s", (cat,))
        if not cur.fetchone():
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (cat,))
    mysql.connection.commit()

    cur.execute("SELECT id, title, category_id, telegram_link, author, description, image_url, language FROM documents WHERE id = %s", (book_id,))
    book_row = cur.fetchone()
    cur.execute("SELECT id, level FROM categories ORDER BY id")
    categories_raw = cur.fetchall()
    categories = [{"id": row[0], "level": row[1]} for row in categories_raw]
    cur.close()
    if not book_row:
        abort(404)
    book = {"id": book_row[0], "title": book_row[1], "category_id": book_row[2], "link": book_row[3],
            "author": book_row[4], "description": book_row[5], "image_url": book_row[6], "language": book_row[7]}
    return render_template('edit_book.html', book=book, categories=categories)


@app.route('/admin/delete/<int:book_id>', methods=['POST'])
@official_admin_required
def delete_book(book_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT telegram_link, image_url FROM documents WHERE id = %s", (book_id,))
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


@app.route('/admin/dashboard')
@official_admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')


@app.route('/api/admin/stats')
@official_admin_required
def admin_stats():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total_books = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM categories")
    total_categories = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT d.title, c.level, d.created_at FROM documents d JOIN categories c ON d.category_id = c.id ORDER BY d.id DESC LIMIT 5")
    recent = cur.fetchall()
    cur.close()
    recent_uploads = [{"title": r[0], "level": r[1], "created_at": str(r[2])} for r in recent]
    return jsonify({"total_books": total_books, "total_categories": total_categories,
                    "total_users": total_users, "recent_uploads": recent_uploads})


@app.route('/api/categories/live-counts')
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


@app.route('/admin/users')
@official_admin_required
def list_users():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, username, email, verified, created_at FROM users ORDER BY id")
    users = cur.fetchall()
    cur.close()
    users_list = [{"id": r[0], "username": r[1], "email": r[2], "verified": r[3], "created_at": str(r[4])} for r in users]
    return render_template('admin_users.html', users=users_list)


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session or not is_official_user(session['user_id']):
        return jsonify({"error": "Unauthorized"}), 403
    if session.get('user_id') == user_id:
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
        cur.execute("UPDATE documents SET uploaded_by = NULL WHERE uploaded_by = %s", (user_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})
    except Exception as e:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": str(e)}), 500


@app.route('/admin/analytics')
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
    return render_template('admin_analytics.html', total_books=total_books,
                           total_downloads=total_downloads, total_users=total_users)


@app.route('/admin/trickle-counts')
@official_admin_required
def trickle_counts():
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM documents WHERE approved = 1 AND created_at >= %s", (seven_days_ago,))
    books = cur.fetchall()
    for book in books:
        dl_growth = random.randint(5, 20)
        vw_growth = random.randint(10, 40)
        cur.execute("""
            UPDATE documents SET download_count = download_count + %s,
                view_count = view_count + %s, last_trickle_time = NOW() WHERE id = %s
        """, (dl_growth, vw_growth, book[0]))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True, "updated": len(books)})


@app.route('/admin/official-profile', methods=['GET', 'POST'])
@official_admin_required
def admin_official_profile():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if username:
            cur = mysql.connection.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()
            if user:
                set_site_setting('official_user_id', str(user[0]))
                flash(f'Official profile set to {username}', 'success')
            else:
                flash('User not found.', 'danger')
        return redirect(url_for('admin_official_profile'))

    official_user_id = get_site_setting('official_user_id')
    official_user = None
    if official_user_id:
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, avatar_url FROM users WHERE id = %s", (official_user_id,))
        official_user = cur.fetchone()
        cur.close()
    return render_template('admin_official_profile.html', official_user=official_user)


# ================== MODERATION API ==================
@app.route('/api/review/<int:review_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_review_api(review_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route('/api/comment/<int:comment_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_comment_api(comment_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM book_comments WHERE id = %s", (comment_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route('/api/comment/<int:comment_id>/reply', methods=['POST'])
@limiter.limit("10 per minute")
def reply_as_official_api(comment_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    reply_text = data.get('reply_text', '').strip()
    if not reply_text:
        return jsonify({"error": "Reply text required"}), 400
    official_user_id = get_site_setting('official_user_id')
    if not official_user_id:
        return jsonify({"error": "Official user not set"}), 500
    cur = mysql.connection.cursor()
    cur.execute("SELECT book_id FROM book_comments WHERE id = %s", (comment_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Comment not found"}), 404
    book_id = row[0]
    cur.execute("INSERT INTO book_comments (book_id, user_id, parent_id, comment) VALUES (%s, %s, %s, %s)",
                (book_id, official_user_id, comment_id, reply_text))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route('/api/review/<int:review_id>/reply', methods=['POST'])
@limiter.limit("10 per minute")
def reply_to_review_api(review_id):
    if not is_moderator():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    reply_text = data.get('reply_text', '').strip()
    if not reply_text:
        return jsonify({"error": "Reply text required"}), 400
    official_user_id = get_site_setting('official_user_id')
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
        cur.execute("INSERT INTO book_comments (book_id, user_id, parent_id, comment) VALUES (%s, %s, %s, %s)",
                    (book_id, official_user_id, -review_id, full_comment))
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
@app.route('/moderation')
@limiter.limit("30 per minute")
def moderation_panel():
    if not is_moderator():
        abort(403)

    days = request.args.get('days', 30, type=int)
    since = datetime.now() - timedelta(days=days)

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT r.id, u.username, u.avatar_url, d.title, d.id AS book_id,
               r.rating, r.comment, r.created_at, u.id
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        JOIN documents d ON r.book_id = d.id
        WHERE r.created_at >= %s
        ORDER BY r.created_at DESC
        LIMIT 50
    """, (since,))
    reviews_raw = cur.fetchall()
    reviews = []
    for row in reviews_raw:
        reviews.append({
            'id': row[0],
            'username': row[1],
            'avatar': row[2],
            'book_title': row[3],
            'book_id': row[4],
            'rating': row[5],
            'comment': row[6],
            'created_at': row[7].strftime('%b %d, %Y %H:%M') if row[7] else '',
            'user_id': row[8],
            'is_official': is_official_user(row[8])
        })

    cur.execute("""
        SELECT c.id, u.username, u.avatar_url, d.title, d.id AS book_id,
               c.comment, c.created_at, u.id
        FROM book_comments c
        JOIN users u ON c.user_id = u.id
        JOIN documents d ON c.book_id = d.id
        WHERE c.parent_id >= 0 AND c.created_at >= %s
        ORDER BY c.created_at DESC
        LIMIT 50
    """, (since,))
    comments_raw = cur.fetchall()
    comments = []
    comment_ids = []
    for row in comments_raw:
        comments.append({
            'id': row[0],
            'username': row[1],
            'avatar': row[2],
            'book_title': row[3],
            'book_id': row[4],
            'comment': row[5],
            'created_at': row[6].strftime('%b %d, %Y %H:%M') if row[6] else '',
            'user_id': row[7],
            'is_official': is_official_user(row[7])
        })
        comment_ids.append(row[0])

    official_user_id = get_site_setting('official_user_id')
    comment_replies = {}
    if official_user_id and comment_ids:
        placeholders = ','.join(['%s'] * len(comment_ids))
        cur.execute(f"""
            SELECT id, user_id, parent_id, comment, created_at
            FROM book_comments
            WHERE user_id = %s AND parent_id IN ({placeholders})
            ORDER BY created_at ASC
        """, [official_user_id] + comment_ids)
        reply_rows = cur.fetchall()
        for r in reply_rows:
            comment_replies[r[2]] = {
                'id': r[0],
                'comment': r[3],
                'created_at': r[4].strftime('%b %d, %Y %H:%M') if r[4] else ''
            }

    cur.execute("SELECT COUNT(*) FROM reviews WHERE created_at >= %s", (since,))
    total_reviews = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM book_comments WHERE parent_id >= 0 AND created_at >= %s", (since,))
    total_comments = cur.fetchone()[0]

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cur.execute("SELECT COUNT(*) FROM reviews WHERE created_at >= %s", (today_start,))
    new_reviews_today = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM book_comments WHERE parent_id >= 0 AND created_at >= %s", (today_start,))
    new_comments_today = cur.fetchone()[0]

    daily_reviews = defaultdict(int)
    daily_comments = defaultdict(int)
    daily_replies = defaultdict(int)

    cur.execute("SELECT DATE(created_at), COUNT(*) FROM reviews WHERE created_at >= %s GROUP BY DATE(created_at)", (since,))
    for row in cur.fetchall():
        daily_reviews[str(row[0])] = row[1]

    cur.execute("SELECT DATE(created_at), COUNT(*) FROM book_comments WHERE parent_id >= 0 AND created_at >= %s GROUP BY DATE(created_at)", (since,))
    for row in cur.fetchall():
        daily_comments[str(row[0])] = row[1]

    if official_user_id:
        cur.execute("SELECT DATE(created_at), COUNT(*) FROM book_comments WHERE parent_id < 0 AND user_id = %s AND created_at >= %s GROUP BY DATE(created_at)", (official_user_id, since))
        for row in cur.fetchall():
            daily_replies[str(row[0])] = row[1]

    date_range = []
    current = since
    while current <= datetime.now():
        date_range.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    chart_labels = json.dumps(date_range)
    chart_reviews = json.dumps([daily_reviews.get(d, 0) for d in date_range])
    chart_comments = json.dumps([daily_comments.get(d, 0) for d in date_range])
    chart_replies = json.dumps([daily_replies.get(d, 0) for d in date_range])

    cur.close()

    return render_template('admin_moderation.html',
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
                           chart_replies=chart_replies)


# ================== FEEDBACK COMMUNITY ==================
@app.route('/feedback', methods=['GET', 'POST'])
def user_feedback():
    if request.method == 'POST':
        if 'user_id' not in session:
            flash('Please login to submit feedback.', 'danger')
            return redirect(url_for('user_login'))

        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        if not subject or not message:
            flash('Please fill both subject and message.', 'danger')
            return redirect(url_for('user_feedback'))

        user_id = session['user_id']
        try:
            cur = mysql.connection.cursor()
            cur.execute(
                "INSERT INTO user_feedback (user_id, subject, message) VALUES (%s, %s, %s)",
                (user_id, subject, message)
            )
            mysql.connection.commit()
            cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            user_row = cur.fetchone()
            username = user_row[0] if user_row else 'User'
            cur.close()

            if app.config.get('ADMIN_NOTIFICATION_EMAIL'):
                html_body = make_feedback_notification_email(username, subject, message)
                send_email_notification(
                    f"New Feedback - {subject}",
                    app.config['ADMIN_NOTIFICATION_EMAIL'],
                    f"New suggestion from {username}: {subject}",
                    html_body=html_body
                )
            flash('Your suggestion has been posted!', 'success')
        except Exception as e:
            app.logger.error(f"Feedback insert failed: {e}")
            flash('Something went wrong. Please try again.', 'danger')
        return redirect(url_for('user_feedback'))

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
    current_user_id = session.get('user_id')
    for row in feedbacks:
        fid = row[0]
        is_liked = False
        if current_user_id:
            cur = mysql.connection.cursor()
            cur.execute("SELECT 1 FROM feedback_likes WHERE user_id=%s AND feedback_id=%s", (current_user_id, fid))
            is_liked = cur.fetchone() is not None
            cur.close()
        feedback_list.append({
            'id': fid,
            'subject': row[1],
            'message': row[2],
            'created_at': row[3],
            'like_count': row[4] if row[4] else 0,
            'official_reply': row[5],
            'official_replied_at': row[6],
            'username': row[7],
            'avatar_url': row[8],
            'user_id': row[9],
            'is_liked': is_liked
        })

    return render_template('feedback.html', feedbacks=feedback_list)


@app.route('/feedback/<int:feedback_id>/like', methods=['POST'])
def toggle_feedback_like(feedback_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id, feedback_id FROM feedback_likes WHERE user_id=%s AND feedback_id=%s",
                (user_id, feedback_id))
    existing = cur.fetchone()
    if existing:
        cur.execute("DELETE FROM feedback_likes WHERE user_id=%s AND feedback_id=%s", (user_id, feedback_id))
        cur.execute("UPDATE user_feedback SET like_count = like_count - 1 WHERE id=%s", (feedback_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({'liked': False, 'count': get_like_count(feedback_id)})
    else:
        cur.execute("INSERT INTO feedback_likes (user_id, feedback_id) VALUES (%s, %s)", (user_id, feedback_id))
        cur.execute("UPDATE user_feedback SET like_count = like_count + 1 WHERE id=%s", (feedback_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({'liked': True, 'count': get_like_count(feedback_id)})


def get_like_count(feedback_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT like_count FROM user_feedback WHERE id=%s", (feedback_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else 0


@app.route('/feedback/<int:feedback_id>/official-reply', methods=['POST'])
@limiter.limit("10 per minute")
def official_feedback_reply(feedback_id):
    if not is_moderator():
        return jsonify({'error': 'Unauthorized'}), 403
    reply_text = request.form.get('reply', '').strip()
    if not reply_text:
        return jsonify({'error': 'Reply cannot be empty'}), 400
    cur = mysql.connection.cursor()
    cur.execute("UPDATE user_feedback SET official_reply=%s, official_replied_at=NOW() WHERE id=%s",
                (reply_text, feedback_id))
    mysql.connection.commit()
    cur.execute("""
        SELECT u.email, u.username, f.subject, f.message
        FROM user_feedback f
        JOIN users u ON f.user_id = u.id
        WHERE f.id = %s
    """, (feedback_id,))
    row = cur.fetchone()
    cur.close()
    if row:
        email, username, subject, message = row
        if email:
            html_body = make_feedback_reply_email(username, subject, message, reply_text)
            send_email_notification(
                "DocoDive replied to your suggestion!",
                email,
                f"Hi {username}, the DocoDive team has replied to your suggestion '{subject}'.",
                html_body=html_body
            )
    return jsonify({'success': True})


@app.route('/feedback/<int:feedback_id>/official-reply/edit', methods=['POST'])
def edit_official_reply(feedback_id):
    if not is_moderator():
        return jsonify({'error': 'Unauthorized'}), 403
    new_reply = request.form.get('reply', '').strip()
    if not new_reply:
        return jsonify({'error': 'Reply cannot be empty'}), 400
    cur = mysql.connection.cursor()
    cur.execute("UPDATE user_feedback SET official_reply=%s, official_replied_at=NOW() WHERE id=%s",
                (new_reply, feedback_id))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})


@app.route('/feedback/<int:feedback_id>/official-reply/delete', methods=['POST'])
def delete_official_reply(feedback_id):
    if not is_moderator():
        return jsonify({'error': 'Unauthorized'}), 403
    cur = mysql.connection.cursor()
    cur.execute("UPDATE user_feedback SET official_reply=NULL, official_replied_at=NULL WHERE id=%s", (feedback_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})


@app.route('/feedback/<int:feedback_id>/reply', methods=['POST'])
def add_feedback_reply(feedback_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    message = request.form.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Reply cannot be empty'}), 400
    user_id = session['user_id']
    try:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO feedback_replies (feedback_id, user_id, message) VALUES (%s, %s, %s)",
                    (feedback_id, user_id, message))
        mysql.connection.commit()
        reply_id = cur.lastrowid
        cur.close()
        return jsonify({'success': True, 'reply_id': reply_id})
    except Exception as e:
        app.logger.error(f"Reply insert failed: {e}")
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/feedback/reply/<int:reply_id>/like', methods=['POST'])
def toggle_reply_like(reply_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id, reply_id FROM reply_likes WHERE user_id=%s AND reply_id=%s",
                (user_id, reply_id))
    existing = cur.fetchone()
    if existing:
        cur.execute("DELETE FROM reply_likes WHERE user_id=%s AND reply_id=%s", (user_id, reply_id))
        mysql.connection.commit()
        liked = False
    else:
        cur.execute("INSERT INTO reply_likes (user_id, reply_id) VALUES (%s, %s)", (user_id, reply_id))
        mysql.connection.commit()
        liked = True
    cur.execute("SELECT COUNT(*) FROM reply_likes WHERE reply_id=%s", (reply_id,))
    count = cur.fetchone()[0]
    cur.close()
    return jsonify({'liked': liked, 'count': count})


@app.route('/feedback/<int:feedback_id>/edit', methods=['POST'])
def edit_feedback(feedback_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    new_message = request.form.get('message', '').strip()
    if not new_message:
        return jsonify({'error': 'Message cannot be empty'}), 400
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM user_feedback WHERE id=%s", (feedback_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({'error': 'Feedback not found'}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({'error': 'Unauthorized'}), 403
    cur.execute("UPDATE user_feedback SET message=%s WHERE id=%s", (new_message, feedback_id))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})


@app.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
def delete_feedback(feedback_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM user_feedback WHERE id=%s", (feedback_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({'error': 'Feedback not found'}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({'error': 'Unauthorized'}), 403
    cur.execute("DELETE FROM user_feedback WHERE id=%s", (feedback_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})


@app.route('/feedback/reply/<int:reply_id>/edit', methods=['POST'])
def edit_reply(reply_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    new_message = request.form.get('message', '').strip()
    if not new_message:
        return jsonify({'error': 'Message cannot be empty'}), 400
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM feedback_replies WHERE id=%s", (reply_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({'error': 'Reply not found'}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({'error': 'Unauthorized'}), 403
    cur.execute("UPDATE feedback_replies SET message=%s WHERE id=%s", (new_message, reply_id))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})


@app.route('/feedback/reply/<int:reply_id>/delete', methods=['POST'])
def delete_reply(reply_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id FROM feedback_replies WHERE id=%s", (reply_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({'error': 'Reply not found'}), 404
    if str(row[0]) != str(user_id) and not is_moderator():
        cur.close()
        return jsonify({'error': 'Unauthorized'}), 403
    cur.execute("DELETE FROM feedback_replies WHERE id=%s", (reply_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})


@app.route('/api/feedback/<int:feedback_id>/replies')
def get_feedback_replies(feedback_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.id, r.message, r.created_at, u.username, u.avatar_url, u.id as user_id,
               (SELECT COUNT(*) FROM reply_likes WHERE reply_id = r.id) as like_count
        FROM feedback_replies r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.feedback_id = %s
        ORDER BY r.created_at ASC
    """, (feedback_id,))
    rows = cur.fetchall()
    cur.close()

    current_user_id = session.get('user_id')
    replies = []
    for row in rows:
        rid = row[0]
        is_liked = False
        if current_user_id:
            cur = mysql.connection.cursor()
            cur.execute("SELECT 1 FROM reply_likes WHERE user_id=%s AND reply_id=%s", (current_user_id, rid))
            is_liked = cur.fetchone() is not None
            cur.close()
        replies.append({
            'id': rid,
            'message': row[1],
            'created_at': str(row[2]),
            'username': row[3],
            'avatar_url': row[4],
            'user_id': row[5],
            'like_count': row[6] if row[6] else 0,
            'is_liked': is_liked
        })
    return jsonify(replies)


# ================== FEEDBACK EMAIL TEMPLATES ==================
def make_feedback_notification_email(username, subject, message):
    feedback_url = url_for('user_feedback', _external=True)
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
        content
    )


def make_feedback_reply_email(username, subject, message, official_reply):
    feedback_url = url_for('user_feedback', _external=True)
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
        content
    )

# ================== NEWSLETTER SUBSCRIBE ==================
@app.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    email = request.form.get('email', '').strip()
    next_url = request.form.get('next', url_for('home'))

    if not email:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Please enter your email.'}), 400
        flash('Please enter your email.', 'danger')
        return redirect(next_url)

    if not is_valid_email(email):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Please enter a valid email address.'}), 400
        flash('Please enter a valid email address.', 'danger')
        return redirect(next_url)

    try:
        sync_brevo_contact(email, 'DocoDive', 'Subscriber')
        success = True
    except Exception as e:
        app.logger.error(f"Newsletter subscribe failed: {e}")
        success = False

    if not success:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Something went wrong. Please try again.'}), 500
        flash('Something went wrong. Please try again.', 'danger')
        return redirect(next_url)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': '✅ Subscribed! Check your inbox for updates.'})

    flash('✅ Subscribed! You will now receive updates about new books.', 'success')
    return redirect(next_url)


# ================== USER NOTIFICATION PREFERENCES ==================
@app.route('/user/preferences', methods=['GET', 'POST'])
def user_preferences():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    user_id = session['user_id']

    if request.method == 'POST':
        notify_new_books = '1' if request.form.get('notify_new_books') else '0'
        favorite_categories = request.form.getlist('favorite_categories')
        email_frequency = request.form.get('email_frequency', 'weekly')

        if email_frequency not in ('daily', 'weekly', 'off'):
            email_frequency = 'weekly'

        categories_json = json.dumps(favorite_categories)

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO user_preferences (user_id, notify_new_books, favorite_categories, email_frequency)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                notify_new_books = VALUES(notify_new_books),
                favorite_categories = VALUES(favorite_categories),
                email_frequency = VALUES(email_frequency)
        """, (user_id, notify_new_books, categories_json, email_frequency))
        mysql.connection.commit()
        cur.close()

        flash('✅ Notification preferences saved successfully!', 'success')
        return redirect(url_for('user_preferences'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT notify_new_books, favorite_categories, email_frequency
        FROM user_preferences
        WHERE user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    cur.close()

    if row:
        pref = {
            'notify_new_books': bool(row[0]),
            'favorite_categories': json.loads(row[1]) if row[1] else [],
            'email_frequency': row[2] or 'weekly'
        }
    else:
        pref = {
            'notify_new_books': True,
            'favorite_categories': [],
            'email_frequency': 'weekly'
        }

    cur = mysql.connection.cursor()
    cur.execute("SELECT level FROM categories ORDER BY level")
    categories = [r[0] for r in cur.fetchall()]
    cur.close()

    return render_template('preferences.html', pref=pref, categories=categories)


# ================== USER PROFILE ==================
@app.route('/user/profile/<username>')
def user_profile(username):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, username, email, verified, created_at, avatar_url, bio, social_links, first_name, last_name
        FROM users WHERE username = %s
    """, (username,))
    user = cur.fetchone()
    if not user:
        cur.close()
        abort(404)
    uid = user[0]

    official_user_id = get_site_setting('official_user_id')
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

    return render_template('user_profile.html', user=user, total_uploads=total_uploads,
                           total_reviews=total_reviews, total_favorites=total_favorites,
                           total_points=total_points, social_links=social_links_dict, is_official=is_official)


@app.route('/user/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    uid = session['user_id']
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        new_username = request.form.get('username', '').strip()
        bio = request.form.get('bio', '').strip()
        social_links = request.form.get('social_links', '').strip()
        avatar_file = request.files.get('avatar')
        avatar_url = None

        if avatar_file and allowed_image_file(avatar_file.filename):
            avatar_data = avatar_file.read()
            avatar_data = compress_image(avatar_data, max_size=(200, 200), quality=80)
            avatar_key = generate_r2_key('avatars', f'user_{uid}', '.jpg')
            try:
                avatar_url = upload_to_r2(avatar_data, avatar_key, content_type='image/jpeg')
            except Exception:
                flash('Avatar upload failed.', 'danger')
                return redirect(url_for('edit_profile'))

        cur = mysql.connection.cursor()

        if new_username and new_username != session.get('user_name'):
            cur.execute("SELECT id FROM users WHERE username = %s AND id != %s", (new_username, uid))
            if cur.fetchone():
                cur.close()
                flash('Username already taken. Please choose another.', 'danger')
                return redirect(url_for('edit_profile'))
            cur.execute("SELECT username_changed_at FROM users WHERE id = %s", (uid,))
            last_changed = cur.fetchone()[0]
            if last_changed and (datetime.utcnow() - last_changed).days < 30:
                cur.close()
                flash('You can change your username only once every 30 days.', 'danger')
                return redirect(url_for('edit_profile'))
            cur.execute("UPDATE users SET username = %s, username_changed_at = NOW() WHERE id = %s", (new_username, uid))
            mysql.connection.commit()
            session['user_name'] = new_username
            full_name = (first_name + ' ' + last_name).strip()
            session['user_display_name'] = full_name or new_username

        cur.execute("""
            UPDATE users
            SET first_name = %s, last_name = %s, bio = %s, social_links = %s,
                avatar_url = COALESCE(%s, avatar_url)
            WHERE id = %s
        """, (first_name, last_name, bio, social_links, avatar_url, uid))
        mysql.connection.commit()
        cur.close()

        full_name = (first_name + ' ' + last_name).strip()
        session['user_display_name'] = full_name or session.get('user_name')
        if avatar_url:
            session['avatar_url'] = avatar_url

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('user_profile', username=session.get('user_name')))

    cur = mysql.connection.cursor()
    cur.execute("SELECT first_name, last_name, bio, social_links, avatar_url FROM users WHERE id = %s", (uid,))
    row = cur.fetchone()
    cur.close()
    profile = {'first_name': row[0] or '', 'last_name': row[1] or '', 'bio': row[2] or '',
               'social_links': row[3] or '', 'avatar_url': row[4] or ''}
    return render_template('edit_profile.html', profile=profile)


# ================== USER STATS API ==================
@app.route('/api/user-stats')
def user_stats_api():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents WHERE uploaded_by = %s", (user_id,))
    uploads = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM book_comments WHERE user_id = %s", (user_id,))
    comments = cur.fetchone()[0]
    cur.execute("SELECT SUM(points) FROM user_points WHERE user_id = %s", (user_id,))
    points = cur.fetchone()[0] or 0
    cur.close()
    return jsonify({"uploads": uploads, "comments": comments, "points": points})


# ================== NOTIFICATIONS PAGE ==================
@app.route('/user/notifications')
def user_notifications():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, message, link, is_read, created_at, type, metadata
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session['user_id'],))
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
            "type": row[5] or 'info',
            "metadata": json.loads(row[6]) if row[6] else {}
        }
        if notif['type'] in ('approval', 'rejection'):
            uid = notif['metadata'].get('uploader_id')
            if uid:
                cur = mysql.connection.cursor()
                cur.execute("SELECT avatar_url FROM users WHERE id = %s", (uid,))
                av = cur.fetchone()
                cur.close()
                notif['avatar_url'] = av[0] if av else None
                notif['is_official_actor'] = is_official_user(uid)
            else:
                notif['avatar_url'] = None
                notif['is_official_actor'] = False
        elif notif['type'] in ('general_comment', 'reply'):
            uid = notif['metadata'].get('actor_user_id')
            if uid:
                cur = mysql.connection.cursor()
                cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (uid,))
                user = cur.fetchone()
                cur.close()
                notif['actor_name'] = user[0] if user else 'Unknown'
                notif['avatar_url'] = user[1] if user else None
                notif['is_official_actor'] = is_official_user(uid)
            else:
                notif['actor_name'] = 'Someone'
                notif['avatar_url'] = None
                notif['is_official_actor'] = False
        else:
            notif['avatar_url'] = None
            notif['is_official_actor'] = False

        enriched.append(notif)

    return render_template('notifications.html', notifications=enriched)


# ================== NOTIFICATIONS API ==================
@app.route('/api/notifications/unread-count')
def unread_notification_count():
    if 'user_id' not in session:
        return jsonify({"count": 0})
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=0", (session['user_id'],))
    count = cur.fetchone()[0]
    cur.close()
    return jsonify({"count": count})


@app.route('/api/notifications')
def get_notifications():
    if 'user_id' not in session:
        return jsonify([])
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, message, link, is_read, created_at, type, metadata
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC LIMIT 20
    """, (session['user_id'],))
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
            "type": row[5] or 'info',
            "metadata": json.loads(row[6]) if row[6] else {}
        }
        if notif['type'] in ('approval', 'rejection'):
            uploader_id = notif['metadata'].get('uploader_id')
            if uploader_id:
                cur = mysql.connection.cursor()
                cur.execute("SELECT avatar_url FROM users WHERE id = %s", (uploader_id,))
                img = cur.fetchone()
                cur.close()
                notif['image_url'] = img[0] if img else None
                notif['is_official_actor'] = is_official_user(uploader_id)
            else:
                notif['image_url'] = None
                notif['is_official_actor'] = False
        elif notif['type'] in ('general_comment', 'reply'):
            actor_id = notif['metadata'].get('actor_user_id')
            if actor_id:
                cur = mysql.connection.cursor()
                cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (actor_id,))
                user = cur.fetchone()
                cur.close()
                notif['actor_name'] = user[0] if user else 'Unknown'
                notif['actor_avatar'] = user[1] if user and user[1] else None
                notif['is_official_actor'] = is_official_user(actor_id)
            else:
                notif['actor_name'] = 'Someone'
                notif['actor_avatar'] = None
                notif['is_official_actor'] = False
        else:
            notif['is_official_actor'] = False

        result.append(notif)

    return jsonify(result)


@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
def mark_notification_read(notif_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    cur = mysql.connection.cursor()
    cur.execute("UPDATE notifications SET is_read=1 WHERE id=%s AND user_id=%s", (notif_id, session['user_id']))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


@app.route('/api/notifications/<int:notif_id>/delete', methods=['POST'])
def delete_notification(notif_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM notifications WHERE id=%s AND user_id=%s", (notif_id, session['user_id']))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True})


# ================== LEADERBOARD ==================
@app.route('/leaderboard')
def leaderboard():
    official_user_id = get_site_setting('official_user_id')

    cur = mysql.connection.cursor()
    if official_user_id:
        cur.execute("""
            SELECT u.id, u.username, u.first_name, u.last_name, u.avatar_url, SUM(up.points) AS total_points
            FROM user_points up
            JOIN users u ON up.user_id = u.id
            WHERE u.id != %s
            GROUP BY u.id
            ORDER BY total_points DESC
            LIMIT 50
        """, (official_user_id,))
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
        full_name = ((row[2] or '') + ' ' + (row[3] or '')).strip()
        if not full_name:
            full_name = row[1]
        leaderboard.append({
            'user_id': row[0],
            'username': row[1],
            'name': full_name,
            'avatar_url': row[4],
            'points': row[5],
            'is_official': is_official_user(row[0])
        })

    current_user_rank = None
    current_user_points = 0
    if 'user_id' in session:
        uid = session['user_id']
        cur = mysql.connection.cursor()
        cur.execute("SELECT SUM(points) FROM user_points WHERE user_id = %s", (uid,))
        total = cur.fetchone()[0] or 0
        current_user_points = total

        if official_user_id and str(uid) != official_user_id:
            cur.execute("""
                SELECT COUNT(*) + 1 FROM (
                    SELECT user_id, SUM(points) AS total
                    FROM user_points
                    WHERE user_id != %s
                    GROUP BY user_id
                    HAVING SUM(points) > %s
                ) AS higher
            """, (official_user_id, total))
        else:
            cur.execute("""
                SELECT COUNT(*) + 1 FROM (
                    SELECT user_id, SUM(points) AS total
                    FROM user_points
                    GROUP BY user_id
                    HAVING SUM(points) > %s
                ) AS higher
            """, (total,))
        rank = cur.fetchone()[0]
        current_user_rank = rank
        cur.close()

    return render_template('leaderboard.html',
                           leaderboard=leaderboard,
                           current_user_rank=current_user_rank,
                           current_user_points=current_user_points)


# ================== BOOK COMMENTS ==================
@app.route('/book/<int:book_id>/comments', methods=['GET'])
def get_comments(book_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT c.id, c.comment, c.parent_id, c.created_at, u.username, u.avatar_url, u.id
        FROM book_comments c JOIN users u ON c.user_id = u.id
        WHERE c.book_id = %s ORDER BY c.created_at ASC
    """, (book_id,))
    comments = cur.fetchall()
    cur.close()
    comment_list = [{
        "id": r[0],
        "comment": r[1],
        "parent_id": r[2],
        "created_at": str(r[3]),
        "username": r[4],
        "avatar_url": r[5],
        "user_id": r[6],
        "is_official": is_official_user(r[6])
    } for r in comments]
    return jsonify(comment_list)


@app.route('/book/<int:book_id>/comments', methods=['POST'])
def add_comment(book_id):
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    data = request.get_json()
    comment = data.get('comment', '').strip()
    parent_id = data.get('parent_id')
    if not comment:
        return jsonify({"error": "Comment cannot be empty"}), 400

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO book_comments (book_id, user_id, parent_id, comment) VALUES (%s, %s, %s, %s)",
                (book_id, session['user_id'], parent_id, comment))
    mysql.connection.commit()
    new_comment_id = cur.lastrowid
    cur.close()

    award_points(session['user_id'], 2, book_id)

    if not parent_id:
        cur = mysql.connection.cursor()
        cur.execute("SELECT uploaded_by, title FROM documents WHERE id = %s", (book_id,))
        book_info = cur.fetchone()
        cur.close()
        if book_info and book_info[0] and book_info[0] != session['user_id']:
            uploader_id = book_info[0]
            book_title = book_info[1]
            snippet = comment[:60] + ('...' if len(comment) > 60 else '')
            msg = f'💬 New comment on <em>{book_title}</em><br><small class="text-muted">&ldquo;{snippet}&rdquo;</small>'
            metadata = {"book_id": book_id, "comment_id": new_comment_id, "actor_user_id": session['user_id']}
            create_notification(uploader_id, 'general_comment', msg,
                                url_for('book_detail', book_id=book_id, _anchor='discussion'),
                                metadata)
    else:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT c.user_id, d.title
            FROM book_comments c
            JOIN documents d ON c.book_id = d.id
            WHERE c.id = %s
        """, (parent_id,))
        parent_info = cur.fetchone()
        cur.close()
        if parent_info and parent_info[0] != session['user_id']:
            parent_author_id = parent_info[0]
            book_title = parent_info[1]
            reply_username = session.get('user_name')
            snippet = comment[:60] + ('...' if len(comment) > 60 else '')
            msg = f'<strong>{reply_username}</strong> replied to your comment on <em>{book_title}</em><br><small class="text-muted">&ldquo;{snippet}&rdquo;</small>'
            metadata = {"book_id": book_id, "comment_id": new_comment_id, "parent_comment_id": parent_id, "actor_user_id": session['user_id']}
            create_notification(parent_author_id, 'reply', msg,
                                url_for('book_detail', book_id=book_id, _anchor='discussion'),
                                metadata)

    return jsonify({"success": True})


# ================== NOTIFICATION DIGEST ==================
def _book_matches_categories(book_category, selected_categories):
    if not selected_categories:
        return True
    return book_category in selected_categories


def _send_book_digest_to_user(user, books, digest_type, period_key):
    uid, email = user[0], user[2]
    cur = mysql.connection.cursor()
    cur.execute("SELECT favorite_categories FROM user_preferences WHERE user_id = %s", (uid,))
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
        (uid, digest_type, period_key)
    )
    if cur.fetchone():
        cur.close()
        return False

    book_list = [{
    "id": b[0],
    "title": b[1],
    "author": b[2],
    "category": b[3],
    "description": b[4],
    "image_url": b[5] if len(b) > 5 else None
} for b in matching]
    
    html = make_digest_email(book_list)

    body = "\n".join(f"{b[1]} by {b[2]} ({b[3]})" for b in matching)
    sent = send_email_notification("New books digest - DocoDive", email, body, html_body=html)
    if sent:
        cur.execute(
            "INSERT INTO notification_digest_log (user_id, digest_type, period_key) VALUES (%s, %s, %s)",
            (uid, digest_type, period_key)
        )
        mysql.connection.commit()
    cur.close()
    return sent

def send_daily_book_digest():
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    period_key = now.strftime('%Y-%m-%d')

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.id, u.username, u.email
        FROM user_preferences up
        JOIN users u ON u.id = up.user_id
        WHERE up.notify_new_books = '1' AND up.email_frequency = 'daily'
    """)
    users = cur.fetchall()
    cur.execute("""
        SELECT d.id, d.title, d.author, c.level, d.description
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved_at >= %s
    """, (since,))
    books = cur.fetchall()
    cur.close()

    sent_count = 0
    for user in users:
        if _send_book_digest_to_user(user, books, 'daily', period_key):
            sent_count += 1
    return {"success": True, "digest": "daily", "emails_sent": sent_count}

def send_weekly_book_digest():
    now = datetime.utcnow()
    since = now - timedelta(days=7)
    period_key = now.strftime('%Y-%W')

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.id, u.username, u.email
        FROM user_preferences up
        JOIN users u ON u.id = up.user_id
        WHERE up.notify_new_books = '1' AND up.email_frequency = 'weekly'
    """)
    users = cur.fetchall()
    cur.execute("""
        SELECT d.id, d.title, d.author, c.level, d.description
        FROM documents d JOIN categories c ON d.category_id = c.id
        WHERE d.approved_at >= %s
    """, (since,))
    books = cur.fetchall()
    cur.close()

    sent_count = 0
    for user in users:
        if _send_book_digest_to_user(user, books, 'weekly', period_key):
            sent_count += 1
    return {"success": True, "digest": "weekly", "emails_sent": sent_count}



@app.route('/internal/notification-digest/<digest_type>', methods=['POST'])
def notification_digest(digest_type):
    provided = request.headers.get('X-Cron-Secret', '')
    if not CRON_SECRET or not provided or not hmac.compare_digest(str(CRON_SECRET), str(provided)):
        return jsonify({"error": "Unauthorized"}), 401

    if digest_type == 'daily':
        return jsonify(send_daily_book_digest())
    if digest_type == 'weekly':
        return jsonify(send_weekly_book_digest())
    return jsonify({"error": "Invalid digest type"}), 400

def make_digest_email(books):
    """Build a DocoDive-styled new-books digest email (HTML string)."""

    book_cards = ""
    for book in books:
        image_url = book.get("image_url") or ""
        image_tag = ""
        if image_url:
            image_tag = f'''
                <img src="{_safe(image_url)}" alt="{_safe(book.get('title', 'Book'))}"
                     style="display:block;width:56px;height:70px;object-fit:cover;border-radius:8px;margin-right:14px;" />
            '''

        book_cards += f'''
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
        '''

    return f'''
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
    '''

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
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_digest_scheduler()

    app.run(host="0.0.0.0", port=port, debug=debug)