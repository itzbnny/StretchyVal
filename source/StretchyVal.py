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
                creationflags=0x08000000 | 0x00000008,  # NO_WINDOW | DETACHED_PROCESS
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
DefaultMonitorDeviceID=
DefaultMonitorIndex=0
LastConfirmedDefaultMonitorDeviceID=
LastConfirmedDefaultMonitorIndex=0
bShouldLetterbox=False
bLastConfirmedShouldLetterbox=False
bUseVSync=False
bUseDynamicResolution=False
ResolutionSizeX={X}
ResolutionSizeY={Y}
LastUserConfirmedResolutionSizeX={X}
LastUserConfirmedResolutionSizeY={Y}
LastConfirmedFullscreenMode=2
PreferredFullscreenMode=2
FullscreenMode=2
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
r.OneFrameThreadLag=0
r.MaximumFrameLatency=1
r.SimpleForwardShading=1
r.CEFGPUAcceleration=1
r.GTSyncType=2
r.rhi.SyncInterval=0
rhi.SyncSlackMS=0
r.FinishCurrentFrame=0
r.DepthOfFieldQuality=0
r.EyeAdaptationQuality=0
r.BloomQuality=0
bRayTracing=False
RayTracingShadowsQuality=False
RayTracingReflectionsQuality=0
RayTracingAmbientOcclusionQuality=False
RayTracingAOQuality=0
RayTracingGIQuality=0
bSmoothFrameRate=false
bEnableMouseSmoothing=False
AllowUserSettingLowInputLatencyMode=True
LowInputLatencyModeEnabled=True
LowInputLatencyModeIsEnabled=True
MouseSamplingTime=0.000125
MouseAccelThreshold=1000000.000000
ReduceMouseLag=True
bDisableMouseAcceleration=True

[/Script/Engine.GameUserSettings]
bUseDesiredScreenHeight=False

[/Script/HardwareTargeting.HardwareTargetingSettings]
TargetedHardwareClass=Desktop
AppliedTargetedHardwareClass=Desktop
DefaultGraphicsPerformance=Minimum
AppliedDefaultGraphicsPerformance=Minimum

[ScalabilityGroups]
sg.ResolutionQuality=100
sg.ViewDistanceQuality=1
sg.AntiAliasingQuality=0
sg.ShadowQuality=0
sg.PostProcessQuality=0
sg.TextureQuality=0
sg.EffectsQuality=0
sg.FoliageQuality=0
sg.TrueSkyQuality=1
sg.GroundClutterQuality=0
sg.IBLQuality=0
sg.HeightFieldShadowQuality=0
sg.ShadingQuality=0
sg.GlobalIlluminationQuality=0
sg.ReflectionQuality=0
sg.GraphicQuality=0
sg.ApplicationQuality=0
sg.AudioQuality=1
sg.DOFQuality=0
sg.AmbientOcclusionQuality=0
sg.MotionBlurQuality=0
sg.SubSurfaceScatteringQuality=0
sg.CapsuleShadowQuality=0
sg.ScreenSpaceShadowQuality=0
sg.LightShaftQuality=0
sg.LensFlareQuality=0
sg.TextureFilteringQuality=0
sg.WorldLODQuality=0
sg.CharacterLODQuality=0
sg.AnimationQuality=0
sg.DynamicResolutionScalingQuality=0
sg.GrassDrawDistanceQuality=0
sg.ScreenSpaceReflectionsQuality=0
sg.ReflectionCaptureActorsQuality=0
sg.RefractionQuality=0
sg.VolumetricFogQuality=0
sg.TessellationQuality=0
sg.ConeStepMappingQuality=0
sg.TranslucencyQuality=0
sg.CharacterTextureDetailQuality=0
sg.WorldTextureDetailQuality=0
sg.EffectsTextureDetailQuality=0
sg.TextureStreamingQuality=0
sg.AsyncComputeQuality=0
sg.TiledResourcesQuality=0
sg.TCDrawCalls=0
sg.PMVQuality=0
sg.ViewDistanceScale=1.0
sg.BloomQuality=0
sg.PerformanceMode=4
sg.FoliageQuality=0

[RayTracing]
r.RayTracing.EnableInGame=False

