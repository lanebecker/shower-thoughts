"""
Multipart upload of a WAV to the backend.

MicroPython's ``urequests`` is a minimal HTTP client with no multipart support,
so we build the ``multipart/form-data`` body by hand to match what the backend's
``POST /upload`` expects (a single file part named ``audio``, plus the
``X-Device-Token`` header). ``build_multipart`` is pure and unit-tested;
``post_wav`` does the actual network call and lazily imports ``urequests`` (only
present on-device), mirroring how the Pi firmware keeps optional deps lazy.
"""

DEFAULT_BOUNDARY = "----showerthoughtsboundary"


def build_multipart(file_bytes, filename="thought.wav", field="audio",
                    content_type="audio/wav", boundary=DEFAULT_BOUNDARY):
    """Return ``(body_bytes, headers)`` for a single-file multipart/form-data POST.

    The backend reads the file from the form field named ``audio`` (see
    backend/main.py), so ``field`` defaults to that.
    """
    dd = b"--" + boundary.encode()
    head = b"\r\n".join([
        dd,
        ('Content-Disposition: form-data; name="%s"; filename="%s"'
         % (field, filename)).encode(),
        ("Content-Type: %s" % content_type).encode(),
        b"",
        b"",
    ])
    body = head + file_bytes + b"\r\n" + dd + b"--\r\n"
    headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
    return body, headers


def post_wav(url, file_bytes, token=None, **kw):
    """POST a WAV to ``url``; return the backend's job_id, or raise on failure.

    Hardware path — uses ``urequests`` (imported lazily so the module stays
    importable off-device for tests).
    """
    import urequests  # lazy: only available on-device

    body, headers = build_multipart(file_bytes, **kw)
    if token:
        headers["X-Device-Token"] = token
    resp = urequests.post(url, data=body, headers=headers)
    try:
        if resp.status_code not in (200, 202):
            raise OSError("upload failed: HTTP %d" % resp.status_code)
        return resp.json().get("job_id")
    finally:
        resp.close()
