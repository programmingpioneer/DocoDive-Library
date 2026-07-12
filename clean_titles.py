import csv
import re

CSV_FILE = 'bulk_upload/metadata.csv'

def clean_title(title):
    """Remove common messy patterns from title"""
    title = re.sub(r'[-_]?@PDFMatrix', '', title)
    title = re.sub(r'[-_]?TechByMehdi', '', title)
    title = re.sub(r'\.pdf\s*.*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(\d+\)\s*$', '', title)
    title = re.sub(r'\s*-\s*$', '', title)
    title = re.sub(r'\s*PDF\s.*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[✅⭐📌🔸✨💡🔥]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.strip('- _')
    return title

def generate_description(title, category):
    """
    Generate a meaningful description based on the category.
    If category not matched, returns a generic description.
    """
    title_clean = clean_title(title)  # ensure title is clean (might already be clean)
    category = category.strip()

    # Custom descriptions per category – aap apne hisaab se edit kar sakte hain
    descriptions = {
        'Python': f"Master Python programming with '{title_clean}'. Covers fundamentals to advanced topics for learners and professionals.",
        'JavaScript': f"Learn JavaScript from scratch with '{title_clean}'. Ideal for web developers and frontend engineers.",
        'Java': f"Understand Java concepts deeply with '{title_clean}'. Perfect for backend development and OOP learners.",
        'C / C++': f"Explore C/C++ programming through '{title_clean}'. A must-have for system programmers and competitive coders.",
        'Web Development': f"Build modern websites using '{title_clean}'. Covers HTML, CSS, JavaScript, and frameworks.",
        'Data Science': f"Discover data science techniques with '{title_clean}'. Includes practical examples and real‑world datasets.",
        'Machine Learning': f"Dive into ML algorithms and projects with '{title_clean}'. Suitable for beginners and practitioners.",
        'Algorithms': f"Strengthen your problem-solving skills with '{title_clean}'. Detailed explanations and coding examples.",
        'Databases': f"Learn database design and SQL with '{title_clean}'. Includes hands‑on exercises and interview prep.",
        'Cyber Security': f"Protect systems and networks with '{title_clean}'. Covers ethical hacking, defense, and security tools.",
        'Mobile Apps': f"Create mobile applications with '{title_clean}'. Covers iOS/Android development and best practices.",
        'DevOps': f"Master DevOps principles with '{title_clean}'. Covers CI/CD, cloud, and automation tools."
    }

    # If category matched, return custom description; else generic
    return descriptions.get(category, f"An insightful resource about {title_clean} in the field of {category}.")

rows = []
with open(CSV_FILE, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # 1. Clean title
        row['title'] = clean_title(row['title'])

        # 2. Auto-fill author if empty (optional)
        if not row['author'].strip():
            row['author'] = 'Unknown'

        # 3. Auto-generate description if empty
        if not row['description'].strip():
            row['description'] = generate_description(row['title'], row['level'])

        rows.append(row)

with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['title','level','author','description','image_url','language','filename','cover_filename'])
    writer.writeheader()
    writer.writerows(rows)

print(f"✅ {len(rows)} books processed – titles cleaned, descriptions generated.")
print(f"   CSV file updated: {CSV_FILE}")
print("   Now run: python bulk_upload.py")