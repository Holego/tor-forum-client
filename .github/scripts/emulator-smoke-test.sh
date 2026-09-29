#!/usr/bin/env bash
# Install the APK on the running emulator, launch it and wait until the Tor built into the
# app reports it has fully bootstrapped (TorController logs every bootstrap phase as "FletTor").
set -euo pipefail

apk="$1"
aapt2="$(ls "$ANDROID_HOME"/build-tools/*/aapt2 | sort -V | tail -1)"
package="$("$aapt2" dump packagename "$apk")"
echo "Installing $package"
adb install -r "$apk"
adb logcat -c
adb shell monkey -p "$package" -c android.intent.category.LAUNCHER 1

for _ in $(seq 1 72); do  # up to 6 minutes
    sleep 5
    tor_log="$(adb logcat -d -s FletTor:I)"
    if grep -q "PROGRESS=100" <<<"$tor_log"; then
        echo "Tor bootstrapped inside the app:"
        grep "Bootstrap\|Connecting\|launching" <<<"$tor_log" | tail -25
        exit 0
    fi
    if adb logcat -d | grep -q -E "FATAL EXCEPTION|Could not start Tor"; then
        break
    fi
done

echo "::error::Tor did not bootstrap in the app"
adb logcat -d | grep -E "FletTor|TorService|Tor|flutter|python|AndroidRuntime" | tail -300
exit 1
