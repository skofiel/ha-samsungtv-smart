"""The thumbnail cache must not grow without limit, or be steerable by callers.

/api/samsungtv_smart/thumbnail is unauthenticated on purpose — plain <img>
requests carry no Home Assistant auth, and it only ever serves files that HA
already publishes at /local/. But it also *writes*: every (path, width, mtime)
gets a JPEG under <config>/www/frame_art/.thumb_cache, and nothing ever deleted
one. A free-running width meant 961 distinct entries per source image, each a
Pillow decode and a file on disk.
"""

import os

from custom_components.samsungtv_smart.http_thumbnail import (
    _MAX_CACHE_FILES,
    _MAX_W,
    _MIN_W,
    _WIDTH_STEP,
    _prune_cache,
    _snap_width,
)

# --------------------------------------------------------------------------
# Width snapping
# --------------------------------------------------------------------------


def test_widths_snap_to_a_small_number_of_buckets():
    distinct = {_snap_width(w) for w in range(0, 2000)}

    assert len(distinct) <= (_MAX_W // _WIDTH_STEP) + 1
    assert all(w % _WIDTH_STEP == 0 for w in distinct)


def test_a_width_snaps_up_so_the_image_is_never_undersized():
    assert _snap_width(400) >= 400
    assert _snap_width(401) >= 401


def test_widths_stay_inside_the_served_range():
    assert _snap_width(-5) == _MIN_W
    assert _snap_width(0) == _MIN_W
    assert _snap_width(99999) == _MAX_W


# --------------------------------------------------------------------------
# Pruning
# --------------------------------------------------------------------------


def _fill(cache_dir, count, *, size=16):
    for index in range(count):
        path = cache_dir / f"{index:04d}.jpg"
        path.write_bytes(b"x" * size)
        # Distinct mtimes so "oldest first" is well defined.
        os.utime(path, (index, index))


def test_a_cache_inside_its_bounds_is_left_alone(tmp_path):
    _fill(tmp_path, 10)

    _prune_cache(str(tmp_path))

    assert len(list(tmp_path.glob("*.jpg"))) == 10


def test_an_oversized_cache_is_pruned_back_to_the_file_limit(tmp_path):
    _fill(tmp_path, _MAX_CACHE_FILES + 50)

    _prune_cache(str(tmp_path))

    assert len(list(tmp_path.glob("*.jpg"))) <= _MAX_CACHE_FILES


def test_pruning_drops_the_oldest_first(tmp_path):
    _fill(tmp_path, _MAX_CACHE_FILES + 10)

    _prune_cache(str(tmp_path))

    remaining = sorted(p.name for p in tmp_path.glob("*.jpg"))
    # The ten oldest went; the newest survived.
    assert "0000.jpg" not in remaining
    assert f"{_MAX_CACHE_FILES + 9:04d}.jpg" in remaining


def test_non_cache_files_are_never_deleted(tmp_path):
    _fill(tmp_path, _MAX_CACHE_FILES + 20)
    keep = tmp_path / "not-a-thumbnail.txt"
    keep.write_text("leave me alone")
    os.utime(keep, (0, 0))  # oldest of all

    _prune_cache(str(tmp_path))

    assert keep.exists()


def test_a_missing_cache_directory_is_not_an_error(tmp_path):
    _prune_cache(str(tmp_path / "does-not-exist"))
