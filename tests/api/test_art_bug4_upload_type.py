"""Bug 4: detect real image format via PIL; send 'jpg' (not 'jpeg') on the wire."""

import io

from PIL import Image


def _jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (40, 50, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _mpo_bytes():
    # An MPO is JPEG-family; PIL reports format 'MPO'. Fake by tagging JPEG bytes
    # as MPO via a second frame is heavy — instead assert the jpeg-family mapping
    # by patching PIL to report 'MPO' is out of scope; use real JPEG whose format
    # maps identically, plus a direct format-string check below.
    return _jpeg_bytes()


def test_detect_jpeg(art_client):
    import art

    assert art._detect_wire_type(_jpeg_bytes(), hint="png") == "jpg"


def test_detect_png(art_client):
    import art

    assert art._detect_wire_type(_png_bytes(), hint="jpeg") == "png"


def test_detect_maps_mpo_and_jpeg_family_to_jpg(art_client):
    import art

    # format-string mapping is the load-bearing rule for MPO/JPEG family
    assert art._map_format_to_wire("MPO") == "jpg"
    assert art._map_format_to_wire("JPEG") == "jpg"
    assert art._map_format_to_wire("PNG") == "png"


def test_wrong_caller_hint_overridden(art_client):
    import art

    # Caller lied and said png, bytes are really JPEG -> detection wins.
    assert art._detect_wire_type(_jpeg_bytes(), hint="png") == "jpg"
