import os
import sys
import json
import time
import ctypes
import subprocess
import winreg
import stat
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# =================================================================
# 1. CONSTANTS & PERSISTENT PATHS
# =================================================================
APP_NAME = "StretchyVal"
DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", APP_NAME)
SESSION_DATA_PATH = os.path.join(DOCUMENTS_DIR, "native_res.json")
PERMANENT_ICON_PATH = os.path.join(DOCUMENTS_DIR, "redyellow.ico")

CONFIG_FILE = f"{APP_NAME}Config.json"
CONFIG_PATH = os.path.join(os.getenv('APPDATA', ''), CONFIG_FILE)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def elevate_and_restart():
    """Re-launch the current script/exe as administrator and exit this instance."""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit(0)

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    full_path = os.path.join(base_path, relative_path)
    if os.path.exists(full_path):
        return full_path

    exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
    fallback = os.path.join(exe_dir, relative_path)
    if os.path.exists(fallback):
        return fallback

    return full_path

def ensure_data_folder():
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    bundled_icon = get_resource_path("redyellow.ico")
    if os.path.exists(bundled_icon) and not os.path.exists(PERMANENT_ICON_PATH):
        try:
            shutil.copy2(bundled_icon, PERMANENT_ICON_PATH)
        except:
            pass

def set_read_only(file_path, read_only=True):
    if not os.path.exists(file_path):
        return
    mode = os.stat(file_path).st_mode
    if read_only:
        os.chmod(file_path, mode & ~stat.S_IWRITE)
    else:
        os.chmod(file_path, mode | stat.S_IWRITE)

def get_riot_client_path():
    possible_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Riot Games\Riot Client"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Riot Games\Riot Client")
    ]
    for hive, key in possible_keys:
        try:
            with winreg.OpenKey(hive, key) as reg_key:
                install_folder, _ = winreg.QueryValueEx(reg_key, "InstallFolder")
                candidate = os.path.join(install_folder, "RiotClientServices.exe")
                if os.path.exists(candidate):
                    return candidate
        except:
            continue
    return None

# =================================================================
# 2. MONITOR ENUMERATION & DISABLE
# =================================================================
#
# Enumeration reads directly from the registry under:
#   HKLM\SYSTEM\CurrentControlSet\Enum\DISPLAY
# This is the same data source Device Manager uses for the Monitors section
# and requires no special privileges to read.
#
# Disabling uses pnputil.exe (built into Windows 10/11) which handles the
# SetupAPI calls internally and reliably requires only that the process is
# elevated. Monitors stay disabled until manually re-enabled — intentional.

def enumerate_monitors():
    """
    Read monitor devices from the registry under HKLM\\SYSTEM\\CurrentControlSet\\Enum\\DISPLAY.
    Returns list of dicts: {"name": "HP 32f", "instance_id": "DISPLAY\\..."}
    No admin required — registry read is unprivileged.
    """
    monitors = []
    base_key = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
    # Monitor class GUID — filters to Monitors section, not Display Adapters
    MONITOR_CLASS_GUID = "{4d36e96e-e325-11ce-bfc1-08002be10318}"

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_key) as display_key:
            i = 0
            while True:
                try:
                    model_name = winreg.EnumKey(display_key, i)
                    i += 1
                except OSError:
                    break

                model_path = f"{base_key}\\{model_name}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, model_path) as model_key:
                        j = 0
                        while True:
                            try:
                                instance_name = winreg.EnumKey(model_key, j)
                                j += 1
                            except OSError:
                                break

                            instance_path = f"{model_path}\\{instance_name}"
                            instance_id   = f"DISPLAY\\{model_name}\\{instance_name}"

                            try:
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, instance_path) as inst_key:
                                    # Filter by ClassGUID (not "Class" — that value doesn't exist here)
                                    try:
                                        class_guid, _ = winreg.QueryValueEx(inst_key, "ClassGUID")
                                        if class_guid.lower() != MONITOR_CLASS_GUID.lower():
                                            continue
                                    except OSError:
                                        continue

                                    # FriendlyName is an indirect registry string like:
                                    #   @System32\drivers\dxgkrnl.sys,#304;Integrated Monitor (%1);(LQ140M1JW46)
                                    # The actual human-readable name is the last ;-segment, strip parens.
                                    try:
                                        raw, _ = winreg.QueryValueEx(inst_key, "FriendlyName")
                                        parts = raw.split(";")
                                        last = parts[-1].strip()
                                        # Strip surrounding parens if present: (HP 32f) → HP 32f
                                        if last.startswith("(") and last.endswith(")"):
                                            last = last[1:-1]
                                        name = last if last else model_name
                                    except OSError:
                                        name = model_name

                                    monitors.append({"name": name, "instance_id": instance_id})
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        pass

    return monitors


