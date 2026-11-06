"""Storage parsing and bounded streaming with synthetic SDK/HTTP objects only."""

from datetime import datetime, timezone
import io
import unittest

from botocore.exceptions import ClientError

from pdf_delivery import (PDFDeliveryError, open_pdf_object, resolve_r2_key,
                          trusted_public_pdf_url)


KEY = "docodive/uploads/Shared_Title_0123456789abcdef.pdf"
PUBLIC = "https://files.example.test/library"
ENDPOINT = "https://account.r2.cloudflarestorage.com"
PDF = b"%PDF-1.7\n" + b"x" * 150000


def sdk_error(code, status, **headers):
    return ClientError({"Error": {"Code": code, "Message": "PRIVATE PROVIDER DETAIL"},
                        "ResponseMetadata": {"HTTPStatusCode": status, "HTTPHeaders": headers}},
                       "GetObject")


class Body:
    def __init__(self, content):
        self.raw = io.BytesIO(content)
        self.read_sizes = []
        self.close_count = 0

    def read(self, size):
        self.read_sizes.append(size)
        return self.raw.read(size)

    def close(self):
        self.close_count += 1
        self.raw.close()


class SDK:
    def __init__(self, content=PDF, error=None, **metadata):
        self.body, self.error, self.calls = Body(content), error, []
        self.metadata = dict(ContentType="application/pdf", ContentLength=len(content),
                             ETag='"sample-etag"', LastModified=datetime(2026, 11, 6, tzinfo=timezone.utc),
                             ResponseMetadata={"HTTPStatusCode": 200})
        self.metadata.update(metadata)

    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs))
        if self.error:
            raise self.error
        return dict(self.metadata, Body=self.body)

    def head_object(self, **kwargs):
        self.calls.append(("head", kwargs))
        if self.error:
            raise self.error
        return self.metadata


class HTTPResponse:
    def __init__(self, content=PDF, status=200, headers=None):
        self.content_bytes, self.status_code, self.close_count = content, status, 0
        self.headers = {"Content-Type": "application/pdf", "Content-Length": str(len(content)),
                        "Accept-Ranges": "bytes", **(headers or {})}
        self.chunk_sizes = []

    def iter_content(self, chunk_size):
        self.chunk_sizes.append(chunk_size)
        for start in range(0, len(self.content_bytes), chunk_size):
            yield self.content_bytes[start:start + chunk_size]

    def close(self):
        self.close_count += 1


class HTTP:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response or HTTPResponse(), error, []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if self.error:
            raise self.error
        return self.response

    def head(self, url, **kwargs):
        self.calls.append(("head", url, kwargs))
        if self.error:
            raise self.error
        return self.response


class R2ReferenceTests(unittest.TestCase):
    def resolve(self, value, **changes):
        return resolve_r2_key(value, public_base=changes.get("public_base", PUBLIC),
                              bucket="bucket", endpoint_url=ENDPOINT)

    def test_raw_and_configured_url_shapes_resolve_the_exact_object_key(self):
        cases = [
            (KEY, KEY),
            ("docodive/uploads/literal%20plus+name.pdf", "docodive/uploads/literal%20plus+name.pdf"),
            (PUBLIC + "/" + KEY + "?old-signature=discard#fragment", KEY),
            (PUBLIC + "/docodive/uploads/Space%20and+Plus%2520.pdf", "docodive/uploads/Space and+Plus%20.pdf"),
            (ENDPOINT + "/bucket/" + KEY, KEY),
            ("https://bucket.account.r2.cloudflarestorage.com/" + KEY + "?discard=1", KEY),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.resolve(value), expected)
        self.assertEqual(self.resolve(PUBLIC + "/" + KEY, public_base=PUBLIC + "/"), KEY)

    def test_bucket_and_object_prefix_with_same_name_are_not_confused(self):
        value = ENDPOINT + "/docodive/" + KEY
        self.assertEqual(resolve_r2_key(value, bucket="docodive", endpoint_url=ENDPOINT), KEY)
        self.assertEqual(resolve_r2_key("https://public.example.test/" + KEY,
                                       public_base="https://public.example.test", bucket="docodive"), KEY)

    def test_untrusted_hosts_buckets_traversal_and_malformed_references_are_rejected(self):
        values = [None, "", "file.pdf", "/" + KEY, "https://evil.example.test/" + KEY,
                  "https://other.r2.dev/" + KEY, ENDPOINT + "/wrong-bucket/" + KEY,
                  "https://wrong.account.r2.cloudflarestorage.com/" + KEY,
                  "https://files.example.test/library-evil/" + KEY,
                  "https://user@files.example.test/library/" + KEY,
                  "docodive/../secret.pdf", "docodive/uploads/./file.pdf",
                  "docodive/uploads/file\r\n.pdf", "docodive\\uploads\\file.pdf",
                  PUBLIC + "/docodive/uploads/%2e%2e/secret.pdf",
                  PUBLIC + "/docodive/uploads/%252e%252e/secret.pdf",
                  PUBLIC + "/docodive/uploads/%2F..%2Fsecret.pdf",
                  PUBLIC + "/docodive/uploads/file%00.pdf"]
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(self.resolve(value))

    def test_public_fallback_preserves_only_the_original_trusted_public_reference(self):
        url = PUBLIC + "/" + KEY
        self.assertEqual(trusted_public_pdf_url(url, PUBLIC, KEY), url)
        self.assertIsNone(trusted_public_pdf_url(KEY, PUBLIC, KEY))
        self.assertIsNone(trusted_public_pdf_url(ENDPOINT + "/bucket/" + KEY, PUBLIC, KEY))
        self.assertIsNone(trusted_public_pdf_url(url, PUBLIC, "docodive/uploads/different.pdf"))
        self.assertIsNone(trusted_public_pdf_url("https://evil.example.test/" + KEY, PUBLIC, KEY))
        self.assertIsNone(trusted_public_pdf_url(url + "?secret=query", PUBLIC, KEY))


