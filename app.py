import os
import io
import re
import random
import secrets
from datetime import datetime, timedelta
from functools import wraps

from PyPDF2 import PdfReader
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, abort, flash
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Optional AI (new google‑genai package)
try:
    import google.genai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# Optional email
try:
    from flask_mail import Mail, Message
    HAS_MAIL = True
except ImportError:
    HAS_MAIL = False

load_dotenv()

app = Flask(__name__)
app.secret_key = 'docodive_super_secret_key_2026'

app.config['MYSQL_HOST'] = os.getenv('DB_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('DB_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('DB_PASSWORD', 'Root123')
app.config['MYSQL_DB'] = os.getenv('DB_NAME', 'docodive_db')

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf'}
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

mysql = MySQL(app)

# Mail setup
mail = None
if HAS_MAIL:
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    mail = Mail(app)

# Gemini setup (new API client)
genai_client = None
if HAS_GEMINI and os.getenv('GEMINI_API_KEY'):
    genai_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# -------------------- HELPERS --------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_admin_by_username(username):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, password, role FROM admins WHERE username = %s", (username,))
        admin = cur.fetchone()
        cur.close()
        return admin
    except Exception:
        return None

def log_login_attempt(admin_id, ip_address, success):
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO login_logs (admin_id, ip_address, success, timestamp) VALUES (%s, %s, %s, NOW())",
            (admin_id, ip_address, 1 if success else 0)
        )
        mysql.connection.commit()
        cur.close()
    except Exception:
        pass

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def send_email_notification(subject, recipient, body, html_body=None):
    """Send an email with optional HTML content."""
    if not mail or not app.config.get('MAIL_USERNAME'):
        return
    try:
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[recipient])
        msg.body = body
        if html_body:
            msg.html = html_body
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Email failed: {e}")

def is_valid_email(email):
    """Check basic email format and reject common disposable domains."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    disposable = ['mailinator.com', 'tempmail.com', 'throwaway.com', 'guerrillamail.com',
                  'sharklasers.com', '10minutemail.com', 'yopmail.com', 'trashmail.com']
    domain = email.split('@')[1].lower()
    if domain in disposable:
        return False
    return True

def track_download(book_id):
    if 'user_id' in session:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
                    (session['user_id'], book_id))
        mysql.connection.commit()
        cur.close()

# -------------------- NEW ROUTE: USER UPLOAD --------------------
@app.route('/user/upload', methods=['GET', 'POST'])
def user_upload():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for('user_upload'))

        file = request.files['pdf_file']
        if file.filename == '' or not allowed_file(file.filename):
            flash('Invalid file. Only PDF allowed.', 'danger')
            return redirect(url_for('user_upload'))

        pdf_bytes = file.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        meta = reader.metadata
        title = meta.title if meta.title else os.path.splitext(file.filename)[0].replace('_', ' ').strip()
        author = meta.author if meta.author else 'Unknown'
        pdf_text = extract_text_from_pdf(reader)

        category = guess_category(pdf_text)
        description = f"A comprehensive resource about '{title}'. Covers essential topics in {category}."

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(file_path, 'wb') as f:
            f.write(pdf_bytes)
        final_link = f"/{file_path}"

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM categories WHERE level = %s", (category,))
        cat = cur.fetchone()
        if not cat:
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (category,))
            cat_id = cur.lastrowid
        else:
            cat_id = cat[0]

        # Insert with uploaded_by set to the current user's id
        cur.execute("""
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, approved, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s)
        """, (cat_id, title, final_link, author, description, None, 'English', session['user_id']))
        mysql.connection.commit()
        cur.close()

        html_notification = make_upload_notification_email(title, author, category)
        send_email_notification(
            "New PDF Uploaded by User - Pending Approval",
            "7t7sufyan@gmail.com",
            f"A new book '{title}' by {author} has been uploaded by a user and is waiting for approval.",
            html_body=html_notification
        )

        flash(f"✅ '{title}' uploaded successfully! It will appear after admin approval.", 'success')
        return redirect(url_for('user_upload'))

    return render_template('user_upload.html')

@app.route('/api/user/uploads')
def user_uploads():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, title, author, status, created_at
        FROM documents
        WHERE uploaded_by = %s
        ORDER BY created_at DESC
    """, (user_id,))
    books = cur.fetchall()
    cur.close()
    result = [{"id": b[0], "title": b[1], "author": b[2], "status": b[3], "created_at": str(b[4])} for b in books]
    return jsonify(result)

