"""Seed random counts for all documents."""
import random
from app import app, mysql

with app.app_context():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM documents")
    book_ids = [row[0] for row in cur.fetchall()]
    
    for bid in book_ids:
        dl = random.randint(1000, 3000)
        vw = random.randint(2000, 5000)
        cur.execute("UPDATE documents SET download_count=%s, view_count=%s WHERE id=%s", (dl, vw, bid))
    
    mysql.connection.commit()
    cur.close()
    print(f"Seeded {len(book_ids)} documents.") 