class PDFObjectTests(unittest.TestCase):
    def test_sdk_stream_uses_bounded_reads_and_closes_once_on_exhaustion(self):
        sdk, http = SDK(), HTTP()
        resource = open_pdf_object(sdk, "bucket", KEY, http_client=http)
        self.assertEqual(resource.status_code, 200)
        self.assertEqual(resource.headers["Content-Length"], str(len(PDF)))
        self.assertEqual(resource.headers["ETag"], '"sample-etag"')
        self.assertEqual(resource.headers["Last-Modified"], "Fri, 06 Nov 2026 00:00:00 GMT")
        chunks = list(resource.iter_chunks())
        self.assertEqual(b"".join(chunks), PDF)
        self.assertTrue(all(len(chunk) <= 65536 for chunk in chunks))
        self.assertTrue(all(size == 65536 for size in sdk.body.read_sizes))
        resource.close()
        self.assertEqual(sdk.body.close_count, 1)
        self.assertEqual(http.calls, [])

    def test_partial_sdk_response_preserves_single_range_and_metadata(self):
        sdk = SDK(b"bytes", ContentLength=5, ContentRange="bytes 10-14/100",
                  ResponseMetadata={"HTTPStatusCode": 206})
        resource = open_pdf_object(sdk, "bucket", KEY, range_header="bytes=10-14")
        self.assertEqual(sdk.calls, [("get", {"Bucket": "bucket", "Key": KEY, "Range": "bytes=10-14"})])
        self.assertEqual(resource.status_code, 206)
        self.assertEqual(resource.headers["Content-Range"], "bytes 10-14/100")
        self.assertEqual(b"".join(resource.iter_chunks()), b"bytes")

    def test_head_ignores_range_and_does_not_read_a_body(self):
        sdk = SDK()
        resource = open_pdf_object(sdk, "bucket", KEY, range_header="not-a-range", head=True)
        self.assertEqual(sdk.calls, [("head", {"Bucket": "bucket", "Key": KEY})])
        self.assertEqual(resource.status_code, 200)
        self.assertEqual(list(resource.iter_chunks()), [])
        self.assertEqual(sdk.body.read_sizes, [])

    def test_head_allows_legacy_generic_pdf_metadata_without_reading_bytes(self):
        for content_type in ["application/octet-stream", "binary/octet-stream", None]:
            with self.subTest(content_type=content_type):
                sdk = SDK(ContentType=content_type)
                resource = open_pdf_object(sdk, "bucket", KEY, head=True)
                self.assertEqual(resource.status_code, 200)
                self.assertEqual(resource.headers["Content-Type"], "application/pdf")
                self.assertEqual(sdk.body.read_sizes, [])
                resource.close()
                http = HTTP(HTTPResponse(headers={"Content-Type": content_type}))
                resource = open_pdf_object(SDK(error=sdk_error("AccessDenied", 403)), "bucket", KEY,
                                           head=True, public_url=PUBLIC + "/" + KEY, http_client=http)
                self.assertEqual(resource.status_code, 200)
                self.assertEqual(http.response.chunk_sizes, [])
                resource.close()
                self.assertEqual(http.response.close_count, 1)

    def test_invalid_ranges_fail_before_any_sdk_or_public_call(self):
        for value in ["", "bytes=0-1,4-8", "bytes=-0", "bytes=3-2", "bytes=-", "items=0-5",
                      "bytes=99999999999999999999999-", "bytes=0-1\r\nInjected: yes"]:
            with self.subTest(value=value):
                sdk, http = SDK(), HTTP()
                with self.assertRaises(PDFDeliveryError) as caught:
                    open_pdf_object(sdk, "bucket", KEY, range_header=value, public_url=PUBLIC + "/" + KEY, http_client=http)
                self.assertEqual((caught.exception.status_code, caught.exception.category), (416, "range"))
                self.assertEqual(sdk.calls, [])
                self.assertEqual(http.calls, [])

    def test_valid_open_ended_and_suffix_ranges_reach_sdk(self):
        for value, content_range in [("bytes=10-", "bytes 10-14/15"), ("bytes=-5", "bytes 10-14/15")]:
            sdk = SDK(b"bytes", ContentRange=content_range, ResponseMetadata={"HTTPStatusCode": 206})
            resource = open_pdf_object(sdk, "bucket", KEY, range_header=value)
            self.assertEqual(sdk.calls[0][1]["Range"], value)
            resource.close()

    def test_short_range_from_zero_does_not_require_unrequested_header_bytes(self):
        sdk = SDK(b"%P", ContentType="application/octet-stream", ContentRange="bytes 0-1/100", ResponseMetadata={"HTTPStatusCode": 206})
        resource = open_pdf_object(sdk, "bucket", KEY, range_header="bytes=0-1")
        self.assertEqual(resource.status_code, 206)
        self.assertEqual(b"".join(resource.iter_chunks()), b"%P")
        http = HTTP(HTTPResponse(b"%", 206, {"Content-Type": "", "Content-Range": "bytes 0-0/100"}))
        resource = open_pdf_object(SDK(error=sdk_error("AccessDenied", 403)), "bucket", KEY,
                                   range_header="bytes=0-0", public_url=PUBLIC + "/" + KEY, http_client=http)
        self.assertEqual(b"".join(resource.iter_chunks()), b"%")

    def test_legacy_generic_mime_allows_valid_nonzero_partial_pdf_seeks(self):
        for content_type in ["application/octet-stream", "binary/octet-stream", None]:
            with self.subTest(content_type=content_type):
                sdk = SDK(b"bytes", ContentType=content_type, ContentRange="bytes 10-14/100",
                          ResponseMetadata={"HTTPStatusCode": 206})
                resource = open_pdf_object(sdk, "bucket", KEY, range_header="bytes=10-14")
                self.assertEqual(b"".join(resource.iter_chunks()), b"bytes")
                self.assertEqual(len(sdk.calls), 1)
                http = HTTP(HTTPResponse(b"bytes", 206, {"Content-Type": content_type,
                                                        "Content-Range": "bytes 10-14/100"}))
                resource = open_pdf_object(SDK(error=sdk_error("AccessDenied", 403)), "bucket", KEY,
                                           range_header="bytes=10-14", public_url=PUBLIC + "/" + KEY, http_client=http)
                self.assertEqual(b"".join(resource.iter_chunks()), b"bytes")
                self.assertEqual(len(http.calls), 1)

    def test_public_compression_cannot_corrupt_forwarded_byte_ranges_or_lengths(self):
        http = HTTP(HTTPResponse(PDF, 200, {"Content-Encoding": "gzip"}))
        with self.assertRaises(PDFDeliveryError):
            open_pdf_object(SDK(error=sdk_error("AccessDenied", 403)), "bucket", KEY,
                            public_url=PUBLIC + "/" + KEY, http_client=http)
        self.assertEqual(http.calls[0][2]["headers"]["Accept-Encoding"], "identity")
        self.assertEqual(http.response.close_count, 1)

    def test_provider_failures_are_safe_and_416_keeps_only_valid_range_metadata(self):
        cases = [("NoSuchKey", 404, 404, "missing"), ("InvalidRange", 416, 416, "range"),
                 ("AccessDenied", 403, 503, "authorization"), ("Unauthorized", 401, 503, "authorization"),
                 ("SignatureDoesNotMatch", 403, 503, "authorization"), ("InternalError", 500, 503, "unavailable")]
        for code, status, expected_status, category in cases:
            with self.subTest(code=code):
                sdk = SDK(error=sdk_error(code, status, **{"content-range": "bytes */100"}))
                with self.assertRaises(PDFDeliveryError) as caught:
                    open_pdf_object(sdk, "bucket", KEY)
                error = caught.exception
                self.assertEqual((error.status_code, error.category), (expected_status, category))
                self.assertNotIn("PRIVATE", str(error))
                if expected_status == 416:
                    self.assertEqual(error.headers, {"Content-Range": "bytes */100"})

    def test_sdk_failure_can_use_trusted_public_stream_without_redirects_or_credentials(self):
        sdk = SDK(error=sdk_error("AccessDenied", 403))
        http = HTTP()
        url = PUBLIC + "/" + KEY
        resource = open_pdf_object(sdk, "bucket", KEY, public_url=url, http_client=http)
        self.assertEqual(b"".join(resource.iter_chunks()), PDF)
        method, called_url, options = http.calls[0]
        self.assertEqual((method, called_url), ("get", url))
        self.assertEqual(options["timeout"], (5, 30))
        self.assertIs(options["allow_redirects"], False)
        self.assertIs(options["stream"], True)
        self.assertNotIn("Authorization", options["headers"])
        self.assertNotIn("Cookie", options["headers"])
        self.assertTrue(all(size == 65536 for size in http.response.chunk_sizes))
        self.assertEqual(http.response.close_count, 1)

    def test_public_range_and_head_have_the_expected_methods_and_safe_headers(self):
        sdk = SDK(error=sdk_error("AccessDenied", 403))
        response = HTTPResponse(b"bytes", status=206, headers={"Content-Range": "bytes 10-14/100"})
        http = HTTP(response)
        resource = open_pdf_object(sdk, "bucket", KEY, range_header="bytes=10-14", public_url=PUBLIC + "/" + KEY, http_client=http)
        self.assertEqual(http.calls[0][2]["headers"]["Range"], "bytes=10-14")
        self.assertEqual(resource.status_code, 206)
        self.assertEqual(b"".join(resource.iter_chunks()), b"bytes")
        http = HTTP()
        resource = open_pdf_object(sdk, "bucket", KEY, range_header="bad", head=True, public_url=PUBLIC + "/" + KEY, http_client=http)
        self.assertEqual(http.calls[0][0], "head")
        self.assertNotIn("Range", http.calls[0][2]["headers"])
        self.assertEqual(http.response.chunk_sizes, [])
        resource.close()
        self.assertEqual(http.response.close_count, 1)

    def test_public_xml_redirect_errors_and_non_pdf_do_not_escape(self):
        for status, content_type, body in [(200, "application/xml", b"<Error>PRIVATE</Error>"),
                                          (200, "application/pdf", b"<Error>PRIVATE</Error>"),
                                          (200, "text/html", b"<html>PRIVATE</html>"),
                                          (302, "application/pdf", PDF), (404, "application/pdf", PDF),
                                          (401, "application/xml", b"<Error>PRIVATE</Error>")]:
            with self.subTest(status=status, content_type=content_type):
                http = HTTP(HTTPResponse(body, status, {"Content-Type": content_type}))
                with self.assertRaises(PDFDeliveryError) as caught:
                    open_pdf_object(SDK(error=sdk_error("AccessDenied", 403)), "bucket", KEY,
                                    public_url=PUBLIC + "/" + KEY, http_client=http)
                self.assertEqual((caught.exception.status_code, caught.exception.category), (503, "authorization"))
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertEqual(http.response.close_count, 1)

    def test_resource_closes_on_disconnect_and_repeated_close_is_harmless(self):
        sdk = SDK()
        resource = open_pdf_object(sdk, "bucket", KEY)
        chunks = resource.iter_chunks()
        next(chunks)
        chunks.close()
        resource.close()
        self.assertEqual(sdk.body.close_count, 1)

    def test_bad_response_headers_are_never_forwarded_and_bad_ranges_are_rejected(self):
        sdk = SDK(ETag='"safe"\r\nInjected: yes', LastModified="bad\nvalue")
        resource = open_pdf_object(sdk, "bucket", KEY)
        self.assertNotIn("ETag", resource.headers)
        self.assertNotIn("Last-Modified", resource.headers)
        self.assertNotIn("Content-Disposition", resource.headers)
        resource.close()
        sdk = SDK(b"bytes", ContentRange="bytes 12-16/100", ResponseMetadata={"HTTPStatusCode": 206})
        with self.assertRaises(PDFDeliveryError):
            open_pdf_object(sdk, "bucket", KEY, range_header="bytes=10-14")
        self.assertEqual(sdk.body.close_count, 1)


if __name__ == "__main__":
    unittest.main()
