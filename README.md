<h1>
  <img src="https://raw.githubusercontent.com/itzbnny/StretchyVal/main/redyellow.ico" alt="logo" width="55" height="55" style="vertical-align:middle; margin-right:10px;">
  StretchyVal
</h1>

Donations are welcome and very appreciated but not required   
Ko-Fi - https://ko-fi.com/itzbnny      
Discord - https://discord.gg/VMSSNYPh8m

# StretchyVal

The best Valorant True Stretched Resolution tool for NVIDIA and AMD. Get true stretched res in 2026 without input lag in ONE CLICK.

---
Yes this was vibe coded, get over it.

---


## What It Does

- Sets a custom stretched resolution (e.g. 1440x1080) in Valorant's config files before the game launches
- Optionally applies a performance-focused `GameUserSettings.ini` template that disables shadows, reduces input latency settings, and enables multithreaded rendering
- Disables selected monitors in Device Manager before Valorant starts, preventing the game from hard-locking to your monitor's native 16:9 aspect ratio
- Restores your native desktop resolution automatically within a few seconds of closing Valorant
- Creates a desktop shortcut so the whole process is one double-click

---

## Requirements

- Windows 10 or 11
- Python 3.10+ (if running from source)
- Valorant installed via the Riot Client
- `SetScreenResolution.exe` placed in the same folder as `StretchyVal.exe` (or the script)

---


## Setup

[Download Latest Release](https://github.com/itzbnny/StretchyVal/releases/tag/StretchyVal1.2)


If you have an AMD GPU [click here](#amd-gpus) and follow those steps first, then resume setup.

- Run Valorant vanilla first if you haven't so your configs are created
- IF YOU HAVE MULTIPLE ACCOUNTS MAKE SURE RIOT CLIENT IS OPEN AND LOGGED IN BEFORE LAUNCHING STRETCHYVAL
- Run `StretchyVal.exe` (or `StretchyVal.py` if using source)
- Select desired resolution from drop down
- Check or uncheck **Apply Performance Upgrade** depending on your preference
- Under **Disable these monitors before launching Valorant**, check the monitor(s) you want disabled (unless you have two pcs connected for streaming or recording you should select them all) — this is what allows the stretch to work without Valorant overriding it
- Click **Install & Apply** and accept the UAC prompt
- Done — a shortcut called **StretchyVal** will appear on your desktop. You can use this to open Valorant from now on (I don't even have the official shortcut on my desktop anymore), and if you want to revert the settings, just renable your monitors in device manager and launch Valorant from the official launcher, from there you can edit your settngs like vanilla.


From now on, just double-click the shortcut instead of launching Valorant directly.


*If you want to change resolutions restart the setup launcher, click unistall, start the setup launcher again and select you desired resolution, and finally complete the setup as usual.*

*If you want to stop playing stretched open the setup launcher, select uninstall, then launch valorant and adjust your video settings as usual, valorant should behave as normal*

## AMD GPUS

AMD — GPU Scaling (to prevent black bars):

- In AMD Software, go to the Display tab
Find GPU Scaling and toggle it On

- Set Scaling Mode to Full Panel
Click Apply

---

## How the Monitor Disabling Works

Valorant detects your connected monitors on launch and uses their native aspect ratio to lock display settings. By temporarily disabling the monitor(s) in Device Manager before the game starts, Valorant cannot read the native aspect ratio and will respect the resolution set in the config file instead.

> **Important:** The monitors are disabled at install time and stay disabled while you use the launcher. Disabling a monitor in Device Manager does **not** affect your ability to see or use your screen — it only hides the device from software that queries it. You will not notice any visual difference.

> **If you stop using StretchyVal or uninstall it**, you need to manually re-enable your monitors in Device Manager:
> 1. Right-click the Start button → **Device Manager**
> 2. Expand the **Monitors** section
> 3. Right-click each disabled monitor → **Enable device**

---

## Performance Upgrade (Optional)

When enabled, the tool writes a custom `GameUserSettings.ini` with the following applied:

- All quality settings set to minimum (shadows, textures, effects, foliage, etc.)
- Multithreaded rendering enabled
- Mouse smoothing and acceleration disabled
- Frame rate smoothing disabled
- Low-latency sync settings

This is aimed at maximising frame rate and input responsiveness on competitive settings. If you prefer to manage your in-game settings manually, uncheck this option during setup.

---

## Resolution Restore

StretchyVal monitors the Valorant process in the background after launch. When both `VALORANT.exe` and `VALORANT-Win64-Shipping.exe` are no longer running, it automatically restores your native desktop resolution within a few seconds.

You do not need to keep any window open. The background process exits on its own after restoring.

---

## Building from Source

```bash
pip install pyinstaller pywin32
pyinstaller --onefile --noconsole --icon=redyellow.ico --add-data "SetScreenResolution.exe;." --add-data "redyellow.ico;." StretchyVal.py
```

The output will be in the `dist/` folder.

---

## Transparency & Security

This tool makes the following changes to your system:

- Saves native resolution data to `Documents\StretchyVal\native_res.json`
- Modifies `GameUserSettings.ini` inside your Valorant local app data folder
- Disables selected monitor devices via `pnputil.exe` (built into Windows)
- Creates a desktop shortcut

No data is collected, transmitted, or stored outside your local machine. The full source code is available in this repository for review.

---

## Known Limitations

- Only tested with Valorant. Not designed for other games.
- Monitor re-enable after uninstall is a manual step (see above)
- Custom Resolutions don't currently work (I WAS working on it but reddit users couldn't help but bully me for using ai, so I will only resume when I see an actual interest in me resuming from the community, you can get incontact with me through discord)

---

## Credits

Built to solve a real problem. Monitors are disabled using `pnputil.exe`, a Microsoft-signed tool built into Windows. Resolution switching uses `SetScreenResolution.exe` by [gurnec](https://github.com/gurnec/SetScreenResolution) or equivalent. Logo by u/Odeuo https://www.reddit.com/user/Odeuo/.
