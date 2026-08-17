import os
import csv
import re
import shutil
import mysql.connector

# ========== CONFIGURATION (same as app.py) ==========
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Root123",
    "database": "docodive_db",
}

UPLOAD_FOLDER = "static/uploads"
CSV_FILE = "bulk_upload/metadata.csv"
PDF_SOURCE_DIR = "bulk_upload/pdfs"
COVER_SOURCE_DIR = "bulk_upload/covers"  # optional

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/covers", exist_ok=True)

# ========== CATEGORY NAME FIXES ==========
# Agar CSV mein galat naam hai to sahi naam se replace karo
CATEGORY_MAP = {
    "Algorithem": "Algorithms",
    "C-C++": "C / C++",
    "Cyber secaurity": "Cyber Security",
    "MobileApp": "Mobile Apps",
    "Web Develepment": "Web Development",
    # Agar aur galat naam ho to yahan add karo
}


# ========== HELPER FUNCTIONS ==========
def clean_title(title):
    """Title se junk hatao"""
    title = re.sub(r"[-_]?@PDFMatrix", "", title)
    title = re.sub(r"[-_]?TechByMehdi", "", title)
    title = re.sub(r"\.pdf\s*.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\(\d+\)\s*$", "", title)
    title = re.sub(r"\s*-\s*$", "", title)
    title = re.sub(r"\s*PDF\s.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[✅⭐📌🔸✨💡🔥]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    title = title.strip("- _")
    return title


def generate_description(title, category):
    """Category ke hisaab se description"""
    title_clean = clean_title(title)
    descriptions = {
        "Python": f"Master Python programming with '{title_clean}'. Covers fundamentals to advanced topics.",
        "JavaScript": f"Learn JavaScript from scratch with '{title_clean}'. Ideal for web developers.",
        "Java": f"Understand Java concepts deeply with '{title_clean}'. Perfect for backend development.",
        "C / C++": f"Explore C/C++ programming through '{title_clean}'. For system programmers and competitive coders.",
        "Web Development": f"Build modern websites using '{title_clean}'. Covers HTML, CSS, JavaScript, and frameworks.",
        "Data Science": f"Discover data science techniques with '{title_clean}'. Includes practical examples.",
        "Machine Learning": f"Dive into ML algorithms and projects with '{title_clean}'.",
        "Algorithms": f"Strengthen your problem-solving skills with '{title_clean}'. Detailed explanations.",
        "Databases": f"Learn database design and SQL with '{title_clean}'. Hands-on exercises included.",
        "Cyber Security": f"Protect systems and networks with '{title_clean}'. Covers ethical hacking and defense.",
        "Mobile Apps": f"Create mobile applications with '{title_clean}'. Covers iOS/Android development.",
        "DevOps": f"Master DevOps principles with '{title_clean}'. Covers CI/CD, cloud, and automation tools.",
    }
    return descriptions.get(
        category,
        f"An insightful resource about {title_clean} in the field of {category}.",
    )


def ensure_category_exists(cursor, category_name):
    """Agar category nahi hai to insert karo (e.g., 'Other')"""
    cursor.execute("SELECT id FROM categories WHERE level = %s", (category_name,))
    cat = cursor.fetchone()
    if not cat:
        cursor.execute("INSERT INTO categories (level) VALUES (%s)", (category_name,))
        return cursor.lastrowid
    return cat[0]


# ========== DATABASE CONNECT ==========
conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# ========== CLEAN CSV & UPLOAD ==========
rows_inserted = 0
with open(CSV_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        # 1. Clean title
        row["title"] = clean_title(row["title"])

        # 2. Fix category name
        original_category = row["level"].strip()
        fixed_category = CATEGORY_MAP.get(original_category, original_category)
        row["level"] = fixed_category

        # 3. Auto fill author
        if not row["author"].strip():
            row["author"] = "Unknown"

        # 4. Auto generate description if empty
        if not row["description"].strip():
            row["description"] = generate_description(row["title"], fixed_category)

        # 5. Copy PDF to static/uploads
        filename = row["filename"].strip()
        src_pdf = os.path.join(PDF_SOURCE_DIR, filename)
        dst_pdf = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(src_pdf):
            print(f"❌ PDF missing: {src_pdf}, skipping.")
            continue
        shutil.copy2(src_pdf, dst_pdf)
        final_pdf_link = f"/{dst_pdf}"

        # 6. Handle cover image (optional)
        cover_filename = row.get("cover_filename", "").strip()
        final_cover_link = row.get("image_url", "").strip()
        if cover_filename:
            src_cover = os.path.join(COVER_SOURCE_DIR, cover_filename)
            dst_cover = os.path.join("static/covers", cover_filename)
            if os.path.exists(src_cover):
                shutil.copy2(src_cover, dst_cover)
                final_cover_link = f"/{dst_cover}"
            else:
                print(f"⚠️ Cover missing: {src_cover}")
        # if final_cover_link still empty, keep as None (DB allows NULL)

        # 7. Get category id (ensure category exists)
        cat_id = ensure_category_exists(cursor, fixed_category)

        # 8. Insert into documents
        cursor.execute(
            """
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
            (
                cat_id,
                row["title"],
                final_pdf_link,
                row["author"],
                row["description"],
                final_cover_link,
                row.get("language", "English"),
            ),
        )
        rows_inserted += 1
        print(f"✅ Inserted: {row['title']}")

conn.commit()
cursor.close()
conn.close()

print(f"\n🎉 Upload complete! {rows_inserted} books added to library.")
