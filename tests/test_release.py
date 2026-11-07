"""Check the release command against a small synthetic integration."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.release import prepare_release


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.component = self.root / "custom_components" / "bluestar_lan"
        self.component.mkdir(parents=True)
        (self.root / "hacs.json").write_text(json.dumps({
            "zip_release": True, "filename": "bluestar_lan.zip",
        }))
        (self.component / "manifest.json").write_text(json.dumps({
            "domain": "bluestar_lan", "version": "0.1.0",
        }))
        (self.component / "__init__.py").write_text('"""Synthetic integration."""\n')
        (self.root / "LICENSE").write_text("Synthetic license\n")
        (self.component / "credentials.json").write_text('"fixture-only"')

    def test_build_uses_marketplace_layout_and_excludes_unrelated_files(self):
        archive = prepare_release(self.root, "0.1.0")
        self.assertEqual(archive, self.root / "dist" / "0.1.0" / "bluestar_lan.zip")
        with ZipFile(archive) as opened:
            self.assertEqual(set(opened.namelist()), {"manifest.json", "__init__.py", "LICENSE"})
        self.assertEqual(prepare_release(self.root, "0.1.0", check_only=True), archive)

    def test_rejects_a_tag_that_differs_from_manifest(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            prepare_release(self.root, "0.1.1")

    def test_rejects_an_archive_after_integration_source_changes(self):
        prepare_release(self.root, "0.1.0")
        (self.component / "__init__.py").write_text('"""Changed after packaging."""\n')
        with self.assertRaisesRegex(ValueError, "differs from source"):
            prepare_release(self.root, "0.1.0", check_only=True)
