# Migration System — Simple Guide

Ye file samjhati hai ki naya database change kaise add karo.

---

## 1. Ye system kya karta hai?

Do DB hain:
- **Staging** (test ke liye) — `.env` file me credentials
- **Prod** (asli users) — `.env.prod` file me credentials

Jab tumhe **naya column** ya **naya table** chahiye, tum:
1. Ek file me SQL likhte ho — `migrations/all_changes.sql`
2. Ek command chalate ho
3. Wo SQL **dono DBs** pe automatically apply ho jata hai

**Bas itni si baat hai.**

---

## 2. Files kaun kaun si hain

```

D:\PioneerDocoDive
│
├── migrations
│   ├── all_changes.sql          ← YAHAN SQL likhoge (bas yahi file kholte ho)
│   └── README-OPTION-B.md       ← ye file
│
├── scripts
│   └── run_all.py               ← YEH script chalate ho
│
├── .env                          ← staging DB ki keys (already hai)
└── .env.prod                     ← prod DB ki keys (already hai)

```

**Do cheezein yaad rakho:**
- **`all_changes.sql`** — yahan SQL likhte ho
- **`run_all.py`** — ye chalate ho

---

## 3. Pehli baar setup (sirf ek baar)

```powershell
cd D:\PioneerDocoDive
pip install mysql-connector-python python-dotenv
```

Bas. Ye ek baar hi karna hai.

---

## 4. Naya change kaise add karo (har baar yehi karoge)

### Step 1: File kholo

`migrations\all_changes.sql` — notepad ya VS Code me kholo.

### Step 2: Sabse NEECHE jao, aur apna SQL likho

Maan lo tum "bookmarks" feature add kar rahe ho. File ke aakhir me ye likho:

```
-- Add bookmarks feature
ALTER TABLE documents ADD COLUMN bookmarks INT DEFAULT 0;
```

**Zaroori baat:**

- SQL ke aakhir me **semicolon (;)** hona chahiye — warna script confuse hoga
- **Kabhi upar wali purani lines ko edit mat karo.** Sirf neeche naya add karo.

### Step 3: Save karo

Ctrl+S.

### Step 4: Pehle dry-run chalao (dekho kya hoga)

```
cd D:\PioneerDocoDive
python scripts\run_all.py --dry-run
```

**Ye kya karta hai:** Sirf **batata hai** kya hoga, actually kuch nahi karta.

**Output aisa aayega:**

```
ENV: .env
  OK #001  SKIP (already applied)  | ALTER TABLE documents ADD COLUMN meta_desc...
  OK #002  SKIP (already applied)  | ALTER TABLE documents ADD COLUMN slug...
  OK #003  WOULD APPLY              | ALTER TABLE documents ADD COLUMN bookmarks...

ENV: .env.prod
  OK #001  WOULD APPLY              | ALTER TABLE documents ADD COLUMN meta_desc...
  OK #002  WOULD APPLY              | ALTER TABLE documents ADD COLUMN slug...
  OK #003  WOULD APPLY              | ALTER TABLE documents ADD COLUMN bookmarks...
```

**Kaise padho:**

- `SKIP (already applied)` = ye statement pehle chal chuki hai, skip ho rahi
- `WOULD APPLY` = ye nayi hai, apply hogi (agar tum `--dry-run` hata ke chalao)

### Step 5: Asli apply karo

Jab `--dry-run` output theek lage:

```
python scripts\run_all.py
```

**Ab actually SQL chal jayegi. Dono DBs pe.**

**Output:**

```
ENV: .env
  OK #001  SKIP (already applied)  | ...
  OK #002  SKIP (already applied)  | ...
  OK #003  APPLIED                 | ALTER TABLE documents ADD COLUMN bookmarks...

ENV: .env.prod
  OK #001  SKIP (already applied)  | ...
  OK #002  SKIP (already applied)  | ...
  OK #003  APPLIED                 | ALTER TABLE documents ADD COLUMN bookmarks...

RESULT: All environments OK.
```

**Kaam khatam. Dono DBs me `bookmarks` column add ho gaya.**

### Step 6: Git me save karo

```
git add migrations\all_changes.sql
git commit -m "feat: add bookmarks column"
git push
```

---

## 5. Poora workflow — ek nazar me

