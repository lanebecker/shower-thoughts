"""Tests for the hand-built multipart/form-data body."""

import uploader


def test_body_structure_and_boundary():
    payload = b"RIFFfakeaudio"
    body, headers = uploader.build_multipart(payload, boundary="XBOUND")

    # Header advertises the same boundary used in the body.
    assert headers["Content-Type"] == "multipart/form-data; boundary=XBOUND"
    # Opens with the dashed boundary, closes with the dashed-boundary-dashes.
    assert body.startswith(b"--XBOUND\r\n")
    assert body.endswith(b"\r\n--XBOUND--\r\n")
    # Carries the file bytes verbatim.
    assert payload in body


def test_default_field_is_audio_and_filename_present():
    body, _ = uploader.build_multipart(b"x", filename="thought_123.wav")
    assert b'name="audio"' in body
    assert b'filename="thought_123.wav"' in body
    assert b"Content-Type: audio/wav" in body


def test_blank_line_separates_headers_from_content():
    # The part headers must be terminated by a blank line (\r\n\r\n) before data.
    body, _ = uploader.build_multipart(b"DATA", boundary="B")
    assert b"\r\n\r\nDATA\r\n--B--\r\n" in body


def test_envelope_matches_build_multipart():
    prefix, suffix = uploader.multipart_envelope(boundary="B")
    body, _ = uploader.build_multipart(b"DATA", boundary="B")
    assert body == prefix + b"DATA" + suffix
    assert prefix.startswith(b"--B\r\n")
    assert suffix == b"\r\n--B--\r\n"
