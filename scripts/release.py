#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Self

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
PYPROJECT_VERSION_RE = re.compile(r'(?m)^(version\s*=\s*")([^"]+)(")$')
DEFAULT_IMAGE = "piphinetwork/matter-sidecar"
DEFAULT_PREID = "alpha"
BUMP_CHOICES = (
    "major",
    "minor",
    "patch",
    "premajor",
    "preminor",
    "prepatch",
    "prerelease",
    "release",
)
PREID_CHOICES = ("alpha", "beta", "rc")


@dataclass(frozen=True, slots=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value: str) -> Self:
        match = SEMVER_RE.match(str(value).strip())
        if match is None:
            raise ValueError(f"Invalid semantic version: {value}")

        prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
        build = tuple(match.group(5).split(".")) if match.group(5) else ()
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=prerelease,
            build=build,
        )

    def __str__(self) -> str:
        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value = f"{value}-" + ".".join(self.prerelease)
        if self.build:
            value = f"{value}+" + ".".join(self.build)
        return value

    def without_prerelease(self) -> Self:
        return SemVer(self.major, self.minor, self.patch, (), self.build)

    def with_prerelease(self, *parts: str) -> Self:
        return SemVer(self.major, self.minor, self.patch, tuple(parts), self.build)

    def stable_key(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch

    def compare(self, other: Self) -> int:
        if self.stable_key() != other.stable_key():
            return -1 if self.stable_key() < other.stable_key() else 1
        if not self.prerelease and not other.prerelease:
            return 0
        if not self.prerelease:
            return 1
        if not other.prerelease:
            return -1
        return _compare_identifiers(self.prerelease, other.prerelease)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bump the Matter sidecar semver across pyproject.toml and src/manifest.json."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bump", choices=BUMP_CHOICES, help="Increment the current version.")
    mode.add_argument("--set-version", help="Set an explicit semantic version.")
    parser.add_argument(
        "--preid",
        choices=PREID_CHOICES,
        default=DEFAULT_PREID,
        help="Prerelease identifier used with pre* or prerelease bumps.",
    )
    parser.add_argument("--docker-image", default=DEFAULT_IMAGE, help="Docker image repository to pin in the manifest.")
    parser.add_argument("--dry-run", action="store_true", help="Print the next version without writing files.")
    return parser.parse_args()


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def dump_manifest(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_pyproject_version(text: str) -> SemVer:
    match = PYPROJECT_VERSION_RE.search(text)
    if match is None:
        raise ValueError("Unable to find project version in pyproject.toml")
    return SemVer.parse(match.group(2))


def write_pyproject_version(text: str, version: str) -> str:
    updated, count = PYPROJECT_VERSION_RE.subn(rf'\g<1>{version}\g<3>', text, count=1)
    if count != 1:
        raise ValueError("Unable to update project version in pyproject.toml")
    return updated


def resolve_target_version(current: SemVer, *, bump: str | None, set_version: str | None, preid: str) -> SemVer:
    if set_version is not None:
        target = SemVer.parse(set_version.strip())
        if target.compare(current) <= 0:
            raise ValueError(f"Explicit version must be newer than the current version ({current})")
        return target

    if bump is None:
        raise ValueError("Either --bump or --set-version is required")
    return bump_version(current, bump=bump, preid=preid)


def bump_version(current: SemVer, *, bump: str, preid: str) -> SemVer:
    stable = current.without_prerelease()
    if bump == "major":
        return SemVer(stable.major + 1, 0, 0)
    if bump == "minor":
        return SemVer(stable.major, stable.minor + 1, 0)
    if bump == "patch":
        return SemVer(stable.major, stable.minor, stable.patch + 1)
    if bump == "premajor":
        return SemVer(stable.major + 1, 0, 0).with_prerelease(preid, "1")
    if bump == "preminor":
        return SemVer(stable.major, stable.minor + 1, 0).with_prerelease(preid, "1")
    if bump == "prepatch":
        return SemVer(stable.major, stable.minor, stable.patch + 1).with_prerelease(preid, "1")
    if bump == "prerelease":
        return bump_prerelease(current, preid=preid)
    if bump == "release":
        if not current.prerelease:
            raise ValueError("Cannot promote a stable version. Use patch/minor/major or --set-version instead.")
        return current.without_prerelease()
    raise ValueError(f"Unsupported bump type: {bump}")


def bump_prerelease(current: SemVer, *, preid: str) -> SemVer:
    if not current.prerelease:
        return SemVer(current.major, current.minor, current.patch + 1).with_prerelease(preid, "1")

    stable = current.without_prerelease()
    current_preid = current.prerelease[0]
    if current_preid != preid:
        return stable.with_prerelease(preid, "1")

    suffix = list(current.prerelease[1:])
    if not suffix:
        return stable.with_prerelease(preid, "1")

    last_token = suffix[-1]
    if last_token.isdigit():
        suffix[-1] = str(int(last_token) + 1)
    else:
        suffix.append("1")
    return stable.with_prerelease(preid, *suffix)


def _compare_identifiers(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    for left_part, right_part in zip(left, right):
        if left_part == right_part:
            continue
        left_numeric = left_part.isdigit()
        right_numeric = right_part.isdigit()
        if left_numeric and right_numeric:
            return -1 if int(left_part) < int(right_part) else 1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return -1 if left_part < right_part else 1
    if len(left) == len(right):
        return 0
    return -1 if len(left) < len(right) else 1


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    pyproject_path = repo_root / "pyproject.toml"
    manifest_path = repo_root / "src" / "manifest.json"

    pyproject_text = pyproject_path.read_text()
    pyproject_version = read_pyproject_version(pyproject_text)
    manifest = load_manifest(manifest_path)
    manifest_version = SemVer.parse(str(manifest.get("version") or "").strip())

    if pyproject_version.compare(manifest_version) != 0:
        raise ValueError(
            f"Version mismatch: pyproject.toml={pyproject_version} manifest.json={manifest_version}"
        )

    target = resolve_target_version(
        pyproject_version,
        bump=args.bump,
        set_version=args.set_version,
        preid=args.preid,
    )
    target_version = str(target)

    if args.dry_run:
        print(target_version)
        return 0

    manifest["version"] = target_version
    runtime = manifest.setdefault("runtime", {}).setdefault("linux", {})
    container = runtime.setdefault("container", {})
    container["image"] = f"{args.docker_image}:{target_version}"

    pyproject_path.write_text(write_pyproject_version(pyproject_text, target_version))
    dump_manifest(manifest_path, manifest)
    print(target_version)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"release.py failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