```
1. migrations\all_changes.sql kholo
2. Sabse neeche SQL likho (semicolon ke saath)
3. Save karo
4. python scripts\run_all.py --dry-run     ← dekho
5. python scripts\run_all.py               ← apply
6. git add + commit + push
```

**Bas. 6 steps.**

---

## 6. Ye safe kyun hai?

**Dobara chalane se kuch nahi todega.**

Agar tum `run_all.py` 10 baar chalao:

- Pehli baar — nayi statements apply hui
- Baaki 9 baar — **saari skip** ho jayengi, kuch nahi badlega

**Kyun?** Kyunki har SQL statement ka **hash** (unique code) ban jata hai, aur ek table (`statement_log`) me save ho jata hai. Agli baar jab chalao, script pehle check karti hai "ye statement pehle chali thi?" Agar haan, to skip.

---

## 7. Ye 3 rules kabhi mat todna

### Rule 1: Purani lines edit mat karo

**Ghalat:**

```
-- Pehle
ALTER TABLE documents ADD COLUMN bookmarks INT;

-- Baad me isko galat tarike se "fix" kiya:
ALTER TABLE documents ADD COLUMN bookmarks BIGINT;  ← GALAT! Purani line edit ki
```

**Sahi:**

```
ALTER TABLE documents ADD COLUMN bookmarks INT;

-- Fix chahiye? Neeche naya statement likho:
ALTER TABLE documents MODIFY COLUMN bookmarks BIGINT;  ← SAHI
```

### Rule 2: Semicolon (;) har statement ke end me

**Ghalat:**

```
ALTER TABLE documents ADD COLUMN bookmarks INT
ALTER TABLE documents ADD COLUMN notes TEXT;
```

↑ Pehle wale me `;` nahi hai — script confuse ho jayegi

**Sahi:**

```
ALTER TABLE documents ADD COLUMN bookmarks INT;
ALTER TABLE documents ADD COLUMN notes TEXT;
```

### Rule 3: Ek waqt me ek feature

**Ghalat:** Ek hi baar me 5 different features add karna (mushkil debug)

**Sahi:** Ek feature → ek migration cycle (write, dry-run, apply, commit)

---

## 8. Real example — shuru se aakhir tak

Maan lo tum "views counter" add karna chahte ho.

### Din 1 — Kaam

**Step 1:** `migrations\all_changes.sql` kholo. Sabse neeche jao. Ye likho:

```
-- Add view count for each bookmark
ALTER TABLE documents ADD COLUMN bookmark_count INT DEFAULT 0;

-- Index for faster lookups
CREATE INDEX idx_documents_bookmark_count ON documents(bookmark_count);
```

**Step 2:** Save.

**Step 3:** Terminal me:

```
python scripts\run_all.py --dry-run
```

Output:

```
ENV: .env
  OK #001  SKIP (already applied)  | ...
  OK #002  WOULD APPLY              | ALTER TABLE documents ADD COLUMN bookmark_count...
  OK #003  WOULD APPLY              | CREATE INDEX idx_documents_bookmark_count...

ENV: .env.prod
  OK #001  SKIP (already applied)  | ...
  OK #002  WOULD APPLY              | ALTER TABLE documents ADD COLUMN bookmark_count...
  OK #003  WOULD APPLY              | CREATE INDEX idx_documents_bookmark_count...
```

Sahi lag raha hai? Aage badho.

**Step 4:**

```
python scripts\run_all.py
```

Output:

```
RESULT: All environments OK.
```

**Step 5:**

```
git add migrations\all_changes.sql
git commit -m "feat: add bookmark count and index"
git push
```

**Kaam khatam. Dono DBs me column + index add ho gaya.**

---

## 9. Kabhi kabhi kya hota hai

### Case 1: "Duplicate column name" error

**Ye galti nahi hai** — matlab column pehle se hai. Script khud handle kar leti hai:

```
OK #005  SKIP (guarded: exists)  | ALTER TABLE documents ADD COLUMN bookmarks...
```

Matlab: koi manual ya pehle migration ne column already add kar diya. Script ne dekha, skip kar diya. **Kuch nahi toota.**

### Case 2: Naya statement ghalat SQL hai

```
OK #005  FAILED: You have an error in your SQL syntax...  | ALTER TABLE...
```

Iska matlab:

1. SQL me galti hai
2. Baaki statements (jo baad me aayi thi) **nahi chalengi**

