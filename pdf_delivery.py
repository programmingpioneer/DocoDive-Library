"""Resolve stored R2 references and stream PDFs without exposing provider errors.

No clients, credentials, configuration or network connections are initialized here.
Public fallback URLs must come from ``trusted_public_pdf_url``.
"""

from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
import re
from urllib.parse import unquote, urlsplit

import requests


CHUNK_SIZE = 64 * 1024
_KEY_PREFIXES = ("docodive/", "uploads/", "covers/")
_MAX_INTEGER = (1 << 63) - 1
_MESSAGES = {
    "missing": "This PDF is not available.",
    "range": "The requested PDF range is not available.",
    "authorization": "PDF storage access could not be confirmed.",
    "unavailable": "The PDF is temporarily unavailable.",
}


class PDFDeliveryError(Exception):
    def __init__(self, category="unavailable", headers=None):
        self.category = category if category in _MESSAGES else "unavailable"
        self.status_code = {"missing": 404, "range": 416}.get(self.category, 503)
        self.headers = dict(headers or {})
        super().__init__(_MESSAGES[self.category])


def _url(value):
    if (not isinstance(value, str) or not value or value.strip() != value
            or "\\" in value or re.search(r"[\x00-\x1f\x7f]", value)):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return None
        port = parsed.port
        if port == 0:
            return None
        return parsed
    except (ValueError, TypeError):
        return None


def _origin(parsed):
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


def _path(parsed):
    try:
        return unquote(parsed.path, encoding="utf-8", errors="strict")
    except (UnicodeError, ValueError):
        return None


def _key(value):
    if (not isinstance(value, str) or not value.startswith(_KEY_PREFIXES)
            or "\\" in value or re.search(r"[\x00-\x1f\x7f]", value)):
        return None
    try:
        if len(value.encode("utf-8")) > 1024:
            return None
    except UnicodeError:
        return None
    parts = value.split("/")
    if any(part in ("", ".", "..") or re.fullmatch(r"(?:\.|%2e){1,2}", part, re.I)
           for part in parts):
        return None
    # A second URL decode must not turn a stored URL into a traversal path.
    if re.search(r"%2f|%5c|%00|%0a|%0d", value, re.I):
        return None
    return value


def _under_path(path, prefix):
    prefix = prefix.rstrip("/")
    if path is None or not path.startswith(prefix + "/"):
        return None
    return path[len(prefix) + 1:]


def resolve_r2_key(reference, public_base="", bucket="", endpoint_url=""):
    """Resolve a literal app key or an exact configured public/S3 URL.

    Raw keys are not URL-decoded. URL paths are decoded once and their query and
    fragment are never included in the object key. No filename is fabricated.
    """
    if isinstance(reference, str) and reference.startswith(_KEY_PREFIXES):
        return _key(reference)
    parsed = _url(reference)
    if parsed is None:
        return None
    path = _path(parsed)
    endpoint = _url(endpoint_url)
    if endpoint is not None and bucket and not endpoint.query and not endpoint.fragment:
        endpoint_path = _path(endpoint)
        remainder = _under_path(path, endpoint_path or "")
        if _origin(parsed) == _origin(endpoint) and remainder is not None:
            prefix = bucket + "/"
            if remainder.startswith(prefix):
                return _key(remainder[len(prefix):])
            return None
        virtual_origin = (endpoint.scheme, bucket.lower() + "." + endpoint.hostname.lower(),
                          endpoint.port or (443 if endpoint.scheme == "https" else 80))
        if _origin(parsed) == virtual_origin:
            return _key(remainder)
    public = _url(public_base)
    if (public is not None and not public.query and not public.fragment
            and _origin(parsed) == _origin(public)):
        return _key(_under_path(path, _path(public) or ""))
    return None


def trusted_public_pdf_url(reference, public_base, key):
    """Keep only an original unsigned URL at the configured public origin/key."""
    parsed = _url(reference)
    if (parsed is None or parsed.query or parsed.fragment
            or resolve_r2_key(reference, public_base=public_base) != _key(key)):
        return None
    if _key(key) is None:
        return None
    return reference


def _integer(value):
    if isinstance(value, bool):
        return None
    text = str(value)
    if not re.fullmatch(r"[0-9]{1,19}", text):
        return None
    number = int(text)
    return number if number <= _MAX_INTEGER else None


