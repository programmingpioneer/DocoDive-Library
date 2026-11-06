"""Existing administrative workflows, isolated from public routes."""

import io
import os
import json
import random
from datetime import datetime, timedelta
from collections import defaultdict
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from .security import (
    required as official_admin_required,
    identity,
    owner_required,
    admin_ids,
    owner_id,
    has_role,
    is_studio_request as is_moderator,
)
from .studio import pagination


def register_admin(app, services):
    app.extensions["studio_services"] = services
    bp = Blueprint("admin", __name__, url_prefix="/admin-studio")
    PdfReader = services["PdfReader"]
    allowed_file = services["allowed_file"]
    allowed_image_file = services["allowed_image_file"]
    clean_professional_name = services["clean_professional_name"]
    clean_title_extra = services["clean_title_extra"]
    compress_image = services["compress_image"]
    create_notification = services["create_notification"]
    delete_from_r2 = services["delete_from_r2"]
    extract_cover_from_pdf = services["extract_cover_from_pdf"]
    extract_r2_key = services["extract_r2_key"]
    fitz = services["fitz"]
    generate_description = services["generate_description"]
    generate_r2_key = services["generate_r2_key"]
    get_site_setting = services["get_site_setting"]
    guess_category_from_filename = services["guess_category_from_filename"]
    guess_category_from_text = services["guess_category_from_text"]
    is_duplicate = services["is_duplicate"]
    is_official_user = services["is_official_user"]
    is_valid_pdf = services["is_valid_pdf"]
    limiter = services["limiter"]
    make_approval_email = services["make_approval_email"]
    make_feedback_reply_email = services["make_feedback_reply_email"]
    mysql = services["mysql"]
    send_email_notification = services["send_email_notification"]
    set_site_setting = services["set_site_setting"]
    slugify = services["slugify"]
    unique_slug = services["unique_slug"]
    upload_to_r2 = services["upload_to_r2"]

    @bp.route("/upload", methods=["GET", "POST"])
    @official_admin_required
    def admin():
        if request.method == "POST":
            # ========== EXISTING PDF FLOW (below, unchanged) ==========
            if "pdf_file" not in request.files:
                return jsonify({"error": "No file part"}), 400
            file = request.files["pdf_file"]
            if file.filename == "" or not allowed_file(file.filename):
                return jsonify({"error": "Invalid file"}), 400

            pdf_bytes = file.read()
            if len(pdf_bytes) > 500 * 1024 * 1024 or not is_valid_pdf(pdf_bytes):
                return jsonify({"error": "Upload a valid PDF up to 500 MB."}), 400
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
            display_title = (
                clean_base.replace("_", " ").replace(" @DocoDive", "").strip()
            )
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
                return (
                    jsonify({"error": "This book already exists in the database."}),
                    400,
                )
            cur.close()

            try:
                pdf_key = generate_r2_key("uploads", clean_base, ".pdf")
                pdf_url = upload_to_r2(
                    pdf_bytes, pdf_key, content_type="application/pdf"
                )
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
                cover_bytes = compress_image(
                    cover_bytes, max_size=(800, 800), quality=80
                )
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

            new_slug = unique_slug(slugify(display_title), cur)
            cur.execute(
                """
                INSERT INTO documents (category_id, title, telegram_link, author, description, image_url, language, slug, approved, uploaded_by, download_count, view_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
            """,
                (
                    cat_id,
                    display_title,
                    pdf_url,
                    author,
                    description,
                    image_url,
                    "English",
                    new_slug,
                    identity()["id"],
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
        return render_template(
            "admin/admin.html",
            categories=categories,
        )

    @bp.route("/pending/count", methods=["GET"])
    @official_admin_required
    def pending_count():
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM documents WHERE approved = 0 AND status = 'pending'"
        )
        count = cur.fetchone()[0]
        cur.close()
        return jsonify({"count": count})

    @bp.route("/pending", methods=["GET"])
    @official_admin_required
    def pending_books():
        page = max(1, request.args.get("page", 1, type=int))
        limit = 9
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM documents WHERE approved=0 AND status='pending'"
        )
        total = cur.fetchone()[0]
        total_pages = max(1, (total + 8) // 9)
        page = min(page, total_pages)
        cur.execute(
            "SELECT d.id,d.title,c.level,d.author,d.created_at,d.telegram_link,d.slug,d.image_url FROM documents d LEFT JOIN categories c ON d.category_id=c.id WHERE d.approved=0 AND d.status='pending' ORDER BY d.id DESC LIMIT %s OFFSET %s",
            (limit, (page - 1) * limit),
        )
        rows = cur.fetchall()
        cur.close()
        books = [
            dict(
                zip(
                    (
                        "id",
                        "title",
                        "level",
                        "author",
                        "created_at",
                        "link",
                        "slug",
                        "image_url",
                    ),
                    row,
                )
            )
            for row in rows
        ]
        return render_template(
            "admin/pending.html",
            books=books,
            page=page,
            total=total,
            total_pages=total_pages,
            per_page=9,
            has_next=page < total_pages,
        )

    @bp.route("/approve/<int:book_id>", methods=["POST"])
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

        # NAYA: Fetch slug for URL
        cur.execute("SELECT slug FROM documents WHERE id = %s", (book_id,))
        slug_row = cur.fetchone()
        book_slug = slug_row[0] if slug_row and slug_row[0] else str(book_id)

        cur.execute(
            "UPDATE documents SET approved = 1, status = 'approved', approved_at = NOW() WHERE id = %s AND status = 'pending'",
            (book_id,),
        )
        mysql.connection.commit()
        if uploader_id:
            cur.execute(
                "SELECT email, username FROM users WHERE id = %s", (uploader_id,)
            )
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
                    f"/book/{book_slug}/{book_id}",
                    {
                        "book_id": book_id,
                        "action_by": "admin",
                        "uploader_id": uploader_id,
                    },
                )
        cur.close()
        return jsonify({"success": True})

    @bp.route("/reject/<int:book_id>", methods=["POST"])
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
        cur.execute(
            "UPDATE documents SET approved = 0, status = 'rejected', approved_at = NULL WHERE id = %s AND status = 'pending'",
            (book_id,),
        )
        mysql.connection.commit()
        if file_link:
            r2_key = extract_r2_key(file_link)
            if r2_key:
                try:
                    delete_from_r2(r2_key)
                except Exception:
                    app.logger.exception(
                        "Storage cleanup failed for rejected book %s", book_id
                    )
        if uploader_id:
            cur.execute(
                "SELECT email, username FROM users WHERE id = %s", (uploader_id,)
            )
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
                    {
                        "book_id": book_id,
                        "action_by": "admin",
                        "uploader_id": uploader_id,
                    },
                )
        cur.close()
        return jsonify({"success": True})

    @bp.route("/approve-all", methods=["POST"])
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

    @bp.route("/books", methods=["GET"])
    @official_admin_required
    def admin_books_list():
        from .directories import books_page

        return books_page(mysql)

    @bp.route("/edit/<int:book_id>", methods=["GET", "POST"])
    @official_admin_required
    def edit_book(book_id):
        cleanup_keys = []
        cur = mysql.connection.cursor()
        if request.method == "POST":
            cur.execute(
                "SELECT telegram_link, image_url FROM documents WHERE id = %s",
                (book_id,),
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
            if not old:
                abort(404)
            if (
                not title
                or not title.strip()
                or len(title) > 255
                or not category_name
                or len(author or "") > 255
                or len(desc or "") > 20000
                or len(language) > 80
            ):
                flash("Please enter valid book details.", "danger")
                return redirect(url_for("admin.edit_book", book_id=book_id))
            cur.execute("SELECT id FROM categories WHERE level=%s", (category_name,))
            if not cur.fetchone():
                abort(400)

            if "pdf_file" in request.files and request.files["pdf_file"].filename != "":
                file = request.files["pdf_file"]
                if not allowed_file(file.filename):
                    return jsonify({"error": "Only PDF files are allowed."}), 400
                pdf_bytes = file.read()

                # ==== NAYA: Size limit ====
                if len(pdf_bytes) > 500 * 1024 * 1024:
                    return (
                        jsonify({"error": "File too large. Maximum 500 MB allowed."}),
                        413,
                    )

                # ==== NAYA: Content validation ====
                if not is_valid_pdf(pdf_bytes):
                    return (
                        jsonify(
                            {"error": "Invalid PDF content. File is not a real PDF."}
                        ),
                        400,
                    )

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
                        cleanup_keys.append(old_key)
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
                                cleanup_keys.append(old_key)
                        cur.execute(
                            "UPDATE documents SET image_url = %s WHERE id = %s",
                            (new_cover_url, book_id),
                        )

            mysql.connection.commit()
            for old_key in cleanup_keys:
                try:
                    delete_from_r2(old_key)
                except Exception:
                    app.logger.exception(
                        "Storage cleanup failed after updating book %s", book_id
                    )
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
        return render_template("admin/edit_book.html", book=book, categories=categories)

    @bp.route("/delete/<int:book_id>", methods=["POST"])
    @official_admin_required
    def delete_book(book_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT telegram_link,image_url FROM documents WHERE id=%s", (book_id,)
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Book not found"}), 404
            cur.execute(
                "DELETE FROM review_likes WHERE review_id IN (SELECT id FROM reviews WHERE book_id=%s)",
                (book_id,),
            )
            for table in (
                "reviews",
                "book_comments",
                "favorites",
                "download_history",
                "user_points",
            ):
                cur.execute(f"DELETE FROM {table} WHERE book_id=%s", (book_id,))
            cur.execute("DELETE FROM documents WHERE id=%s", (book_id,))
            mysql.connection.commit()
        except Exception:
            mysql.connection.rollback()
            app.logger.exception("Book deletion failed for %s", book_id)
            return (
                jsonify({"error": "Book could not be deleted. Please try again."}),
                500,
            )
        finally:
            cur.close()
        # Storage cleanup follows a successful DB commit so a failed deletion leaves the book readable.
        for link in row:
            key = extract_r2_key(link) if link else None
            if key:
                try:
                    delete_from_r2(key)
                except Exception:
                    app.logger.exception(
                        "Storage cleanup failed after deleting book %s", book_id
                    )
        return jsonify({"success": "Book deleted successfully!"})

    @bp.route("/dashboard", methods=["GET"])
    @official_admin_required
    def admin_dashboard():
        return render_template("admin/admin_dashboard.html")

    @bp.route("/api/admin/stats", methods=["GET"])
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
                "total_admins": len(admin_ids() | {owner_id()}),
                "recent_uploads": recent_uploads,
            }
        )

    @bp.route("/users", methods=["GET"])
    @official_admin_required
    def list_users():
        from .directories import users_page

        return users_page(mysql)

    @bp.route("/users/delete/<int:user_id>", methods=["POST"])
    @official_admin_required
    def delete_user(user_id):
        return (
            jsonify(
                error="Direct deletion is disabled. Use a verified user request in Pending Deletions."
            ),
            410,
        )

    @bp.route("/analytics", methods=["GET"])
    @official_admin_required
    def admin_analytics():
        return render_template("admin/admin_analytics.html")

    @bp.route("/trickle-counts", methods=["POST"])
    @official_admin_required
    def trickle_counts():
        return (
            jsonify(
                error="Artificial activity counters are disabled. See recorded activity in Analytics."
            ),
            410,
        )

    @bp.route("/official-profile", methods=["GET", "POST"])
    @official_admin_required
    def admin_official_profile():
        owner_required()
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            if username:
                cur = mysql.connection.cursor()
                cur.execute(
                    "SELECT id FROM users WHERE username = %s AND verified = 1",
                    (username,),
                )
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
        return render_template(
            "admin/admin_official_profile.html", official_user=official_user
        )

    @bp.route("/api/review/<int:review_id>/delete", methods=["POST"])
    @limiter.limit("10 per minute")
    @official_admin_required
    def delete_review_api(review_id):
        if not is_moderator():
            return jsonify({"error": "Unauthorized"}), 403
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM review_likes WHERE review_id=%s", (review_id,))
        cur.execute("DELETE FROM book_comments WHERE parent_id=%s", (-review_id,))
        cur.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})

    @bp.route("/api/comment/<int:comment_id>/delete", methods=["POST"])
    @limiter.limit("10 per minute")
    @official_admin_required
    def delete_comment_api(comment_id):
        if not is_moderator():
            return jsonify({"error": "Unauthorized"}), 403
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM book_comments WHERE parent_id=%s", (comment_id,))
        cur.execute("DELETE FROM book_comments WHERE id = %s", (comment_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})

    @bp.route("/api/comment/<int:comment_id>/reply", methods=["POST"])
    @limiter.limit("10 per minute")
    @official_admin_required
    def reply_as_official_api(comment_id):
        if not is_moderator():
            return jsonify({"error": "Unauthorized"}), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("reply_text"), str):
            return jsonify({"error": "Reply text required"}), 400
        reply_text = data["reply_text"].strip()
        if not reply_text or len(reply_text) > 5000:
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

    @bp.route("/api/review/<int:review_id>/reply", methods=["POST"])
    @limiter.limit("10 per minute")
    @official_admin_required
    def reply_to_review_api(review_id):
        if not is_moderator():
            return jsonify({"error": "Unauthorized"}), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("reply_text"), str):
            return jsonify({"error": "Reply text required"}), 400
        reply_text = data["reply_text"].strip()
        if not reply_text or len(reply_text) > 5000:
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

    @bp.route("/reviews", methods=["GET"])
    @limiter.limit("30 per minute")
    @official_admin_required
    def moderation_panel():
        page, limit, offset = pagination()
        book_filter = request.args.get("book_id", type=int)
        rating = request.args.get("rating", type=int)
        day = request.args.get("day", "")
        days = request.args.get("days", 0, type=int)
        if rating is not None and rating not in range(1, 6):
            abort(400)
        if day:
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                abort(400)
        since = (
            datetime.utcnow() - timedelta(days=min(max(days, 1), 36500))
            if days
            else datetime(1970, 1, 1)
        )
        cur = mysql.connection.cursor()

        def rows_for(table, alias, is_review):
            conditions = [alias + ".created_at>=%s"]
            args = [since]
            if not is_review:
                conditions.append(
                    "(" + alias + ".parent_id IS NULL OR " + alias + ".parent_id=0)"
                )
            if book_filter:
                conditions.append(alias + ".book_id=%s")
                args.append(book_filter)
            if day:
                conditions.append("DATE(" + alias + ".created_at)=%s")
                args.append(day)
            if is_review and rating:
                conditions.append(alias + ".rating=%s")
                args.append(rating)
            score = alias + ".rating" if is_review else "NULL"
            document_join = "LEFT JOIN" if is_review else "JOIN"
            cur.execute(
                f"SELECT {alias}.id,u.username,u.avatar_url,d.title,{alias}.book_id,d.slug,{score},{alias}.comment,{alias}.created_at,u.id FROM {table} {alias} JOIN users u ON u.id={alias}.user_id {document_join} documents d ON d.id={alias}.book_id WHERE "
                + " AND ".join(conditions)
                + f" ORDER BY {alias}.created_at DESC LIMIT %s OFFSET %s",
                (*args, limit + 1, offset),
            )
            return [
                dict(
                    zip(
                        (
                            "id",
                            "username",
                            "avatar",
                            "book_title",
                            "book_id",
                            "book_slug",
                            "rating",
                            "comment",
                            "created_at",
                            "user_id",
                        ),
                        r,
                    )
                )
                for r in cur.fetchall()
            ]

        reviews = rows_for("reviews", "r", True)
        comments = [] if rating else rows_for("book_comments", "c", False)
        has_next = len(reviews) > limit or len(comments) > limit
        reviews = reviews[:limit]
        comments = comments[:limit]
        review_replies = {}
        comment_replies = {}
        parents = [-r["id"] for r in reviews] + [c["id"] for c in comments]
        if parents:
            cur.execute(
                "SELECT parent_id,comment,created_at FROM book_comments WHERE parent_id IN ("
                + ",".join(["%s"] * len(parents))
                + ") ORDER BY created_at",
                tuple(parents),
            )
            for parent, text, created in cur.fetchall():
                target = review_replies if parent < 0 else comment_replies
                target.setdefault(abs(parent), []).append(
                    dict(comment=text, created_at=created)
                )
        cur.close()
        return render_template(
            "admin/admin_moderation.html",
            reviews=reviews,
            comments=comments,
            review_replies=review_replies,
            comment_replies=comment_replies,
            page=page,
            has_next=has_next,
            days=days,
        )

    @bp.route("/feedback/<int:feedback_id>/official-reply", methods=["POST"])
    @limiter.limit("10 per minute")
    @official_admin_required
    def official_feedback_reply(feedback_id):
        if not is_moderator():
            return jsonify({"error": "Unauthorized"}), 403
        reply_text = request.form.get("reply", "").strip()
        if not reply_text or len(reply_text) > 5000:
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

    @bp.route("/feedback/<int:feedback_id>/official-reply/edit", methods=["POST"])
    @official_admin_required
    def edit_official_reply(feedback_id):
        if not is_moderator():
            return jsonify({"error": "Unauthorized"}), 403
        new_reply = request.form.get("reply", "").strip()
        if not new_reply or len(new_reply) > 5000:
            return jsonify({"error": "Reply cannot be empty"}), 400
        cur = mysql.connection.cursor()
        cur.execute(
            "UPDATE user_feedback SET official_reply=%s, official_replied_at=NOW() WHERE id=%s",
            (new_reply, feedback_id),
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})

    @bp.route("/feedback/<int:feedback_id>/official-reply/delete", methods=["POST"])
    @official_admin_required
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

    from .studio import add_studio_pages

    add_studio_pages(bp, services)
    from .insights import add_insights_pages

    add_insights_pages(bp, services)
    app.register_blueprint(bp)

    # Preserve bookmarks and endpoint names; authorize before forwarding old URLs.
    def legacy_redirect(endpoint):
        @official_admin_required
        def forward(**values):
            target = url_for("admin." + endpoint, **values)
            if request.query_string:
                target += "?" + request.query_string.decode("utf-8", errors="replace")
            return redirect(target, code=307 if request.method != "GET" else 302)

        return forward

    app.add_url_rule(
        "/admin",
        endpoint="admin",
        view_func=legacy_redirect("admin"),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/admin/pending/count",
        endpoint="pending_count",
        view_func=legacy_redirect("pending_count"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/pending",
        endpoint="pending_books",
        view_func=legacy_redirect("pending_books"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/approve/<int:book_id>",
        endpoint="approve_book",
        view_func=legacy_redirect("approve_book"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/reject/<int:book_id>",
        endpoint="reject_book",
        view_func=legacy_redirect("reject_book"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/approve-all",
        endpoint="approve_all_books",
        view_func=legacy_redirect("approve_all_books"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/books",
        endpoint="admin_books_list",
        view_func=legacy_redirect("admin_books_list"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/edit/<int:book_id>",
        endpoint="edit_book",
        view_func=legacy_redirect("edit_book"),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/admin/delete/<int:book_id>",
        endpoint="delete_book",
        view_func=legacy_redirect("delete_book"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/dashboard",
        endpoint="admin_dashboard",
        view_func=legacy_redirect("admin_dashboard"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/stats",
        endpoint="admin_stats",
        view_func=legacy_redirect("admin_stats"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/users",
        endpoint="list_users",
        view_func=legacy_redirect("list_users"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/users/delete/<int:user_id>",
        endpoint="delete_user",
        view_func=legacy_redirect("delete_user"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/analytics",
        endpoint="admin_analytics",
        view_func=legacy_redirect("admin_analytics"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/trickle-counts",
        endpoint="trickle_counts",
        view_func=legacy_redirect("admin_dashboard"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/trickle-counts",
        endpoint="trickle_counts_post",
        view_func=legacy_redirect("trickle_counts"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/official-profile",
        endpoint="admin_official_profile",
        view_func=legacy_redirect("admin_official_profile"),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/api/review/<int:review_id>/delete",
        endpoint="delete_review_api",
        view_func=legacy_redirect("delete_review_api"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/comment/<int:comment_id>/delete",
        endpoint="delete_comment_api",
        view_func=legacy_redirect("delete_comment_api"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/comment/<int:comment_id>/reply",
        endpoint="reply_as_official_api",
        view_func=legacy_redirect("reply_as_official_api"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/review/<int:review_id>/reply",
        endpoint="reply_to_review_api",
        view_func=legacy_redirect("reply_to_review_api"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/moderation",
        endpoint="moderation_panel",
        view_func=legacy_redirect("moderation_panel"),
        methods=["GET"],
    )
    app.add_url_rule(
        "/feedback/<int:feedback_id>/official-reply",
        endpoint="official_feedback_reply",
        view_func=legacy_redirect("official_feedback_reply"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/feedback/<int:feedback_id>/official-reply/edit",
        endpoint="edit_official_reply",
        view_func=legacy_redirect("edit_official_reply"),
        methods=["POST"],
    )
    app.add_url_rule(
        "/feedback/<int:feedback_id>/official-reply/delete",
        endpoint="delete_official_reply",
        view_func=legacy_redirect("delete_official_reply"),
        methods=["POST"],
    )
