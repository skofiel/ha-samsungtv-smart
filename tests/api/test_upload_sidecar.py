"""Upload sidecar: skip-unchanged bookkeeping for batch uploads."""

import json
import os


def test_list_images_sorted_and_filtered(tmp_path):
    from custom_components.samsungtv_smart.api import _upload_sidecar as sc

    (tmp_path / "b.jpg").write_bytes(b"x")
    (tmp_path / "a.PNG").write_bytes(b"x")
    (tmp_path / "note.txt").write_text("nope")
    (tmp_path / "sub").mkdir()  # directories excluded
    result = [os.path.basename(p) for p in sc.list_images(str(tmp_path))]
    assert result == ["a.PNG", "b.jpg"]


def test_needs_upload_new_and_changed():
    from custom_components.samsungtv_smart.api import _upload_sidecar as sc

    sidecar = {"a.jpg": {"content_id": "MY-F0001", "modified": 100.0}}
    assert sc.needs_upload("new.jpg", 1.0, sidecar) is True  # never seen
    assert sc.needs_upload("a.jpg", 100.0, sidecar) is False  # unchanged -> skip
    assert sc.needs_upload("a.jpg", 200.0, sidecar) is True  # mtime changed


def test_sidecar_roundtrip_and_bad_file(tmp_path):
    from custom_components.samsungtv_smart.api import _upload_sidecar as sc

    path = str(tmp_path / ".samsungtv_upload.json")
    assert sc.load_sidecar(path) == {}  # missing -> {}
    data = {"a.jpg": {"content_id": "MY-F0001", "modified": 100.0}}
    sc.save_sidecar(path, data)
    assert sc.load_sidecar(path) == data
    assert json.loads((tmp_path / ".samsungtv_upload.json").read_text()) == data

    (tmp_path / "corrupt.json").write_text("{not json")
    assert sc.load_sidecar(str(tmp_path / "corrupt.json")) == {}  # unreadable -> {}


def _png(color, size=(64, 64)):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_dhash_matches_reencoded_same_image():
    # Same gradient content, different size/format (mimics the TV re-encode).
    import io

    from PIL import Image, ImageDraw

    from custom_components.samsungtv_smart.api import _upload_sidecar as sc

    def gradient(size):
        im = Image.new("L", size)
        d = ImageDraw.Draw(im)
        for x in range(size[0]):
            d.line([(x, 0), (x, size[1])], fill=int(255 * x / size[0]))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG" if size[0] > 100 else "PNG")
        return buf.getvalue()

    full = sc.dhash(gradient((400, 300)))
    thumb = sc.dhash(gradient((160, 120)))
    assert full is not None and thumb is not None
    assert sc.is_duplicate_hash(full, [thumb]) is True


def test_dhash_distinguishes_different_images():
    from custom_components.samsungtv_smart.api import _upload_sidecar as sc

    a = sc.dhash(_png((0, 0, 0)))
    # A very different picture must NOT be treated as a duplicate.
    import io

    from PIL import Image, ImageDraw

    im = Image.new("RGB", (64, 64), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, 50, 50], fill=(0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    b = sc.dhash(buf.getvalue())
    assert sc.is_duplicate_hash(a, [b]) is False


def test_bad_bytes_never_a_duplicate():
    from custom_components.samsungtv_smart.api import _upload_sidecar as sc

    assert sc.dhash(b"not an image") is None
    # None candidate must never be skipped (anti-false-skip).
    assert sc.is_duplicate_hash(None, [123, 456]) is False
