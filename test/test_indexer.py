"""Unit tests for LocalLibraryIndex (real fixture files, no mocking)."""
import os
import shutil
import stat
import time

import pytest

from ovos_media_provider_local.indexer import LocalLibraryIndex

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def test_empty_library(tmp_path):
    idx = LocalLibraryIndex([str(tmp_path / "does-not-exist")])
    idx.refresh()
    assert idx.files == []


def test_scans_configured_paths(library):
    idx = LocalLibraryIndex([str(library / "Music"), str(library / "Videos")])
    idx.refresh()
    paths = {f.path for f in idx.files}
    assert any(p.endswith("untagged_song.wav") for p in paths)
    assert any(p.endswith("home_movie.avi") for p in paths)
    # non-media file is not indexed
    assert not any(p.endswith("notes.txt") for p in paths)


def test_unreadable_directory_is_skipped_not_raised(library):
    locked = library / "Music" / "locked"
    locked.mkdir()
    (locked / "secret.wav").write_bytes(b"\x00")
    os.chmod(locked, 0o000)
    try:
        idx = LocalLibraryIndex([str(library / "Music")])
        idx.refresh()  # must not raise
        paths = {f.path for f in idx.files}
        assert not any("secret.wav" in p for p in paths)
    finally:
        os.chmod(locked, stat.S_IRWXU)  # allow cleanup


def test_unicode_and_bracketed_filenames_are_indexed(library):
    idx = LocalLibraryIndex([str(library / "Music")])
    idx.refresh()
    matches = [f for f in idx.files if "Café" in f.title or "Café" in f.path]
    assert matches, "unicode filename should be indexed"


def test_tagless_file_falls_back_to_filename_title(library):
    idx = LocalLibraryIndex([str(library / "Music")])
    idx.refresh()
    untagged = [f for f in idx.files if f.path.endswith("untagged_song.wav")][0]
    assert "untagged song" in untagged.title
    assert untagged.artist == ""


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not available to synthesize tagged fixtures")
def test_tagged_file_uses_tags_over_filename(library):
    idx = LocalLibraryIndex([str(library / "Music")])
    idx.refresh()
    track = [f for f in idx.files if f.path.endswith("track1.mp3")][0]
    assert track.title == "Groove Salad"
    assert track.artist == "Test Artist"
    assert track.genres == ["ambient"]


def test_video_extension_is_flagged_non_audio(library):
    idx = LocalLibraryIndex([str(library / "Videos")])
    idx.refresh()
    vid = [f for f in idx.files if f.path.endswith("home_movie.avi")][0]
    assert vid.is_audio is False


def test_mtime_invalidation_rescans_changed_file(library):
    target = library / "Music" / "untagged_song.wav"
    idx = LocalLibraryIndex([str(library / "Music")])
    idx.refresh()
    first_mtime = [f for f in idx.files if f.path == str(target)][0].mtime

    # bump mtime without changing content and force a rescan
    future = time.time() + 5
    os.utime(target, (future, future))
    idx.refresh()
    second = [f for f in idx.files if f.path == str(target)][0]
    assert second.mtime != first_mtime


def test_deleted_file_is_dropped_from_index(library):
    target = library / "Music" / "untagged_song.wav"
    idx = LocalLibraryIndex([str(library / "Music")])
    idx.refresh()
    assert any(f.path == str(target) for f in idx.files)

    target.unlink()
    idx.refresh()
    assert not any(f.path == str(target) for f in idx.files)


def test_uri_is_file_scheme(library):
    idx = LocalLibraryIndex([str(library / "Music")])
    idx.refresh()
    f = idx.files[0]
    assert f.uri == "file://" + f.path
