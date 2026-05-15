from __future__ import annotations

from pathlib import Path

from versioning import read_package_version, read_pyproject_version, validate_semver


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    pyproject_version = read_pyproject_version(project_root)
    package_version = read_package_version(project_root)

    if not pyproject_version or not package_version:
        print("Version check failed: version field missing.")
        return 1
    if pyproject_version != package_version:
        print(
            "Version check failed: "
            f"pyproject={pyproject_version} package={package_version} (must be identical)."
        )
        return 1
    if not validate_semver(pyproject_version):
        print(f"Version check failed: `{pyproject_version}` is not a valid semver string.")
        return 1

    print(f"Version check passed: {pyproject_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