def disable_monitors(instance_ids):
    """
    Disable each monitor using pnputil.exe /disable-device.
    pnputil is built into Windows 10 and 11, handles SetupAPI internally,
    and only requires the process to be elevated — which the launcher enforces.
    Monitors stay disabled until manually re-enabled in Device Manager.
    """
    for iid in instance_ids:
        try:
            subprocess.run(
                ["pnputil", "/disable-device", iid],
                creationflags=0x08000000,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # Let Windows finish re-enumerating before Valorant starts
    time.sleep(1)

# =================================================================
# 3. ELITE PERFORMANCE TEMPLATE
# =================================================================
ELITE_INI_TEMPLATE = """[/Script/ShooterGame.ShooterGameUserSettings]
bShouldLetterbox=False
bLastConfirmedShouldLetterbox=False
ResolutionSizeX={X}
ResolutionSizeY={Y}
LastUserConfirmedResolutionSizeX={X}
LastUserConfirmedResolutionSizeY={Y}
FullscreenMode=2
PreferredFullscreenMode=2
DesiredScreenWidth={X}
DesiredScreenHeight={Y}
LastUserConfirmedDesiredScreenWidth={X}
LastUserConfirmedDesiredScreenHeight={Y}
r.rhicmdbypass=0
r.rhithread.enable=1
bAllowMultiThreadedShaderCompile=True
AllowMultiThreadedShaderCompile=True
AllowMultithreadedRendering=True
bAllowMultithreadedRendering=True
bAllowMultithreaded=True
AllowMultithreaded=True
r.AllowMultithreadedRendering=True
r.AllowMultithreaded=True
r.ParallelRendering=1
r.GTSyncType=2
r.rhi.SyncInterval=0
rhi.SyncSlackMS=0
r.FinishCurrentFrame=0
r.DepthOfFieldQuality=0
bSmoothFrameRate=false
bEnableMouseSmoothing=False
MouseSamplingTime=0.000125
MouseAccelThreshold=1000000.000000
ReduceMouseLag=True
bDisableMouseAcceleration=True

[ScalabilityGroups]
sg.ResolutionQuality=100
sg.ViewDistanceQuality=1
sg.AntiAliasingQuality=0
sg.ShadowQuality=0
sg.PostProcessQuality=0
sg.TextureQuality=0
sg.EffectsQuality=0
sg.FoliageQuality=0
sg.ShadingQuality=0
sg.GlobalIlluminationQuality=0
sg.ReflectionQuality=0
sg.PerformanceMode=4
"""

# =================================================================
# 4. CORE PATCHING LOGIC
# =================================================================

def patch_ini_standard(path, x, y):
    try:
        set_read_only(path, False)
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            if "ResolutionSizeX=" in line:                        line = f"ResolutionSizeX={x}\n"
            elif "ResolutionSizeY=" in line:                      line = f"ResolutionSizeY={y}\n"
            elif "LastUserConfirmedResolutionSizeX=" in line:     line = f"LastUserConfirmedResolutionSizeX={x}\n"
            elif "LastUserConfirmedResolutionSizeY=" in line:     line = f"LastUserConfirmedResolutionSizeY={y}\n"
            elif "DesiredScreenWidth=" in line:                   line = f"DesiredScreenWidth={x}\n"
            elif "DesiredScreenHeight=" in line:                  line = f"DesiredScreenHeight={y}\n"
            elif "LastUserConfirmedDesiredScreenWidth=" in line:  line = f"LastUserConfirmedDesiredScreenWidth={x}\n"
            elif "LastUserConfirmedDesiredScreenHeight=" in line: line = f"LastUserConfirmedDesiredScreenHeight={y}\n"
            elif "FullscreenMode=" in line:                       line = "FullscreenMode=2\n"
            elif "bShouldLetterbox=" in line:                     line = "bShouldLetterbox=False\n"
            elif "bLastConfirmedShouldLetterbox=" in line:        line = "bLastConfirmedShouldLetterbox=False\n"
            new_lines.append(line)
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        set_read_only(path, True)
    except Exception as e:
        print(f"Patch error: {e}")

def patch_ini_elite(path, x, y):
    try:
        set_read_only(path, False)
        content = ELITE_INI_TEMPLATE.replace("{X}", str(x)).replace("{Y}", str(y))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        set_read_only(path, True)
    except Exception as e:
        print(f"Patch error: {e}")

def run_installation(res_x, res_y, perf_enabled):
    local_app = os.getenv('LOCALAPPDATA', '')
    config_root = Path(local_app) / "VALORANT" / "Saved" / "Config"
    if not config_root.exists():
        return
    for folder in config_root.iterdir():
        if folder.is_dir() and len(folder.name) > 20:
            ini_path = folder / "Windows" / "GameUserSettings.ini"
            if ini_path.exists():
                if perf_enabled:
                    patch_ini_elite(ini_path, res_x, res_y)
                else:
                    patch_ini_standard(ini_path, res_x, res_y)

def create_shortcut():
    try:
        from win32com.client import Dispatch
        ensure_data_folder()
        desktop = os.path.join(os.getenv('USERPROFILE', ''), 'Desktop')
        path = os.path.join(desktop, f"{APP_NAME}.lnk")
        target = sys.executable
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(path)
        shortcut.Targetpath = target
        shortcut.Arguments = "--launch"
        shortcut.WorkingDirectory = os.path.dirname(target)
        if os.path.exists(PERMANENT_ICON_PATH):
            shortcut.IconLocation = PERMANENT_ICON_PATH
        shortcut.save()
    except Exception as e:
        print(f"Shortcut error: {e}")

# =================================================================
# 5. GUI & SETUP
# =================================================================

class SetupApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} Installer")
        self.root.geometry("440x620")

        ttk.Label(root, text=f"{APP_NAME.upper()} SETUP",
                  font=("Arial", 14, "bold")).pack(pady=12)

        # Resolution
        ttk.Label(root, text="Stretch Resolution Width (X):").pack()
        self.x_var = tk.StringVar(value="1440")
        ttk.Entry(root, textvariable=self.x_var).pack(pady=4)

        ttk.Label(root, text="Stretch Resolution Height (Y):").pack()
        self.y_var = tk.StringVar(value="1080")
        ttk.Entry(root, textvariable=self.y_var).pack(pady=4)

        # Performance toggle
        self.perf_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(root, text="Apply Performance Upgrade",
                        variable=self.perf_var).pack(pady=8)

        # Monitor picker
        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=20, pady=6)
        ttk.Label(root, text="Disable these monitors before launching Valorant:",
                  font=("Arial", 9, "bold")).pack()
        ttk.Label(root,
                  text="Prevents Valorant from hard-locking to 16:9 aspect ratio",
                  font=("Arial", 8), foreground="gray").pack()

        self.monitor_frame = ttk.Frame(root)
        self.monitor_frame.pack(pady=6, padx=24, fill="x")

        self.monitor_checks = []  # list of (BooleanVar, instance_id, friendly_name)
        self._populate_monitors()

        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=20, pady=8)
        ttk.Button(root, text="Install & Apply", command=self.install).pack(pady=6)
        ttk.Label(root, text=f"Recovery data: Documents\\{APP_NAME}",
                  font=("Arial", 8), foreground="gray").pack()

    def _populate_monitors(self):
        raw = enumerate_monitors()
        if not raw:
            ttk.Label(self.monitor_frame,
                      text="No monitors found in Device Manager.",
                      foreground="red").pack(anchor="w")
            return

        # Merge duplicates — same name gets all its instance IDs grouped together
        # so one checkbox disables every port/instance for that monitor.
        seen = {}  # name -> [instance_id, ...]
        for m in raw:
            seen.setdefault(m["name"], []).append(m["instance_id"])

        for name, ids in seen.items():
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(self.monitor_frame, text=name,
                            variable=var).pack(anchor="w", pady=1)
            self.monitor_checks.append((var, ids, name))

    def install(self):
        if not is_admin():
            # Re-launch elevated, passing current selections as CLI args so the
            # elevated instance can run install directly without showing the UI again.
            selected_ids = ",".join(
                iid
                for var, ids, name in self.monitor_checks if var.get()
                for iid in ids
            )
            selected_names = "|".join(
                f"{name}:::{','.join(ids)}"
                for var, ids, name in self.monitor_checks if var.get()
            )
            args = [
                sys.executable,
                *([sys.argv[0]] if not getattr(sys, 'frozen', False) else []),
                "--install-direct",
                f"--res-x={self.x_var.get()}",
                f"--res-y={self.y_var.get()}",
                f"--perf={int(self.perf_var.get())}",
                f"--monitors={selected_names}",
            ]
            arg_str = " ".join(f'"{a}"' for a in args[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", args[0], arg_str, None, 1
            )
            self.root.destroy()
            return

        self._run_install(
            x=self.x_var.get(),
            y=self.y_var.get(),
            perf=self.perf_var.get(),
            selected=[
                {"name": name, "instance_ids": ids}
                for var, ids, name in self.monitor_checks if var.get()
            ],
        )

    def _run_install(self, x, y, perf, selected):
        ensure_data_folder()
        config = {"x": x, "y": y, "perf": perf, "monitors": selected}
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)
            run_installation(config['x'], config['y'], config['perf'])

            all_ids = [iid for m in selected for iid in m.get("instance_ids", [])]
            if all_ids:
                disable_monitors(all_ids)

            create_shortcut()

            mon_lines = (
                "\n".join(f"  • {m['name']}" for m in selected)
                if selected else "  (none — monitors will stay enabled)"
            )
            messagebox.showinfo(
                "Success",
                f"{APP_NAME} is ready!\n\n"
                f"Monitors disabled at launch:\n{mon_lines}\n\n"
                f"Recovery data: Documents\\{APP_NAME}"
            )
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Setup failed: {e}")