@app.route('/api/user/pending-uploads')
def user_pending_uploads():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, title, author, created_at
        FROM documents
        WHERE uploaded_by = %s AND approved = 0
        ORDER BY created_at DESC
    """, (user_id,))
    books = cur.fetchall()
    cur.close()
    result = [{"id": b[0], "title": b[1], "author": b[2], "created_at": str(b[3])} for b in books]
    return jsonify(result)

# -------------------- API: CHECK USERNAME/EMAIL AVAILABILITY --------------------
@app.route('/api/check-availability')
def check_availability():
    field = request.args.get('field', '')
    value = request.args.get('value', '').strip()

    if not field or not value:
        return jsonify({'error': 'Invalid request'}), 400

    cur = mysql.connection.cursor()
    if field == 'username':
        cur.execute("SELECT id FROM users WHERE username = %s", (value,))
    elif field == 'email':
        cur.execute("SELECT id FROM users WHERE email = %s", (value,))
    else:
        cur.close()
        return jsonify({'error': 'Invalid field'}), 400

    exists = cur.fetchone() is not None
    cur.close()
    return jsonify({'exists': exists})


# -------------------- Keyword-based category detection --------------------
KEYWORDS = {
    'Python': ['import ', 'def ', 'class ', 'print(', 'pandas', 'numpy', 'python'],
    'JavaScript': ['var ', 'const ', 'function', 'document.', 'console.log'],
    'Java': ['public class', 'system.out', 'java'],
    'C / C++': ['#include', 'int main', 'printf', 'cout'],
    'Web Development': ['html', 'css', '<div', 'react', 'angular'],
    'Data Science': ['dataframe', 'scikit', 'matplotlib', 'pandas'],
    'Machine Learning': ['model.fit', 'train_test_split', 'tensorflow', 'keras'],
    'Algorithms': ['algorithm', 'sort', 'complexity', 'big o'],
    'Databases': ['sql', 'query', 'select *', 'mysql', 'postgresql'],
    'Cyber Security': ['encrypt', 'hack', 'firewall', 'penetration'],
    'Mobile Apps': ['android', 'ios', 'swift', 'kotlin', 'flutter'],
    'DevOps': ['docker', 'kubernetes', 'ci/cd', 'terraform', 'jenkins']
}

def extract_text_from_pdf(reader, max_pages=5):
    text = ''
    for page in reader.pages[:max_pages]:
        extracted = page.extract_text()
        if extracted:
            text += extracted
    return text.lower()

def guess_category(text):
    scores = {}
    for cat, kwds in KEYWORDS.items():
        scores[cat] = sum(1 for kw in kwds if kw in text)
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return 'Other'
    return best

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
        response = genai_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        response_text = response.text
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            import json
            data = json.loads(json_match.group())
            return data.get('title', title), data.get('author', author), data.get('description', '')
    except Exception as e:
        app.logger.error(f"AI metadata failed: {e}")
    return title, author, f"A comprehensive resource about '{title}'. Covers essential topics."

# -------------------- FORGOT PASSWORD ROUTES (AJAX version) --------------------
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
        cur.execute("INSERT INTO password_resets (email, code, expires_at) VALUES (%s, %s, %s)",
                    (email, code, expires))
        mysql.connection.commit()
        cur.close()

        html_body = make_code_email(code)
        send_email_notification(
            "Password Reset Code - DocoDive",
            email,
            f"Your verification code is: {code}",
            html_body=html_body
        )

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
    cur.execute("SELECT id, email, code, expires_at FROM password_resets WHERE email = %s AND code = %s",
                (email, code))
    row = cur.fetchone()
    if not row or row[3] < datetime.now():
        cur.close()
        return jsonify({'error': 'Invalid or expired code.'}), 400

    token = secrets.token_urlsafe(32)
    new_expires = datetime.now() + timedelta(minutes=30)
    cur.execute("UPDATE password_resets SET token = %s, code = NULL, expires_at = %s WHERE id = %s",
                (token, new_expires, row[0]))
    mysql.connection.commit()
    cur.close()

    reset_link = url_for('reset_password', token=token, _external=True)
    html_body = make_reset_link_email(reset_link)
    send_email_notification(
        "Reset Your Password - DocoDive",
        email,
        f"Click the link to reset your password: {reset_link}",
        html_body=html_body
    )

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

# -------------------- EMAIL TEMPLATES --------------------
def make_verification_email(username, verify_link):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Poppins', Arial, sans-serif; background: #f8faff; margin:0; padding:20px; }}
            .container {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; }}
            .header {{ background: linear-gradient(135deg, #4338ca, #818cf8); padding: 30px 20px; text-align: center; color: white; }}
            .header h1 {{ margin:0; font-size: 28px; font-weight: 800; }}
            .header p {{ margin:10px 0 0; opacity:0.9; }}
            .body {{ padding: 30px 25px; color: #1e1b4b; }}
            .button {{ display: inline-block; background: #ffb703; color: #1e1b4b; text-decoration: none; padding: 14px 36px; border-radius: 50px; font-weight: 700; font-size: 16px; margin: 20px 0; transition: 0.3s; }}
            .button:hover {{ background: #e6a800; transform: translateY(-2px); }}
            .link {{ word-break: break-all; color: #4338ca; font-size: 13px; }}
            .footer {{ background: #f8f9fc; text-align: center; padding: 20px; font-size: 13px; color: #888; border-top: 1px solid #eee; }}
            .social {{ margin-top: 10px; }}
            .social a {{ display: inline-block; margin: 0 6px; width: 32px; height: 32px; background: #e0e7ff; border-radius: 50%; text-align: center; line-height: 32px; color: #4338ca; text-decoration: none; font-size: 16px; transition: 0.2s; }}
            .social a:hover {{ background: #ffb703; color: #1e1b4b; }}
    </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📚 DocoDive</h1>
                <p>Verify your email to start reading!</p>
            </div>
            <div class="body">
                <h2 style="margin-top:0;">Hi {username},</h2>
                <p>Thank you for joining DocoDive, your premium programming library. Click the button below to verify your email address and unlock 500+ free books.</p>
                <a href="{verify_link}" class="button">Verify Email Now</a>
                <p style="margin-top: 20px; font-size: 14px;">If the button doesn’t work, copy and paste this link into your browser:</p>
                <p class="link">{verify_link}</p>
            </div>
            <div class="footer">
                <p>Connect with us</p>
                <div class="social">
                    <a href="https://github.com/programmingpioneer" target="_blank" title="GitHub"><i class="bi bi-github" style="font-style:normal;">🐙</i></a>
                    <a href="https://www.linkedin.com/in/sufyan-khans/" target="_blank" title="LinkedIn"><i class="bi bi-linkedin" style="font-style:normal;">💼</i></a>
                    <a href="https://x.com/programerPioner" target="_blank" title="X"><i class="bi bi-twitter-x" style="font-style:normal;">𝕏</i></a>
                    <a href="https://www.instagram.com/programmingpioneer/" target="_blank" title="Instagram"><i class="bi bi-instagram" style="font-style:normal;">📷</i></a>
                    <a href="https://www.facebook.com/Programmingpioneer" target="_blank" title="Facebook"><i class="bi bi-facebook" style="font-style:normal;">📘</i></a>
                    <a href="https://t.me/Programmingpioneers" target="_blank" title="Telegram"><i class="bi bi-telegram" style="font-style:normal;">✈️</i></a>
                </div>
                <p style="margin-top: 15px;">© 2026 DocoDive – Free Knowledge, Pure Discipline.</p>
            </div>
        </div>
    </body>
    </html>
    """