def _range(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64 or re.search(r"[\x00-\x1f\x7f]", value):
        raise PDFDeliveryError("range")
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", value.strip(), re.I)
    if not match or not any(match.groups()):
        raise PDFDeliveryError("range")
    first = _integer(match[1]) if match[1] else None
    last = _integer(match[2]) if match[2] else None
    if ((match[1] and first is None) or (match[2] and last is None)
            or (first is not None and last is not None and first > last)
            or (first is None and last == 0)):
        raise PDFDeliveryError("range")
    return "bytes=" + (str(first) if first is not None else "") + "-" + (str(last) if last is not None else "")


def _header(headers, name):
    for key, value in (headers or {}).items():
        if str(key).lower() == name.lower():
            return value
    return None


def _error_range(headers):
    value = _header(headers, "Content-Range")
    if isinstance(value, str) and re.fullmatch(r"bytes \*/[0-9]{1,19}", value):
        total = _integer(value.split("/")[1])
        if total is not None:
            return {"Content-Range": "bytes */" + str(total)}
    return {}


def _provider_error(error):
    if isinstance(error, PDFDeliveryError):
        return error
    response = getattr(error, "response", None)
    response = response if isinstance(response, dict) else {}
    metadata = response.get("ResponseMetadata", {})
    code = str(response.get("Error", {}).get("Code", ""))
    status = metadata.get("HTTPStatusCode")
    if code == "NoSuchBucket":
        return PDFDeliveryError("unavailable")
    if code in ("NoSuchKey", "NotFound", "404") or status == 404:
        return PDFDeliveryError("missing")
    if code in ("InvalidRange", "RequestedRangeNotSatisfiable", "416") or status == 416:
        return PDFDeliveryError("range", _error_range(metadata.get("HTTPHeaders")))
    if status in (401, 403) or code in (
            "AccessDenied", "Unauthorized", "InvalidAccessKeyId", "SignatureDoesNotMatch",
            "ExpiredToken", "InvalidToken", "TokenRefreshRequired", "401", "403"):
        return PDFDeliveryError("authorization")
    return PDFDeliveryError("unavailable")


def _last_modified(value):
    if not isinstance(value, datetime) and (
            not isinstance(value, str) or len(value) > 128 or re.search(r"[\x00-\x1f\x7f]", value)):
        return None
    try:
        date = value if isinstance(value, datetime) else parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return format_datetime(date.astimezone(timezone.utc), usegmt=True)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None


def _safe_headers(metadata, status, requested_range):
    headers = {"Content-Type": "application/pdf", "Accept-Ranges": "bytes"}
    length = _integer(_header(metadata, "Content-Length"))
    if length is not None:
        headers["Content-Length"] = str(length)
    etag = _header(metadata, "ETag")
    if isinstance(etag, str) and re.fullmatch(r'(?:W/)?"[\x21\x23-\x7e]{0,200}"', etag):
        headers["ETag"] = etag
    modified = _last_modified(_header(metadata, "Last-Modified"))
    if modified:
        headers["Last-Modified"] = modified
    content_range = _header(metadata, "Content-Range")
    if status == 206:
        match = re.fullmatch(r"bytes ([0-9]{1,19})-([0-9]{1,19})/([0-9]{1,19})", content_range or "")
        if not match or requested_range is None:
            raise PDFDeliveryError()
        start, end, total = (_integer(value) for value in match.groups())
        if None in (start, end, total) or not 0 <= start <= end < total:
            raise PDFDeliveryError()
        requested_first, requested_last = requested_range[6:].split("-")
        expected_start = int(requested_first) if requested_first else max(0, total - int(requested_last))
        expected_end = min(int(requested_last), total - 1) if requested_first and requested_last else total - 1
        if start != expected_start or end != expected_end or (length is not None and length != end - start + 1):
            raise PDFDeliveryError()
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(end - start + 1)
    elif content_range is not None:
        raise PDFDeliveryError()
    return headers


def _chunks(source, public=False):
    if public:
        iterator = source.iter_content(chunk_size=CHUNK_SIZE)
    elif hasattr(source, "iter_chunks"):
        iterator = source.iter_chunks(chunk_size=CHUNK_SIZE)
    else:
        iterator = iter(lambda: source.read(CHUNK_SIZE), b"")
    for chunk in iterator:
        if not chunk:
            continue
        if not isinstance(chunk, bytes):
            raise PDFDeliveryError()
        for offset in range(0, len(chunk), CHUNK_SIZE):
            yield chunk[offset:offset + CHUNK_SIZE]


class _PDFResource:
    def __init__(self, status, headers, closer, chunks=(), prefix=()):
        self.status_code, self.headers = status, headers
        self._closer, self._chunks, self._prefix = closer, iter(chunks), tuple(prefix)
        self._closed = False

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._closer()
            except Exception:
                pass

    def iter_chunks(self):
        try:
            for chunk in self._prefix:
                if self._closed:
                    return
                yield chunk
            while not self._closed:
                try:
                    chunk = next(self._chunks)
                except StopIteration:
                    break
                yield chunk
        except Exception:
            raise PDFDeliveryError() from None
        finally:
            self.close()


def _resource(status, metadata, closer, chunks, requested_range, head):
    headers = _safe_headers(metadata, status, requested_range)
    content_type = str(_header(metadata, "Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type not in ("application/pdf", "application/x-pdf", "application/octet-stream", "binary/octet-stream", ""):
        raise PDFDeliveryError()
    if head:
        # Legacy approved PDFs may have generic metadata. HEAD carries no bytes;
        # full GET still checks the actual PDF header before returning a stream.
        return _PDFResource(status, headers, closer)
    iterator = iter(chunks)
    prefix = []
    # A nonzero byte range cannot contain the PDF header. The caller's approved
    # PDF namespace gate and validated Content-Range permit legacy generic MIME.
    starts_at_zero = status == 200 or headers.get("Content-Range", "").startswith("bytes 0-")
    if starts_at_zero:
        probe_length = min(5, int(headers["Content-Length"])) if status == 206 else 5
        beginning = b""
        while len(beginning) < probe_length:
            try:
                chunk = next(iterator)
            except StopIteration:
                raise PDFDeliveryError() from None
            prefix.append(chunk)
            beginning += chunk[:probe_length - len(beginning)]
        if beginning != b"%PDF-"[:probe_length]:
            raise PDFDeliveryError()
    return _PDFResource(status, headers, closer, iterator, prefix)


def _open_sdk(client, bucket, key, requested_range, head):
    arguments = {"Bucket": bucket, "Key": key}
    if requested_range and not head:
        arguments["Range"] = requested_range
    data = client.head_object(**arguments) if head else client.get_object(**arguments)
    body = data.get("Body")
    closer = body.close if body is not None else lambda: None
    try:
        status = data.get("ResponseMetadata", {}).get("HTTPStatusCode", 206 if data.get("ContentRange") else 200)
        if status not in (200, 206) or (head and status != 200) or (not head and body is None):
            raise PDFDeliveryError()
        metadata = {"Content-Type": data.get("ContentType"), "Content-Length": data.get("ContentLength"),
                    "Content-Range": data.get("ContentRange"), "ETag": data.get("ETag"),
                    "Last-Modified": data.get("LastModified")}
        return _resource(status, metadata, closer, () if head else _chunks(body), requested_range, head)
    except Exception:
        try:
            closer()
        except Exception:
            pass
        raise


def _open_public(http_client, public_url, requested_range, head):
    parsed = _url(public_url)
    if parsed is None or parsed.query or parsed.fragment:
        raise PDFDeliveryError()
    headers = {"Accept": "application/pdf", "Accept-Encoding": "identity"}
    if requested_range and not head:
        headers["Range"] = requested_range
    method = http_client.head if head else http_client.get
    response = method(public_url, headers=headers, timeout=(5, 30), stream=True, allow_redirects=False)
    try:
        if response.status_code not in (200, 206) or (head and response.status_code != 200):
            raise PDFDeliveryError()
        if str(_header(response.headers, "Content-Encoding") or "identity").strip().lower() != "identity":
            raise PDFDeliveryError()
        return _resource(response.status_code, response.headers, response.close,
                         () if head else _chunks(response, public=True), requested_range, head)
    except Exception:
        try:
            response.close()
        except Exception:
            pass
        raise


def open_pdf_object(client, bucket, key, *, range_header=None, head=False,
                    public_url=None, http_client=requests):
    """Open a bounded SDK stream, optionally falling back to a trusted public URL.

    Failed public fallback preserves the original SDK error classification. No
    provider message, XML body, signed URL or arbitrary provider header escapes.
    The caller must authorize the reader and approved ``docodive/uploads/*.pdf``
    record first. Generic legacy MIME is allowed for HEAD and validated partial
    responses; full GET still proves the PDF header, and explicit XML/HTML or
    other incompatible content types are always rejected.
    """
    if _key(key) is None:
        raise PDFDeliveryError("missing")
    requested_range = None if head else _range(range_header)
    try:
        return _open_sdk(client, bucket, key, requested_range, head)
    except Exception as error:
        failure = _provider_error(error)
    if public_url:
        try:
            return _open_public(http_client, public_url, requested_range, head)
        except Exception:
            pass
    raise failure from None
