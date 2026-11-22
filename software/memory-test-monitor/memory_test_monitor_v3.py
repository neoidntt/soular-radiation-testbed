"""
Memory Test Monitor v3 — FRAM & FLASH Radiation Test UI
========================================================
Connects to a Teensy (or any MCU) via UART at 115200 baud.

Hardware geometry (must match the Arduino sketch exactly):
  FRAM  : 8 192 B = 8 KB  →  128 chunks  × 64 B each  →  128 data-points / full read
  FLASH : 4 194 304 B = 4 MB  →  16 384 pages × 256 B  →  16 384 data-points / full scan
          NOTE: the sketch comment says "8 MB" but 8*1024*512 = 4 194 304 B = 4 MB.

Arduino serial protocol (Serial4 @ 115200):
  FRAM  chunk  : "{global_loop_cnt} ...Loop done. Errors: {cum_errors}"
  FLASH page   : " Address: {addr} ...FLASH Errors: {cum_errors}"
  FLASH done   : "{FLASH_cnt} ...FLASH Read done. Errors: {total}"

pip install pyserial matplotlib
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import csv
import os
import random
from datetime import datetime
import matplotlib
import matplotlib.ticker
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ══════════════════════════════════════════════════════════════════════════════
#  HARDWARE CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
BAUD        = 115200

FLASH_SIZE  = 8 * 1024 * 512     # 4 194 304 B  (4 MB — Arduino comment wrong)
FLASH_PAGE  = 256                 # bytes per page-program / read call
FLASH_PAGES = FLASH_SIZE // FLASH_PAGE   # 16 384

FRAM_SIZE   = 8192                # 8 KB
FRAM_CHUNK  = 64                  # bytes per read / verify chunk
FRAM_CHUNKS = FRAM_SIZE // FRAM_CHUNK    # 128

WATCHDOG_S  = 10                  # silence seconds before watchdog alert

# ══════════════════════════════════════════════════════════════════════════════
#  COLOUR / FONT THEME
# ══════════════════════════════════════════════════════════════════════════════
BG  = '#0d1117'
PNL = '#161b22'
ACC = '#21262d'
FGT = '#c9d1d9'
FGD = '#8b949e'
GRN = '#3fb950'
RED = '#f85149'
BLU = '#58a6ff'
AMB = '#d29922'
ACN = '#79c0ff'
PRP = '#bc8cff'
ORG = '#ff7b2c'   # simulation accent colour
MNO = 'Courier New'

# ══════════════════════════════════════════════════════════════════════════════
#  SHARED STATE
# ══════════════════════════════════════════════════════════════════════════════

# ── FRAM ──
# Each FRAM_Read() emits 128 lines (one per 64-B chunk).
# errorCount is CUMULATIVE within that read cycle.
# We diff consecutive values to get per-chunk delta errors.
fram_cum     = []   # cumulative errors so far in current cycle  (0..128 entries)
fram_deltas  = []   # per-chunk delta errors, current cycle
fram_history = []   # completed cycles:  list of 128-element delta lists
fram_session = []   # CSV rows (every chunk ever received)

# ── FRAM time-bucket state ──
# X axis = wall-clock time since first chunk ever received, bucketed at 0.5 s.
# Each bucket stores: total errors, chunk count, whether any chunk arrived.
FRAM_BUCKET_S   = 0.5          # seconds per bucket
fram_t0         = None         # wall-clock time of the very first FRAM chunk
fram_buckets    = {}           # bucket_index → {'errors': int, 'chunks': int}
fram_bucket_max = 0            # highest bucket index seen so far (for gray placeholders)

# ── FLASH ──
# FLASH_Read() emits 16 384 lines (one per 256-B page).
# errorCount is CUMULATIVE within that scan.
flash_addrs   = []  # page start addresses (bytes), current scan
flash_cum     = []  # cumulative errors per page, current scan
flash_deltas  = []  # per-page delta errors, current scan
flash_history = []  # completed scans: list of (addrs_list, deltas_list) tuples
flash_session = []  # CSV rows

# ── FLASH time-bucket state ──
# Same 0.5-s bucketing as FRAM.
# Y axis = error rate (errors / pages) in that bucket.
# Dot size encodes the same error rate — larger = worse fraction of bad pages.
FLASH_BUCKET_S   = 0.5   # seconds per bucket
flash_t0         = None  # wall-clock time of the very first FLASH page received
flash_buckets    = {}    # bucket_index → {'errors': int, 'pages': int}
flash_bucket_max = 0     # highest bucket index seen (drives gray placeholder range)

error_log_lines = []

# ── Connection ──
ser            = None
running        = False
last_data_time = None   # wall-clock time of last non-empty received line

# ── Arduino-mirrored counters ──
mask_FRAM    = 0   # 1 = FRAM tests masked on Arduino
mask_FLASH   = 0   # 1 = FLASH tests masked on Arduino
loop_cnt     = 0   # global cumulative FRAM chunk counter (never resets)
FLASH_cnt    = 0   # completed FLASH scans
out_loop_cnt = 0   # outer read-loop iteration

# ── Simulation ──
sim_running    = False
sim_stop_event = threading.Event()

# ── Write state ──
write_in_progress = False
write_status = ""


# ══════════════════════════════════════════════════════════════════════════════
#  LINE PARSER  (shared by real serial AND simulation)
# ══════════════════════════════════════════════════════════════════════════════

def handle_line(line: str):
    """Parse one text line.  MUST be called on the Tk main thread."""
    global last_data_time, loop_cnt, FLASH_cnt

    append_output(f"[RX] {line}")
    last_data_time = time.time()
    set_led(True)

    # ── FRAM chunk ─────────────────────────────────────────────────────────────
    # Format: "<loop_cnt> ...Loop done. Errors: <cum_errors>"
    if '...Loop done. Errors:' in line:
        try:
            parts      = line.split()
            loop_num   = int(parts[0])
            cum_errors = int(parts[parts.index('Errors:') + 1])
            loop_cnt   = loop_num

            chunk_i = (loop_num - 1) % FRAM_CHUNKS   # 0-indexed within this cycle

            if chunk_i == 0:
                # New cycle starting — archive previous if it was complete
                if len(fram_deltas) == FRAM_CHUNKS:
                    fram_history.append(list(fram_deltas))
                fram_cum.clear()
                fram_deltas.clear()

            if chunk_i == len(fram_cum):   # only accept next expected chunk
                prev  = fram_cum[-1] if fram_cum else 0
                delta = max(0, cum_errors - prev)
                fram_cum.append(cum_errors)
                fram_deltas.append(delta)

                if delta > 0:
                    log_error(
                        f"[FRAM] chunk {chunk_i}  addr 0x{chunk_i*FRAM_CHUNK:04X}"
                        f"  — {delta} new error(s)  (cum={cum_errors})"
                        + ("  [SIM]" if sim_running else ""))

                cycle_num = (loop_num - 1) // FRAM_CHUNKS + 1

                # ── Time-bucket accounting ──────────────────────────────────
                # Assign this chunk to the 0.5-s bucket it arrived in,
                # measured from the very first FRAM chunk of the session.
                now = time.time()
                if fram_t0 is None:
                    globals()['fram_t0'] = now
                elapsed    = now - fram_t0
                bucket_idx = int(elapsed / FRAM_BUCKET_S)
                if bucket_idx not in fram_buckets:
                    fram_buckets[bucket_idx] = {'errors': 0, 'chunks': 0}
                fram_buckets[bucket_idx]['errors'] += delta
                fram_buckets[bucket_idx]['chunks'] += 1
                if bucket_idx > fram_bucket_max:
                    globals()['fram_bucket_max'] = bucket_idx

                t_start = fram_t0 + bucket_idx * FRAM_BUCKET_S
                fram_session.append({
                    'cycle':                cycle_num,
                    'chunk':                chunk_i,
                    'address_bytes':        chunk_i * FRAM_CHUNK,
                    'cumulative_errors':    cum_errors,
                    'errors_this_chunk':    delta,
                    'bucket_index':         bucket_idx,
                    'bucket_t_start_s':     round(bucket_idx * FRAM_BUCKET_S, 1),
                    'chunks_in_bucket':     fram_buckets[bucket_idx]['chunks'],
                    'errors_in_bucket':     fram_buckets[bucket_idx]['errors'],
                    'timestamp':            datetime.now().strftime('%H:%M:%S'),
                    'simulated':            '1' if sim_running else '0',
                })

            refresh_fram_graph()
        except (ValueError, IndexError):
            pass

    # ── FLASH page ─────────────────────────────────────────────────────────────
    # Format: " Address: <addr> ...FLASH Errors: <cum_errors>"
    elif 'Address:' in line and '...FLASH Errors:' in line:
        try:
            parts      = line.split()
            addr       = int(parts[parts.index('Address:') + 1])
            cum_errors = int(parts[parts.index('Errors:') + 1])

            prev  = flash_cum[-1] if flash_cum else 0
            delta = max(0, cum_errors - prev)
            flash_addrs.append(addr)
            flash_cum.append(cum_errors)
            flash_deltas.append(delta)

            if delta > 0:
                log_error(
                    f"[FLASH] page 0x{addr:08X}  ({addr//1024} KB)"
                    f"  — {delta} new error(s)  (cum={cum_errors})"
                    + ("  [SIM]" if sim_running else ""))

            # ── FLASH time-bucket accounting ────────────────────────────────
            now = time.time()
            if flash_t0 is None:
                globals()['flash_t0'] = now
            elapsed    = now - flash_t0
            bucket_idx = int(elapsed / FLASH_BUCKET_S)
            if bucket_idx not in flash_buckets:
                flash_buckets[bucket_idx] = {'errors': 0, 'pages': 0}
            flash_buckets[bucket_idx]['errors'] += delta
            flash_buckets[bucket_idx]['pages']  += 1
            if bucket_idx > flash_bucket_max:
                globals()['flash_bucket_max'] = bucket_idx

            pages_in_bkt  = flash_buckets[bucket_idx]['pages']
            errors_in_bkt = flash_buckets[bucket_idx]['errors']
            error_rate    = errors_in_bkt / pages_in_bkt if pages_in_bkt else 0.0

            flash_session.append({
                'scan':                  FLASH_cnt + 1,
                'address_bytes':         f'0x{addr:08X}',
                'address_kb':            addr // 1024,
                'cumulative_errors':     cum_errors,
                'errors_this_page':      delta,
                'bucket_index':          bucket_idx,
                'bucket_t_start_s':      round(bucket_idx * FLASH_BUCKET_S, 1),
                'pages_in_bucket':       pages_in_bkt,
                'errors_in_bucket':      errors_in_bkt,
                'error_rate_in_bucket':  round(error_rate, 6),
                'timestamp':             datetime.now().strftime('%H:%M:%S'),
                'simulated':             '1' if sim_running else '0',
            })
            # Graph refresh is timer-driven (periodic_flash_refresh) — NOT per page —
            # because redrawing 16 384 times per scan would freeze the UI.
        except (ValueError, IndexError):
            pass

    # ── FLASH scan complete ─────────────────────────────────────────────────────
    # Format: "<FLASH_cnt> ...FLASH Read done. Errors: <total>"
    elif '...FLASH Read done. Errors:' in line:
        try:
            parts     = line.split()
            FLASH_cnt = int(parts[0])
            total     = int(parts[parts.index('Errors:') + 1])

            flash_history.append((list(flash_addrs), list(flash_deltas)))
            flash_addrs.clear()
            flash_cum.clear()
            flash_deltas.clear()

            flash_session.append({
                'scan':              FLASH_cnt,
                'address_bytes':     'SUMMARY',
                'address_kb':        '',
                'cumulative_errors': total,
                'errors_this_page':  total,
                'timestamp':         datetime.now().strftime('%H:%M:%S'),
                'simulated':         '1' if sim_running else '0',
            })
            refresh_flash_graph()
        except (ValueError, IndexError):
            pass

    # ── Write operation feedback ────────────────────────────────────────────────
    # Detect write operation messages from Arduino
    elif 'Writing FRAM Start' in line:
        globals()['write_status'] = "FRAM write in progress..."
        append_output(f"[WRITE] ▶ {write_status}")
    elif 'FRAM write complete' in line:
        globals()['write_status'] = "FRAM write complete ✓"
        append_output(f"[WRITE] ✓ {write_status}")
    elif 'Chip erase' in line:
        globals()['write_status'] = "FLASH chip erase in progress..."
        append_output(f"[WRITE] ▶ {write_status}")
    elif 'Erase done' in line:
        globals()['write_status'] = "FLASH erase complete ✓"
        append_output(f"[WRITE] ✓ {write_status}")
    elif 'Programming flash' in line:
        globals()['write_status'] = "FLASH programming in progress..."
        append_output(f"[WRITE] ▶ {write_status}")
    elif 'Written:' in line:
        globals()['write_status'] = line
        append_output(f"[WRITE] {write_status}")
    elif 'Programming complete' in line:
        globals()['write_status'] = "FLASH programming complete ✓"
        append_output(f"[WRITE] ✓ {write_status}")
    elif '[WRITE_COMPLETE]' in line:
        globals()['write_in_progress'] = False
        append_output("[WRITE] ✓✓✓ ALL WRITES COMPLETE ✓✓✓")


# ══════════════════════════════════════════════════════════════════════════════
#  SIMULATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _sim_worker(interval_s: float, stop_ev: threading.Event):
    """
    Runs in a background thread.  Synthesises realistic Arduino UART output.

    One outer loop iteration:
      1. Full FRAM read  — 128 lines at ~40 ms each  (~5 s real-time)
      2. Full FLASH scan — 16 384 lines compressed to ~2 s real-time
         (real hardware pages take a fraction of a ms each but there are 16 K of them)

    Error injection (random each iteration):
      FRAM  — 0–3 chunks each get 1–3 errors
      FLASH — 0–6 pages each get 1–5 errors, scattered across the address space

    After both memories finish, the thread waits `interval_s` before the next
    iteration, allowing the user to set a gap between simulated test loops.
    """
    global sim_running

    # Shadow real counters so we don't corrupt live data
    local_loop  = loop_cnt
    local_flash = FLASH_cnt

    while not stop_ev.is_set():

        # ── randomise errors for this iteration ────────────────────────────────
        fram_bad = {
            random.randint(0, FRAM_CHUNKS - 1): random.randint(1, 3)
            for _ in range(random.randint(0, 3))
        }
        flash_bad = {
            random.randint(0, FLASH_PAGES - 1): random.randint(1, 5)
            for _ in range(random.randint(0, 6))
        }

        # ── simulate FRAM read (128 chunks) ────────────────────────────────────
        cum_fram = 0
        for ci in range(FRAM_CHUNKS):
            if stop_ev.is_set():
                sim_running = False
                root.after(0, _sim_stopped_ui)
                return
            local_loop += 1
            cum_fram   += fram_bad.get(ci, 0)
            line = f"{local_loop} ...Loop done. Errors: {cum_fram}"
            root.after(0, lambda l=line: handle_line(l))
            stop_ev.wait(0.04)    # 40 ms per chunk → ~5.1 s for full FRAM read

        # ── simulate FLASH scan (16 384 pages compressed to ~2 s) ──────────────
        page_delay = 2.0 / FLASH_PAGES
        cum_flash  = 0
        for pi in range(FLASH_PAGES):
            if stop_ev.is_set():
                sim_running = False
                root.after(0, _sim_stopped_ui)
                return
            addr       = pi * FLASH_PAGE
            cum_flash += flash_bad.get(pi, 0)
            line = f" Address: {addr} ...FLASH Errors: {cum_flash}"
            root.after(0, lambda l=line: handle_line(l))
            stop_ev.wait(page_delay)

        # ── FLASH scan done ─────────────────────────────────────────────────────
        local_flash += 1
        done_line = f"{local_flash} ...FLASH Read done. Errors: {cum_flash}"
        root.after(0, lambda l=done_line: handle_line(l))

        # ── inter-loop wait ─────────────────────────────────────────────────────
        stop_ev.wait(interval_s)

    sim_running = False
    root.after(0, _sim_stopped_ui)


def _sim_stopped_ui():
    sim_btn.config(text="▶  Run Simulation", bg=ACC, fg=ORG,
                   command=start_simulation)
    sim_status_lbl.config(text="SIM: idle", fg=FGD)
    append_output("[SIM] Simulation stopped.")


def start_simulation():
    global sim_running, sim_stop_event

    try:
        interval = float(sim_interval_var.get())
        if interval < 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Simulation",
                             "Enter a valid non-negative number of seconds\n"
                             "(e.g. 0, 2, 5.5).")
        return

    if sim_running:
        return

    sim_running    = True
    sim_stop_event = threading.Event()
    threading.Thread(target=_sim_worker,
                     args=(interval, sim_stop_event),
                     daemon=True).start()

    sim_btn.config(text="⏹  Stop Simulation", bg='#2d1b1b', fg=RED,
                   command=stop_simulation)
    sim_status_lbl.config(text="SIM: RUNNING", fg=ORG)
    append_output(f"[SIM] Started  (inter-loop pause = {interval} s)")


def stop_simulation():
    global sim_running
    sim_stop_event.set()
    sim_running = False
    _sim_stopped_ui()


# ══════════════════════════════════════════════════════════════════════════════
#  GRAPH RENDERING
# ══════════════════════════════════════════════════════════════════════════════

def _style_ax(ax, title):
    ax.set_facecolor(BG)
    ax.tick_params(colors=FGD, labelsize=7)
    for sp in ax.spines.values():
        sp.set_color(ACC)
    ax.set_title(title, color=FGT, fontsize=9, pad=5)


# ── FRAM — time-bucketed scatter plot ────────────────────────────────────────
def refresh_fram_graph():
    """
    Scatter plot across the full test session (accumulating time, never resets).

    X axis : time elapsed since first FRAM chunk, in seconds.
             Tick marks every 0.5 s (one bucket per tick).
    Y axis : total errors that arrived in that 0.5-s bucket.
    Dot size : proportional to number of chunks that landed in that bucket
               (min size = 40 so even single-chunk buckets are visible).
    Dot colour:
      Gray  (#4a4a55) — bucket is in the past but no chunk arrived yet
                        (placeholder so the axis always shows the full timeline)
      Green (GRN)     — chunks arrived, zero errors
      Red   (RED)     — chunks arrived, one or more errors
      Orange (ORG)    — same as green/red but simulation mode border
    """
    ax_fram.cla()
    _style_ax(ax_fram,
              f"FRAM  [{FRAM_SIZE} B = {FRAM_SIZE//1024} KB]  —  "
              f"session scatter  ({FRAM_BUCKET_S}s buckets,  "
              f"dot size ∝ chunks/bucket)")
    ax_fram.set_xlabel("Session time (seconds)", color=FGD, fontsize=7)
    ax_fram.set_ylabel("Errors in bucket", color=FGD, fontsize=7)

    # Total time window: from 0 to (last bucket + 1) × bucket width
    x_max = max(fram_bucket_max + 2, 10) * FRAM_BUCKET_S
    ax_fram.set_xlim(-FRAM_BUCKET_S * 0.5, x_max)

    # ── Gray placeholder dots for every 0.5-s slot up to now ──────────────────
    GRAY = '#4a4a55'
    all_bucket_xs  = [b * FRAM_BUCKET_S for b in range(fram_bucket_max + 1)]
    gray_xs        = [x for b, x in enumerate(all_bucket_xs)
                      if b not in fram_buckets]
    if gray_xs:
        ax_fram.scatter(gray_xs,
                        [0] * len(gray_xs),
                        s=28, color=GRAY, alpha=0.45, zorder=2,
                        linewidths=0)

    # ── Active buckets (chunks arrived) ───────────────────────────────────────
    if fram_buckets:
        bxs    = []   # x positions (seconds)
        bys    = []   # y values    (errors)
        bsizes = []   # dot sizes
        bcolors= []   # dot colours
        bedges = []   # edge colours (orange border in sim mode)

        for bidx, bdata in sorted(fram_buckets.items()):
            x      = bidx * FRAM_BUCKET_S
            errs   = bdata['errors']
            chunks = bdata['chunks']
            # Size: 40 base + 18 per extra chunk, capped at 300
            size   = min(40 + (chunks - 1) * 18, 300)
            color  = RED if errs > 0 else GRN

            bxs.append(x)
            bys.append(errs)
            bsizes.append(size)
            bcolors.append(color)
            bedges.append(ORG if sim_running else color)

        ax_fram.scatter(bxs, bys,
                        s=bsizes, c=bcolors, zorder=4,
                        linewidths=1.1 if sim_running else 0,
                        edgecolors=bedges, alpha=0.92)

        # Thin vertical grid lines at every bucket boundary
        for b in range(fram_bucket_max + 2):
            ax_fram.axvline(b * FRAM_BUCKET_S, color=ACC,
                            linewidth=0.4, alpha=0.5, zorder=1)

    # Y-axis headroom
    all_errs = [v['errors'] for v in fram_buckets.values()] if fram_buckets else [0]
    ax_fram.set_ylim(-0.5, max(max(all_errs), 3) + 1.5)

    # Annotation — top right
    cycle_num = ((loop_cnt - 1) // FRAM_CHUNKS + 1) if loop_cnt > 0 else 1
    chunk_i   = ((loop_cnt - 1) % FRAM_CHUNKS  + 1) if loop_cnt > 0 else 0
    total_err = sum(v['errors'] for v in fram_buckets.values())
    n_buckets = len(fram_buckets)
    sim_tag   = "  [SIM]" if sim_running else ""
    ax_fram.text(0.99, 0.97,
                 f"cycle {cycle_num}  chunk {chunk_i}/{FRAM_CHUNKS}  "
                 f"buckets active: {n_buckets}  "
                 f"total errors: {total_err}{sim_tag}",
                 transform=ax_fram.transAxes, ha='right', va='top',
                 color=ORG if sim_running else ACN, fontsize=7, fontfamily=MNO)

    # Legend
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker='o', color='none', markerfacecolor=GRN,
               markersize=7, label='No errors in bucket'),
        Line2D([0], [0], marker='o', color='none', markerfacecolor=RED,
               markersize=7, label='Errors in bucket'),
        Line2D([0], [0], marker='o', color='none', markerfacecolor=GRAY,
               markersize=5, alpha=0.5, label='No data in bucket'),
        Line2D([0], [0], marker='o', color='none', markerfacecolor=GRN,
               markersize=11, label='Larger dot = more chunks'),
    ]
    if sim_running:
        handles.append(mpatches.Patch(color=ORG, label='Simulation active'))
    ax_fram.legend(handles=handles, loc='upper left',
                   facecolor=PNL, edgecolor=ACC, labelcolor=FGT, fontsize=7)

    fig.tight_layout(pad=1.1)
    mpl_canvas.draw_idle()


# ── FLASH — time-bucketed scatter plot ───────────────────────────────────────
def refresh_flash_graph():
    """
    Scatter plot across the full test session (accumulating, never resets).

    X axis : seconds elapsed since first FLASH page received.
             One dot per 0.5-s bucket regardless of how many pages arrived.
    Y axis : error rate = errors / pages in that bucket  (0.0 → 1.0).
    Dot size : encodes the same error rate, scaled for visibility.
               A clean bucket has the smallest dot; a fully corrupt bucket
               has the largest.  This avoids dot-size being dominated by
               page-count volume (which is meaningless for FLASH health).
    Dot colour:
      Gray  — bucket passed, no pages arrived yet (placeholder)
      Green — pages arrived, error rate = 0.0
      Red   — pages arrived, error rate > 0  (shade intensity from rate)
      Orange border — simulation mode active
    """
    from matplotlib.lines import Line2D

    ax_flash.cla()
    _style_ax(ax_flash,
              f"FLASH  [{FLASH_SIZE:,} B = {FLASH_SIZE//1024//1024} MB]  —  "
              f"session scatter  ({FLASH_BUCKET_S}s buckets,  "
              f"dot size & colour ∝ error rate)")
    ax_flash.set_xlabel("Session time (seconds)", color=FGD, fontsize=7)
    ax_flash.set_ylabel("Error rate  (errors / pages in bucket)", color=FGD, fontsize=7)

    x_max = max(flash_bucket_max + 2, 10) * FLASH_BUCKET_S
    ax_flash.set_xlim(-FLASH_BUCKET_S * 0.5, x_max)
    ax_flash.set_ylim(-0.02, 1.05)

    # Y-axis as percentage ticks
    ax_flash.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v*100:.1f}%"))

    GRAY = '#4a4a55'

    # ── Gray placeholder dots ──────────────────────────────────────────────────
    gray_xs = [b * FLASH_BUCKET_S for b in range(flash_bucket_max + 1)
               if b not in flash_buckets]
    if gray_xs:
        ax_flash.scatter(gray_xs, [0.0] * len(gray_xs),
                         s=22, color=GRAY, alpha=0.40, zorder=2, linewidths=0)

    # ── Active buckets ─────────────────────────────────────────────────────────
    if flash_buckets:
        bxs    = []
        bys    = []
        bsizes = []
        bcolors= []
        bedges = []

        for bidx, bdata in sorted(flash_buckets.items()):
            x      = bidx * FLASH_BUCKET_S
            pages  = bdata['pages']
            errors = bdata['errors']
            rate   = errors / pages if pages > 0 else 0.0

            # Size: 30 minimum (zero-error bucket), up to 250 at rate=1.0
            size  = 30 + rate * 220
            color = GRN if rate == 0.0 else RED

            bxs.append(x)
            bys.append(rate)
            bsizes.append(size)
            bcolors.append(color)
            bedges.append(ORG if sim_running else color)

        ax_flash.scatter(bxs, bys,
                         s=bsizes, c=bcolors, zorder=4,
                         linewidths=1.1 if sim_running else 0,
                         edgecolors=bedges, alpha=0.90)

        # Vertical grid lines at every bucket boundary
        for b in range(flash_bucket_max + 2):
            ax_flash.axvline(b * FLASH_BUCKET_S, color=ACC,
                             linewidth=0.4, alpha=0.5, zorder=1)

        # Horizontal reference line at 0% and 100%
        ax_flash.axhline(0.0,  color=GRN, linewidth=0.6, alpha=0.4, linestyle='-')
        ax_flash.axhline(1.0,  color=RED, linewidth=0.6, alpha=0.4, linestyle='--')

    # Annotation
    pages_done  = len(flash_addrs)
    total_errs  = sum(v['errors'] for v in flash_buckets.values())
    total_pages = sum(v['pages']  for v in flash_buckets.values())
    overall_rate = total_errs / total_pages if total_pages else 0.0
    n_buckets   = len(flash_buckets)
    sim_tag     = "  [SIM]" if sim_running else ""

    ax_flash.text(0.99, 0.97,
                  f"scan {FLASH_cnt + (1 if flash_addrs else 0)}  "
                  f"page {pages_done:,}/{FLASH_PAGES:,}  "
                  f"buckets active: {n_buckets}  "
                  f"overall error rate: {overall_rate*100:.4f}%{sim_tag}",
                  transform=ax_flash.transAxes, ha='right', va='top',
                  color=ORG if sim_running else ACN, fontsize=7, fontfamily=MNO)

    handles = [
        Line2D([0], [0], marker='o', color='none', markerfacecolor=GRN,
               markersize=7,  label='0% error rate'),
        Line2D([0], [0], marker='o', color='none', markerfacecolor=RED,
               markersize=7,  label='Error rate > 0%'),
        Line2D([0], [0], marker='o', color='none', markerfacecolor=GRAY,
               markersize=5,  alpha=0.5, label='No data in bucket'),
        Line2D([0], [0], marker='o', color='none', markerfacecolor=RED,
               markersize=12, label='Larger dot = higher error rate'),
    ]
    if sim_running:
        handles.append(mpatches.Patch(color=ORG, label='Simulation active'))
    ax_flash.legend(handles=handles, loc='upper left',
                    facecolor=PNL, edgecolor=ACC, labelcolor=FGT, fontsize=7)

    fig.tight_layout(pad=1.1)
    mpl_canvas.draw_idle()


def periodic_flash_refresh():
    """Called every 1 s. Refreshes FLASH graph if a scan is in progress."""
    if flash_addrs or flash_buckets:
        refresh_flash_graph()
    root.after(1000, periodic_flash_refresh)


# ══════════════════════════════════════════════════════════════════════════════
#  GUI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def append_output(text: str):
    output_box.configure(state='normal')
    output_box.insert(tk.END, text + '\n')
    output_box.see(tk.END)
    output_box.configure(state='disabled')


def log_error(msg: str):
    ts   = datetime.now().strftime('%H:%M:%S')
    full = f"[{ts}]  {msg}"
    error_log_lines.append(full)
    error_box.configure(state='normal')
    error_box.insert(tk.END, full + '\n')
    error_box.see(tk.END)
    error_box.configure(state='disabled')


def set_led(active: bool):
    col = GRN if active else RED
    ind_canvas.itemconfig(ind_oval, fill=col, outline=col)
    ind_text_var.set("TEST ACTIVE" if active else "IDLE")
    ind_lbl.config(fg=col)


def update_mask_display():
    mask_fram_lbl.config(
        text="FRAM: MASKED" if mask_FRAM else "FRAM: active",
        fg=AMB if mask_FRAM else GRN)
    mask_flash_lbl.config(
        text="FLASH: MASKED" if mask_FLASH else "FLASH: active",
        fg=AMB if mask_FLASH else GRN)


def update_stats():
    """Refresh bottom stat bar.  Self-rescheduling — registered ONCE at startup."""
    fram_total = sum(sum(h) for h in fram_history) + sum(fram_deltas)
    stat_fram_errors.set(str(fram_total))
    stat_fram_cycles.set(str(len(fram_history)))

    flash_total = sum(sum(d[1]) for d in flash_history) + sum(flash_deltas)
    stat_flash_errors.set(str(flash_total))
    stat_flash_scans.set(str(FLASH_cnt))

    root.after(800, update_stats)


# ── Watchdog — single definition, self-rescheduling ───────────────────────────
_wd_flagged = False

def watchdog_tick():
    global _wd_flagged
    if last_data_time is not None and (running or sim_running):
        elapsed   = time.time() - last_data_time
        remaining = WATCHDOG_S - elapsed
        if elapsed > WATCHDOG_S:
            set_led(False)
            wd_lbl.config(text=f"no data  {int(elapsed)}s", fg=RED)
            if not _wd_flagged:
                log_error(f"Watchdog: no data for {int(elapsed)}s")
                _wd_flagged = True
        else:
            _wd_flagged = False
            wd_lbl.config(text=f"timeout in {int(remaining)}s", fg=FGD)
    else:
        wd_lbl.config(text="awaiting data…", fg=FGD)
    root.after(1000, watchdog_tick)


# ══════════════════════════════════════════════════════════════════════════════
#  SERIAL CONTROLS
# ══════════════════════════════════════════════════════════════════════════════

def serial_read_loop():
    """Background thread — reads lines, dispatches to main thread."""
    while running:
        try:
            if ser and ser.in_waiting:
                raw = ser.readline().decode(errors='replace').strip()
                if raw:
                    root.after(0, lambda r=raw: handle_line(r))
        except Exception as exc:
            root.after(0, lambda e=exc: log_error(f"Serial error: {e}"))
        time.sleep(0.02)


def connect_serial():
    global ser, running, last_data_time
    port = port_var.get()
    if not port:
        messagebox.showerror("Error", "Select a COM port first.")
        return
    try:
        ser = serial.Serial(port, BAUD, timeout=1)
        time.sleep(2)          # wait for Teensy to reset after DTR toggle
        running        = True
        last_data_time = None
        threading.Thread(target=serial_read_loop, daemon=True).start()
        conn_btn.config(text="Disconnect", bg=RED, command=disconnect_serial)
        status_lbl.config(text=f"● {port}", fg=GRN)
        append_output(f"Connected to {port} @ {BAUD} baud")
    except Exception as exc:
        messagebox.showerror("Connection Error", str(exc))


def disconnect_serial():
    global ser, running
    running = False
    if ser:
        ser.close()
        ser = None
    conn_btn.config(text="Connect", bg=GRN, fg='#000', command=connect_serial)
    status_lbl.config(text="● Disconnected", fg=RED)
    set_led(False)
    append_output("Disconnected.")


def refresh_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    port_combo['values'] = ports
    if ports:
        port_var.set(ports[0])


def send_command(event=None):
    cmd = cmd_entry.get().strip()
    if not cmd:
        return
    if ser and ser.is_open:
        try:
            ser.write((cmd + '\n').encode())
            append_output(f"[TX] {cmd}")
        except Exception as exc:
            log_error(f"Send error: {exc}")
    else:
        append_output(f"[NOT SENT — not connected] {cmd}")
    cmd_entry.delete(0, tk.END)


def quick_send(cmd: str):
    """Send a single-char command and mirror its state effect locally."""
    global mask_FRAM, mask_FLASH, out_loop_cnt, write_in_progress, write_status
    if ser and ser.is_open:
        try:
            ser.write((cmd + '\n').encode())
        except Exception as exc:
            log_error(f"Send error: {exc}")
    append_output(f"[TX] {cmd}")

    if cmd == 'a':
        mask_FRAM = 1;  update_mask_display()
    elif cmd == 'b':
        mask_FLASH = 1; update_mask_display()
    elif cmd == 'w':
        write_in_progress = True
        write_status = ""
        append_output("[WRITE] ▶ Starting write to FRAM and FLASH addresses...")
    elif cmd == 'r':
        out_loop_cnt = 0
    elif cmd == 's':
        # Arduino resets both masks when it receives 's'
        mask_FRAM = 0; mask_FLASH = 0
        update_mask_display()
        write_in_progress = False
        append_output("[STOP] Stop request sent to device.")


# ══════════════════════════════════════════════════════════════════════════════
#  SAVE / CLEAR / CATALOG
# ══════════════════════════════════════════════════════════════════════════════

def _save_csv(session_list, prefix):
    if not session_list:
        messagebox.showinfo("No Data", f"No {prefix} data to save.")
        return
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fp = filedialog.asksaveasfilename(
        defaultextension='.csv',
        initialfile=f"{prefix}_{ts}.csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
    if not fp:
        return
    with open(fp, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(session_list[0].keys()),
                           extrasaction='ignore')
        w.writeheader()
        w.writerows(session_list)
    append_output(f"Saved → {fp}")
    messagebox.showinfo("Saved", fp)


def save_fram():  _save_csv(fram_session, 'fram')
def save_flash(): _save_csv(flash_session, 'flash')


def clear_fram():
    global fram_t0, fram_bucket_max
    if not messagebox.askyesno("Clear FRAM", "Discard all FRAM test data?"):
        return
    fram_cum.clear(); fram_deltas.clear()
    fram_history.clear(); fram_session.clear()
    fram_buckets.clear()
    fram_t0         = None
    fram_bucket_max = 0
    refresh_fram_graph()
    append_output("FRAM data cleared.")


def clear_flash():
    global FLASH_cnt, flash_t0, flash_bucket_max
    if not messagebox.askyesno("Clear FLASH", "Discard all FLASH test data?"):
        return
    flash_addrs.clear(); flash_cum.clear()
    flash_deltas.clear(); flash_history.clear(); flash_session.clear()
    flash_buckets.clear()
    flash_t0         = None
    flash_bucket_max = 0
    FLASH_cnt = 0
    refresh_flash_graph()
    append_output("FLASH data cleared.")


def save_error_log():
    if not error_log_lines:
        messagebox.showinfo("Empty", "Error log is empty.")
        return
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fp = filedialog.asksaveasfilename(
        defaultextension='.txt', initialfile=f"errors_{ts}.txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
    if not fp:
        return
    with open(fp, 'w') as f:
        f.write('\n'.join(error_log_lines))
    append_output(f"Error log saved → {fp}")


def open_catalog():
    folder = filedialog.askdirectory(title="Select catalog folder")
    if not folder:
        return
    files = sorted([f for f in os.listdir(folder) if f.endswith('.csv')], reverse=True)
    if not files:
        messagebox.showinfo("Catalog", "No CSV files found.")
        return

    win = tk.Toplevel(root)
    win.title("Test Results Catalog")
    win.configure(bg=BG)
    win.geometry("820x480")

    tk.Label(win, text="MEMORY TEST CATALOG", bg=BG, fg=ACN,
             font=(MNO, 12, 'bold')).pack(pady=(12, 2))
    tk.Label(win, text=folder, bg=BG, fg=FGD, font=(MNO, 8)).pack(pady=(0, 8))

    fr = tk.Frame(win, bg=BG)
    fr.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

    cols = ('File', 'Type', 'Rows', 'Total Errors', 'Sim rows', 'Created')
    tree = ttk.Treeview(fr, columns=cols, show='headings', height=18)
    widths = {'File': 230, 'Type': 58, 'Rows': 68,
              'Total Errors': 100, 'Sim rows': 80, 'Created': 140}
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=widths[c],
                    anchor='w' if c == 'File' else 'center')

    sb = ttk.Scrollbar(fr, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)

    for fname in files:
        fpath = os.path.join(folder, fname)
        ftype = ('FRAM' if fname.startswith('fram') else
                 'FLASH' if fname.startswith('flash') else '?')
        try:
            with open(fpath, newline='') as f:
                rows = list(csv.DictReader(f))
            n_err = n_sim = 0
            for r in rows:
                for key in ('errors_this_chunk', 'errors_this_page'):
                    v = r.get(key, '')
                    if str(v).isdigit():
                        n_err += int(v)
                        break
                if r.get('simulated') == '1':
                    n_sim += 1
            creat = datetime.fromtimestamp(
                os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M')
            sim_str = str(n_sim) if n_sim else "—"
            tree.insert('', tk.END,
                        values=(fname, ftype, len(rows), n_err, sim_str, creat))
        except Exception:
            tree.insert('', tk.END, values=(fname, ftype, '?', '?', '?', '?'))

    sty2 = ttk.Style()
    sty2.configure("Treeview", background=PNL, foreground=FGT,
                   fieldbackground=PNL, rowheight=22)
    sty2.configure("Treeview.Heading", background=ACC, foreground=FGT)


# ══════════════════════════════════════════════════════════════════════════════
#  ROOT WINDOW  &  LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
root = tk.Tk()
root.title("Memory Test Monitor  v3")
root.configure(bg=BG)
root.geometry('1480x940')
root.minsize(1120, 740)

sty = ttk.Style()
sty.theme_use('clam')
sty.configure('TCombobox', fieldbackground=ACC, background=ACC,
               foreground=FGT, selectbackground=ACC)

# ── Top bar ────────────────────────────────────────────────────────────────────
top = tk.Frame(root, bg=BG, pady=7)
top.pack(fill=tk.X, padx=14)

tk.Label(top, text="MEMORY TEST MONITOR  v3", bg=BG, fg=ACN,
         font=(MNO, 13, 'bold')).pack(side=tk.LEFT)

status_lbl = tk.Label(top, text="● Idle", bg=BG, fg=RED, font=(MNO, 10))
status_lbl.pack(side=tk.LEFT, padx=14)

mask_fram_lbl  = tk.Label(top, text="FRAM: active",  bg=BG, fg=GRN, font=(MNO, 9))
mask_flash_lbl = tk.Label(top, text="FLASH: active", bg=BG, fg=GRN, font=(MNO, 9))
mask_fram_lbl.pack(side=tk.LEFT, padx=5)
mask_flash_lbl.pack(side=tk.LEFT, padx=5)

conn_row = tk.Frame(top, bg=BG)
conn_row.pack(side=tk.RIGHT)

port_var   = tk.StringVar()
port_combo = ttk.Combobox(conn_row, textvariable=port_var, width=9, font=(MNO, 10))
port_combo.pack(side=tk.LEFT, padx=3)

tk.Button(conn_row, text="↺", bg=ACC, fg=FGT, font=(MNO, 11),
          bd=0, padx=6, pady=2, command=refresh_ports).pack(side=tk.LEFT, padx=2)

conn_btn = tk.Button(conn_row, text="Connect", bg=GRN, fg='#000',
                     font=(MNO, 10, 'bold'), bd=0, padx=14, pady=3,
                     command=connect_serial)
conn_btn.pack(side=tk.LEFT, padx=6)

for lbl, cmd, col in [
    ("a: Mask FRAM",  'a', AMB),
    ("b: Mask FLASH", 'b', AMB),
    ("w: Write",      'w', AMB),
    ("r: Read",       'r', GRN),
    ("s: Stop",       's', RED),
]:
    tk.Button(conn_row, text=lbl, bg=ACC, fg=col, font=(MNO, 9, 'bold'),
              bd=0, padx=9, pady=3,
              command=lambda c=cmd: quick_send(c)).pack(side=tk.LEFT, padx=2)

# ── Main split (left = graphs, right = log panel) ─────────────────────────────
main = tk.Frame(root, bg=BG)
main.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)

left = tk.Frame(main, bg=BG)
left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

right = tk.Frame(main, bg=BG, width=440)
right.pack(side=tk.RIGHT, fill=tk.BOTH)
right.pack_propagate(False)

# ── Indicator + simulation strip ───────────────────────────────────────────────
ind_row = tk.Frame(left, bg=BG)
ind_row.pack(fill=tk.X, pady=(0, 4))

IND = 22
ind_canvas = tk.Canvas(ind_row, width=IND, height=IND, bg=BG, highlightthickness=0)
ind_canvas.pack(side=tk.LEFT)
ind_oval = ind_canvas.create_oval(2, 2, IND-2, IND-2, fill=RED, outline=RED)

ind_text_var = tk.StringVar(value="IDLE")
ind_lbl = tk.Label(ind_row, textvariable=ind_text_var, bg=BG,
                   fg=RED, font=(MNO, 10, 'bold'))
ind_lbl.pack(side=tk.LEFT, padx=6)

wd_lbl = tk.Label(ind_row, text="awaiting data…", bg=BG, fg=FGD, font=(MNO, 9))
wd_lbl.pack(side=tk.LEFT, padx=8)

# Separator
tk.Frame(ind_row, bg=ACC, width=1, height=20).pack(side=tk.LEFT, padx=10)

# ── Simulation controls ────────────────────────────────────────────────────────
tk.Label(ind_row, text="SIMULATION", bg=BG, fg=ORG,
         font=(MNO, 8, 'bold')).pack(side=tk.LEFT, padx=(0, 6))

tk.Label(ind_row, text="pause between loops (s):", bg=BG, fg=FGD,
         font=(MNO, 8)).pack(side=tk.LEFT)

sim_interval_var = tk.StringVar(value="0")
tk.Entry(ind_row, textvariable=sim_interval_var,
         width=5, bg=PNL, fg=FGT, font=(MNO, 9),
         insertbackground=FGT, relief='flat', bd=3,
         justify='center').pack(side=tk.LEFT, padx=(3, 8))

sim_btn = tk.Button(ind_row, text="▶  Run Simulation", bg=ACC, fg=ORG,
                    font=(MNO, 9, 'bold'), bd=0, padx=12, pady=2,
                    command=start_simulation)
sim_btn.pack(side=tk.LEFT, padx=(0, 6))

sim_status_lbl = tk.Label(ind_row, text="SIM: idle", bg=BG, fg=FGD, font=(MNO, 8))
sim_status_lbl.pack(side=tk.LEFT)

# ── Dual matplotlib figure ─────────────────────────────────────────────────────
fig, (ax_fram, ax_flash) = plt.subplots(
    2, 1, figsize=(8.0, 6.4), facecolor=PNL)
fig.subplots_adjust(hspace=0.55, top=0.95, bottom=0.07, left=0.08, right=0.98)

_style_ax(ax_fram,
          f"FRAM  [{FRAM_SIZE} B = {FRAM_SIZE//1024} KB]   "
          f"{FRAM_CHUNKS} chunks × {FRAM_CHUNK} B  →  {FRAM_SIZE} addressable bytes")
ax_fram.set_xlabel("Chunk start address (bytes)", color=FGD, fontsize=7)
ax_fram.set_ylabel("Errors in chunk", color=FGD, fontsize=7)
ax_fram.set_xlim(-FRAM_CHUNK, FRAM_SIZE + FRAM_CHUNK)
ax_fram.set_ylim(0, 4)

_style_ax(ax_flash,
          f"FLASH  [{FLASH_SIZE:,} B = {FLASH_SIZE//1024//1024} MB]   "
          f"{FLASH_PAGES:,} pages × {FLASH_PAGE} B  →  {FLASH_SIZE:,} addressable bytes")
ax_flash.set_xlabel("Address (KB)", color=FGD, fontsize=7)
ax_flash.set_ylabel("Cumulative errors in scan", color=FGD, fontsize=7)
ax_flash.set_xlim(0, FLASH_SIZE // 1024)
ax_flash.set_ylim(0, 4)

mpl_canvas = FigureCanvasTkAgg(fig, master=left)
mpl_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# ── Per-graph Save + Clear button rows ────────────────────────────────────────
def _graph_btn_row(parent, label, save_fn, clear_fn):
    row = tk.Frame(parent, bg=BG)
    row.pack(fill=tk.X, pady=(2, 1))
    tk.Label(row, text=label, bg=BG, fg=FGD, font=(MNO, 8, 'bold'),
             width=9, anchor='w').pack(side=tk.LEFT, padx=(2, 8))
    tk.Button(row, text="💾  Save CSV", bg=ACC, fg=BLU,
              font=(MNO, 8, 'bold'), bd=0, padx=10, pady=2,
              command=save_fn).pack(side=tk.LEFT, padx=(0, 4))
    tk.Button(row, text="🗑  Clear", bg='#2d1b1b', fg=RED,
              font=(MNO, 8, 'bold'), bd=0, padx=10, pady=2,
              command=clear_fn).pack(side=tk.LEFT)

_graph_btn_row(left, "FRAM  ▲", save_fram,  clear_fram)
_graph_btn_row(left, "FLASH ▼", save_flash, clear_flash)

# ── Right panel (errors + serial output + command) ─────────────────────────────
def _section(parent, title, color=FGD):
    tk.Label(parent, text=title, bg=BG, fg=color,
             font=(MNO, 9, 'bold')).pack(anchor='w', pady=(8, 2))

_section(right, "⚠   ERROR LOG", AMB)
error_box = scrolledtext.ScrolledText(
    right, height=8, bg=PNL, fg=RED, font=(MNO, 9),
    state='disabled', relief='flat', wrap=tk.WORD)
error_box.pack(fill=tk.BOTH)

_section(right, "📡  SERIAL OUTPUT")
output_box = scrolledtext.ScrolledText(
    right, height=14, bg=PNL, fg=FGT, font=(MNO, 9),
    state='disabled', relief='flat', wrap=tk.WORD)
output_box.pack(fill=tk.BOTH, expand=True)

_section(right, "⌨   COMMAND")
cmd_row = tk.Frame(right, bg=BG)
cmd_row.pack(fill=tk.X, pady=(2, 0))
cmd_entry = tk.Entry(cmd_row, bg=PNL, fg=FGT, font=(MNO, 10),
                     insertbackground=FGT, relief='flat', bd=4)
cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
cmd_entry.bind('<Return>', send_command)
tk.Button(cmd_row, text="Send", bg=ACC, fg=BLU, font=(MNO, 10, 'bold'),
          bd=0, padx=12, pady=3,
          command=send_command).pack(side=tk.RIGHT, padx=(4, 0))

# ── Bottom stats / utility bar ─────────────────────────────────────────────────
bot = tk.Frame(root, bg=BG, pady=6)
bot.pack(fill=tk.X, padx=14)

def _btn(p, label, fn, bg=ACC, fg=FGT):
    return tk.Button(p, text=label, command=fn, bg=bg, fg=fg,
                     font=(MNO, 9, 'bold'), bd=0, padx=12, pady=5, relief='flat')

_btn(bot, "📋  Save Error Log", save_error_log).pack(side=tk.LEFT, padx=(0, 6))
_btn(bot, "📂  Open Catalog",   open_catalog).pack(side=tk.LEFT, padx=(0, 6))

tk.Frame(bot, bg=ACC, width=1, height=26).pack(side=tk.LEFT, padx=10)

stats_frame = tk.Frame(bot, bg=BG)
stats_frame.pack(side=tk.LEFT)

def _stat(parent, label):
    f = tk.Frame(parent, bg=BG)
    f.pack(side=tk.LEFT, padx=12)
    tk.Label(f, text=label, bg=BG, fg=FGD, font=(MNO, 8)).pack()
    v = tk.StringVar(value="—")
    tk.Label(f, textvariable=v, bg=BG, fg=FGT, font=(MNO, 10, 'bold')).pack()
    return v

stat_fram_errors  = _stat(stats_frame, "FRAM errors (total)")
stat_fram_cycles  = _stat(stats_frame, "FRAM cycles done")
stat_flash_errors = _stat(stats_frame, "FLASH errors (total)")
stat_flash_scans  = _stat(stats_frame, "FLASH scans done")

# ══════════════════════════════════════════════════════════════════════════════
#  START ALL RECURRING TIMERS  (each registered EXACTLY ONCE here)
# ══════════════════════════════════════════════════════════════════════════════
update_stats()            # → reschedules every 800 ms
periodic_flash_refresh()  # → reschedules every 1 000 ms
watchdog_tick()           # → reschedules every 1 000 ms
update_mask_display()
refresh_ports()

root.mainloop()
