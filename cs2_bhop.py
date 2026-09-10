"""
CS2 External Bunny Hop — Python Edition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Hold SPACE to auto bunny hop.
Press INSERT to toggle on/off.
Press END to exit.

Requirements:
    pip install pymem

Run as Administrator:
    Right-click cs2_bhop.bat → Run as administrator

DISCLAIMER: Educational purposes only. Using this in live matches
violates CS2's Terms of Service and risks a VAC ban.
"""

import ctypes
import ctypes.wintypes as wt
import sys
import time
import random

# ──────────────────────────────────────────────────────────────
#  Try to import pymem — install it automatically if missing
# ──────────────────────────────────────────────────────────────
try:
    import pymem
    import pymem.process
except ImportError:
    print("[!] 'pymem' not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymem"])
    import pymem
    import pymem.process

# ══════════════════════════════════════════════════════════════
#  OFFSETS — Generated 2026-09-10 from a2x/cs2-dumper
#  Update from: https://github.com/a2x/cs2-dumper
# ══════════════════════════════════════════════════════════════

# client.dll globals
OFFSET_LOCAL_PLAYER_PAWN = 0x23CCC08   # dwLocalPlayerPawn
OFFSET_FORCE_JUMP        = 0x20BA010   # buttons -> jump (dwForceJump)

# Entity field offsets
OFFSET_FLAGS             = 0x3F4       # C_BaseEntity -> m_fFlags
OFFSET_MOVEMENT_SERVICES = 0x1248      # C_BasePlayerPawn -> m_pMovementServices

FL_ONGROUND = 1 << 0   # bit 0 of m_fFlags = on ground

# ──────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────
BHOP_KEY   = 0x20   # VK_SPACE
TOGGLE_KEY = 0x2D   # VK_INSERT
EXIT_KEY   = 0x23   # VK_END

# ──────────────────────────────────────────────────────────────
#  Win32 helpers
# ──────────────────────────────────────────────────────────────
user32 = ctypes.WinDLL("user32", use_last_error=True)

def key_held(vk_code: int) -> bool:
    return (user32.GetAsyncKeyState(vk_code) & 0x8000) != 0

def game_is_focused(window_title: str = "Counter-Strike 2") -> bool:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    buf = ctypes.create_string_buffer(256)
    user32.GetWindowTextA(hwnd, buf, 256)
    return window_title.encode() in buf.value

# ──────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────
def main():
    print("""
  ╔══════════════════════════════════════════════╗
  ║    CS2 External Bunny Hop  (Python)          ║
  ╠══════════════════════════════════════════════╣
  ║  SPACE  — hold to bunny hop                 ║
  ║  INSERT — toggle on / off                   ║
  ║  END    — exit                              ║
  ╚══════════════════════════════════════════════╝
    """)

    # ── Attach to CS2 ────────────────────────────────────────
    print("[*] Waiting for cs2.exe ...")
    pm = None
    while pm is None:
        try:
            pm = pymem.Pymem("cs2.exe")
        except pymem.exception.ProcessNotFound:
            time.sleep(1)
        except pymem.exception.CouldNotOpenProcess:
            print("[!] Could not open cs2.exe — are you running as Administrator?")
            time.sleep(2)

    print(f"[+] Attached to cs2.exe  (PID {pm.process_id})")

    # ── Resolve client.dll ───────────────────────────────────
    print("[*] Waiting for client.dll ...")
    client_base = None
    while client_base is None:
        try:
            client_module = pymem.process.module_from_name(
                pm.process_handle, "client.dll"
            )
            if client_module:
                client_base = client_module.lpBaseOfDll
        except Exception:
            pass
        if client_base is None:
            time.sleep(0.5)

    print(f"[+] client.dll @ {hex(client_base)}")
    print()

    # ── State ────────────────────────────────────────────────
    enabled = True
    toggle_was_pressed = False
    last_focus_check = 0
    is_focused = False
    print("[+] Bhop: ON  — hold SPACE in-game to bhop")
    print()

    # ── Main loop ────────────────────────────────────────────
    try:
        while True:
            now = time.perf_counter()

            # Exit
            if key_held(EXIT_KEY):
                print("\n[*] Exit key pressed. Bye!")
                break

            # Safety: check if game is still running (throttled)
            if now - last_focus_check > 1.0:
                try:
                    pm.read_int(client_base)
                except Exception:
                    print("\n[!] Game closed. Shutting down.")
                    break

            # Toggle
            if key_held(TOGGLE_KEY):
                if not toggle_was_pressed:
                    enabled = not enabled
                    print(f"[~] Bhop: {'ON' if enabled else 'OFF'}")
                    toggle_was_pressed = True
            else:
                toggle_was_pressed = False

            # Check focus less often (every 200ms) to save CPU for the tight loop
            if now - last_focus_check > 0.2:
                is_focused = game_is_focused()
                last_focus_check = now

            # Only bhop when enabled, game focused, and space held
            if enabled and is_focused and key_held(BHOP_KEY):
                try:
                    # 1. Read local player pawn pointer
                    pawn = pm.read_longlong(client_base + OFFSET_LOCAL_PLAYER_PAWN)
                    if pawn == 0:
                        time.sleep(0.05)
                        continue

                    # 2. Read m_fFlags from the pawn
                    flags = pm.read_uint(pawn + OFFSET_FLAGS)
                    on_ground = (flags & FL_ONGROUND) != 0

                    if on_ground:
                        # ON GROUND → force jump IMMEDIATELY (no delay!)
                        # This is the key to keeping momentum: minimize ground time.
                        pm.write_int(client_base + OFFSET_FORCE_JUMP, 65537)
                    else:
                        # IN AIR → release jump so it can re-trigger on next landing
                        pm.write_int(client_base + OFFSET_FORCE_JUMP, 256)

                except Exception:
                    time.sleep(0.05)
                    continue

                # Tight poll — as fast as possible to catch the landing frame
                # sleep(0) yields the thread without wasting time
                time.sleep(0)
            else:
                # Idle — low CPU
                time.sleep(0.005)

    except KeyboardInterrupt:
        print("\n[*] Interrupted.")
    finally:
        # Release jump on exit
        try:
            pm.write_int(client_base + OFFSET_FORCE_JUMP, 256)
            pm.close_process()
        except Exception:
            pass
        print("[*] Done.")


if __name__ == "__main__":
    main()

