#!/usr/bin/env python3
"""
HubSpot install — pulls your HubSpot property definitions into a local CSV.

Flow:
    1. We generate a random device_code on your machine.
    2. We open Sculpted's hosted OAuth app in your default browser, with the
       device_code as a query parameter.
    3. You authorize the app inside HubSpot.
    4. The app exports your property definitions (NOT your contact or company
       records — schema only) to a CSV blob, keyed by the device_code.
    5. This script polls until the CSV is ready, then writes it to
       tmp/hubspot-properties.csv.

Privacy posture:
    The Sculpted app holds `crm.objects.contacts.read` + `.companies.read`
    scopes (the minimum HubSpot allows for fetching property definitions
    plus total record counts). The server-side code only reads:
      • Property definitions via /crm/v3/properties/* (schemas only)
      • Total record counts via /crm/v3/objects/*/search (limit=1, total only)
    No record bodies (contact emails, company details, etc.) are ever read,
    logged, or persisted. See the repo README + Sculpted's audit notes.

Usage:
    python tools/install_hubspot.py
    python tools/install_hubspot.py --output tmp/my-properties.csv
    python tools/install_hubspot.py --timeout 600

Environment (optional):
    SCULPTED_HUBSPOT_INSTALL_BASE
        Override the install URL base. Defaults to Sculpted's hosted Supabase.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

DEFAULT_BASE = "https://aofpyrbquqxovunsxosb.supabase.co/functions/v1"
DEFAULT_TIMEOUT_SEC = 300         # 5 minutes — typical install completes in <60s
MAX_CSV_BYTES = 50_000_000        # 50 MB defense-in-depth cap on what we'll write to disk
POLL_INTERVAL_SEC = 3
DEVICE_CODE_BYTES = 24            # 24 bytes → 32-char URL-safe base64

ROOT = pathlib.Path(__file__).resolve().parent.parent


def generate_device_code() -> str:
    """Cryptographically random URL-safe token. Min 16 chars enforced server-side."""
    return secrets.token_urlsafe(DEVICE_CODE_BYTES)


def build_install_url(base: str, device_code: str) -> str:
    qs = urllib.parse.urlencode({"mode": "local-csv", "device_code": device_code})
    return f"{base.rstrip('/')}/hubspot-oauth-start?{qs}"


def build_fetch_url(base: str, device_code: str) -> str:
    qs = urllib.parse.urlencode({"device_code": device_code})
    return f"{base.rstrip('/')}/hubspot-csv-fetch?{qs}"


def poll_for_csv(fetch_url: str, timeout_sec: int) -> bytes:
    """
    Poll the fetch endpoint until the CSV is ready.

    Returns the CSV body as bytes on 200.
    Raises RuntimeError on 410 (expired) or timeout.
    """
    deadline = time.monotonic() + timeout_sec
    last_status: int | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(fetch_url, timeout=15) as resp:
                last_status = resp.status
                if resp.status == 200:
                    # Defense-in-depth size cap. Property-definitions CSVs are typically
                    # well under 1 MB; 50 MB is a generous ceiling that prevents an
                    # unbounded write if the upstream ever returns something pathological.
                    declared_len = resp.headers.get("Content-Length")
                    if declared_len and declared_len.isdigit() and int(declared_len) > MAX_CSV_BYTES:
                        raise RuntimeError(
                            f"CSV body unexpectedly large ({int(declared_len):,} bytes, cap is {MAX_CSV_BYTES:,}). "
                            "Refusing to write. If your HubSpot has an unusual property volume, raise the cap in install_hubspot.py."
                        )
                    body = resp.read(MAX_CSV_BYTES + 1)
                    if len(body) > MAX_CSV_BYTES:
                        raise RuntimeError(
                            f"CSV body exceeded {MAX_CSV_BYTES:,} bytes. Refusing to write."
                        )
                    return body
                # 202 falls through — still waiting
        except urllib.error.HTTPError as e:
            last_status = e.code
            if e.code == 410:
                raise RuntimeError(
                    "The CSV expired before download. The install may have stalled, "
                    "or this script ran into a connectivity hiccup. Re-run the command."
                )
            if e.code == 404:
                # device_code unknown — caller bug or completely fresh
                pass  # treat like 202, keep polling within timeout
            elif e.code == 400:
                raise RuntimeError(
                    "Server rejected the device_code as malformed. Re-run the command."
                )
            elif e.code >= 500:
                # Transient — keep polling
                pass
            else:
                raise RuntimeError(f"Unexpected HTTP {e.code} from fetch endpoint.")
        except urllib.error.URLError as e:
            # Network hiccup. Keep polling within timeout.
            print(f"  (network: {e.reason} — retrying)")

        time.sleep(POLL_INTERVAL_SEC)

    raise RuntimeError(
        f"Timed out after {timeout_sec}s waiting for the install to complete. "
        f"Last status: {last_status}. If you completed the OAuth flow, try increasing --timeout."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install Sculpted's HubSpot app and download your property definitions to a local CSV.",
    )
    parser.add_argument(
        "--output", type=pathlib.Path,
        default=ROOT / "tmp" / "hubspot-properties.csv",
        help="Where to write the downloaded CSV. Default: tmp/hubspot-properties.csv",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SEC,
        help=f"Total time (seconds) to wait for install + sync. Default: {DEFAULT_TIMEOUT_SEC}",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Print the install URL but don't open a browser. Useful on headless setups.",
    )
    args = parser.parse_args()

    base = os.environ.get("SCULPTED_HUBSPOT_INSTALL_BASE", DEFAULT_BASE)
    device_code = generate_device_code()
    install_url = build_install_url(base, device_code)
    fetch_url = build_fetch_url(base, device_code)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print()
    print("Sculpted HubSpot Install")
    print("=" * 56)
    print()
    print("Scopes requested: crm.objects.contacts.read + crm.objects.companies.read")
    print("What we read:    property definitions (schema) + record counts only")
    print("What we DON'T:   any individual contact or company records")
    print()
    print("Install URL:")
    print(f"  {install_url}")
    print()

    if args.no_browser:
        print("Open the URL above in your browser, complete the HubSpot consent,")
        print("then come back here.")
    else:
        print("Opening your browser...")
        try:
            webbrowser.open(install_url, new=2)
        except Exception as e:
            print(f"(could not auto-open browser: {e})")
            print("Copy the URL above into your browser manually.")

    print()
    print(f"Waiting for install to complete (up to {args.timeout}s). Press Ctrl+C to cancel.")
    print()

    try:
        csv_bytes = poll_for_csv(fetch_url, timeout_sec=args.timeout)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1
    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 2

    args.output.write_bytes(csv_bytes)

    line_count = csv_bytes.count(b"\n")
    print(f"Done. Wrote {len(csv_bytes):,} bytes ({line_count:,} rows incl. header) to:")
    print(f"  {args.output}")
    print()
    print("Next steps:")
    print(f"  • Inspect the CSV: open {args.output}")
    print(f"  • Run cleanup against it: python tools/enrich.py {args.output}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
