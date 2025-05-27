#!/usr/bin/env python3
"""
safe_move.py — v 9.4  (console + directory-layout tweak)

What's new
──────────
* **Root-folder preserved**: when you run

      safe_move.py /example/X  /target

  every file that was under */example/X* is now copied to */target/X/* …  
  (The *X* directory is created automatically if it doesn't exist.)
* No other behaviour changes.  Copy / hash / journalling / progress bars all
  work exactly as in v 9.3.
"""

from __future__ import annotations
import argparse, hashlib, itertools, logging, os, shutil, signal, sqlite3, sys
from pathlib import Path
from typing import Generator
from time import monotonic
import shutil as _shutil

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("Please `pip install tqdm` first.")

# ────────────────  Config  ────────────────
DB, LOGFILE     = "copy_progress.db", "safe_move.log"
CHUNK           = 1 << 20
TEMP_SFX        = ".part"
SAFETY_FREE     = 5 << 30          # ≥ 5 GiB free

COLS            = _shutil.get_terminal_size(fallback=(120, 20)).columns
BAR_NCOLS       = min(100, COLS)   # fixed bar width

SPIN            = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
ESC_CLEAR       = "\x1b[K"
LABEL_PAD       = "       "        # column alignment

# ────────────────  Pretty helpers  ────────────────
def fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if b < 1024 or unit == "PB":
            return f"{b/1024 if unit!='B' else b:.1f} {unit}"
        b /= 1024

def fmt_secs(s: float) -> str:
    m, s = divmod(int(round(s)), 60)
    return f"{m} min {s} s" if m else f"{s} s"

# ────────────────  Logging  ────────────────
class _TqdmHdlr(logging.Handler):
    def emit(self, rec): tqdm.write(self.format(rec))

logging.basicConfig(
    level=logging.INFO,
    handlers=[_TqdmHdlr(), logging.FileHandler(LOGFILE, encoding="utf-8")],
    format="%(asctime)s %(levelname)s: %(message)s",
)
log = logging.getLogger("safe_move")

# ────────────────  Misc helpers  ────────────────
def print_desc(bar: tqdm, text: str):
    bar.set_description(text + ESC_CLEAR, refresh=False)
    bar.refresh()

def shorten(txt: str, avail: int) -> str:
    if len(txt) <= avail:
        return txt
    keep = (avail - 3) // 2
    return txt[:keep] + "..." + txt[-keep:]

def sha256sum(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(CHUNK), b""):
            h.update(blk)
    return h.hexdigest()

def _with_stem(p: Path, stem: str) -> Path:
    try:
        return p.with_stem(stem)
    except AttributeError:
        return p.with_name(stem + p.suffix)

def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    i = 1
    while True:
        cand = _with_stem(p, f"{p.stem}_{i}")
        if not cand.exists():
            return cand
        i += 1

def enough_space(dir_: Path, need: int) -> bool:
    probe = dir_
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    s = os.statvfs(probe)
    return (s.f_bavail * s.f_frsize) - SAFETY_FREE >= need

def verify(src: Path, dst: Path) -> bool:
    return (
        src.stat().st_size == dst.stat().st_size
        and sha256sum(src) == sha256sum(dst)
    )