[ShaderPipelineCache.CacheFile]
LastOpened=ShooterGame
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
            if "ResolutionSizeX=" in line:                            line = f"ResolutionSizeX={x}\n"
            elif "ResolutionSizeY=" in line:                          line = f"ResolutionSizeY={y}\n"
            elif "LastUserConfirmedResolutionSizeX=" in line:         line = f"LastUserConfirmedResolutionSizeX={x}\n"
            elif "LastUserConfirmedResolutionSizeY=" in line:         line = f"LastUserConfirmedResolutionSizeY={y}\n"
            elif "DesiredScreenWidth=" in line:                       line = f"DesiredScreenWidth={x}\n"
            elif "DesiredScreenHeight=" in line:                      line = f"DesiredScreenHeight={y}\n"
            elif "LastUserConfirmedDesiredScreenWidth=" in line:      line = f"LastUserConfirmedDesiredScreenWidth={x}\n"
            elif "LastUserConfirmedDesiredScreenHeight=" in line:     line = f"LastUserConfirmedDesiredScreenHeight={y}\n"
            elif "FullscreenMode=" in line:                           line = "FullscreenMode=2\n"
            elif "PreferredFullscreenMode=" in line:                  line = "PreferredFullscreenMode=2\n"
            elif "LastConfirmedFullscreenMode=" in line:              line = "LastConfirmedFullscreenMode=2\n"
            elif "bShouldLetterbox=" in line:                         line = "bShouldLetterbox=False\n"
            elif "bLastConfirmedShouldLetterbox=" in line:            line = "bLastConfirmedShouldLetterbox=False\n"
            elif "DefaultMonitorDeviceID=" in line:              line = "DefaultMonitorDeviceID=\n"
            elif "LastConfirmedDefaultMonitorDeviceID=" in line: line = "LastConfirmedDefaultMonitorDeviceID=\n"
            elif "DefaultMonitorIndex=" in line:                 line = "DefaultMonitorIndex=0\n"
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

def run_installation(res_x, res_y, perf_enabled, log_path=None):
    """
    Find and patch EVERY GameUserSettings.ini under the Valorant config root,
    regardless of subfolder structure. Uses recursive search so we never miss
    files in unexpected locations like WindowsClient\\GameUserSettings.ini.
    """
    import re

    def dbg(msg):
        if not log_path:
            return
        ts = time.strftime("%H:%M:%S")
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{ts}] {msg}\n")
        except:
            pass

    local_app = os.getenv('LOCALAPPDATA', '')
    config_root = Path(local_app) / "VALORANT" / "Saved" / "Config"
    dbg(f"Config root: {config_root} (exists={config_root.exists()})")
    if not config_root.exists():
        return

    # Find every GameUserSettings.ini recursively — catches Windows\, WindowsClient\, etc.
    all_inis = [
        p for p in config_root.rglob("GameUserSettings.ini")
        if "CrashReportClient" not in str(p)
    ]
    dbg(f"Found {len(all_inis)} GameUserSettings.ini file(s): {[str(p) for p in all_inis]}")

    for ini_path in all_inis:
        dbg(f"Patching: {ini_path.name} in {ini_path.parent.parent.name}\\{ini_path.parent.name}")

        try:
            set_read_only(str(ini_path), False)

            if perf_enabled:
                patch_ini_elite(str(ini_path), res_x, res_y)
            else:
                patch_ini_standard(str(ini_path), res_x, res_y)

            set_read_only(str(ini_path), False)
            with open(str(ini_path), 'r', encoding='utf-8') as f:
                content = f.read()

            replacements = {
                'bShouldLetterbox':                'False',
                'bLastConfirmedShouldLetterbox':   'False',
                'FullscreenMode':                  '2',
                'PreferredFullscreenMode':         '2',
                'LastConfirmedFullscreenMode':     '2',
                'LastConfirmedDefaultMonitorIndex': '0',
                'DefaultMonitorIndex':             '0',
                'DefaultMonitorDeviceID':          '',
                'LastConfirmedDefaultMonitorDeviceID': '',
            }
            for key, val in replacements.items():
                # Remove ALL existing occurrences first, then append once
                # This prevents duplicates from multiple sections or repeated patching
                import re as _re
                content = _re.sub(rf'(?m)^{key}=.*\n?', '', content)
                # Add the key in the correct section
                if '[/Script/ShooterGame.ShooterGameUserSettings]' in content:
                    content = content.replace(
                        '[/Script/ShooterGame.ShooterGameUserSettings]\n',
                        f'[/Script/ShooterGame.ShooterGameUserSettings]\n{key}={val}\n'
                    )
                else:
                    content += f'{key}={val}\n'

            with open(str(ini_path), 'w', encoding='utf-8') as f:
                f.write(content)
            set_read_only(str(ini_path), True)
            dbg(f"  Done.")

        except Exception as e:
            dbg(f"  Error: {e}")