# =================================================================
# 6. THE LAUNCHER
# =================================================================

def is_process_running(name):
    try:
        output = subprocess.check_output(
            ['tasklist', '/FI', f'IMAGENAME eq {name}', '/NH', '/FO', 'CSV'],
            creationflags=0x08000000,
            stderr=subprocess.DEVNULL
        ).decode(errors='ignore')
        return name.lower() in output.lower()
    except:
        return False


def launch_stretchy():
    if not os.path.exists(CONFIG_PATH):
        return

    ensure_data_folder()

    with open(CONFIG_PATH, 'r') as f:
        cfg = json.load(f)

    # Flatten all instance IDs from all selected monitors into one list
    monitor_ids = [iid for m in cfg.get("monitors", []) for iid in m.get("instance_ids", [])]

    # 1. CAPTURE native resolution before anything changes
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    orig_x = user32.GetSystemMetrics(0)
    orig_y = user32.GetSystemMetrics(1)

    with open(SESSION_DATA_PATH, 'w') as f:
        json.dump({"x": orig_x, "y": orig_y}, f)

    # 2. APPLY STRETCH RESOLUTION
    res_tool = get_resource_path("SetScreenResolution.exe")
    if not os.path.exists(res_tool):
        messagebox.showerror("Error", f"SetScreenResolution.exe not found.\nExpected: {res_tool}")
        restore_and_exit(orig_x, orig_y, res_tool)
        return

    subprocess.run([res_tool, str(cfg['x']), str(cfg['y'])], creationflags=0x08000000)

    # 4. LAUNCH RIOT CLIENT → VALORANT
    riot_path = get_riot_client_path()
    if not riot_path:
        for p in [
            r"C:\Riot Games\Riot Client\RiotClientServices.exe",
            r"D:\Riot Games\Riot Client\RiotClientServices.exe",
        ]:
            if os.path.exists(p):
                riot_path = p
                break

    if not riot_path:
        messagebox.showerror("Error", "Riot Client not found. Restoring resolution.")
        restore_and_exit(orig_x, orig_y, res_tool)
        return

    # Launch via ShellExecuteW with "open" verb — this forces the Riot Client
    # to start at normal (medium) integrity regardless of StretchyVal's privilege
    # level, which prevents it blocking overlays and crosshair tools.
    ctypes.windll.shell32.ShellExecuteW(
        None, "open", riot_path,
        "--launch-product=valorant --launch-patchline=live",
        os.path.dirname(riot_path), 1
    )

    # 5. MONITORING LOOP
    #
    # Phase A — Wait up to 5 min for VALORANT-Win64-Shipping.exe to appear.
    # Phase B — Watch BOTH VALORANT.exe + VALORANT-Win64-Shipping.exe.
    #           Require 4 consecutive "both gone" polls (~20 s) before restoring.
    # Phase C — Restore resolution and exit. Monitors stay disabled intentionally.

    STARTUP_TIMEOUT   = 300
    POLL_INTERVAL     = 3  # seconds between checks
    CONFIRM_THRESHOLD = 1  # gone for ~3 s before restoring

    # --- Phase A ---
    start_wait = time.time()
    while True:
        if is_process_running("VALORANT-Win64-Shipping.exe"):
            break
        elapsed = time.time() - start_wait
        if not is_process_running("RiotClientServices.exe") and elapsed > 180:
            restore_and_exit(orig_x, orig_y, res_tool)
            return
        if elapsed > STARTUP_TIMEOUT:
            restore_and_exit(orig_x, orig_y, res_tool)
            return
        time.sleep(POLL_INTERVAL)

    # --- Phase B ---
    gone_count = 0
    while True:
        if is_process_running("VALORANT-Win64-Shipping.exe") or is_process_running("VALORANT.exe"):
            gone_count = 0
        else:
            gone_count += 1
            if gone_count >= CONFIRM_THRESHOLD:
                break
        time.sleep(POLL_INTERVAL)

    # --- Phase C ---
    restore_and_exit(orig_x, orig_y, res_tool)


