"""Shared fixtures: a small on-disk library of real, tagged/untagged media
files. ``ffmpeg`` synthesizes a real, tiny, tagged MP3 (the tag
reader needs a genuinely decodable stream, not just an ID3 header); the
plain WAV file is built with the stdlib ``wave`` module and carries no tags
at all, exercising the filename-fallback path.
"""
import shutil
import struct
import subprocess
import wave

import pytest

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def _write_silent_wav(path):
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 800)


def _write_tagged_mp3(path, title, artist, genre=None):
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
        "-ar", "8000", "-ac", "1",
        "-metadata", f"title={title}",
        "-metadata", f"artist={artist}",
    ]
    if genre:
        cmd += ["-metadata", f"genre={genre}"]
    cmd += [str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture
def library(tmp_path):
    """A small library: one tagged mp3, one tag-less wav, one video file, one
    unicode-named file, one file whose extension we don't recognise."""
    music = tmp_path / "Music"
    music.mkdir()
    videos = tmp_path / "Videos"
    videos.mkdir()

    if HAVE_FFMPEG:
        _write_tagged_mp3(music / "track1.mp3", "Groove Salad", "Test Artist", genre="ambient")
        _write_tagged_mp3(music / "track2.mp3", "Loud Song", "Metal Band", genre="metal")

    _write_silent_wav(music / "untagged_song.wav")
    _write_silent_wav(music / "Café Ünïcödé (Remix) [Live].wav")

    _write_silent_wav(videos / "home_movie.avi")  # wav codec but .avi extension -> still indexed as video

    (music / "notes.txt").write_text("not media")

    return tmp_path
