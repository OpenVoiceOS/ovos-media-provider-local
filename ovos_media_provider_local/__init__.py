"""OVOS MediaProvider plugin for a local file-system media library.

Replaces the catalog/search half of the deprecated OCP skill
``ovos-skill-local-media``. Instead of scanning fixed ``MediaType``
subfolders under a single ``media_path`` and answering
``ovos.common_play.query`` over the bus, this provider is loaded in-process
by the OCP pipeline: it indexes one or more configured library ``paths``
(recursively, no subfolder convention required) and answers ``search()``
directly.

Each audio/video file under a configured path becomes one
``mediavocab.Release`` with a ``file://`` uri. Tags are read with
``tinytag`` where the format supports it; the filename is the fallback title
when tags are absent, unreadable, or the format is untagged. The index is
rebuilt lazily (see :mod:`ovos_media_provider_local.indexer`) — no daemon
thread, no persisted cache.
"""
from typing import ClassVar, List, Optional, Set

from ovos_utils.log import LOG
from ovos_utils.parse import fuzzy_match

from mediavocab import MediaType, Release, Signals, Work

from ovos_plugin_manager.templates.media_provider import MediaProvider

from ovos_media_provider_local.indexer import IndexedFile, LocalLibraryIndex
from ovos_media_provider_local.version import __version__  # noqa: F401


def _file_media_type(indexed: IndexedFile) -> MediaType:
    return MediaType.MUSIC if indexed.is_audio else MediaType.MOVIE


def score_file(indexed: IndexedFile, signals: Signals) -> float:
    """Score an indexed file against the parsed request, in ``0.0``-``1.0``.

    Title similarity (``fuzzy_match``) against the tagged/derived title is
    the base. A query naming an artist that matches the file's tagged artist
    adds a small bonus. A bare browse request (no title, no artist) scores
    every file the same low-confidence match so the caller can still list
    the whole library without any one file looking authoritative.
    """
    query = (signals.title or "").strip().lower()
    want_artist = (signals.artist or "").strip().lower()
    if not query and not want_artist:
        return 0.5

    title = (indexed.title or "").lower()
    score = fuzzy_match(title, query) if query else 0.0

    artist = (indexed.artist or "").lower()
    if want_artist and artist and want_artist in artist:
        score = min(1.0, score + 0.2)
        if not query:
            score = max(score, 0.5)
    return round(score, 3)


def _to_release(indexed: IndexedFile) -> Release:
    media_type = _file_media_type(indexed)
    work = Work(title=indexed.title or indexed.path, media_type=media_type)
    # mediavocab.Credit needs a full Entity, not a bare tag string, so the
    # tagged artist/album go on `extra` rather than `credits`.
    if indexed.artist:
        work.extra = {**work.extra, "artist": indexed.artist}
    if indexed.album:
        work.extra = {**work.extra, "album": indexed.album}
    if indexed.genres:
        work.content_genres = list(indexed.genres)
    if indexed.duration:
        work.runtime = indexed.duration
    return Release(work=work, uri=indexed.uri)


class LocalMediaProvider(MediaProvider):
    """Search a local media library indexed from filesystem paths.

    Serves ``MUSIC`` (audio files) and ``MOVIE`` (video files) — the two
    generic buckets a plain file collection can be classified into without a
    metadata provider. A request for any other medium narrows to nothing.
    """

    name: ClassVar[str] = "local"

    SERVED_MEDIA: ClassVar[Set[MediaType]] = {MediaType.MUSIC, MediaType.MOVIE}

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        paths = self.config.get("paths")
        self.max_results: int = int(self.config.get("max_results", 10))
        self.min_confidence: float = float(self.config.get("min_confidence", 0.3))
        self.index = LocalLibraryIndex(paths)

    def search(self, signals: Signals, lang: str = "en-us", *,
               supported_playback_types: Optional[Set[str]] = None,
               blocked_genres: Optional[Set[str]] = None,
               region: Optional[str] = None,
               session_id: Optional[str] = None) -> List[Release]:
        """Refresh the local index and return matching files as Releases.

        When ``signals.medium`` names a specific type this provider serves,
        results are narrowed to that type. Files carrying a genre tag in
        ``blocked_genres`` are dropped. Scoring is honest: an untagged file
        matched only by its raw filename never outscores a tagged, exact
        title match, and files below ``min_confidence`` are excluded.
        """
        try:
            self.index.refresh()
        except Exception:
            LOG.exception("Local media library scan failed")
            return []

        medium = signals.medium
        narrow = medium in self.SERVED_MEDIA
        blocked = {g.lower() for g in (blocked_genres or set()) if g}

        scored = []
        for indexed in self.index.files:
            media_type = _file_media_type(indexed)
            if narrow and media_type != medium:
                continue
            if blocked and any(g.lower() in blocked for g in indexed.genres):
                continue
            confidence = score_file(indexed, signals)
            if confidence < self.min_confidence:
                continue
            scored.append((confidence, indexed))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        out: List[Release] = []
        for confidence, indexed in scored[: self.max_results]:
            try:
                release = _to_release(indexed)
            except Exception:
                LOG.exception(f"Failed to build Release for {indexed.path}")
                continue
            release.match_confidence = confidence
            out.append(release)
        return out
