"""Public metadata and bounded XML sitemaps; no credentials or startup I/O."""

from urllib.parse import urlencode, urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

from flask import Response, abort, request, url_for

PUBLIC_ENDPOINTS = {
    "home",
    "all_books",
    "book_detail",
    "learning_hub",
    "category_module",
    "python_practice",
    "reviews_page",
    "leaderboard",
    "user_feedback",
    "privacy_policy",
    "terms_of_service",
    "data_deletion",
    "cookies_policy",
    "contact_page",
    "community_guidelines",
    "accessibility_page",
}
SITEMAP_SIZE = 5000
XML_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def register_seo(app, services):
    def absolute(path):
        configured = app.config.get("PUBLIC_SITE_URL", "").rstrip("/")
        parsed = urlsplit(configured)
        base = (
            configured
            if parsed.scheme in ("http", "https") and parsed.netloc
            else request.url_root.rstrip("/")
        )
        return base + path

    def canonical_url():
        args = {}
        for key in ("page", "category"):
            value = request.args.get(key)
            if key == "page":
                value = request.args.get(key, 1, type=int)
                if value <= 1:
                    continue
            if value:
                args[key] = value
        return absolute(request.path) + ("?" + urlencode(args) if args else "")

    def indexable():
        return request.endpoint in PUBLIC_ENDPOINTS and not any(
            request.args.get(key)
            for key in ("q", "search_query", "author", "sort", "offset")
        )

    @app.context_processor
    def seo_context():
        return dict(
            seo_canonical=canonical_url(),
            seo_indexable=indexable(),
            seo_absolute=absolute,
            seo_home=absolute("/"),
        )

    @app.after_request
    def indexing_headers(response):
        if response.status_code >= 400 or (
            request.endpoint != "static"
            and not indexable()
            and request.endpoint
            not in ("sitemap", "sitemap_books", "sitemap_pages", "robots")
        ):
            response.headers["X-Robots-Tag"] = "noindex, follow"
        return response

    def fetch(sql, args=()):
        cursor = services["mysql"].connection.cursor()
        try:
            cursor.execute(sql, args)
            return cursor.fetchall()
        finally:
            cursor.close()

    def xml_response(root):
        return Response(
            tostring(root, encoding="utf-8", xml_declaration=True),
            mimetype="application/xml",
        )

    def urlset(paths):
        root = Element("urlset", xmlns=XML_NS)
        for path in dict.fromkeys(paths):
            SubElement(SubElement(root, "url"), "loc").text = absolute(path)
        return xml_response(root)

    def sitemap():
        count = fetch("SELECT COUNT(*) FROM documents WHERE approved=1")[0][0]
        root = Element("sitemapindex", xmlns=XML_NS)
        paths = [url_for("sitemap_pages")] + [
            url_for("sitemap_books", page=page)
            for page in range(1, (count + SITEMAP_SIZE - 1) // SITEMAP_SIZE + 1)
        ]
        for path in paths:
            SubElement(SubElement(root, "sitemap"), "loc").text = absolute(path)
        return xml_response(root)

    def sitemap_books(page):
        if page < 1:
            abort(404)
        rows = fetch(
            "SELECT id,slug FROM documents WHERE approved=1 ORDER BY id LIMIT %s OFFSET %s",
            (SITEMAP_SIZE, (page - 1) * SITEMAP_SIZE),
        )
        if not rows:
            abort(404)
        return urlset(
            url_for("book_detail", book_id=row[0], slug=row[1] or str(row[0]))
            for row in rows
        )

    def sitemap_pages():
        paths = [
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.endpoint in PUBLIC_ENDPOINTS
            and not rule.arguments
            and "GET" in rule.methods
        ]
        for (name,) in fetch("SELECT level FROM categories ORDER BY level"):
            slug = services["category_to_slug"](name)
            paths.append(url_for("learning_hub", category_slug=slug))
            modules = (
                services["IELTS_MODULES"]
                if slug == "ielts"
                else services["GENERIC_MODULES"]
            )
            paths.extend(
                url_for("category_module", slug=slug, module=module["slug"])
                for module in modules
            )
        return urlset(paths)

    def robots():
        # Allow crawlers to see noindex on private/login pages; authorization protects data.
        return Response(
            "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /internal/\n"
            + "Sitemap: "
            + absolute(url_for("sitemap"))
            + "\n",
            mimetype="text/plain",
        )

    app.add_url_rule("/sitemap.xml", "sitemap", sitemap)
    app.add_url_rule("/sitemaps/pages.xml", "sitemap_pages", sitemap_pages)
    app.add_url_rule("/sitemaps/books-<int:page>.xml", "sitemap_books", sitemap_books)
    app.add_url_rule("/robots.txt", "robots", robots)
