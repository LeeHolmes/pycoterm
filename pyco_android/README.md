# Pyco for Android

This project packages the existing `../pyco_web` UI in a native Android app and
runs calculations with CPython 3.13 through Chaquopy. Pyco itself is bundled in
the APK, so calculations work offline. At startup, a background check compares
the installed `pyco.py` with the canonical GitHub version without blocking the
calculator. If an update is available, the status reads **pyco - update available**
and **File > Update pyco** downloads it to private app storage. After a successful
download, the app automatically restarts to load the new code. This resets the
current calculator session, including variables and console history; saved
settings and customizations are preserved. A separate, non-exported restart
activity replaces the entire Python process rather than reusing cached modules.
Failed checks and downloads are reported in the console, and a failed download
does not replace the installed copy. The app also supports an optional HTTPS
customization script through **File > Load Customizations**.

Open this directory in Android Studio, install Android SDK 36, and build the
`app` module. Chaquopy 17.1 requires API 24 or newer and builds 64-bit ARM and
x86 emulator packages.

The `app` module declares `../pyco_web` as an Android asset source directory.
Do not copy web assets into this project: changes to the web UI are picked up
automatically on the next Android build.

The build downloads the current `pyco.py` and README from the canonical Pyco
repository into Gradle-generated source and asset directories. It also copies
the shared `../markdown_renderer.py` into generated Python sources. These files
are not maintained under `app/src/main`, preventing source drift while still
bundling them in the APK for offline runtime use. A source asset is also bundled
for update comparisons. Downloaded updates take precedence over the bundled
module on subsequent process starts. Building requires network access to
download Pyco.

The update loader and native UI regression tests run without an Android device.
From the repository root, run:

```text
python -m unittest discover -s pyco_android/tests -v
node --test pyco_android/tests/android_updates.test.cjs
```
