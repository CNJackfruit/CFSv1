#!/usr/bin/env python3
"""concurrent_test.py - simultaneous-transfer test tool (plan section 7.9).

One process, N threads. Every thread opens its own connection, logs in as
user (1 + i % 5), waits at a threading.Barrier so that all threads start
together, then does ONE transfer (upload or download) using the functions
from client/client2.py. One row per transfer is appended to transfers.csv
(format of section 4.5):

    tag,time,host,user,op,file,size_bytes,seconds,mbps,ok

At the end one summary line is printed: threads, successes, failures,
wall time, and min / average / max seconds per transfer.

Usage (localhost):
    python3 tests/concurrent_test.py 127.0.0.1 5 download tests/files/5MB.bin E2_N5
    python3 tests/concurrent_test.py 127.0.0.1 5 upload   tests/files/5MB.bin E2_up_N5

Usage (Mininet, spread N=20 over h2..h6, 4 threads each; same tag everywhere):
    mininet> h2 python3 tests/concurrent_test.py 10.0.0.1 4 download tests/files/5MB.bin E2_N20 &
    mininet> h3 python3 tests/concurrent_test.py 10.0.0.1 4 download tests/files/5MB.bin E2_N20 &
    ...

Assumptions: users user1..user5 exist, with password "user<n>123" by default
(change with --password-fmt). The aggregate numbers across hosts come from
analyse.py, not from the per-host summary lines.
"""
import argparse
import csv
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "client"))
import client2 as cl  # connect, login, list_files, upload, download

CSV_HEADER = ["tag", "time", "host", "user", "op", "file",
              "size_bytes", "seconds", "mbps", "ok"]
NUM_USERS = 5

