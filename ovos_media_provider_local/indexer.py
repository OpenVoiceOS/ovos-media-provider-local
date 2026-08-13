"""Local media library scanner and mtime-cached index.

Walks a set of configured directories, reads tags with ``mutagen`` where the
file format is supported, and falls back to the filename when tags are
missing or unreadable. The index is a plain in-memory dict keyed by file
path; :meth:`LocalLibraryIndex.refresh` re-walks the configured paths and
only re-reads a file's tags when its ``mtime`` changed since the last scan,
so repeated searches are cheap. There is no background thread — the index is
refreshed synchronously, on demand, at the start of each search.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from ovos_utils.log import LOG

try:
    from mutagen import File as MutagenFile
except ImportError:  # pragma: no cover - mutagen is a hard dependency, kept
    MutagenFile = None  # defensive only; install always brings mutagen in

AUDIO_EXTENSIONS = {
    "aac", "ac3", "aiff", "amr", "ape", "au", "flac", "alac", "m4a",
    "m4b", "m4p", "mp2", "mp3", "mpc", "oga", "ogg", "opus", "wav", "wma",
}
VIDEO_EXTENSIONS = {
    "3g2", "3gp", "3gpp", "asf", "avi", "flv", "m2ts", "mkv", "mov",
    "mp4", "mpeg", "mpg", "mts", "ogm", "ogv", "qt", "vob", "webm", "wmv",
}

# XDG_MUSIC_DIR / XDG_VIDEOS_DIR are honoured when set (xdg-user-dirs); the
# plain ~/Music, ~/Videos fallback covers systems without xdg-user-dirs.
DEFAULT_MUSIC_DIR = os.environ.get("XDG_MUSIC_DIR") or os.path.expanduser("~/Music")
DEFAULT_VIDEOS_DIR = os.environ.get("XDG_VIDEOS_DIR") or os.path.expanduser("~/Videos")


@dataclass
class IndexedFile:
    """A single scanned media file, tags-first with filename fallback."""

    path: str
    is_audio: bool
    mtime: float
    title: str = ""
    artist: str = ""
    album: str = ""
    genres: List[str] = field(default_factory=list)
    duration: Optional[float] = None

    @property
    def uri(self) -> str:
        return "file://" + self.path


def _extension(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""


def _title_from_filename(path: str) -> str:
    name = os.path.splitext(os.path.basename(path))[0]
    return name.replace("_", " ").replace(".", " ").strip()


def _read_tags(path: str) -> Optional[dict]:
    """Best-effort tag read via mutagen. Returns ``None`` on any failure
    (missing tags, unsupported/corrupt file, permission error) so the caller
    falls back to the filename."""
    if MutagenFile is None:
        return None
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        LOG.debug(f"Could not read tags from {path}", exc_info=True)
        return None
    if audio is None:
        return None
    out = {}
    try:
        tags = audio.tags or {}
        for key in ("title", "artist", "album", "genre"):
            vals = tags.get(key)
            if vals:
                out[key] = vals[0] if isinstance(vals, list) else str(vals)
        if getattr(audio, "info", None) is not None:
            out["duration"] = getattr(audio.info, "length", None)
    except Exception:
        LOG.debug(f"Could not parse tags from {path}", exc_info=True)
        return None
    return out


def scan_file(path: str, is_audio: bool, mtime: float) -> IndexedFile:
    """Build an :class:`IndexedFile` for ``path``, preferring tags and
    falling back to the filename for any field tags did not provide."""
    tags = _read_tags(path) or {}
    genre = tags.get("genre")
    return IndexedFile(
        path=path,
        is_audio=is_audio,
        mtime=mtime,
        title=tags.get("title") or _title_from_filename(path),
        artist=tags.get("artist", ""),
        album=tags.get("album", ""),
        genres=[genre] if genre else [],
        duration=tags.get("duration"),
    )


class LocalLibraryIndex:
    """Filesystem-backed index over configured library paths.

    Call :meth:`refresh` before reading :attr:`files` — it is cheap when
    nothing changed (a per-file ``os.stat`` and an mtime comparison) and only
    re-parses tags for new or modified files.
    """

    def __init__(self, paths: Optional[Iterable[str]] = None):
        self.paths: List[str] = list(paths) if paths else [DEFAULT_MUSIC_DIR, DEFAULT_VIDEOS_DIR]
        self._files: Dict[str, IndexedFile] = {}

    @property
    def files(self) -> List[IndexedFile]:
        return list(self._files.values())

    def refresh(self) -> None:
        """Re-walk configured paths. Unreadable/missing directories are
        skipped (logged, not raised) so one bad path doesn't blank the whole
        library. Files no longer present are dropped from the index."""
        seen = set()
        for base in self.paths:
            base = os.path.expanduser(base)
            if not os.path.isdir(base):
                continue
            try:
                walker = os.walk(base, onerror=lambda e: LOG.debug(f"Cannot list {e.filename}: {e}"))
                for root, _dirs, filenames in walker:
                    for name in filenames:
                        ext = _extension(name)
                        is_audio = ext in AUDIO_EXTENSIONS
                        is_video = ext in VIDEO_EXTENSIONS
                        if not (is_audio or is_video):
                            continue
                        path = os.path.join(root, name)
                        try:
                            mtime = os.stat(path).st_mtime
                        except OSError:
                            continue
                        seen.add(path)
                        cached = self._files.get(path)
                        if cached is not None and cached.mtime == mtime:
                            continue
                        try:
                            self._files[path] = scan_file(path, is_audio, mtime)
                        except Exception:
                            LOG.exception(f"Failed to index {path}")
            except Exception:
                LOG.exception(f"Failed to scan library path {base}")
        # drop entries for files that disappeared since the last scan
        for stale in set(self._files) - seen:
            del self._files[stale]
