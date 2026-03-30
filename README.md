<h1>
  <img src="https://raw.githubusercontent.com/itzbnny/StretchyVal/main/redyellow.ico" alt="logo" width="55" height="55" style="vertical-align:middle; margin-right:10px;">
  StretchyVal
</h1>

*THIS WAS VIBE CODED AS A CHALLANGE TO PROVE AI CAN"T REPLACE HUMAN CODERS SO PLEASE DON'T JUDGE TOO HARD (getting a working product and forcing it to fix bugs itself is harder then you think, I was frustratingly hands off the code for the most part) I dont know whether to be happy or sad it works* I work with java not python cause I make minecraft mods lol, but thank you for your support and understanding, and if you would like to support the further develoment of this tool and other like it feel free to check out my Ko-Fi and Discord.
Donations are welcome and very appreciated but not required   
https://ko-fi.com/itzbnny      
https://discord.gg/VMSSNYPh8m

A lightweight Windows utility that automates stretched resolution for Valorant. It patches the game config, applies your chosen resolution before launch, and restores your native resolution automatically when you close the game — no manual steps required.

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

[Download Latest Release](https://github.com/itzbnny/StretchyVal/releases/tag/StretchyValV1.01)


If you have an AMD GPU [click here](#amd-gpus) and follow those steps first, then resume setup.

1. Run Valorant vanilla first if you haven't so your configs are created
2. IF YOU HAVE MULTIPLE ACCOUNTS MAKE SURE RIOT CLIENT IS OPEN AND LOGGED IN BEFORE LAUNCHING STRETCHYVAL
3. Run `StretchyVal.exe` (or `StretchyVal.py` if using source)
4. Enter your desired stretch resolution width and height (default: 1440x1080)
5. Check or uncheck **Apply Performance Upgrade** depending on your preference
6. Under **Disable these monitors before launching Valorant**, check the monitor(s) you want disabled (unless you have two pcs connected for streaming or recording you should select them all) — this is what allows the stretch to work without Valorant overriding it
7. Click **Install & Apply** and accept the UAC prompt
8. Done — a shortcut called **StretchyVal** will appear on your desktop. You can use this to open Valorant from now on (I don't even have the official shortcut on my desktop anymore), and if you want to revert the settings, just renable your monitors in device manager and launch Valorant from the official launcher, from there you can edit your settngs like vanilla.


From now on, just double-click the shortcut instead of launching Valorant directly.


If you want to change resolutions delete the shortcut, open valorant through the official launcher and redo step 1, and finally redo the install launcher setup process


## AMD GPUS
DO BOTH STEPS BEFORE STRETCHYVAL SETUP

AMD — Adding a Custom Resolution:

Right-click the desktop → AMD Software: Adrenalin Edition
Click the Display tab at the top
Scroll down and click Custom Resolutions
Click + Create New
Enter your desired Width (e.g. 1440) and Height (e.g. 1080)
Leave refresh rate at your monitor's native rate
Click Save — the screen will briefly go black to test it
If compatible, it saves as a preset under Custom Resolutions
Now you can input that resolution into the StretchyVal Setup Launcher

AMD — GPU Scaling (to prevent black bars):

In AMD Software, go to the Display tab
Find GPU Scaling and toggle it On
Set Scaling Mode to Full Panel
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

---

## Credits

Built to solve a real problem. Monitors are disabled using `pnputil.exe`, a Microsoft-signed tool built into Windows. Resolution switching uses `SetScreenResolution.exe` by [4r5t6y7](https://github.com/4r5t6y7/SetScreenResolution) or equivalent. Logo by u/Odeuo https://www.reddit.com/user/Odeuo/.
