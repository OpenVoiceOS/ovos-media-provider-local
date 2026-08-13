# ovos-media-provider-local

OVOS **MediaProvider** plugin for a local file-system media library.

Given a parsed media request, it searches one or more configured directories
on disk and returns ranked, playable `mediavocab.Release` objects with
`file://` uris. Instead of a fixed set of `MediaType` subfolders and a bus
listener, this provider is loaded in-process by the OCP pipeline and its
`search()` is called directly. It supersedes the catalog/search half of the
legacy OCP skill
[`ovos-skill-local-media`](https://github.com/OpenVoiceOS/ovos-skill-local-media).

## Routing

| Axis | Value |
|---|---|
| `media` | `MUSIC`, `MOVIE` |
| `playback_type` | `AUDIO`, `VIDEO` |
| `genre_filter` | *(none)* |

## Install

```bash
pip install ovos-media-provider-local
```

## Configure

Per-provider settings live under `media_providers` in `mycroft.conf`, keyed
by the provider's entry-point name:

```json
{
  "media_providers": {
    "local": {
      "paths": ["~/Music", "~/Videos", "/mnt/media"],
      "max_results": 10,
      "min_confidence": 0.3
    }
  }
}
```

| Key | Default | Description |
|---|---|---|
| `paths` | `$XDG_MUSIC_DIR`/`~/Music`, `$XDG_VIDEOS_DIR`/`~/Videos` | Directories scanned recursively for media files. |
| `max_results` | `10` | Maximum number of matching files returned per search. |
| `min_confidence` | `0.3` | Files scoring below this are dropped from the results. |

Set `"enabled": false` to disable without uninstalling.

## How it works

Every audio/video file under a configured path is indexed once and re-used
across searches; the index is rebuilt on the next `search()` call only for
files whose `mtime` changed or that are new, and entries for files that
disappeared are dropped. There is no background thread — the refresh runs
synchronously at the start of `search()`.

Tags are read with [`mutagen`](https://mutagen.readthedocs.io/) where the
format supports it (title/artist/album/genre/duration). A file with no
readable tags falls back to a title derived from its filename. `search()`
scores each candidate with `fuzzy_match` against the query title, with a
bonus when the requested artist is tagged on the file; a bare browse request
(no title, no artist) returns the whole library at a flat low confidence
instead of favouring one arbitrary file.

## Related projects

- [ovos-skill-local-media](https://github.com/OpenVoiceOS/ovos-skill-local-media): the legacy OCP search skill this provider supersedes
- [mediavocab](https://github.com/TigreGotico/mediavocab): the `Release`/`Signals`/`Work` types this provider returns and consumes
- [ovos-plugin-manager](https://github.com/OpenVoiceOS/ovos-plugin-manager): defines the `MediaProvider` template and `opm.media.provider` plugin type

## Docs

- [docs/index.md](docs/index.md): overview and how it fits the ovos-media stack

## Tests

```bash
pip install -e .[test]
pytest test/
```

Tests use real fixture files generated under `tmp_path` (a tag-less WAV built
with the stdlib `wave` module, plus a tiny tagged MP3 synthesized with
`ffmpeg` where available). Tests that need the tagged MP3 are skipped, not
failed, when `ffmpeg` is not on `PATH`.

## License

Apache-2.0