**Fix:**

1. `all_changes.sql` me woh statement theek karo
2. Phir dobara `run_all.py` chalao

### Case 3: Sirf staging pe apply karna hai

```
python scripts\run_all.py --env .env
```

### Case 4: Sirf prod pe apply karna hai

```
python scripts\run_all.py --env .env.prod
```

---

## 10. Commands — poori list

```
# Dono envs (staging + prod) pe apply
python scripts\run_all.py

# Sirf preview (kuch change nahi)
python scripts\run_all.py --dry-run

# Sirf staging
python scripts\run_all.py --env .env

# Sirf prod
python scripts\run_all.py --env .env.prod
```

---

## 11. Ye system kaise kaam karta hai (andar ki baat)

### Jab tum `run_all.py` chalate ho, ye hota hai:

```
1. migrations\all_changes.sql padho
        ↓
2. Har SQL statement ko alag karo (semicolon se)
        ↓
3. Har statement ka hash (unique code) banao
        ↓
4. DB me statement_log table check karo
   "Ye hash pehle aaya hai?"
        ↓
   HAAN  → skip karo
   NAHI  → SQL chalao, hash save karo
        ↓
5. Dono DBs ke liye ye karo
```

### `statement_log` table kaisa dikhta hai:

| hash ↕▾ | stmt_preview ↕▾ | applied_at ↕▾ |
|---|---|---|
| −`a3f8b2c1d4e5f6g7` | `ALTER TABLE documents ADD COLUMN bookmarks...` | 2026-09-18 15:30 |
| `b4c2d8e6f1a3g5h7` | `CREATE INDEX idx_documents_bookmark_count...` | 2026-09-18 15:31 |
⚙

Isi table se pata chalta hai konsi statement apply ho chuki.

---

## 12. Sawaal-jawab (FAQ)

**Q: Kya main `all_changes.sql` me lines upar add kar sakta hoon?**
A: Nahi. Sirf neeche add karo. Script isi order me chalti hai.

**Q: Agar galti se ek statement upar wali line me change kar di?**
A: Script us statement ko naya samjhegi (hash change ho gaya). DB me error aayega (e.g. Duplicate column). Phir script guard kar degi (skip). **Lekin ye galat practice hai** — behtar hai git se undo karo.

**Q: Kya ek statement `;` ke andar bhi ho sakta hai?**
A: Jaise stored procedures me `;` hota hai andar — ye case abhi handle nahi. Isliye simple `ALTER TABLE`, `CREATE TABLE`, `CREATE INDEX` type statements hi likho.

**Q: Backup chahiye?**
A: Haan, agar `DROP` ya `MODIFY` wale statements hain, to pehle TiDB console me:

```
CREATE TABLE documents_backup_YYYYMMDD AS SELECT * FROM documents;
```

Phir `run_all.py` chalao.

**Q: Sirf staging pe test karna hai, prod pe nahi?**
A: `python scripts\run_all.py --env .env`

**Q: Purani statements kaise dekhoon jo apply ho chuki?**
A: TiDB console me:

```
SELECT * FROM statement_log ORDER BY applied_at DESC;
```

---

## 13. Yaad rakhne ki 3 baatein

1. **Sirf `migrations\all_changes.sql` me SQL likho.** Sabse neeche. Semicolon ke saath.
2. **Har baar: dry-run → phir apply.** 30 second bachata hai, galti se bachata hai.
3. **Kabhi upar wali lines edit mat karo.** Sirf neeche add karo.

---

## 14. Troubleshooting

| Problem ↕▾ | Kya karo ↕▾ |
|---|---|
| −"No such file: migrations\all_changes.sql" | File exist karti hai ya nahi check karo |
| "Missing dependency" | `pip install mysql-connector-python python-dotenv` |
| "FAILED: You have an error in your SQL syntax" | `all_changes.sql` me us statement ko theek karo |
| "SKIP (guarded: exists)" | Ye normal hai, column pehle se hai, skip ho gaya |
| Statement apply hui lekin delete karni hai | Neeche naya statement likho: `ALTER TABLE ... DROP COLUMN xxx;` |
⚙

---

## 15. Ek line me summary

```
all_changes.sql me neeche SQL likho → 
  run_all.py --dry-run → 
  run_all.py → 
  git commit
```

**Bas. Yehi karna hai har feature ke liye.**