def create_shortcut(exe_path=None):
    """
    Create a desktop shortcut using VBScript (no pywin32 dependency).
    exe_path overrides sys.executable — pass this when called from an elevated
    subprocess so the shortcut points to the original exe, not the temp folder.
    """
    try:
        ensure_data_folder()
        desktop = os.path.join(os.getenv('USERPROFILE', ''), 'Desktop')
        shortcut_path = os.path.join(desktop, f"{APP_NAME}.lnk")

        if exe_path:
            target      = exe_path
            args        = "--launch"
            working_dir = os.path.dirname(exe_path)
        elif getattr(sys, 'frozen', False):
            target      = sys.executable
            args        = "--launch"
            working_dir = os.path.dirname(sys.executable)
        else:
            target      = sys.executable
            args        = f'"{os.path.abspath(sys.argv[0])}" --launch'
            working_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

        icon = PERMANENT_ICON_PATH if os.path.exists(PERMANENT_ICON_PATH) else target

        # Use Windows Script Host via subprocess as the most reliable fallback
        # that works without pywin32 on any machine.
        vbs = f"""
Set oShell = CreateObject("WScript.Shell")
Set oLink = oShell.CreateShortcut("{shortcut_path}")
oLink.TargetPath = "{target}"
oLink.Arguments = "{args}"
oLink.WorkingDirectory = "{working_dir}"
oLink.IconLocation = "{icon}"
oLink.Save
"""
        vbs_path = os.path.join(DOCUMENTS_DIR, "_make_shortcut.vbs")
        with open(vbs_path, 'w') as f:
            f.write(vbs)

        result = subprocess.run(
            ["cscript", "//Nologo", vbs_path],
            creationflags=0x08000000,
            capture_output=True
        )

        try:
            os.remove(vbs_path)
        except:
            pass

        return os.path.exists(shortcut_path)

    except Exception as e:
        print(f"Shortcut error: {e}")
        return False

def check_nvidia_scaling():
    """
    Detect if the system has an NVIDIA GPU and show a one-time reminder
    to enable the GPU scaling override in NVIDIA Control Panel.
    This setting is required for stretch to work without black bars
    and cannot be reliably set programmatically.
    """
    try:
        output = subprocess.check_output(
            ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
            creationflags=0x08000000,
            stderr=subprocess.DEVNULL
        ).decode(errors='ignore').lower()
        if 'nvidia' not in output:
            return
    except:
        return

    messagebox.showinfo(
        "NVIDIA GPU Detected — Action Required",
        "To prevent black bars in Valorant you must enable GPU scaling override:\n\n"
        "1. Right-click your desktop → NVIDIA Control Panel\n"
        "2. Click 'Adjust desktop size and position'\n"
        "3. Set Scaling to 'Full-screen'\n"
        "4. Check 'Override the scaling mode set by games and programs'\n"
        "5. Click Apply\n\n"
        "This is a one-time setup step and only needs to be done once."
    )

