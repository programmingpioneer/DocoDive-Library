import os
import csv
import shutil
import mysql.connector

# ========== CONFIG ==========
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Root123',
    'database': 'docodive_db'
}
UPLOAD_FOLDER = 'static/uploads'
COVERS_FOLDER = 'static/covers'
CSV_FILE = 'bulk_upload/metadata.csv'
PDF_SOURCE_DIR = 'bulk_upload/pdfs'
COVER_SOURCE_DIR = 'bulk_upload/covers'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COVERS_FOLDER, exist_ok=True)

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

with open(CSV_FILE, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        title = row['title'].strip()
        level = row['level'].strip()
        author = row['author'].strip()
        desc = row['description'].strip()
        img_url = row.get('image_url', '').strip()
        language = row.get('language', 'English').strip()
        filename = row['filename'].strip()
        cover_filename = row.get('cover_filename', '').strip()

        # Copy PDF
        src_pdf = os.path.join(PDF_SOURCE_DIR, filename)
        dst_pdf = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(src_pdf):
            print(f"❌ PDF missing: {src_pdf}")
            continue
        shutil.copy2(src_pdf, dst_pdf)
        final_pdf_link = f"/{dst_pdf}"

        # Handle cover image
        final_cover_link = None
        if cover_filename:
            src_cover = os.path.join(COVER_SOURCE_DIR, cover_filename)
            dst_cover = os.path.join(COVERS_FOLDER, cover_filename)
            if os.path.exists(src_cover):
                shutil.copy2(src_cover, dst_cover)
                final_cover_link = f"/{dst_cover}"
            else:
                print(f"⚠️ Cover missing: {src_cover}")
        if not final_cover_link and img_url:
            final_cover_link = img_url

        # Get category_id
        cursor.execute("SELECT id FROM categories WHERE level = %s", (level,))
        cat = cursor.fetchone()
        if not cat:
            print(f"❌ Category '{level}' not found")
            continue
        cat_id = cat[0]

        # Insert
        cursor.execute("""
            INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (cat_id, title, final_pdf_link, author, desc, final_cover_link, language))
        print(f"✅ Inserted: {title}")

conn.commit()
cursor.close()
conn.close()
print("\n🎉 Bulk upload complete!")