def make_upload_notification_email(title, author, category):
    pending_url = url_for('pending_books', _external=True)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Poppins', Arial, sans-serif; background: #f8faff; padding:20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: #fff; border-radius: 18px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); padding: 30px; }}
            h2 {{ color: #1e1b4b; margin-top:0; }}
            p {{ color: #333; }}
            .details {{ background: #f0f4ff; padding: 15px; border-radius: 12px; margin: 15px 0; }}
            .button {{ display: inline-block; background: #4338ca; color: #fff; text-decoration: none; padding: 12px 28px; border-radius: 50px; font-weight: 600; }}
            .button:hover {{ background: #312e81; }}
            .footer {{ margin-top: 25px; font-size: 12px; color: #999; text-align: center; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h2>📥 New PDF Uploaded</h2>
            <p>A new book has been submitted and is awaiting your approval.</p>
            <div class="details">
                <strong>Title:</strong> {title}<br>
                <strong>Author:</strong> {author}<br>
                <strong>Category:</strong> {category}
            </div>
            <a href="{pending_url}" class="button">Review Pending Books</a>
            <div class="footer">DocoDive · Free Knowledge, Pure Discipline</div>
        </div>
    </body>
    </html>
    """

def make_code_email(code):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Poppins', Arial, sans-serif; background: #f8faff; padding:20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: #fff; border-radius: 18px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); padding: 30px; text-align: center; }}
            h2 {{ color: #1e1b4b; }}
            .code {{ display: inline-block; font-size: 48px; font-weight: 800; letter-spacing: 12px; color: #4338ca; background: #e0e7ff; padding: 15px 30px; border-radius: 16px; margin: 20px 0; }}
            .note {{ color: #666; font-size: 14px; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #999; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h2>🔐 Password Reset Code</h2>
            <p>Enter this 4-digit code in the verification box to reset your password:</p>
            <div class="code">{code}</div>
            <p class="note">This code expires in 10 minutes.</p>
            <div class="footer">DocoDive · Free Knowledge, Pure Discipline</div>
        </div>
    </body>
    </html>
    """

def make_reset_link_email(reset_link):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Poppins', Arial, sans-serif; background: #f8faff; padding:20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: #fff; border-radius: 18px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); padding: 30px; text-align: center; }}
            h2 {{ color: #1e1b4b; }}
            .button {{ display: inline-block; background: #4338ca; color: #fff; text-decoration: none; padding: 14px 32px; border-radius: 50px; font-weight: 700; margin: 20px 0; }}
            .button:hover {{ background: #312e81; }}
            .link {{ word-break: break-all; color: #4338ca; font-size: 13px; margin-top: 10px; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #999; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h2>🔗 Reset Your Password</h2>
            <p>Click the button below to set a new password. The link is valid for 30 minutes.</p>
            <a href="{reset_link}" class="button">Reset Password</a>
            <p class="link">If the button doesn’t work, copy and paste this link:</p>
            <p class="link">{reset_link}</p>
            <div class="footer">DocoDive · Free Knowledge, Pure Discipline</div>
        </div>
    </body>
    </html>
    """

def make_approval_email(title, status, message):
    """HTML email for book approval/rejection notification to the uploader."""
    color = "#10b981" if status == "approved" else "#ef4444"
    emoji = "✅" if status == "approved" else "❌"
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Poppins', Arial, sans-serif; background: #f8faff; padding:20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: #fff; border-radius: 18px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); padding: 30px; text-align: center; }}
            h2 {{ color: #1e1b4b; }}
            .status {{ font-size: 24px; font-weight: 700; color: {color}; margin: 20px 0; }}
            .details {{ background: #f0f4ff; padding: 15px; border-radius: 12px; margin: 15px 0; }}
            .button {{ display: inline-block; background: #4338ca; color: #fff; text-decoration: none; padding: 12px 28px; border-radius: 50px; font-weight: 600; }}
            .button:hover {{ background: #312e81; }}
            .social {{ margin-top: 20px; }}
            .social a {{ display: inline-block; margin: 0 6px; width: 32px; height: 32px; background: #e0e7ff; border-radius: 50%; text-align: center; line-height: 32px; color: #4338ca; text-decoration: none; font-size: 16px; }}
            .social a:hover {{ background: #ffb703; color: #1e1b4b; }}
            .footer {{ margin-top: 25px; font-size: 12px; color: #999; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h2>{emoji} Book {status.capitalize()}</h2>
            <div class="status">{message}</div>
            <div class="details">
                <strong>Title:</strong> {title}<br>
                <strong>Status:</strong> {status.capitalize()}
            </div>
            <p>Thank you for contributing to DocoDive.</p>
            <a href="{url_for('home', _external=True)}" class="button">Visit Library</a>
            <div class="social">
                <a href="https://github.com/programmingpioneer" target="_blank" title="GitHub">🐙</a>
                <a href="https://www.linkedin.com/in/sufyan-khans/" target="_blank" title="LinkedIn">💼</a>
                <a href="https://x.com/programerPioner" target="_blank" title="X">𝕏</a>
                <a href="https://www.instagram.com/programmingpioneer/" target="_blank" title="Instagram">📷</a>
                <a href="https://www.facebook.com/Programmingpioneer" target="_blank" title="Facebook">📘</a>
                <a href="https://t.me/Programmingpioneers" target="_blank" title="Telegram">✈️</a>
            </div>
            <div class="footer">DocoDive · Free Knowledge, Pure Discipline</div>
        </div>
    </body>
    </html>
    """

# -------------------- ERROR HANDLERS --------------------
@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    return jsonify({"error": "File size too large. Maximum 500 MB allowed."}), 413

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

# -------------------- LOGIN / LOGOUT (ADMIN) --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('home'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        admin_record = get_admin_by_username(username)
        if admin_record and check_password_hash(admin_record[2], password):
            session['logged_in'] = True
            session['admin_id'] = admin_record[0]
            session['admin_role'] = admin_record[3]
            log_login_attempt(admin_record[0], request.remote_addr, True)
            return redirect(url_for('home'))
        else:
            error = "Invalid credentials."
            log_login_attempt(admin_record[0] if admin_record else 0, request.remote_addr, False)

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# -------------------- PUBLIC ROUTES (locked) --------------------
@app.route('/')
def home():
    if not session.get('user_id') and not session.get('logged_in'):
        return redirect(url_for('user_login'))

    search_query = request.args.get('search_query', '').strip()
    category = request.args.get('category', '').strip()
    author_filter = request.args.get('author', '').strip()
    lang_filter = request.args.get('language', '').strip()
    page = request.args.get('page', 1, type=int)
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

    books_query = f"""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE {where_clause}
        ORDER BY d.id DESC
        LIMIT %s OFFSET %s
    """
    cur.execute(books_query, params + [per_page, offset])
    books_data = cur.fetchall()

    cur.execute("""
        SELECT c.id, c.level, COUNT(d.id) AS total
        FROM categories c
        LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1
        GROUP BY c.id
        ORDER BY c.id
    """)
    cat_data = cur.fetchall()
    cur.close()

    real_pdfs = [
        {
            "id": r[0], "title": r[1], "level": r[2], "link": r[3],
            "author": r[4], "description": r[5], "image_url": r[6], "language": r[7]
        } for r in books_data
    ]

    categories = [
        {"id": r[0], "level": r[1], "count": r[2]} for r in cat_data
    ]

    return render_template('index.html',
                           pdfs=real_pdfs,
                           search_query=search_query,
                           category=category,
                           author_filter=author_filter,
                           lang_filter=lang_filter,
                           categories=categories,
                           page=page,
                           total_pages=total_pages)

# -------------------- BOOK DETAIL (with reviews) --------------------
@app.route('/book/<int:book_id>')
def book_detail(book_id):
    if not session.get('user_id') and not session.get('logged_in'):
        return redirect(url_for('user_login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE d.id = %s AND d.approved = 1
    """, (book_id,))
    book = cur.fetchone()
    if not book:
        cur.close()
        abort(404)

    cur.execute("""
        SELECT u.username, r.rating, r.comment, r.created_at
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s
        ORDER BY r.created_at DESC
    """, (book_id,))
    reviews = cur.fetchall()
    cur.close()

    book_data = {
        "id": book[0], "title": book[1], "level": book[2], "link": book[3],
        "author": book[4], "description": book[5], "image_url": book[6], "language": book[7]
    }
    return render_template('book_detail.html', book=book_data, reviews=reviews)

# -------------------- SEARCH AUTOCOMPLETE --------------------
@app.route('/api/search/suggest')
def search_suggest():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, title FROM documents WHERE title LIKE %s AND approved = 1 ORDER BY title LIMIT 8",
                (f'%{q}%',))
    results = cur.fetchall()
    cur.close()
    return jsonify([{"id": r[0], "title": r[1]} for r in results])

# -------------------- API: BOOK DETAIL FOR MODAL --------------------
@app.route('/api/book/<int:book_id>')
def api_book_detail(book_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE d.id = %s AND d.approved = 1
    """, (book_id,))
    book = cur.fetchone()
    if not book:
        cur.close()
        return jsonify({"error": "Book not found"}), 404

    cur.execute("""
        SELECT u.username, r.rating, r.comment, r.created_at
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s
        ORDER BY r.created_at DESC
    """, (book_id,))
    reviews = cur.fetchall()

    is_fav = False
    if 'user_id' in session:
        cur.execute("SELECT id FROM favorites WHERE user_id = %s AND book_id = %s",
                    (session['user_id'], book_id))
        is_fav = cur.fetchone() is not None

    cur.close()

    book_data = {
        "id": book[0],
        "title": book[1],
        "level": book[2],
        "link": book[3],
        "author": book[4],
        "description": book[5],
        "image_url": book[6],
        "language": book[7],
        "reviews": [{"username": r[0], "rating": r[1], "comment": r[2], "created_at": str(r[3])} for r in reviews],
        "is_favorite": is_fav,
        "is_logged_in": 'user_id' in session
    }
    return jsonify(book_data)

# -------------------- USER ACCOUNTS --------------------
@app.route('/user/signup', methods=['GET', 'POST'])
def user_signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            return render_template('auth.html', mode='signup', error='All fields are required.')

        if not is_valid_email(email):
            return render_template('auth.html', mode='signup', error='Please enter a valid email address.')

        if len(username) < 3 or len(username) > 20 or not username.isalnum():
            return render_template('auth.html', mode='signup', error='Username must be 3-20 letters and numbers only.')

        if len(password) < 6:
            return render_template('auth.html', mode='signup', error='Password must be at least 6 characters.')

        hashed = generate_password_hash(password)
        token = secrets.token_urlsafe(32)

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cur.fetchone():
            cur.close()
            return render_template('auth.html', mode='signup', error='Username or email already exists.')

        cur.execute("INSERT INTO users (username, email, password, verification_token) VALUES (%s, %s, %s, %s)",
                    (username, email, hashed, token))
        mysql.connection.commit()
        cur.close()

        verify_link = url_for('verify_email', token=token, _external=True)
        html_body = make_verification_email(username, verify_link)
        send_email_notification(
            "Verify your email - DocoDive",
            email,
            "Please view this email in HTML format to see the verification button.",
            html_body=html_body
        )

        flash('Account created! Please check your email to verify.', 'success')
        return redirect(url_for('user_login'))

    return render_template('auth.html', mode='signup')

@app.route('/user/login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, password, verified FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user[2], password):
            if not user[3]:
                return render_template('auth.html', mode='login', error='Please verify your email first. Check your inbox.')
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            return redirect(url_for('home'))
        else:
            return render_template('auth.html', mode='login', error='Invalid email or password.')
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
        flash('Invalid or expired verification link.', 'danger')
    return redirect(url_for('user_login'))

@app.route('/user/logout')
def user_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    return redirect(url_for('home'))

# -------------------- FAVORITES & HISTORY --------------------
@app.route('/user/favorites')
def user_favorites():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, c.level, d.telegram_link, d.author, d.description, d.image_url, d.language
        FROM favorites f
        JOIN documents d ON f.book_id = d.id
        JOIN categories c ON d.category_id = c.id
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
        FROM download_history h
        JOIN documents d ON h.book_id = d.id
        JOIN categories c ON d.category_id = c.id
        WHERE h.user_id = %s
        ORDER BY h.downloaded_at DESC
    """, (session['user_id'],))
    books = cur.fetchall()
    cur.close()
    real_pdfs = [{"id": r[0], "title": r[1], "level": r[2], "link": r[3],
                   "author": r[4], "description": r[5], "image_url": r[6], "language": r[7],
                   "downloaded_at": str(r[8])} for r in books]
    return render_template('user_history.html', pdfs=real_pdfs)

# -------------------- DOWNLOAD TRACKING --------------------
@app.route('/api/download/<int:book_id>', methods=['POST'])
def track_download_route(book_id):
    if 'user_id' in session:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO download_history (user_id, book_id) VALUES (%s, %s)",
                    (session['user_id'], book_id))
        mysql.connection.commit()
        cur.close()
    return jsonify({'success': True})

# -------------------- REVIEWS --------------------
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
    return jsonify({"success": True})

# -------------------- READ ONLINE --------------------
@app.route('/book/<int:book_id>/read')
def read_online(book_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT telegram_link FROM documents WHERE id = %s AND approved = 1", (book_id,))
    book = cur.fetchone()
    cur.close()
    if not book:
        abort(404)
    return render_template('read_online.html', pdf_url=book[0])

# -------------------- ADMIN UPLOAD (AI optional) --------------------
@app.route('/admin', methods=['GET', 'POST'])
@admin_required
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
        title = meta.title if meta.title else os.path.splitext(file.filename)[0].replace('_', ' ').strip()
        author = meta.author if meta.author else 'Unknown'
        pdf_text = extract_text_from_pdf(reader)

        if genai_client:
            title, author, description = ai_enhance_metadata(title, author, pdf_text)
        else:
            category = guess_category(pdf_text)
            description = f"A comprehensive resource about '{title}'. Covers essential topics in {category}."
            category = guess_category(pdf_text)

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(file_path, 'wb') as f:
            f.write(pdf_bytes)
        final_link = f"/{file_path}"

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM categories WHERE level = %s", (category,))
        cat = cur.fetchone()
        if not cat:
            cur.execute("INSERT INTO categories (level) VALUES (%s)", (category,))
            cat_id = cur.lastrowid
        else:
            cat_id = cat[0]

        # Admin upload: uploaded_by is NULL (default)
        cur.execute("""
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, approved)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
        """, (cat_id, title, final_link, author, description, None, 'English'))
        mysql.connection.commit()
        cur.close()

        html_notification = make_upload_notification_email(title, author, category)
        send_email_notification(
            "New PDF Uploaded - Pending Approval",
            "7t7sufyan@gmail.com",
            f"A new book '{title}' by {author} has been uploaded and is waiting for approval.",
            html_body=html_notification
        )

        return jsonify({
            "success": True,
            "title": title,
            "category": category,
            "message": f"Book '{title}' uploaded in {category}! Waiting for approval."
        })

    return render_template('admin.html')

# -------------------- APPROVAL ROUTES --------------------
@app.route('/admin/pending')
@admin_required
def pending_books():
    if session.get('admin_role') != 'super':
        return redirect(url_for('admin_dashboard'))
    cur = mysql.connection.cursor()
    # Added telegram_link for preview
    cur.execute("""
        SELECT d.id, d.title, c.level, d.author, d.created_at, d.telegram_link
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE d.approved = 0
        ORDER BY d.id DESC
    """)
    books = cur.fetchall()
    cur.close()
    books_list = [{"id": b[0], "title": b[1], "level": b[2], "author": b[3],
                   "created_at": str(b[4]) if b[4] else '', "link": b[5]} for b in books]
    return render_template('pending.html', books=books_list)

@app.route('/admin/approve/<int:book_id>', methods=['POST'])
@admin_required
def approve_book(book_id):
    if session.get('admin_role') != 'super':
        return jsonify({"error": "Only super admin can approve."}), 403
    cur = mysql.connection.cursor()
    # Get title and uploader id
    cur.execute("SELECT title, uploaded_by FROM documents WHERE id = %s", (book_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Book not found"}), 404
    title, uploader_id = row

    cur.execute("UPDATE documents SET approved = 1 WHERE id = %s", (book_id,))
    mysql.connection.commit()

    # Send email to uploader if exists
    if uploader_id:
        cur.execute("SELECT email, username FROM users WHERE id = %s", (uploader_id,))
        user = cur.fetchone()
        if user:
            html = make_approval_email(title, "approved", "Your book has been approved and is now live!")
            send_email_notification(
                "Book Approved - DocoDive",
                user[0],
                f"Your book '{title}' has been approved.",
                html_body=html
            )
    cur.close()
    return jsonify({"success": True})

@app.route('/admin/reject/<int:book_id>', methods=['POST'])
@admin_required
def reject_book(book_id):
    if session.get('admin_role') != 'super':
        return jsonify({"error": "Only super admin can reject."}), 403
    cur = mysql.connection.cursor()
    # Get title, uploader id and file path before deleting
    cur.execute("SELECT title, uploaded_by, telegram_link FROM documents WHERE id = %s", (book_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Book not found"}), 404
    title, uploader_id, file_link = row

    # Delete the file
    file_path = file_link.lstrip('/')
    if os.path.exists(file_path):
        os.remove(file_path)

    cur.execute("DELETE FROM documents WHERE id = %s", (book_id,))
    mysql.connection.commit()

    # Send rejection email to uploader if exists
    if uploader_id:
        cur.execute("SELECT email, username FROM users WHERE id = %s", (uploader_id,))
        user = cur.fetchone()
        if user:
            html = make_approval_email(title, "rejected", "Unfortunately, your book was rejected. It may not meet our guidelines.")
            send_email_notification(
                "Book Rejected - DocoDive",
                user[0],
                f"Your book '{title}' has been rejected.",
                html_body=html
            )
    cur.close()
    return jsonify({"success": True})

@app.route('/admin/approve-all', methods=['POST'])
@admin_required
def approve_all_books():
    if session.get('admin_role') != 'super':
        return jsonify({"error": "Only super admin can approve."}), 403
    cur = mysql.connection.cursor()
    # For approve-all we skip individual emails (or could loop, but not necessary)
    cur.execute("UPDATE documents SET approved = 1 WHERE approved = 0")
    count = cur.rowcount
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": True, "count": count})

# -------------------- ADMIN BOOKS LIST --------------------
@app.route('/admin/books')
@admin_required
def admin_books_list():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.id, d.title, d.category_id, d.telegram_link, d.author, d.description, d.image_url, d.language, c.level
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        ORDER BY d.id DESC
    """)
    books = cur.fetchall()
    cur.close()
    books_list = []
    for b in books:
        books_list.append({
            "id": b[0], "title": b[1], "category_id": b[2], "link": b[3],
            "author": b[4], "description": b[5], "image_url": b[6], "language": b[7], "level": b[8]
        })
    return render_template('admin_books.html', books=books_list)

# -------------------- ADMIN EDIT / DELETE BOOKS --------------------
@app.route('/admin/edit/<int:book_id>', methods=['GET', 'POST'])
@admin_required
def edit_book(book_id):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        title = request.form.get('title')
        category_name = request.form.get('category')
        author = request.form.get('author')
        desc = request.form.get('desc')
        img_url = request.form.get('img')
        language = request.form.get('language', 'English')

        final_cover_link = None
        if 'cover_image' in request.files and request.files['cover_image'].filename != '':
            cover_file = request.files['cover_image']
            allowed_img = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            if '.' in cover_file.filename and cover_file.filename.rsplit('.', 1)[1].lower() in allowed_img:
                cover_filename = secure_filename(cover_file.filename)
                cover_path = os.path.join('static/covers', cover_filename)
                os.makedirs('static/covers', exist_ok=True)
                cover_file.save(cover_path)
                final_cover_link = f"/{cover_path}"
        if final_cover_link is None and img_url and img_url.strip():
            final_cover_link = img_url.strip()

        if 'pdf_file' in request.files and request.files['pdf_file'].filename != '':
            file = request.files['pdf_file']
            if not allowed_file(file.filename):
                return jsonify({"error": "Only PDF files are allowed."}), 400
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            final_link = f"/{file_path}"
            cur.execute("""
                UPDATE documents
                SET category_id=(SELECT id FROM categories WHERE level=%s), title=%s, telegram_link=%s, author=%s, description=%s, image_url=%s, language=%s
                WHERE id=%s
            """, (category_name, title, final_link, author, desc, final_cover_link, language, book_id))
        else:
            cur.execute("""
                UPDATE documents
                SET category_id=(SELECT id FROM categories WHERE level=%s), title=%s, author=%s, description=%s, image_url=%s, language=%s
                WHERE id=%s
            """, (category_name, title, author, desc, final_cover_link, language, book_id))
        mysql.connection.commit()
        cur.close()
        return redirect(url_for('admin_books_list'))

    cur.execute("""
        SELECT id, title, category_id, telegram_link, author, description, image_url, language
        FROM documents WHERE id = %s
    """, (book_id,))
    book_row = cur.fetchone()
    cur.execute("SELECT id, level FROM categories ORDER BY id")
    categories = cur.fetchall()
    cur.close()
    if not book_row:
        abort(404)
    book = {
        "id": book_row[0], "title": book_row[1], "category_id": book_row[2], "link": book_row[3],
        "author": book_row[4], "description": book_row[5], "image_url": book_row[6], "language": book_row[7]
    }
    return render_template('edit_book.html', book=book, categories=categories)

@app.route('/admin/delete/<int:book_id>', methods=['POST'])
@admin_required
def delete_book(book_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT telegram_link FROM documents WHERE id = %s", (book_id,))
    file_record = cur.fetchone()
    if file_record:
        file_path = file_record[0].lstrip('/')
        if os.path.exists(file_path):
            os.remove(file_path)
    cur.execute("DELETE FROM documents WHERE id = %s", (book_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": "Book deleted successfully!"})

# -------------------- ADMIN DASHBOARD --------------------
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total_books = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM categories")
    total_categories = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM admins")
    total_admins = cur.fetchone()[0]
    cur.execute("""
        SELECT d.title, c.level, d.created_at
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        ORDER BY d.id DESC LIMIT 5
    """)
    recent = cur.fetchall()
    cur.close()
    recent_uploads = [{"title": r[0], "level": r[1], "created_at": str(r[2])} for r in recent]
    return jsonify({
        "total_books": total_books,
        "total_categories": total_categories,
        "total_admins": total_admins,
        "recent_uploads": recent_uploads
    })

# -------------------- LIVE CATEGORY COUNT --------------------
@app.route('/api/categories/live-counts')
def live_category_counts():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT c.id, c.level, COUNT(d.id) AS total
        FROM categories c
        LEFT JOIN documents d ON c.id = d.category_id AND d.approved = 1
        GROUP BY c.id
        ORDER BY c.id
    """)
    data = cur.fetchall()
    cur.close()
    return jsonify([{"id": r[0], "level": r[1], "count": r[2]} for r in data])

# -------------------- MANAGE ADMINS (super admin) --------------------
@app.route('/admin/admins')
@admin_required
def list_admins():
    if session.get('admin_role') != 'super':
        return redirect(url_for('admin_dashboard'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, username, role FROM admins ORDER BY id")
    admins = cur.fetchall()
    cur.close()
    return render_template('admin_admins.html', admins=admins)

@app.route('/admin/admins/add', methods=['POST'])
@admin_required
def add_admin():
    if session.get('admin_role') != 'super':
        return jsonify({"error": "Only super admin can add new admins."}), 403
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'admin')
    if not username or not password:
        return jsonify({"error": "Username and password required."}), 400
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO admins (username, password, role) VALUES (%s, %s, %s)", (username, password, role))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": "Admin added successfully!"})

@app.route('/admin/admins/edit/<int:admin_id>', methods=['POST'])
@admin_required
def edit_admin(admin_id):
    if session.get('admin_role') != 'super':
        return jsonify({"error": "Only super admin can edit admins."}), 403
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    fields = []
    params = []
    if username:
        fields.append("username = %s")
        params.append(username)
    if password:
        fields.append("password = %s")
        params.append(password)
    if role:
        fields.append("role = %s")
        params.append(role)
    if not fields:
        return jsonify({"error": "No fields to update."}), 400
    params.append(admin_id)
    cur = mysql.connection.cursor()
    cur.execute(f"UPDATE admins SET {', '.join(fields)} WHERE id = %s", params)
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": "Admin updated!"})

@app.route('/admin/admins/delete/<int:admin_id>', methods=['POST'])
@admin_required
def delete_admin(admin_id):
    if session.get('admin_role') != 'super':
        return jsonify({"error": "Only super admin can delete admins."}), 403
    if admin_id == session.get('admin_id'):
        return jsonify({"error": "You cannot delete your own account."}), 400
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM admins WHERE id = %s", (admin_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({"success": "Admin deleted."})

# -------------------- LOGIN LOGS --------------------
@app.route('/api/admin/login-logs')
@admin_required
def login_logs():
    if session.get('admin_role') != 'super':
        return jsonify({"error": "Unauthorized"}), 403
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT l.id, a.username, l.ip_address, l.success, l.timestamp
        FROM login_logs l
        LEFT JOIN admins a ON l.admin_id = a.id
        ORDER BY l.timestamp DESC LIMIT 50
    """)
    logs = cur.fetchall()
    cur.close()
    result = [{
        "id": r[0], "username": r[1] if r[1] else "Unknown",
        "ip": r[2], "success": bool(r[3]), "timestamp": str(r[4])
    } for r in logs]
    return jsonify(logs=result)

# -------------------- ANALYTICS --------------------
@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total_books = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM download_history")
    total_downloads = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.close()
    return render_template('admin_analytics.html',
                           total_books=total_books,
                           total_downloads=total_downloads,
                           total_users=total_users)

# -------------------- PWA --------------------
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "DocoDive",
        "short_name": "DocoDive",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#4338ca",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.route('/sw.js')
def service_worker():
    return app.send_static_file('sw.js')

# -------------------- RUN --------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)