def enable_monitors(instance_ids):
    """Re-enable monitors that were disabled by StretchyVal."""
    for iid in instance_ids:
        try:
            subprocess.run(
                ["pnputil", "/enable-device", iid],
                creationflags=0x08000000 | 0x00000008,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except Exception:
            pass
    time.sleep(1)


def run_uninstall():
    """
    Uninstall StretchyVal:
    - Re-enable any disabled monitors
    - Unlock all Valorant INI files so the game can edit them again
    - Delete the config file
    - Delete the desktop shortcut
    - Leave the Documents folder intact (user may want the logs)
    """
    # Re-enable monitors that were disabled at install time
    monitors_enabled = 0
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            all_ids = [iid for m in cfg.get("monitors", []) for iid in m.get("instance_ids", [])]
            if all_ids:
                enable_monitors(all_ids)
                monitors_enabled = len(all_ids)
    except:
        pass
    # Unlock all INIs
    local_app = os.getenv('LOCALAPPDATA', '')
    config_root = Path(local_app) / "VALORANT" / "Saved" / "Config"
    unlocked = 0
    if config_root.exists():
        for ini_path in config_root.rglob("GameUserSettings.ini"):
            if "CrashReportClient" in str(ini_path):
                continue
            try:
                set_read_only(str(ini_path), False)
                unlocked += 1
            except:
                pass

    # Delete config file
    try:
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
    except:
        pass

    # Delete desktop shortcut
    try:
        shortcut = os.path.join(os.getenv('USERPROFILE', ''), 'Desktop', f"{APP_NAME}.lnk")
        if os.path.exists(shortcut):
            os.remove(shortcut)
    except:
        pass

    messagebox.showinfo(
        "Uninstalled",
        f"{APP_NAME} has been uninstalled.\n\n"
        f"• {monitors_enabled} monitor(s) re-enabled\n"
        f"• {unlocked} Valorant config file(s) unlocked\n"
        f"• Desktop shortcut removed\n"
        f"• Config file deleted\n\n"
        f"Your Valorant settings are now fully editable again.\n"
        f"Launch Valorant from the official shortcut to restore your preferred settings."
    )


# =================================================================
# =================================================================

class SetupApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} Installer")
        self.root.geometry("440x620")

        ttk.Label(root, text=f"{APP_NAME.upper()} SETUP",
                  font=("Arial", 14, "bold")).pack(pady=12)

        # Resolution
        # Resolution dropdown — populated from system display modes
        ttk.Label(root, text="⚠ Custom Resolutions Don't Work",
                  font=("Arial", 8, "bold"), foreground="orange").pack()
        ttk.Label(root, text="Select a stretch resolution:").pack()

        # Enumerate all unique resolutions from the system
        resolutions = self._get_system_resolutions()
        res_strings = [f"{w}x{h}" for w, h in resolutions]

        self.res_var = tk.StringVar(value="1440x1080" if "1440x1080" in res_strings else res_strings[0] if res_strings else "1440x1080")
        res_combo = ttk.Combobox(root, textvariable=self.res_var, values=res_strings, state="readonly", width=20)
        res_combo.pack(pady=4)

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
        ttk.Button(root, text="Uninstall", command=self.uninstall).pack(pady=2)
        ttk.Label(root, text=f"Recovery data: Documents\\{APP_NAME}",
                  font=("Arial", 8), foreground="gray").pack()

    def _get_system_resolutions(self):
        """Return sorted list of (width, height) tuples from system display modes, non-native only."""
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

        # Get native resolution to exclude it
        user32 = ctypes.windll.user32
        native_w = user32.GetSystemMetrics(0)
        native_h = user32.GetSystemMetrics(1)

        seen = set()
        i = 0
        while True:
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            if not user32.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
                break
            w, h = dm.dmPelsWidth, dm.dmPelsHeight
            # Only include non-native resolutions with non-16:9 aspect ratios
            # (stretched resolutions are typically 4:3 or other non-widescreen)
            if (w, h) != (native_w, native_h) and w > 0 and h > 0:
                seen.add((w, h))
            i += 1

        # Sort by width descending
        return sorted(seen, key=lambda r: (-r[0], -r[1]))

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

    def uninstall(self):
        if not is_admin():
            args = [
                sys.executable,
                *([sys.argv[0]] if not getattr(sys, 'frozen', False) else []),
                "--uninstall-direct",
            ]
            arg_str = " ".join(f'"{a}"' for a in args[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", args[0], arg_str, None, 1
            )
            self.root.destroy()
            sys.exit(0)
        run_uninstall()
        self.root.destroy()

    def install(self):
        if not is_admin():
            selected_names = "|".join(
                f"{name}:::{','.join(ids)}"
                for var, ids, name in self.monitor_checks if var.get()
            )
            # Pass the real exe path so the elevated process can create the
            # shortcut pointing back to the original location, not the temp folder
            real_exe = os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0])
            args = [
                sys.executable,
                *([sys.argv[0]] if not getattr(sys, 'frozen', False) else []),
                "--install-direct",
                f"--res-x={self.res_var.get().split('x')[0]}",
                f"--res-y={self.res_var.get().split('x')[1]}",
                f"--perf={int(self.perf_var.get())}",
                f"--monitors={selected_names}",
                f"--exe-path={real_exe}",
            ]
            arg_str = " ".join(f'"{a}"' for a in args[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", args[0], arg_str, None, 1
            )
            self.root.destroy()
            sys.exit(0)

        self._run_install(
            x=self.res_var.get().split('x')[0],
            y=self.res_var.get().split('x')[1],
            perf=self.perf_var.get(),
            selected=[
                {"name": name, "instance_ids": ids}
                for var, ids, name in self.monitor_checks if var.get()
            ],
        )

    def _run_install(self, x, y, perf, selected):
        ensure_data_folder()

        # Validate the resolution is supported by Windows before saving anything.
        # SetScreenResolution.exe runs CDS_TEST internally and exits with code 1
        # if the resolution is unsupported — catch that here with a clear message.
        res_tool = get_resource_path("SetScreenResolution.exe")
        if os.path.exists(res_tool):
            test = subprocess.run(
                [res_tool, str(x), str(y)],
                creationflags=0x08000000,
                capture_output=True
            )
            if test.returncode != 0:
                messagebox.showerror(
                    "Unsupported Resolution",
                    f"{x}x{y} is not supported by your display driver.\n\n"
                    f"Please try a different resolution. Common stretched resolutions:\n"
                    f"  • 1440x1080\n"
                    f"  • 1280x1080\n"
                    f"  • 1024x768\n\n"
                    f"If you need a custom resolution, add it first via\n"
                    f"NVIDIA Control Panel → Change Resolution → Customize."
                )
                return

        config = {"x": x, "y": y, "perf": perf, "monitors": selected}
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)
            run_installation(config['x'], config['y'], config['perf'],
                            log_path=os.path.join(DOCUMENTS_DIR, "debug.log"))
            register_custom_resolution(int(config['x']), int(config['y']))
            check_nvidia_scaling()

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