def restore_and_exit(fallback_x, fallback_y, tool_path):
    """Restore resolution and exit. Monitors stay disabled intentionally."""
    res_x, res_y = fallback_x, fallback_y
    if os.path.exists(SESSION_DATA_PATH):
        try:
            with open(SESSION_DATA_PATH, 'r') as f:
                data = json.load(f)
                res_x, res_y = data['x'], data['y']
        except:
            pass

    if os.path.exists(tool_path):
        subprocess.run([tool_path, str(res_x), str(res_y)], creationflags=0x08000000)
    else:
        _set_resolution_via_api(res_x, res_y)

    os._exit(0)


def _set_resolution_via_api(width, height):
    """Fallback: set resolution via ctypes if SetScreenResolution.exe is missing."""
    DM_PELSWIDTH  = 0x00080000
    DM_PELSHEIGHT = 0x00100000

    class DEVMODE(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName",         ctypes.c_wchar * 32),
            ("dmSpecVersion",        ctypes.c_ushort),
            ("dmDriverVersion",      ctypes.c_ushort),
            ("dmSize",               ctypes.c_ushort),
            ("dmDriverExtra",        ctypes.c_ushort),
            ("dmFields",             ctypes.c_ulong),
            ("dmPositionX",          ctypes.c_long),
            ("dmPositionY",          ctypes.c_long),
            ("dmDisplayOrientation", ctypes.c_ulong),
            ("dmDisplayFixedOutput", ctypes.c_ulong),
            ("dmColor",              ctypes.c_short),
            ("dmDuplex",             ctypes.c_short),
            ("dmYResolution",        ctypes.c_short),
            ("dmTTOption",           ctypes.c_short),
            ("dmCollate",            ctypes.c_short),
            ("dmFormName",           ctypes.c_wchar * 32),
            ("dmLogPixels",          ctypes.c_ushort),
            ("dmBitsPerPel",         ctypes.c_ulong),
            ("dmPelsWidth",          ctypes.c_ulong),
            ("dmPelsHeight",         ctypes.c_ulong),
            ("dmDisplayFlags",       ctypes.c_ulong),
            ("dmDisplayFrequency",   ctypes.c_ulong),
            ("dmICMMethod",          ctypes.c_ulong),
            ("dmICMIntent",          ctypes.c_ulong),
            ("dmMediaType",          ctypes.c_ulong),
            ("dmDitherType",         ctypes.c_ulong),
            ("dmReserved1",          ctypes.c_ulong),
            ("dmReserved2",          ctypes.c_ulong),
            ("dmPanningWidth",       ctypes.c_ulong),
            ("dmPanningHeight",      ctypes.c_ulong),
        ]

    dm = DEVMODE()
    dm.dmSize       = ctypes.sizeof(DEVMODE)
    dm.dmFields     = DM_PELSWIDTH | DM_PELSHEIGHT
    dm.dmPelsWidth  = width
    dm.dmPelsHeight = height
    ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(dm), 0)


