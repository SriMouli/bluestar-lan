"""Build or verify the ZIP asset for a Blue Star LAN release tag."""

import argparse
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile


def check_archive(archive_path, sources):
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(sources) or set(names) != sources.keys():
            raise ValueError("ZIP files or layout differ from the integration source")
        for name, source in sources.items():
            if archive.read(name) != source.read_bytes():
                raise ValueError(f"ZIP entry {name} differs from source")


def prepare_release(root, tag, *, check_only=False):
    component = root / "custom_components" / "bluestar_lan"
    manifest_path = component / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", tag):
        raise ValueError("Use the unprefixed manifest version as the release tag")
    if tag != manifest.get("version"):
        raise ValueError(f"Release tag {tag} does not match manifest version {manifest.get('version')}")
    if manifest.get("domain") != component.name:
        raise ValueError("Manifest domain does not match the integration folder")
    marketplace = json.loads((root / "hacs.json").read_text(encoding="utf-8"))
    filename = marketplace.get("filename")
    if marketplace.get("zip_release") is not True or filename != f"{component.name}.zip":
        raise ValueError(f"Marketplace must use the {component.name}.zip release asset")
    sources = {
        item.relative_to(component).as_posix(): item
        for pattern in ("*.py", "translations/*.json", "brand/*.png")
        for item in sorted(component.glob(pattern))
    }
    sources["manifest.json"] = manifest_path
    sources["LICENSE"] = root / "LICENSE"
    if "__init__.py" not in sources or any(not item.is_file() or item.is_symlink() for item in sources.values()):
        raise ValueError("Release sources must include an integration entry point and regular files")
    archive_path = root / "dist" / tag / filename
    if check_only:
        check_archive(archive_path, sources)
        return archive_path

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=archive_path.parent) as directory:
        candidate = Path(directory) / filename
        with ZipFile(candidate, "w", compression=ZIP_DEFLATED) as archive:
            for name, source in sources.items():
                archive.write(source, name)
        check_archive(candidate, sources)
        candidate.replace(archive_path)
    return archive_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Release tag matching the manifest version, such as 0.1.0")
    parser.add_argument("--check", action="store_true", help="Verify the existing ZIP without rebuilding it")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        archive_path = prepare_release(root, args.tag, check_only=args.check)
    except (OSError, ValueError, BadZipFile) as error:
        parser.exit(1, f"Release check failed: {error}\n")
    print(f"Verified {archive_path.relative_to(root)} for tag {args.tag}")


if __name__ == "__main__":
    main()