def register_custom_resolution(width, height):
    """
    Register a custom resolution with Windows via ChangeDisplaySettingsW
    using CDS_UPDATEREGISTRY | CDS_NORESET so it's saved to the registry
    and recognised by SetScreenResolution.exe on every launch, without
    actually switching the display right now.
    Called at install time when the process is already elevated.
    """
    DM_PELSWIDTH        = 0x00080000
    DM_PELSHEIGHT       = 0x00100000
    DM_DISPLAYFREQUENCY = 0x00400000
    CDS_UPDATEREGISTRY  = 0x00000001
    CDS_NORESET         = 0x10000000

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

    # Get current refresh rate to preserve it
    dm_current = DEVMODE()
    dm_current.dmSize = ctypes.sizeof(DEVMODE)
    hz = 60
    if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm_current)):
        hz = dm_current.dmDisplayFrequency

    dm = DEVMODE()
    dm.dmSize             = ctypes.sizeof(DEVMODE)
    dm.dmFields           = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    dm.dmPelsWidth        = width
    dm.dmPelsHeight       = height
    dm.dmDisplayFrequency = hz

    result = ctypes.windll.user32.ChangeDisplaySettingsW(
        ctypes.byref(dm), CDS_UPDATEREGISTRY | CDS_NORESET
    )
    return result == 0  # DISP_CHANGE_SUCCESSFUL


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

    LOG_PATH = os.path.join(DOCUMENTS_DIR, "debug.log")
    try:
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.write(f"=== StretchyVal Debug — {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
    except:
        pass

    def dbg(msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        try:
            with open(LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
        except:
            pass

    with open(CONFIG_PATH, 'r') as f:
        cfg = json.load(f)
    dbg(f"Config: stretch={cfg['x']}x{cfg['y']} perf={cfg.get('perf')}")

    monitor_ids = [iid for m in cfg.get("monitors", []) for iid in m.get("instance_ids", [])]

    # --- PATCH all INI files BEFORE launching ---
    local_app = os.getenv('LOCALAPPDATA', '')
    config_root = Path(local_app) / "VALORANT" / "Saved" / "Config"
    if not config_root.exists():
        dbg("WARNING: Valorant config root not found")

    dbg("Patching INI files before launch...")
    run_installation(cfg['x'], cfg['y'], cfg.get('perf', False), log_path=LOG_PATH)
    dbg("Pre-launch patch complete.")

    # 1. CAPTURE native resolution AND refresh rate before anything changes
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    orig_x = user32.GetSystemMetrics(0)
    orig_y = user32.GetSystemMetrics(1)
    dbg(f"Native resolution captured: {orig_x}x{orig_y}")

    # Read current refresh rate from the active display mode
    orig_hz = 60  # safe fallback
    try:
        DM_DISPLAYFREQUENCY = 0x00400000
        class _DEVMODE(ctypes.Structure):
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
        dm = _DEVMODE()
        dm.dmSize = ctypes.sizeof(_DEVMODE)
        # EnumDisplaySettingsW(NULL, ENUM_CURRENT_SETTINGS=-1) reads the active mode
        if user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):
            orig_hz = dm.dmDisplayFrequency
    except:
        pass

    dbg(f"Refresh rate captured: {orig_hz}hz")
    with open(SESSION_DATA_PATH, 'w') as f:
        json.dump({"x": orig_x, "y": orig_y, "hz": orig_hz}, f)
    dbg(f"Session data saved to: {SESSION_DATA_PATH}")

    # 2. APPLY STRETCH RESOLUTION (keeping native refresh rate)
    res_tool = get_resource_path("SetScreenResolution.exe")
    dbg(f"SetScreenResolution.exe: {res_tool} (exists={os.path.exists(res_tool)})")
    if not os.path.exists(res_tool):
        messagebox.showerror("Error", f"SetScreenResolution.exe not found.\nExpected: {res_tool}")
        restore_and_exit(orig_x, orig_y, res_tool)
        return

    dbg(f"Applying stretch: {cfg['x']}x{cfg['y']} @ {orig_hz}hz")
    subprocess.run([res_tool, str(cfg['x']), str(cfg['y'])], creationflags=0x08000000)
    _set_resolution_via_api(int(cfg['x']), int(cfg['y']), orig_hz)
    check_x = user32.GetSystemMetrics(0)
    check_y = user32.GetSystemMetrics(1)
    dbg(f"Resolution after stretch apply: {check_x}x{check_y} (expected {cfg['x']}x{cfg['y']})")

    riot_path = get_riot_client_path()
    if not riot_path:
        for p in [
            r"C:\Riot Games\Riot Client\RiotClientServices.exe",
            r"D:\Riot Games\Riot Client\RiotClientServices.exe",
        ]:
            if os.path.exists(p):
                riot_path = p
                break

    dbg(f"Riot Client path: {riot_path if riot_path else 'NOT FOUND'}")

    if not riot_path:
        messagebox.showerror("Error", "Riot Client not found. Restoring resolution.")
        restore_and_exit(orig_x, orig_y, res_tool)
        return

    dbg("Launching Riot Client...")
    ctypes.windll.shell32.ShellExecuteW(
        None, "open", riot_path,
        "--launch-product=valorant --launch-patchline=live",
        os.path.dirname(riot_path), 1
    )
    dbg("Riot Client launched.")

    # Snapshot config folders that exist BEFORE Valorant launches.
    # Any new folders that appear after launch are fresh account installs
    # that need patching — Valorant creates them during first login.
    local_app = os.getenv('LOCALAPPDATA', '')
    config_root = Path(local_app) / "VALORANT" / "Saved" / "Config"
    folders_before = set()
    if config_root.exists():
        folders_before = {
            f.name for f in config_root.iterdir()
            if f.is_dir() and f.name not in ("CrashReportClient",)
        }
    dbg(f"Config folders before launch: {folders_before}")

    STARTUP_TIMEOUT   = 300
    POLL_INTERVAL     = 3
    CONFIRM_THRESHOLD = 1

    # --- Phase A ---
    dbg("Phase A — waiting for VALORANT-Win64-Shipping.exe...")
    start_wait = time.time()
    while True:
        if is_process_running("VALORANT-Win64-Shipping.exe"):
            dbg("Phase A — VALORANT-Win64-Shipping.exe detected.")
            # Immediately patch any new folders Valorant created during login
            if config_root.exists():
                folders_now = {
                    f.name for f in config_root.iterdir()
                    if f.is_dir() and f.name not in ("CrashReportClient",)
                }
                new_folders = folders_now - folders_before
                if new_folders:
                    dbg(f"New folders detected at Valorant start: {new_folders} — patching immediately")
                    run_installation(cfg['x'], cfg['y'], cfg.get('perf', False), log_path=LOG_PATH)
            break
        elapsed = time.time() - start_wait
        if not is_process_running("RiotClientServices.exe") and elapsed > 180:
            dbg("Phase A — Riot Client closed before Valorant appeared. Restoring.")
            restore_and_exit(orig_x, orig_y, res_tool)
            return
        if elapsed > STARTUP_TIMEOUT:
            dbg("Phase A — Timed out. Restoring.")
            restore_and_exit(orig_x, orig_y, res_tool)
            return
        time.sleep(POLL_INTERVAL)

    # Wait for Valorant to finish its cloud sync and write its settings.
    # Instead of a fixed delay we watch the INI files for changes and patch
    # immediately after each write, for the first 90 seconds after launch.
    # This catches the cloud sync write as soon as it happens.
    dbg("Watching INI files for Valorant cloud sync writes (90s max)...")

    def get_ini_mtimes():
        """Return mtime for every GameUserSettings.ini under the config root."""
        mtimes = {}
        if not config_root.exists():
            return mtimes
        for ini in config_root.rglob("GameUserSettings.ini"):
            if "CrashReportClient" in str(ini):
                continue
            try:
                mtimes[str(ini)] = ini.stat().st_mtime
            except:
                pass
        return mtimes

    watch_start = time.time()
    WATCH_DURATION  = 90
    NO_CHANGE_EXIT  = 30  # exit early if no changes for this many seconds after a patch
    last_change_time = None

    last_mtimes = get_ini_mtimes()
    patch_fired = False

    while time.time() - watch_start < WATCH_DURATION:
        time.sleep(3)

        # Exit immediately if Valorant closed during the watch window
        if not is_process_running("VALORANT-Win64-Shipping.exe") and not is_process_running("VALORANT.exe"):
            dbg("Valorant closed during watch window — patching and exiting")
            run_installation(cfg['x'], cfg['y'], cfg.get('perf', False), log_path=LOG_PATH)
            patch_fired = True
            break

        current_mtimes = get_ini_mtimes()
        changed = [p for p, t in current_mtimes.items() if last_mtimes.get(p) != t]
        if changed:
            dbg(f"INI change detected: {changed} — patching now")
            run_installation(cfg['x'], cfg['y'], cfg.get('perf', False), log_path=LOG_PATH)
            last_mtimes = get_ini_mtimes()
            last_change_time = time.time()
            patch_fired = True
        elif patch_fired and (time.time() - last_change_time) > NO_CHANGE_EXIT:
            dbg("No further changes for 30s after patch — exiting watch early")
            break

    if not patch_fired:
        dbg("No INI changes detected — patching as safety net")
        run_installation(cfg['x'], cfg['y'], cfg.get('perf', False), log_path=LOG_PATH)

    dbg("INI watch complete.")

    # If Valorant already closed during the watch window, skip Phase B
    if not is_process_running("VALORANT-Win64-Shipping.exe") and not is_process_running("VALORANT.exe"):
        dbg("Valorant already closed — final patch then restoring.")
        run_installation(cfg['x'], cfg['y'], cfg.get('perf', False), log_path=LOG_PATH)
        restore_and_exit(orig_x, orig_y, res_tool)
        return

    # --- Phase B ---
    dbg("Phase B — monitoring for Valorant close...")
    gone_count = 0

    while True:
        shipping = is_process_running("VALORANT-Win64-Shipping.exe")
        bootstrap = is_process_running("VALORANT.exe")

        if shipping or bootstrap:
            gone_count = 0
        else:
            gone_count += 1
            dbg(f"Phase B — both gone ({gone_count}/{CONFIRM_THRESHOLD})")
            if gone_count >= CONFIRM_THRESHOLD:
                dbg("Phase B — confirmed closed. Restoring.")
                break

        time.sleep(POLL_INTERVAL)

    # --- Phase C ---
    # Valorant writes its final settings on close, overwriting our patches.
    # We patch one last time NOW that it's fully dead so the INI is correct
    # for the next launch.
    dbg("Phase C — final INI patch after Valorant closed...")
    run_installation(cfg['x'], cfg['y'], cfg.get('perf', False), log_path=LOG_PATH)
    dbg("Phase C — restoring resolution and exiting.")
    restore_and_exit(orig_x, orig_y, res_tool)


def restore_and_exit(fallback_x, fallback_y, tool_path):
    """Restore resolution and refresh rate, then exit. Monitors stay disabled intentionally."""
    res_x, res_y, res_hz = fallback_x, fallback_y, 60
    if os.path.exists(SESSION_DATA_PATH):
        try:
            with open(SESSION_DATA_PATH, 'r') as f:
                data = json.load(f)
                res_x  = data.get('x', fallback_x)
                res_y  = data.get('y', fallback_y)
                res_hz = data.get('hz', 60)
        except:
            pass

    if os.path.exists(tool_path):
        subprocess.run([tool_path, str(res_x), str(res_y)], creationflags=0x08000000)
        _set_resolution_via_api(res_x, res_y, res_hz)
    else:
        _set_resolution_via_api(res_x, res_y, res_hz)

    # Clean up temp files
    try:
        vbs_path = os.path.join(DOCUMENTS_DIR, "_make_shortcut.vbs")
        if os.path.exists(vbs_path):
            os.remove(vbs_path)
    except:
        pass

    os._exit(0)


def _set_resolution_via_api(width, height, hz=60):
    """Set resolution via ChangeDisplaySettingsExW targeting the primary monitor
    device by name — same method Windows Display Settings uses internally."""
    DM_PELSWIDTH        = 0x00080000
    DM_PELSHEIGHT       = 0x00100000
    DM_DISPLAYFREQUENCY = 0x00400000

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

    # Get the primary monitor's device name (e.g. "\\.\DISPLAY1")
    # EnumDisplayDevices with iDevNum=0 returns the primary display
    class DISPLAY_DEVICE(ctypes.Structure):
        _fields_ = [
            ("cb",           ctypes.c_ulong),
            ("DeviceName",   ctypes.c_wchar * 32),
            ("DeviceString", ctypes.c_wchar * 128),
            ("StateFlags",   ctypes.c_ulong),
            ("DeviceID",     ctypes.c_wchar * 128),
            ("DeviceKey",    ctypes.c_wchar * 128),
        ]

    dd = DISPLAY_DEVICE()
    dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
    primary_device = None
    DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004
    i = 0
    while ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
        if dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE:
            primary_device = dd.DeviceName
            break
        i += 1

    dm = DEVMODE()
    dm.dmSize             = ctypes.sizeof(DEVMODE)
    dm.dmFields           = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    dm.dmPelsWidth        = width
    dm.dmPelsHeight       = height
    dm.dmDisplayFrequency = hz

    if primary_device:
        # Target the primary monitor specifically — same as Windows Display Settings
        ctypes.windll.user32.ChangeDisplaySettingsExW(
            primary_device, ctypes.byref(dm), None, 1, None  # CDS_UPDATEREGISTRY
        )
    else:
        # Fallback to NULL device (generic primary)
        ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(dm), 1)

    # Broadcast WM_DISPLAYCHANGE so all applications including Valorant
    # are notified of the resolution change — same as Windows Display Settings
    HWND_BROADCAST = 0xFFFF
    WM_DISPLAYCHANGE = 0x007E
    ctypes.windll.user32.SendMessageW(
        HWND_BROADCAST, WM_DISPLAYCHANGE, 32,
        ctypes.c_long(height | (width << 16))
    )


# =================================================================
# 7. MAIN ENTRY
# =================================================================

if __name__ == "__main__":
    if "--launch" in sys.argv:
        # Launcher mode — no elevation needed, monitors already disabled at install time
        launch_stretchy()

    elif "--uninstall-direct" in sys.argv:
        # Elevated uninstall triggered by the setup UI
        import tkinter as tk
        from tkinter import messagebox
        _r = tk.Tk()
        _r.withdraw()
        run_uninstall()
        _r.destroy()
        sys.exit(0)

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
        orig_exe = _get_arg("--exe-path=") or None

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
        run_installation(x, y, perf, log_path=os.path.join(DOCUMENTS_DIR, "debug.log"))
        register_custom_resolution(int(x), int(y))
        check_nvidia_scaling()

        all_ids = [iid for m in selected for iid in m.get("instance_ids", [])]
        if all_ids:
            disable_monitors(all_ids)

        shortcut_ok = create_shortcut(exe_path=orig_exe)

        import tkinter as tk
        from tkinter import messagebox
        _r = tk.Tk()
        _r.withdraw()
        if shortcut_ok:
            messagebox.showinfo("StretchyVal", "Installation complete!\nA shortcut has been added to your Desktop.")
        else:
            messagebox.showwarning("StretchyVal", "Installation complete but the desktop shortcut could not be created.\nYou can run StretchyVal.exe directly with the --launch argument.")
        _r.destroy()
        sys.exit(0)

    else:
        # Setup mode — open window without elevation, monitors list reads fine unprivileged
        root = tk.Tk()
        SetupApp(root)
        root.mainloop()
