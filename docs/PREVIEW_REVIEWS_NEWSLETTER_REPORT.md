# Preview, reviews, newsletter aur file cleanup

Latest arrow placement was corrected to transparent side-center overlays after this report; see [scroll overlay report](SCROLL_OVERLAY_REPORT.md). The top-center descriptions below record the earlier pass.

6 November 2026. Changes isi local project mein hain. Is pass ka local workflow aur owner-run SQL neeche diya gaya hai.

## UI mein kya badla

- Home, Learning Hub aur baqi shared book cards ab ek Quick Preview controller use karte hain. Purana duplicate Home preview controller aur us ka unused popup/share markup hataya gaya hai.
- Popup ka design Book Details jaisa hai: cover ke saath title, author, category/language, description, actions aur reviews. Chhoti screen par content stack hota hai.
- Preview arrows ab header mein upar center par hain. Side rail aur us ke liye reserved jagah hata di gayi hai. Arrows sirf popup ke andar scroll karte hain, ends par disable hote hain, aur reduced-motion preference follow karte hain. Page scroll arrows bhi top-center hain.
- Review mein book optional hai. Khali selection general DocoDive feedback banati hai; kisi fake book ID se attach nahi hoti. Title/author search poori approved catalogue mein hoti hai. Arrow keys, Enter, Escape, Tab aur clear control kaam karte hain.
- Sirf type kiya hua, select na kiya hua book name submit nahi hota. Purane search replies naye results ko replace nahi karte. Pehla Escape picker band karta hai; doosra popup band kar sakta hai. Ruki hui query dobara focus/click par resume hoti hai.
- Review ke neeche selected book ka compact linked label dikhta hai. General feedback ka apna label hai; unpublished book ka title expose nahi hota.
- Profile milestones ke icon aur lock/status ke beech accidental dark rectangle selector collision se aa raha tha. Heading class ka naam badla hai; asli cards aur filters barqarar hain.

## Welcome email

Naye newsletter subscriber ke liye colorful, responsive HTML aur plain-text welcome tayyar hai. Repeat aur concurrent submissions par unique email-hash ledger sirf ek automatic welcome attempt allow karta hai. Raw email ya message content ledger mein store nahi hota.

Provider ka acceptance inbox delivery ki guarantee nahi hai. Rejection/timeout par UI sach batati hai aur automatic retry nahi karti, kyun ke ambiguous timeout ke baad repeat send duplicate bana sakta hai. Process claim ke baad band ho jaye to welcome na bhi ja sake; is limit ko deployment notes mein likha hai.

Email links configured `PUBLIC_SITE_URL` use karte hain. Khali configuration par repository README ka existing public address `https://docodive-library.onrender.com` fallback hai. Incoming Host header email links change nahi kar sakta. Malformed configuration provider call se pehle reject hoti hai. Existing provider suppression settings barqarar hain.

## Pehle ye do SQL files khud apply karein

Ye files **execute nahi ki gayi hain**. Apne database backup aur established connection se, intended database select karke stop-on-error ke saath chalayein:

1. [Optional review books](../migrations/20261106_optional_review_books.sql), [instructions](../migrations/README-OPTIONAL-REVIEW-BOOKS.md): `reviews.book_id` aur official reply ke `book_comments.book_id` ko nullable karta hai; existing integer types preserve hote hain.
2. [Newsletter welcome ledger](../migrations/20261106_newsletter_welcomes.sql), [instructions](../migrations/README-NEWSLETTER-WELCOMES.md): unique hash/status/timestamps table banata hai.

Doosri file ko pehli file ke same connection mein chalana zaroori nahi. Har file ke result/schema ko us ki instructions ke mutabiq verify karein. Existing hardcoded `run_migration.py` is update ka runner nahi hai. Koi naya Python package nahi chahiye. Phir app restart karein aur Ctrl+F5 karein.

## Backup aur arrangement

[Verified source backup](../deliverables/source-backup-before-cleanup-20261106-155704.zip) cleanup se pehle banaya gaya: **623 source files**, ZIP CRC aur har entry source se compare hui. SHA-256: `00a4443adfc5d18f94b3a7be4cc25d93ce94d4f64b597c9027e4a84ba5c0d69e`.

Ye source snapshot hai. Credentials, environment files, database backups, private uploads aur Git history is mein shamil nahi; unhein read ya modify nahi kiya gaya.

[File cleanup report](FILE_CLEANUP_REPORT.md) mein exact findings hain. Byte-identical learning templates dynamic routes mein abhi use hote hain, is liye unhein rakha gaya hai. Manual import tools aur uncertain public images bhi retain hue hain. `app.py`/root helpers, `admin/`, `templates/`, `static/`, `scripts/`, `tests/`, `migrations/`, `docs/` aur generated `deliverables/` ki existing responsibilities barqarar hain; paths todne wali bulk relocation nahi hui.

## Verification aur limits

Verification sirf isolated test apps, in-memory fixtures aur local browser port 5012 par synthetic data ke saath hui. User ke port 5000, credentials, TiDB, real email, OAuth, storage, Sentry, staging ya production access nahi hua. MySQL/TiDB migration execution aur actual inbox delivery owner ke final checks hain.

Evidence: `deliverables/preview-optional-reviews/` aur `deliverables/newsletter-welcome/`. Browser views mein selected catalogue result, compact title label, milestone filters, Home/Hub shared preview, top-center arrows, light/dark modes aur responsive sizes check hue. Email HTML browser rendering actual Outlook/Gmail client certification nahi hai.

Delivery: `deliverables/updated-source.zip`; per-file hashes `deliverables/manifest.json` mein hain. Current source ka purane uncommitted work ke saath package refresh hota hai; deployment ya push nahi hua.

## Final checks

- **182/182 isolated tests pass** (124.240 seconds). The final full suite includes preview/draft/race/auth checks, review search/optional-book backend and moderation, milestone filters, newsletter validation/concurrent dedup and Host-header safety.
- **97/97 synthetic render audits pass**; 154 Jinja templates, 25 static scripts and 393 inline scripts parse. Four changed CSS files parse without errors.
- Centered preview: **10 mode/width records** at 320, 390, 768, 1366 and 3840 pixels, light and dark. Modal fits, header arrows centered, direct full-width body and no page horizontal overflow. Home and Hub both open this same popup.
- Review modal, keyboard-selected catalogue book, clear/general state and Escape/resume behavior checked in browser fixtures. Profile shows 4 unlocked and 5 in-progress fixture milestones with transparent icon/status headings.
- Welcome HTML checked at 320, 390, 768 and 1366 pixels without horizontal overflow. Real email delivery was not attempted.
- Cleanup after backup verification: **69 generated `.pyc` files (4,776,840 bytes)** and one obsolete synthetic failure log removed. All source counterparts remain. [Exact result](../deliverables/preview-optional-reviews/cleanup-execution.json). No source/assets deleted.