# =================================================================
# 7. MAIN ENTRY
# =================================================================

if __name__ == "__main__":
    if "--launch" in sys.argv:
        # Launcher mode — no elevation needed, monitors already disabled at install time
        launch_stretchy()

    elif "--install-direct" in sys.argv:
        # Elevated install triggered by the setup UI — run silently, no window needed
        def _get_arg(prefix):
            for a in sys.argv:
                if a.startswith(prefix):
                    return a[len(prefix):]
            return ""

        x    = _get_arg("--res-x=") or "1440"
        y    = _get_arg("--res-y=") or "1080"
        perf = bool(int(_get_arg("--perf=") or "1"))
        raw_monitors = _get_arg("--monitors=")

        selected = []
        if raw_monitors:
            for entry in raw_monitors.split("|"):
                if ":::" in entry:
                    name, ids_str = entry.split(":::", 1)
                    selected.append({"name": name, "instance_ids": ids_str.split(",")})

        ensure_data_folder()
        config = {"x": x, "y": y, "perf": perf, "monitors": selected}
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        run_installation(x, y, perf)

        all_ids = [iid for m in selected for iid in m.get("instance_ids", [])]
        if all_ids:
            disable_monitors(all_ids)

        create_shortcut()

    else:
        # Setup mode — open window without elevation, monitors list reads fine unprivileged
        root = tk.Tk()
        SetupApp(root)
        root.mainloop()