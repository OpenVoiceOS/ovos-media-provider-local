# ovos-media-provider-local

A `MediaProvider` plugin (`opm.media.provider` entry point) that serves a
local file-system media library to the OCP pipeline. It is the local-files
counterpart to providers like `ovos-media-provider-mass` (Music Assistant) or
`ovos-media-provider-somafm` (SomaFM): the OCP pipeline loads it in-process
and calls `search(signals, lang, *, supported_playback_types, blocked_genres,
region, session_id) -> List[Release]` directly — no bus round trip.

## Indexing

`ovos_media_provider_local.indexer.LocalLibraryIndex` walks the configured
`paths` recursively and keeps one `IndexedFile` per audio/video file found
(matched by extension). Each file's `mtime` is compared against the cached
entry on every `refresh()`; only new or changed files are re-read, and
entries for files no longer on disk are dropped. There is no persistence
across process restarts and no background thread — `refresh()` runs inline
at the start of every `search()`.

Tag extraction is best-effort via `mutagen`'s `easy` interface
(title/artist/album/genre/duration). Any failure to open or parse a file
(corrupt file, unsupported format, permission error) is logged and the file
falls back to a title derived from its filename — it is never dropped from
the index just because it has no tags.

## Matching

`ovos_media_provider_local.score_file` scores each candidate against the
request's `Signals`:

- Query title vs. the file's (tagged or filename-derived) title, via
  `ovos_utils.parse.fuzzy_match`.
- A bonus when the requested artist substring-matches the file's tagged
  artist.
- A bare browse request (no title, no artist) returns every file at a flat
  `0.5` confidence rather than ranking arbitrarily.

`blocked_genres` is applied before scoring: a file whose tagged genre
matches a blocked genre is dropped outright, not merely down-ranked.
Files scoring below `min_confidence` are excluded from the results.

## Media type

Files are classified only by extension into the two buckets a plain file
collection can be classified into without external metadata:
`MediaType.MUSIC` for recognised audio extensions, `MediaType.MOVIE` for
recognised video extensions. A request naming any other `medium` narrows to
an empty result.
