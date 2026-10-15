# Pyco for Android

This project packages the existing `../pyco_web` UI in a native Android app and
runs calculations with CPython 3.13 through Chaquopy. Pyco itself is bundled in
the APK, so normal use is offline. The only runtime network request made by the
app is an optional HTTPS customization script configured through **File > Load
Customizations**.

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
bundling them in the APK for fully offline runtime use. Building therefore
requires network access to download Pyco.
