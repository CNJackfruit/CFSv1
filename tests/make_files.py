#!/usr/bin/env python3
"""make_files.py - create random-content test files (plan section 7.9, step 1).

Creates 1, 5, 10 and 50 MB files in tests/files/ (1MB.bin, 5MB.bin, ...).
Content comes from os.urandom and is written in 64 KB chunks, so even the
50 MB file is never held in memory.

Usage:
    python3 tests/make_files.py                 # default sizes
    python3 tests/make_files.py --sizes 1 5     # only 1 MB and 5 MB
    python3 tests/make_files.py --dir /tmp/f    # another output folder
"""
import argparse
import os

CHUNK = 65536                      # 64 KB, same as the transfer chunk size
MB = 1024 * 1024
DEFAULT_SIZES_MB = [1, 5, 10, 50]
HERE = os.path.dirname(os.path.abspath(__file__))


def make_file(path, size_bytes):
    """Write size_bytes of random data to path, one chunk at a time."""
    remaining = size_bytes
    with open(path, "wb") as f:
        while remaining > 0:
            n = min(CHUNK, remaining)
            f.write(os.urandom(n))
            remaining -= n


def main():
    parser = argparse.ArgumentParser(description="Create random test files.")
    parser.add_argument("--sizes", type=int, nargs="+", default=DEFAULT_SIZES_MB,
                        help="file sizes in MB (default: 1 5 10 50)")
    parser.add_argument("--dir", default=os.path.join(HERE, "files"),
                        help="output folder (default: tests/files/)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite files that already exist with the right size")
    args = parser.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    for mb in args.sizes:
        path = os.path.join(args.dir, f"{mb}MB.bin")
        size = mb * MB
        if (not args.force and os.path.exists(path)
                and os.path.getsize(path) == size):
            print(f"[=] {path} already exists ({size} bytes), skipping")
            continue
        make_file(path, size)
        print(f"[+] created {path} ({size} bytes)")


if __name__ == "__main__":
    main()

