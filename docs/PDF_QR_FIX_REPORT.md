# PDF delivery and in-page QR popup

6 November 2026. Local source and synthetic fixtures only.

## Findings and changes

The old reader/download routes could replace an unrecognized stored reference with a guessed slug filename. Actual upload keys include their own filenames and unique suffixes. Key resolution now preserves literal app keys and decodes only the paths of exact configured public or S3 endpoint URLs. It removes URL query/signature data from the key and rejects unrelated hosts, buckets and traversal paths. It does not invent a filename.

Read Online now embeds the authenticated, same-origin `/book/<id>/pdf` endpoint. Download uses `/book/<id>/download`. Each request obtains the object server-side rather than reusing a short-lived browser storage URL. GET, HEAD and single byte ranges are supported; If-Range safely returns the complete current object. Streaming uses bounded 64 KiB chunks and closes resources. The response validates PDF content/metadata and never passes a provider XML error to the reader.

If SDK access fails, fallback is allowed only for the original unsigned stored URL at the exact configured public base and object key. It does not create public access, follow redirects, forward user credentials or fetch arbitrary stored hosts. If neither path works, the app returns a friendly 404/503 page. Unknown references remain unavailable rather than being guessed.

Downloads are recorded once, after storage accepts a full attachment request. Reader requests, ranges, HEAD requests and storage failures are excluded. The reader's duplicate tracking POSTs were removed. A metrics failure does not prevent an already accepted PDF response.

QR Code opens one animated native dialog on the current page from Book Details, Home and Learning Hub previews. Each book requests its own same-origin QR image. The dialog supports Escape, backdrop/close, focus return, retry, reduced motion and light/dark tokens. Its white QR paper is intentional for scanning. The duplicate legacy overlay and unused QR CDN script were removed. Recovery page support/theme controls now remain in the normal layout on small screens.

## Validation

- 214 isolated automated tests pass. Added coverage for exact key resolution, authorization errors, public fallback restrictions, content/range validation, stream closure, route gates, metric failures, filenames, stable reader links and QR behavior.
- 98 synthetic public/lesson renders pass; 155 Jinja templates, 25 static scripts and 393 rendered inline scripts parse successfully.
- Local Chrome checks use generated sample PDF/QR data only. The sample PDF renders in the browser. QR images load from Book Details, Home and Learning Hub without navigation; changing the book changes its QR. Escape closes only the QR dialog and restores focus to its button while the preview remains open. Desktop and 320/390 px phone views, light/dark modes and friendly error layouts were checked.
- Browser screenshots and observations: `deliverables/pdf-qr-fix/`. No actual storage credentials, private documents, database, email, staging or production were accessed.

## What the owner still verifies locally

Restart the app and refresh with Ctrl+F5. Open a book, Read Online, Download and QR Code. No new package or SQL migration is needed for this fix.

The reported storage authorization itself cannot be confirmed from a signed URL or fixed by UI changes. If the app still shows the unavailable page, check the existing local R2 configuration yourself: the token needs Object Read access to the intended bucket (Read & Write when uploading), and the endpoint/account and bucket must match. Check the computer's UTC clock as well. Do not send credentials or signed URLs in chat. Read permission does not require making the bucket public.

Cloudflare documents that presigning is local and does not confirm server authorization, and that signatures expire: [presigned URL documentation](https://developers.cloudflare.com/r2/api/s3/presigned-urls/). Its [error codes](https://developers.cloudflare.com/r2/api/error-codes/) and [token documentation](https://developers.cloudflare.com/r2/api/tokens/) describe authentication and bucket permissions. The exact cause of the owner's Unauthorized response remains unverified.

All PDF bytes now pass through the application, so concurrency and outbound bandwidth depend on the application's server capacity. Range support and bounded streaming limit memory use; an interrupted stream can still end a transfer after response headers have been sent. Download totals represent accepted initiations, not proof that the entire file was saved.
