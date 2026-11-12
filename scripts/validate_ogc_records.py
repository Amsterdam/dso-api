import os
import subprocess
import sys

import requests

BASE_URL = os.getenv(
    "OGC_BASE_URL",
    "https://api.data.amsterdam.nl/v1/ogc/records",
).rstrip("/")

CHECKER_VERSION = os.getenv("OGC_CHECKER_VERSION", "latest")

TIMEOUT = 15

session = requests.Session()
session.headers.update({"Accept": "application/json"})


def get_json(url):
    """Fetch and return a JSON response."""
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()

    if "json" not in response.headers.get("Content-Type", "").lower():
        raise ValueError(f"Expected JSON response from {url}")

    return response.json()


def get_self_links(document, rel=None) -> list:
    """Return links, optionally filtered by relation."""
    links = document.get("links", [])

    if not isinstance(links, list):
        return []

    return [
        link
        for link in links
        if isinstance(link, dict)
        and isinstance(link.get("href"), str)
        and (rel is None or link.get("rel") == rel)
    ]


def get_record_paths(links, rel=None) -> list:
    """Return record links, exclude self link."""

    return [
        link.get("href")
        for link in links
        if isinstance(link, dict)
        and isinstance(link.get("href"), str)
        and (rel is None or link.get("rel") != rel)
    ]


def discover_collections():
    """Discover all collection endpoints."""
    print("\nDiscovering collections...")

    document = get_json(f"{BASE_URL}/collections")
    collections = document.get("collections")

    if not isinstance(collections, list):
        raise ValueError("Invalid collections response.")

    paths = []

    for collection in collections:
        if not isinstance(collection, dict):
            continue

        # Try to use the self links.
        links = collection.get("links")
        self_path = links[0].get("href")

        if not isinstance(self_path, str) or not self_path:
            print(f"[WARN] Collection has no valid path: {collection}")
            continue

        paths.append(self_path)

    if not paths:
        raise ValueError("No collections discovered.")

    print(f"Discovered {len(paths)} collections.")

    return paths


def discover_records(collection_path):
    """Discover individual record endpoints."""
    collection = get_json(collection_path)
    records = collection.get("records")

    if not isinstance(records, list):
        raise ValueError("Invalid records response.")

    record_links = records[0].get("links", [])

    # Exclude self path
    record_paths = get_record_paths(record_links, "self")

    if not record_paths:
        raise ValueError(f"No records paths found for {collection_path}")

    return record_paths


def validate_endpoint(url, endpoint_type):
    """Run the OGC checker against an endpoint."""
    print(f"\n[CHECK] {endpoint_type}: {url}")

    result = subprocess.run(
        [
            "npx",
            "--yes",
            f"@geonovum/ogc-checker@{CHECKER_VERSION}",
            "validate",
            "--standard",
            "ogc-api-records",
            "--input",
            url,
        ],
        text=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        print(f"[FAIL] {endpoint_type}: {url}")
        return False

    print(f"[PASS] {endpoint_type}: {url}")
    return True


def main():
    print("=" * 60)
    print("OGC API RECORDS VALIDATION")
    print("=" * 60)
    print(f"API URL: {BASE_URL}")

    try:
        collections = discover_collections()
    except (requests.RequestException, ValueError) as exc:
        print(f"\n[FATAL] Could not discover collections: {exc}")
        return 1

    results = {
        "collections": {"passed": 0, "failed": 0},
        "records": {"passed": 0, "failed": 0},
    }

    for collection_url in collections:
        # Validate the collection itself.
        passed = validate_endpoint(collection_url, "Collection")
        results["collections"]["passed" if passed else "failed"] += 1

        # Discover records belonging to this collection.
        try:
            records = discover_records(collection_url)
            print(f"Discovered {len(records)} records in {collection_url}")
        except (requests.RequestException, ValueError) as exc:
            print(f"[FAIL] Could not discover records: {exc}")
            results["records"]["failed"] += 1
            continue

        for record_url in records:
            passed = validate_endpoint(record_url, "Record")
            results["records"]["passed" if passed else "failed"] += 1

    total_passed = sum(item["passed"] for item in results.values())
    total_failed = sum(item["failed"] for item in results.values())

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    for name, counts in results.items():
        print(f"{name.capitalize()}: {counts['passed']} passed, {counts['failed']} failed")

    print(f"\nTotal passed: {total_passed}")
    print(f"Total failed: {total_failed}")

    if total_failed:
        print("\nOGC VALIDATION FAILED.")
        return 1

    print("\nOGC VALIDATION PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