def fsync_path(p: Path):
    fd = os.open(p, os.O_RDONLY | (os.O_DIRECTORY if p.is_dir() else 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def fmt_actions(state: str, spinner: str) -> str:
    parts: list[str] = []
    for phase in ("Copying", "Hashing", "Renaming"):
        if state == phase.lower():
            parts.append(f"{phase} {spinner}")
        elif (phase == "Copying" and state in ("hashing", "renaming", "done")) or \
             (phase == "Hashing" and state in ("renaming", "done")) or \
             (phase == "Renaming" and state == "done"):
            parts.append(f"{phase} DONE")
        else:
            parts.append(phase)
    return "Actions:" + LABEL_PAD + "  –  ".join(parts)

def _prune_empty_dirs(start: Path, stop: Path):
    p = start
    while p != stop and p != p.parent:
        try:
            p.rmdir()
        except OSError:
            break
        p = p.parent

# ────────────────  Journal  ────────────────
class Journal:
    def __init__(self, db: Path):
        self.conn = sqlite3.connect(db)
        self.conn.execute("PRAGMA busy_timeout=10000")
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS progress("
            "src TEXT PRIMARY KEY, dst TEXT, done INTEGER DEFAULT 0)"
        )
        self.conn.commit()

    def mark(self, src: Path, dst: Path, done: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO progress VALUES (?,?,?)",
            (str(src), str(dst), done),
        )
        self.conn.commit()

    def pending(self, root: Path) -> Generator[Path, None, None]:
        done = {
            Path(r[0])
            for r in self.conn.execute("SELECT src FROM progress WHERE done=1")
        }
        for p in root.rglob("*"):
            if p.is_file() and p not in done:
                yield p

    def close(self):
        self.conn.close()

# ────────────────  Signals  ────────────────
_stop = False
def _sig(*_):
    global _stop
    _stop = True
    #log.warning("Signal received – finishing current file then stopping.")
signal.signal(signal.SIGINT, _sig)
signal.signal(signal.SIGTERM, _sig)

# ────────────────  Copier  ────────────────
def copy_one(
    src: Path,
    src_root: Path,
    dst_root: Path,
    journal: Journal,
    info: tqdm,
    bar: tqdm,
    act: tqdm,
    idx: int,
    total_files: int,
):
    overall_start = monotonic()

    rel = src.relative_to(src_root)
# path within src_root
    dst = dst_root / rel
# full destination file path
    if dst.exists() and not verify(src, dst):
        dst = unique_path(dst)

    tmp = dst.with_suffix(dst.suffix + TEMP_SFX)
    size = src.stat().st_size
    dst.parent.mkdir(parents=True, exist_ok=True)

    if not enough_space(dst.parent, size):
        print_desc(act, "Actions:" + LABEL_PAD + "SKIP (disk full)")
        return

    done = tmp.stat().st_size if tmp.exists() else 0
    if done > size:
        tmp.unlink()
        done = 0

    # ── live block prep ───────────────────────────────────────────
    print_desc(
        info,
        "Current file:" + LABEL_PAD +
        shorten(src.name, COLS - len("Current file:" + LABEL_PAD) - 1),
    )
    bar.reset(total=size)
    bar.update(done)
    print_desc(act, fmt_actions("copying", next(SPIN)))

    # ─────────────────── Copy ─────────────────────────────────────
    last = monotonic()
    while True:
        with src.open("rb") as fin, tmp.open("ab" if done else "wb") as fout:
            fin.seek(done)
            chunk = fin.read(CHUNK)
            if not chunk:
                break
            fout.write(chunk)
            done += len(chunk)
            bar.update(len(chunk))
            if monotonic() - last > 0.2:
                print_desc(act, fmt_actions("copying", next(SPIN)))
                last = monotonic()

    if _stop:
        return

    # ─────────────────── Hash ─────────────────────────────────────
    last = monotonic()
    print_desc(act, fmt_actions("hashing", next(SPIN)))
    if not verify(src, tmp):
        print_desc(act, "Actions:" + LABEL_PAD + "HASH FAIL")
        return
    while monotonic() - last < 0.6:
        print_desc(act, fmt_actions("hashing", next(SPIN)))
        last = monotonic()

    # ─────────────────── Rename ───────────────────────────────────
    print_desc(act, fmt_actions("renaming", next(SPIN)))
    tmp.rename(dst)
    fsync_path(dst.parent)

    shutil.copystat(src, dst, follow_symlinks=False)
    st = src.stat()
    if os.geteuid() == 0:
        os.chown(dst, st.st_uid, st.st_gid)
    src.unlink()
    journal.mark(src, dst, 1)

    # ── tidy empty directories under src_root ─────────────────────
    _prune_empty_dirs(src.parent, src_root)

    print_desc(act, fmt_actions("done", ""))
    bar.refresh()           # force final 100 %

    duration = monotonic() - overall_start
    tqdm.write(
        f"INFO: OK {idx}/{total_files}  "
        f"Size: {fmt_size(size)}  "
        f"Time: {fmt_secs(duration)}  "
        f"FILE: {dst.name}"
    )

# ────────────────  Driver  ────────────────
def drive(src_root: Path, dst_root: Path):
    """
    Ensures that the *leaf* folder of src_root is recreated under dst_root.

        src_root  = /example/X
        dst_root  = /target
        effective destination root = /target/X
    """
    # build /target/X
    dst_root_final = dst_root / src_root.name
    dst_root_final.mkdir(parents=True, exist_ok=True)

    journal = Journal(Path(DB))
    total_files = sum(1 for p in src_root.rglob("*") if p.is_file())

    files_bar = tqdm(
        total=total_files,
        bar_format="Files  {n_fmt}/{total_fmt} |{bar}| {percentage:3.0f} %",
        ncols=BAR_NCOLS,
        position=0,
        leave=True,
    )

    info_bar = tqdm(total=0, bar_format="{desc}", ncols=COLS, position=1, leave=True)
    prog_bar = tqdm(
        total=1,
        unit="B",
        unit_scale=True,
        bar_format=(
            "Progress:" + LABEL_PAD +
            "|{bar}| {percentage:3.0f} %  {n_fmt}/{total_fmt}  {rate_fmt}"
        ),
        ncols=BAR_NCOLS,
        position=2,
        leave=True,
    )
    act_bar = tqdm(total=0, bar_format="{desc}", ncols=COLS, position=3, leave=True)

    for src in journal.pending(src_root):
        if _stop:
            break
        copy_one(
            src,
            src_root,
            dst_root_final,
            journal,
            info_bar,
            prog_bar,
            act_bar,
            idx=files_bar.n + 1,
            total_files=total_files,
        )
        files_bar.update(1)

    # try to remove now-empty src_root
    try:
        src_root.rmdir()
    except OSError:
        pass

    files_bar.close()
    info_bar.close()
    prog_bar.close()
    act_bar.close()
    journal.close()
    log.info("Session finished – re-run to resume.")

# ────────────────  CLI  ────────────────
def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Crash-resilient safe mover")
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    return p.parse_args()

if __name__ == "__main__":
    args = parse()
    if not args.source.is_dir():
        sys.exit(f"Source is not a directory: {args.source}")
    drive(args.source.resolve(), args.destination.resolve())