csv_lock = threading.Lock()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def local_host_name(server_host):
    """Name for the 'host' column: h2..h6 in Mininet, otherwise the IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((server_host, 9))          # no packet is sent for UDP connect
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        return socket.gethostname()
    if ip.startswith("10.0.0."):
        return "h" + ip.rsplit(".", 1)[1]
    return ip


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def append_row(csv_path, row):
    """Append one row; the lock keeps threads from interleaving their writes."""
    with csv_lock:
        os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
        try:                                   # create + header exactly once,
            with open(csv_path, "x", newline="") as f:   # even across processes
                csv.writer(f).writerow(CSV_HEADER)
        except FileExistsError:
            pass
        with open(csv_path, "a", newline="") as f:
            csv.writer(f).writerow(row)


def login_as(args, user_n):
    sock = cl.connect(args.host, args.port)
    try:
        reader = cl.ProtocolReader(sock)
        cl.login(sock, f"user{user_n}", args.password_fmt.format(n=user_n), reader)
    except Exception:
        sock.close()
        raise
    return sock, reader


def close_quietly(sock):
    if sock is None:
        return
    try:
        sock.sendall(b'{"cmd": "QUIT"}\n')
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass


def setup_download(args, name, size, sha):
    """Make sure the file is on the server (not timed, not recorded)."""
    sock, reader = login_as(args, 1)
    try:
        meta = cl.list_files(sock, reader).get(name)
        if meta and meta.get("size") == size and meta.get("sha256") == sha:
            return                              # already there, e.g. another host did it
        cl.upload(sock, args.file, reader)
    finally:
        close_quietly(sock)


# --------------------------------------------------------------------------
# one transfer thread
# --------------------------------------------------------------------------
def worker(i, args, ctx):
    user_n = 1 + (i % NUM_USERS)
    user = f"user{user_n}"
    base = os.path.basename(args.file)
    size = os.path.getsize(args.file)
    sock = reader = None
    err = None
    ok = 0
    seconds = 0.0
    start_wall = time.time()

    # 1. connect + login (not part of the measured transfer)
    try:
        sock, reader = login_as(args, user_n)
    except Exception as e:
        err = e
        sock = None

    # 2. everybody starts together. A thread that failed above still waits,
    #    otherwise the others would hang at the barrier.
    try:
        ctx["barrier"].wait(timeout=args.barrier_timeout)
    except threading.BrokenBarrierError:
        pass

    # 3. the transfer
    if sock is not None:
        start_wall = time.time()
        t0 = time.perf_counter()
        try:
            if args.op == "upload":
                # unique name per thread/process; a symlink avoids copying 50 MB
                link_dir = os.path.join(ctx["workdir"], f"up_t{i}")
                os.makedirs(link_dir, exist_ok=True)
                up_name = f"{user}_t{i}_p{os.getpid()}_{base}"
                link = os.path.join(link_dir, up_name)
                try:
                    os.symlink(os.path.abspath(args.file), link)
                except OSError:
                    shutil.copyfile(args.file, link)
                name, nbytes, seconds = cl.upload(sock, link, reader)
            else:
                dest = os.path.join(ctx["workdir"], f"dl_t{i}")   # own folder per thread
                name, nbytes, seconds = cl.download(sock, base, dest, reader)
            ok = 1
        except Exception as e:
            err = e
            seconds = time.perf_counter() - t0
            name = base
        finally:
            close_quietly(sock)
    else:
        name = base

    end_wall = time.time()
    mbps = (size * 8 / seconds / 1e6) if (ok and seconds > 0) else 0.0
    append_row(args.csv, [args.tag, f"{start_wall:.3f}", ctx["host_name"], user,
                          args.op, name, size, f"{seconds:.4f}", f"{mbps:.2f}", ok])
    with ctx["lock"]:
        ctx["results"].append({"ok": ok, "seconds": seconds, "end": end_wall,
                               "err": None if ok else str(err)})


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Simultaneous upload/download test.")
    p.add_argument("host", help="file server IP (10.0.0.1 in Mininet)")
    p.add_argument("threads", type=int, help="number of simultaneous clients")
    p.add_argument("operation", choices=["upload", "download"])
    p.add_argument("file", help="local file to upload / to use as download source")
    p.add_argument("tag", help="experiment name, e.g. E2_N10 or E1_up_10MB")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--password-fmt", default="user{n}123",
                   help="password of user<n> (default: user{n}123)")
    p.add_argument("--csv", default=os.path.join(HERE, "..", "results", "transfers.csv"),
                   help="CSV to append to (default: results/transfers.csv)")
    p.add_argument("--name", help="value for the host column (default: h<N> from the IP)")
    p.add_argument("--barrier-timeout", type=float, default=60.0)
    p.add_argument("--keep", action="store_true", help="keep temp/download folders")
    args = p.parse_args()
    args.op = args.operation

    if args.threads < 1:
        sys.exit("[-] threads must be at least 1")
    if not os.path.isfile(args.file):
        sys.exit(f"[-] file not found: {args.file}")

    size = os.path.getsize(args.file)
    base = os.path.basename(args.file)

    # download tests: put the file on the server first (not recorded, no barrier)
    if args.op == "download":
        try:
            setup_download(args, base, size, sha256_of(args.file))
        except Exception as e:
            sys.exit(f"[-] set-up upload failed: {e}")

    ctx = {
        "workdir": tempfile.mkdtemp(prefix="cft_"),
        "host_name": args.name or local_host_name(args.host),
        "results": [], "lock": threading.Lock(),
        "start": None,
    }

    def mark_start():                         # runs once, when the barrier opens
        ctx["start"] = time.time()
    ctx["barrier"] = threading.Barrier(args.threads, action=mark_start)

    threads = [threading.Thread(target=worker, args=(i, args, ctx), daemon=True)
               for i in range(args.threads)]
    t_begin = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if not args.keep:
        shutil.rmtree(ctx["workdir"], ignore_errors=True)

    res = ctx["results"]
    good = [r["seconds"] for r in res if r["ok"]]
    failed = len(res) - len(good)
    start = ctx["start"] or t_begin
    wall = max(r["end"] for r in res) - start

    if good:
        stats = (f"min={min(good):.3f}s avg={sum(good) / len(good):.3f}s "
                 f"max={max(good):.3f}s")
    else:
        stats = "min=n/a avg=n/a max=n/a"
    print(f"[{args.tag}] {args.op} threads={args.threads} ok={len(good)} "
          f"failed={failed} wall={wall:.3f}s {stats}")

    for msg in sorted({r["err"] for r in res if r["err"]})[:5]:
        print(f"    error: {msg}", file=sys.stderr)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
