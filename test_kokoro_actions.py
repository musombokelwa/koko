import unittest
from pathlib import Path
from unittest.mock import patch

import kokoro_actions as actions


class ActionParsingTests(unittest.TestCase):
    def test_unknown_tags_are_not_executed(self):
        clean, results = actions.process_actions("Bonjour [CMD: rm -rf /]")
        self.assertEqual(clean, "Bonjour [CMD: rm -rf /]")
        self.assertEqual(results, [])

    def test_action_tag_is_removed_and_result_is_returned(self):
        with patch.dict(
            actions._HANDLERS,
            {"SEARCH": lambda _query: "Recherche ouverte."},
        ):
            clean, results = actions.process_actions("Je cherche [SEARCH: météo]")
        self.assertEqual(clean, "Je cherche")
        self.assertEqual(results, ["Recherche ouverte."])

    def test_file_search_never_returns_outside_allowed_roots(self):
        outside = Path("/etc/hosts")
        with patch.object(actions, "allowed_roots", return_value=[]):
            self.assertIsNone(actions._find_in_roots(str(outside)))


if __name__ == "__main__":
    unittest.main()
