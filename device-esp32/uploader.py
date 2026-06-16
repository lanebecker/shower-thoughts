"""
Multipart upload of a WAV to the backend.

MicroPython's ``urequests`` is a minimal HTTP client with no multipart support,
so we build the ``multipart/form-data`` body by hand to match what the backend's
``POST /upload`` expects (a single file part named ``audio`` + the
``X-Device-Token`` header).

- ``multipart_envelope`` returns the (prefix, suffix) chunks that wrap the file —
  pure, and the basis for a streaming sender (Content-Length = len(prefix) +
  file_size + len(suffix)) that never holds the whole file in RAM.
- ``build_multipart`` is the in-RAM convenience (prefix + file + suffix); fine for
  short clips. Both are unit-tested.
- ``post_wav`` does the network call (lazy ``urequests`` import) and decides
  success on the HTTP status, not on the response body.
"""

DEFAULT_BOUNDARY = "----showerthoughtsboundary"


def multipart_envelope(filename="thought.wav", field="audio",
                       content_type="audio/wav", boundary=DEFAULT_BOUNDARY):
    """Return ``(prefix, suffix)`` byte chunks wrapping a file body for streaming."""
    dd = b"--" + boundary.encode()
    prefix = b"\r\n".join([
        dd,
        ('Content-Disposition: form-data; name="%s"; filename="%s"'
         % (field, filename)).encode(),
        ("Content-Type: %s" % content_type).encode(),
        b"",
        b"",
    ])
    suffix = b"\r\n" + dd + b"--\r\n"
    return prefix, suffix


def build_multipart(file_bytes, filename="thought.wav", field="audio",
                    content_type="audio/wav", boundary=DEFAULT_BOUNDARY):
    """Return ``(body_bytes, headers)`` for a single-file multipart/form-data POST."""
    prefix, suffix = multipart_envelope(filename, field, content_type, boundary)
    body = prefix + file_bytes + suffix
    headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
    return body, headers


def post_wav(url, file_bytes, token=None, **kw):
    """POST a WAV to ``url``; return the backend's job_id (or None), or raise.

    Success is decided by the HTTP status (200/202). A 2xx with an unparseable
    body still counts as success — the upload happened — so we never re-send (and
    duplicate) a thought the backend already accepted. Only a non-2xx or a
    transport error raises, which leaves the file buffered for retry.
    Hardware path — ``urequests`` is imported lazily (on-device only).
    """
    import urequests  # lazy: only available on-device

    body, headers = build_multipart(file_bytes, **kw)
    if token:
        headers["X-Device-Token"] = token
    resp = urequests.post(url, data=body, headers=headers)
    try:
        if resp.status_code not in (200, 202):
            raise OSError("upload failed: HTTP %d" % resp.status_code)
        try:
            return resp.json().get("job_id")
        except Exception:
            return None    # uploaded fine; body just wasn't parseable JSON
    finally:
        resp.close()
