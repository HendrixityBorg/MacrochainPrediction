from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from macro_gold_latent.data import _release_dates


class DataTests(unittest.TestCase):
    def test_release_rule_ignores_midmonth_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dates.txt"
            path.write_text("2024-08-02\n2024-08-21\n2024-09-06\n", encoding="utf-8")
            result = _release_dates(path, ["2024:07", "2024:08"])
        self.assertEqual(result["2024:07"], date(2024, 8, 2))
        self.assertEqual(result["2024:08"], date(2024, 9, 6))


if __name__ == "__main__":
    unittest.main()

