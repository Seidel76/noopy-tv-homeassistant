"""Tests purs (sans Home Assistant) du filtre des séparateurs et de la résolution de chaîne.

Lancement : `python3 -m unittest tests/test_naming.py` ou `pytest tests/`.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "noopy_tv" / "naming.py"
_spec = importlib.util.spec_from_file_location("onetv_naming", _PATH)
n = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = n
_spec.loader.exec_module(n)


class SeparatorFilterTests(unittest.TestCase):
    def test_real_channels_with_leading_punctuation_are_kept(self):
        # Régression de l'ancien filtre (1er caractère = ponctuation ⇒ rejeté).
        for name in ("|FR| TF1 FHD", "[FR] M6", "(FR) W9", "L'Équipe", "TF1", "A-B"):
            self.assertTrue(n.is_channel_name_valid(name), name)

    def test_separators_are_rejected(self):
        for name in ("▼●★ --- |FR| M6 PLAY |FR| --- ★●▼", "---●★| MANGA |★●---", "====", "★", "", None):
            self.assertFalse(n.is_channel_name_valid(name), name)


class ResolveChannelTests(unittest.TestCase):
    CHANNELS = {
        "u1": {"name": "FRANCE 2"},
        "u2": {"name": "TF1"},
        "u3": {"name": "TF1 HD"},
        "u4": {"name": "Chérie 25"},
        "u5": {"name": "----- FRANCE 2 -----"},
    }

    def test_id_and_exact_name(self):
        self.assertEqual(n.resolve_channel_id(self.CHANNELS, "u2"), "u2")
        self.assertEqual(n.resolve_channel_id(self.CHANNELS, "TF1 HD"), "u3")

    def test_case_accents_and_punctuation_are_ignored(self):
        self.assertEqual(n.resolve_channel_id(self.CHANNELS, "france 2"), "u1")
        self.assertEqual(n.resolve_channel_id(self.CHANNELS, "France-2"), "u1")
        self.assertEqual(n.resolve_channel_id(self.CHANNELS, "cherie 25"), "u4")
        self.assertEqual(n.resolve_channel_id(self.CHANNELS, "tf1"), "u2")

    def test_no_partial_match(self):
        self.assertIsNone(n.resolve_channel_id(self.CHANNELS, "france"))
        self.assertIsNone(n.resolve_channel_id(self.CHANNELS, ""))
        self.assertIsNone(n.resolve_channel_id({}, "TF1"))


if __name__ == "__main__":
    unittest.main()
