"""Tests purs (sans Home Assistant) de la protection des identifiants dans les URLs.

Lancement : `python3 -m unittest tests/test_redact.py` ou `pytest tests/`.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "noopy_tv" / "redact.py"
_spec = importlib.util.spec_from_file_location("onetv_redact", _PATH)
r = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = r
_spec.loader.exec_module(r)


class CredentialDetectionTests(unittest.TestCase):
    def test_xtream_typed_path(self):
        for url in (
            "http://provider.example:8080/live/alice/s3cret/12345.ts",
            "http://provider.example/movie/alice/s3cret/987.mkv",
            "http://provider.example/series/alice/s3cret/55.mp4",
            "http://provider.example/timeshift/alice/s3cret/60/2026-10-19:20-00/12.ts",
        ):
            self.assertTrue(r.url_has_credentials(url), url)

    def test_xtream_short_path(self):
        self.assertTrue(r.url_has_credentials("http://provider.example:80/alice/s3cret/12345"))
        self.assertTrue(r.url_has_credentials("http://provider.example/alice/s3cret/12345.m3u8"))

    def test_query_and_userinfo(self):
        for url in (
            "http://provider.example/get.php?username=alice&password=s3cret&type=m3u",
            "http://plex.local:32400/photo/:/transcode?width=400&X-Plex-Token=abc",
            "http://emby.local/Items/1/Images/Primary?api_key=abc",
            "http://alice:s3cret@provider.example/stream.ts",
            "http://portal.example/play/live.php?mac=00:1A:79:00:00:00&stream=1&play_token=x",
        ):
            self.assertTrue(r.url_has_credentials(url), url)

    def test_public_urls_kept(self):
        for url in (
            "https://image.tmdb.org/t/p/w500/abc.jpg",
            "https://raw.githubusercontent.com/tv-logo/tv-logos/main/fr/tf1.png",
            "http://provider.example/images/logos/tf1.png",
        ):
            self.assertFalse(r.url_has_credentials(url), url)
            self.assertEqual(r.public_url(url), url)

    def test_public_url_drops_credentialed(self):
        self.assertIsNone(r.public_url("http://p.example/live/alice/s3cret/1.ts"))
        self.assertIsNone(r.public_url(None))
        self.assertIsNone(r.public_url(""))

    def test_loggable_url(self):
        self.assertEqual(
            r.loggable_url("http://p.example:8080/live/alice/s3cret/1.ts?x=1"),
            "http://p.example/…",
        )


class PayloadScrubTests(unittest.TestCase):
    def test_strip_stream_urls_nested(self):
        payload = {
            "current_channel": {"name": "TF1", "stream_url": "http://p/live/a/b/1.ts"},
            "available_channels": [{"id": "1", "stream_url": "x"}, {"id": "2"}],
            "streamURL": "http://p/movie/a/b/2.mkv",
            "contentTitle": "Film",
        }
        out = r.strip_stream_urls(payload)
        self.assertNotIn("streamURL", out)
        self.assertNotIn("stream_url", out["current_channel"])
        self.assertEqual(out["available_channels"], [{"id": "1"}, {"id": "2"}])
        self.assertEqual(out["contentTitle"], "Film")
        # La source n'est pas modifiée.
        self.assertIn("stream_url", payload["current_channel"])

    def test_redact_urls_any_key(self):
        out = r.redact_urls({"a": {"weirdNewURLField": "http://p/live/a/b/1.ts"}, "n": 3, "s": "TF1"})
        self.assertEqual(out["a"]["weirdNewURLField"], r.REDACTED)
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["s"], "TF1")


if __name__ == "__main__":
    unittest.main()
