"""Regression checks for packaging and reproducible direct dependencies."""

from __future__ import annotations

import unittest
from pathlib import Path

import aitrader_bot


ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_pyproject_version_entry_point_and_package_data(self) -> None:
        metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn(
            f'version = "{aitrader_bot.__version__}"',
            metadata,
        )
        self.assertIn('ai-trading-bot = "aitrader_bot.cli:main"', metadata)
        self.assertIn('"aitrader_bot.app" = ["dashboard_template.html"]', metadata)

    def test_every_direct_requirement_is_exactly_pinned(self) -> None:
        requirements = [
            line.strip()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertGreater(len(requirements), 0)
        for requirement in requirements:
            package_spec = requirement.split(";", 1)[0].strip()
            self.assertIn("==", package_spec, requirement)
            name, version = package_spec.split("==", 1)
            self.assertTrue(name.strip(), requirement)
            self.assertTrue(version.strip(), requirement)


if __name__ == "__main__":
    unittest.main()
