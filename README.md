# Exvius Offline

**Play Final Fantasy Brave Exvius offline on Android.**

**[Download the APK (74 MB)](https://github.com/Elvlin/exvius-offline/releases/download/v0.1.23/exvius-offline-v0.1.23.apk)**

This is a fan project built from the original Global game. Download the game data once, then play it offline.

Replay stages to farm Lapis, pick the summon banner you want, and revisit events you want

This project is still being worked on. It is unofficial and is not affiliated with Square Enix or gumi.

[What changed in v0.1.23](release/notes-v0.1.23.md)

## Screenshots

| Home | Choose a summon season | Choose an event season |
| :---: | :---: | :---: |
| ![Home screen](release/screenshots/home.png) | ![Summon dropdown showing Standard, Seasons 1 to 4 and Collab](release/screenshots/summon-seasons.png) | ![Vortex dropdown showing All Events, Permanent, Seasons 1 to 4, Collab and Other Events](release/screenshots/vortex-seasons.png) |

## What changed from the online game?

### You can farm Lapis by replaying stages.

Quest objectives that award Lapis can pay out again when you replay the stage and meet those objectives again. For example, if a quest gives Lapis for clearing it without using an item, you can earn that Lapis again on another successful run.

Other first-clear rewards, such as equipment, units and tickets, stay one-time. Normal battle drops still work as usual. This gives you a way to keep earning Lapis for summons without a cash shop.

### You choose which summon banners you want.

The dropdown at the top of **Summon** lets you pick **Standard, Season 1, Season 2, Season 3, Season 4 or Collab**. Choose a group, then use the Rare Summon, Standard Summon and Limited Time tabs to find its banners.

Seasons group banners by when they came out. Collab groups crossover banners by series.

Banner prices, featured units, tickets, step-ups and guarantees are kept where their original details are known. Some missing campaign details use replacements. You can check the current pool and rates through the banner's **Drop Rates** button.

### Events are always available

Open **Vortex** and use **Filter** to choose **All Events, Permanent, Season 1, Season 2, Season 3, Season 4, Collab or Other Events**. 
The summon dropdown and Vortex filter are separate. You can browse one season's summons and another season's events on the same save.

### Raids are adjusted for solo play

The shared raid progress is adjusted for one player. The original bosses, battle stats and personal point reward targets are kept; this change is to the shared progress, rather than a blanket reduction in enemy difficulty.

### Former cash bundles cost Lapis

Bundles that used to cost real money are bought with Lapis. There is also a **2,000 Friend Points** bundle for **100 Lapis**.

Daily login rewards use your local save and date.


## Install

1. [Download the APK](https://github.com/Elvlin/exvius-offline/releases/download/v0.1.23/exvius-offline-v0.1.23.apk) from the [release page](https://github.com/Elvlin/exvius-offline/releases/tag/v0.1.23).
2. Install it on an **Android 7.0 or newer phone with 64-bit ARM support**.
3. Open it with an internet connection. The app downloads all the game data automatically, about **14.5 GB**. Allow about **18 GB of free space** for setup.
4. Once setup is done, you can play offline.

If the download stops, reopen the app to continue. You do not have to choose or download chapters separately.

To update, install the newer APK over the existing app. **Uninstalling the app can erase your save.**

## Play on an Apple silicon Mac

You can run the Android APK in a persistent Android 13 virtual phone. This setup uses
Homebrew, Python 3.9 or newer, and the official Android tools; it does not rebuild the APK.
Allow **40 GiB free on your Mac** for Android, the game data, and working space.

From this repository, run the one-time setup:

```sh
python3 source/exvius/macos_emulator.py setup
```

Setup installs ARM64 OpenJDK 25 and Android command-line tools through Homebrew,
accepts the required Android SDK licenses, and creates `Exvius_Offline_API_33` with
4 CPU cores, 4 GB RAM, and 32 GiB internal storage. It downloads the APK described by
`release/app.json`, verifies its size and SHA-256, and installs it into that device.
Install [Homebrew](https://brew.sh) first if it is not already installed.

Then double-click **`Play Exvius.command`** in Finder, or run:

```sh
python3 source/exvius/macos_emulator.py launch
```

Keep the Mac awake and online while the app completes its approximately **14.65 GB**
first-run download. The app resumes interrupted downloads when reopened. Once the
game opens, you can play offline. Closing the launcher terminal leaves the emulator
running; close the emulator window or use the stop command below to shut it down.

```sh
python3 source/exvius/macos_emulator.py doctor  # inspect without changing anything
python3 source/exvius/macos_emulator.py stop    # stop only the Exvius virtual phone
```

The scripts work without changes to your shell configuration. SDK packages live in
`~/Library/Android/sdk` (override with `--sdk-root PATH` on each command). The virtual
phone and its saves live in `~/.android/avd/Exvius_Offline_API_33.avd`, or under your
existing `ANDROID_AVD_HOME`. Verified APKs are cached in
`~/Library/Caches/exvius-offline/emulator`. Startup logs are in
`~/Library/Logs/Exvius Offline/emulator.log`.

**Keep the AVD and its userdata to keep your save.** Setup safely reuses the existing
device and installs updates over the app; daily launching never reinstalls it. An
already-installed newer version is retained. Do not uninstall the app, clear its
storage, delete the AVD, or use Android's Wipe Data action. To back up the whole
virtual phone, stop it first and copy its `.avd` directory and matching `.ini` file
from `~/.android/avd` (or your configured AVD directory).

If startup fails, inspect the log and rerun `doctor`. Fix missing tools with `setup`.
A signing mismatch needs the correctly signed APK, not an uninstall. An incompatible
existing AVD is left untouched. The launcher waits up to five minutes for Android
and uses cold boots with persistent userdata, avoiding large Quick Boot snapshots.
Intel Macs and importing existing phone saves are outside this helper's scope.

## Play through a browser on your home network

The Mac can stream its existing Android game to Chrome/Edge or Safari, including
iPhone and iPad, while keeping the same Android installation and save.

After the Android setup above, run:

```sh
python3 source/exvius/macos_emulator.py setup-browser --lan
python3 source/exvius/macos_emulator.py browser --lan
```

Subsequent launches can use **Play Exvius in Browser.command**. The terminal prints
the LAN URL and access code. Other devices need a one-time local certificate trust
step; see [browser setup, controls, and troubleshooting](source/browser_bridge/README.md).
One player can connect at a time. Keep the Mac awake and the launcher terminal open.
Disconnecting preserves Android and its save; Ctrl+C stops streaming.

## Updates and offline play

When you open the app online, it checks GitHub for updates. If there is nothing new, it uses the files already on your phone. If you are offline, it skips the check and uses your downloaded data.

Changed data downloads in the background and is installed after you close and reopen the app. Existing data is reused across app updates.

## Still being worked on

Some advanced upgrades and event interactions still need fixes. Loading can also be slow on some devices. 
Restored text, artwork and events may have mistakes, so please report anything you find.
To report a problem, [open an issue](https://github.com/Elvlin/exvius-offline/issues). Tell me which screen or quest you were on, what you tried and what happened. A screenshot helps.

## Support or get in touch

If you would like to support the project, you can find me on [Ko-fi](https://ko-fi.com/elvlin) or [Patreon](https://www.patreon.com/c/ElvlinGame).

You can also contact me there if you have a project request or an idea you want to discuss. 

## Files in this repository

- [source/](source/): the code and build instructions.
- [release/](release/): the APK, screenshots and release notes.
- [data/](data/): information about the downloadable game data.

The APK is in the release folder. The large game data packs are in GitHub Releases and download automatically when you first open the app.

## Credits

Final Fantasy Brave Exvius and its original characters, artwork, music and other game content belong to their respective owners, including Square Enix and gumi. This is an unofficial fan project.
