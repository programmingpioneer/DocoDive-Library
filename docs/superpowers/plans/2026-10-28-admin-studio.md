# Admin Studio implementation

Scope: attached PioneerDoc request; local files only. User explicitly delegated implementation choices and will run the app/browser/staging checks. No credentials, environment edits, deployment, or database access. Work in the supplied checkout so the user receives updated files there; preserve the pre-existing fly.toml deletion.

Design: a Flask Blueprint at /admin-studio with independent studio session keys and existing password hashes. Resolve roles through existing site_settings; official_user_id remains the bootstrap owner. User login never creates a Studio session. Retain old endpoints as guarded compatibility redirects. Move all templates into user/ or admin/ and preserve lesson subdirectories. Shared utilities stay in app.py; inject dependencies into Blueprint registration to avoid circular imports when running python app.py.

1. Add local regression tests for authentication isolation, CSRF, validation, and compatibility mappings. Use a separate Flask test app and fake database boundary, never import production configuration.
2. Extract existing admin handlers into admin/admin_routes.py; add login/logout and role helpers in admin/security.py. Register after user routes. Move templates and update template inheritance/references.
3. Add responsive Studio layout, dashboard, paginated/searchable books/users/pending lists, user editing and admin roles, review/comment/suggestion moderation, leaderboard point adjustments, settings and editable home/about/learning content using existing site_settings.
4. Add scoped user.css and user.js for consistent sizing/focus/grid behavior and AJAX CSRF. Retain existing lesson content and user features. Remove admin navigation and privileges from public templates.
5. Close missing CSRF/input/HTML escaping checks, avoid session-sensitive caching, preserve existing limiter/password/security configuration. Keep destructive operations confirmed and protect owner/self.
6. Run local syntax, templates, route construction and regression tests with synthetic data. Record limitations and provide full changed files in the working tree plus a copyable source bundle and manual test checklist.

Review focus: user login cannot authorize Studio; revoked/deleted Studio account loses access; legacy POSTs retain CSRF and admin guards; user-owned suggestion editing still works; no new schema/env requirements; python app.py and gunicorn registration avoid circular imports.

Progress: implementation complete; 21 isolated automated tests pass. 112 templates parse, key public/Studio pages render with synthetic data, their inline JavaScript and JSON-LD parse, all static JavaScript parses, Python syntax and diff whitespace checks pass. Final read-only reviewer findings (legal SEO endpoint names and missing review-reply UI) resolved. Full browser/database/integration checks remain with the user as agreed. No commit/push performed.

Ruling: user explicitly expanded scope to latest SEO and app.py organization on 29 October. Added seo.py with canonical/indexing policy and bounded sitemaps; moved 68 lesson collections to learning_content.py and verified exact AST equivalence against original source. Official Google documentation consulted; no project live/staging URL accessed.

Ruling: existing site_settings keys hold roles/content to avoid requiring a new schema or credentials. Existing official_user_id is the owner bootstrap assumption. Integration verification uses a separate Flask app and synthetic DB responses because actual app import initializes configured integrations.

Ruling: latest user request authorizes our own local tests; browser prohibition remains respected. Tests cover routing/rendering/metadata/auth behavior, not live SQL or external integrations. LOCAL_HANDOVER.md contains the exact boundaries and final local checklist.
