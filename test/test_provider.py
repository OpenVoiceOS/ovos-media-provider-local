"""Unit tests for LocalMediaProvider (real fixture files, no mocking)."""
import shutil

import pytest
from mediavocab import MediaType, Release, Signals

from ovos_media_provider_local import LocalMediaProvider

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def _provider(library, **config):
    cfg = {"paths": [str(library / "Music"), str(library / "Videos")], "min_confidence": 0.0}
    cfg.update(config)
    return LocalMediaProvider(cfg)


def test_instantiation():
    prov = LocalMediaProvider()
    assert prov.name == "local"


def test_search_accepts_context_kwargs(library):
    prov = _provider(library)
    results = prov.search(
        Signals(medium=MediaType.MUSIC),
        lang="en-us",
        supported_playback_types={"audio"},
        blocked_genres={"adult"},
        region="US",
        session_id="sess-1",
    )
    assert isinstance(results, list)
    assert all(isinstance(r, Release) for r in results)


def test_empty_library_returns_no_results(tmp_path):
    prov = LocalMediaProvider({"paths": [str(tmp_path / "nothing-here")]})
    results = prov.search(Signals(title="anything"))
    assert results == []


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not available to synthesize tagged fixtures")
def test_search_matches_tagged_title(library):
    prov = _provider(library)
    results = prov.search(Signals(title="Groove Salad"))
    assert results
    assert results[0].work.title == "Groove Salad"
    assert results[0].uri.endswith("track1.mp3")
    assert results[0].uri.startswith("file://")


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not available to synthesize tagged fixtures")
def test_search_matches_artist(library):
    prov = _provider(library)
    results = prov.search(Signals(artist="Metal Band"))
    assert any(r.work.title == "Loud Song" for r in results)


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not available to synthesize tagged fixtures")
def test_blocked_genres_are_excluded(library):
    prov = _provider(library)
    results = prov.search(Signals(), blocked_genres={"metal"})
    assert not any(r.work.title == "Loud Song" for r in results)
    # the non-blocked tagged track is still present
    assert any(r.work.title == "Groove Salad" for r in results)


def test_untagged_file_returned_with_filename_title(library):
    prov = _provider(library)
    results = prov.search(Signals())
    matches = [r for r in results if "untagged song" in r.work.title]
    assert matches
    assert matches[0].work.media_type == MediaType.MUSIC


def test_video_file_gets_movie_media_type(library):
    prov = _provider(library)
    results = prov.search(Signals(medium=MediaType.MOVIE))
    assert results
    assert all(r.work.media_type == MediaType.MOVIE for r in results)


def test_narrowing_by_medium_excludes_other_type(library):
    prov = _provider(library)
    results = prov.search(Signals(medium=MediaType.MUSIC))
    assert results
    assert all(r.work.media_type == MediaType.MUSIC for r in results)


def test_unicode_filename_is_searchable(library):
    prov = _provider(library)
    results = prov.search(Signals())
    assert any("Café" in r.work.title for r in results)


def test_match_confidence_is_bounded(library):
    prov = _provider(library)
    results = prov.search(Signals(title="Groove Salad"))
    for r in results:
        assert 0.0 <= r.match_confidence <= 1.0


def test_min_confidence_filters_out_poor_matches(library):
    prov = _provider(library, min_confidence=0.9)
    results = prov.search(Signals(title="zzzzzzzz_no_such_title_zzzzzzzz"))
    assert results == []


def test_max_results_is_respected(library):
    prov = _provider(library, max_results=1)
    results = prov.search(Signals())
    assert len(results) <= 1


def test_search_survives_unreadable_index(tmp_path, monkeypatch):
    prov = LocalMediaProvider({"paths": [str(tmp_path)]})

    def boom():
        raise RuntimeError("disk error")

    monkeypatch.setattr(prov.index, "refresh", boom)
    assert prov.search(Signals(title="x")) == []


def test_no_query_browses_whole_library(library):
    prov = _provider(library)
    results = prov.search(Signals())
    assert len(results) >= 1
