# React Native (Expo) project template

This dev-boost stack provisions everything you need to build a React Native app
for Android with Expo — no globally-installed `expo-cli` (it is deprecated; use
`npx` instead).

## What the stack provides

- **Node / pnpm / bun** — via the `web-runtimes` module (mise-managed, shared global).
- **JDK 17 (Temurin)** — `mise use -g java@temurin-17`. React Native's validated JDK.
- **Android SDK** — `commandlinetools` unzipped to `$ANDROID_HOME/cmdline-tools/latest/`
  (default `$ANDROID_HOME=$HOME/Android/Sdk`), then:
  - `platform-tools`
  - `platforms;android-35` (Android **API 35**)
  - `build-tools;36.0.0`
  - `cmdline-tools;latest`
  - licenses accepted unattended (`yes | sdkmanager --licenses`).

> **Note:** React Native on Android requires **JDK 17** and **Android API 35**.
> Metro uses inotify on Linux (watchman is intentionally not installed); if you
> watch large trees you may need to raise `fs.inotify.max_user_watches`.

## Create a new app

```sh
npx create-expo-app@latest my-app
cd my-app
```

## Run on Android

For most development, the managed Expo workflow is enough:

```sh
npx expo start            # Metro bundler; open in Expo Go or a dev client
```

When you need native modules / a custom dev client, generate the native
Android project and build it:

```sh
npx expo prebuild         # generate the native android/ (+ ios/) projects
npx expo run:android      # build & install the debug APK on a device/emulator
```

## Editor config

`.fresh/config.json` ships with `tab_size: 2` to match the JS/TS ecosystem
conventions. Copy it into your project root (it merges with fresh's base config).
