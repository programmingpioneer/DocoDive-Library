#!/usr/bin/env python3
"""
ONE-TIME SEED — Har approved book ko 3 meaningful, humanized reviews deta hai.
10 reviewers ka pool, har book pe randomly 3 alag reviewers + ratings 5/5/4 (random order).
Rerun-safe: agar kisi book pe pehle se 3 seeded reviews hain to us book ko skip kar deta hai.
Run karne ke baad is file ko delete kar dena.
"""

import os
import random
from dotenv import load_dotenv
import mysql.connector
from werkzeug.security import generate_password_hash

load_dotenv()

# ================== DB CONFIG (.env se) ==================
db_config = {
    "host": os.environ.get("MYSQL_HOST") or os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("MYSQL_PORT") or os.environ.get("DB_PORT", "4000")),
    "user": os.environ.get("MYSQL_USER") or os.environ.get("DB_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD") or os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DB") or os.environ.get("DB_NAME", "docodive_dev"),
    "use_pure": True,
    "autocommit": False,
}

ssl_ca = os.environ.get("MYSQL_SSL_CA")
if ssl_ca:
    if not os.path.isabs(ssl_ca):
        ssl_ca = os.path.join(os.path.dirname(os.path.abspath(__file__)), ssl_ca)
    db_config["ssl_ca"] = ssl_ca
    db_config["ssl_verify_cert"] = os.environ.get("MYSQL_SSL_VERIFY_CERT", "false").lower() == "true"
    db_config["ssl_verify_identity"] = os.environ.get("MYSQL_SSL_VERIFY_IDENTITY", "false").lower() == "true"

# ================== 10 REVIEWERS ==================
USERS = [
    ("ayesha.khan", "ayesha.khan@example.com", "Ayesha", "Khan", "https://i.pravatar.cc/150?img=47"),
    ("muhammad.bilal", "m.bilal@example.com", "Muhammad", "Bilal", "https://i.pravatar.cc/150?img=12"),
    ("fatima.noor", "fatima.noor@example.com", "Fatima", "Noor", "https://i.pravatar.cc/150?img=32"),
    ("hamza.sheikh", "hamza.sheikh@example.com", "Hamza", "Sheikh", "https://i.pravatar.cc/150?img=68"),
    ("zainab.tariq", "zainab.tariq@example.com", "Zainab", "Tariq", "https://i.pravatar.cc/150?img=44"),
    ("ali.raza", "ali.raza@example.com", "Ali", "Raza", "https://i.pravatar.cc/150?img=15"),
    ("sana.malik", "sana.malik@example.com", "Sana", "Malik", "https://i.pravatar.cc/150?img=26"),
    ("bilal.ahmed", "bilal.ahmed@example.com", "Bilal", "Ahmed", "https://i.pravatar.cc/150?img=60"),
    ("hira.shah", "hira.shah@example.com", "Hira", "Shah", "https://i.pravatar.cc/150?img=36"),
    ("usman.javed", "usman.javed@example.com", "Usman", "Javed", "https://i.pravatar.cc/150?img=53"),
]

SEEDED_USERNAMES = [u[0] for u in USERS]


def clean_title(title):
    """Title ko readable banata hai."""
    if not title:
        return "this book"
    return str(title).replace("_", " ").strip()


def build_review(title, author, category, style):
    """Title, author aur category ke hisaab se humanized review banata hai."""
    t = clean_title(title)
    a = author if author and author != "None" else "the author"
    c = category if category and category != "None" else "the subject"

    if style == 0:
        return (
            f"I finally felt comfortable with {c} after reading {t}. "
            f"The explanations are clear and the flow is perfect for someone who is learning from scratch. "
            f"{a} has a way of turning difficult topics into something practical and easy to follow."
        )
    elif style == 1:
        return (
            f"{t} is one of those resources I keep coming back to. "
            f"The examples feel realistic and every chapter builds naturally on the previous one. "
            f"If you are working with {c}, this book gives you a strong foundation without unnecessary fluff."
        )
    else:
        return (
            f"What I appreciated most about {t} is how balanced it is. "
            f"It covers the important {c} concepts step by step and the exercises actually make you apply what you learn. "
            f"A worthwhile read for anyone who wants to go deeper instead of just memorizing."
        )


def main():
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    # 1) Reviewers ensure karo
    hashed = generate_password_hash("DocoDiveSeed@2026")
    reviewer_ids = []
    for username, email, first, last, avatar in USERS:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        if row:
            reviewer_ids.append(row[0])
            continue

        cur.execute(
            """
            INSERT INTO users (username, email, password, verified,
                               verification_token, first_name, last_name, avatar_url)
            VALUES (%s, %s, %s, 1, NULL, %s, %s, %s)
            """,
            (username, email, hashed, first, last, avatar),
        )
        reviewer_ids.append(cur.lastrowid)

    conn.commit()

    # 2) Approved books fetch karo
    cur.execute(
        """
        SELECT d.id, d.title, d.author, c.level
        FROM documents d
        JOIN categories c ON d.category_id = c.id
        WHERE d.approved = 1
        ORDER BY d.id
        """
    )
    books = cur.fetchall()

    if not books:
        print("❌ Koi approved book nahi mili. Pehle books approve karo.")
        cur.close()
        conn.close()
        return

    placeholders = ",".join(["%s"] * len(SEEDED_USERNAMES))

    inserted = 0
    skipped = 0

    for book in books:
        book_id, title, author, category = book

        # Rerun-safe: kya is book pe pehle se 3 seeded reviews hain?
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM reviews r
            JOIN users u ON r.user_id = u.id
            WHERE r.book_id = %s
              AND u.username IN ({placeholders})
            """,
            (book_id, *SEEDED_USERNAMES),
        )
        existing_seeded = cur.fetchone()[0] or 0

        if existing_seeded >= 3:
            skipped += 1
            continue

        # Har book ke liye randomly 3 alag reviewers
        chosen_ids = random.sample(reviewer_ids, 3)

        # Ratings 5,5,4 random order mein
        ratings = [5, 5, 4]
        random.shuffle(ratings)

        for idx, uid in enumerate(chosen_ids):
            comment = build_review(title, author, category, style=idx)
            cur.execute(
                "INSERT INTO reviews (user_id, book_id, rating, comment) VALUES (%s, %s, %s, %s)",
                (uid, book_id, ratings[idx], comment),
            )
            inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Seeding complete!")
    print(f"   Books processed : {len(books)}")
    print(f"   Reviews inserted: {inserted}")
    print(f"   Books skipped   : {skipped} (pehle se 3 seeded reviews the)")


if __name__ == "__main__":
    main()