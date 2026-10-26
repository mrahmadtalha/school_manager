SCHOOL MANAGER GUARD APP (Android) - how to build the APK
=========================================================
What it is: the gate guard's phone app. It scans the QR code on a student's ID card
and the school computer saves the attendance. Needs no internet - only the school
Wi-Fi (or a phone hotspot) shared with the school computer.

You need: a computer with Android Studio (free) and internet ONCE (to download the
build tools, about 1 GB). Phone: Android 7.0 or newer.

A. Build the APK
1. Open Android Studio -> File -> Open -> choose this folder (android_guard_app).
2. Wait for "Gradle sync" to finish (first time it downloads things; be patient).
   If it asks to trust the project or to use the wrapper/JDK, accept the defaults.
3. Menu: Build -> Build Bundle(s) / APK(s) -> Build APK(s).
4. When it says "APK(s) generated", click "locate". The file is:
   app\build\outputs\apk\debug\app-debug.apk

B. Put it on the guard's phone
1. Copy app-debug.apk to the phone (USB cable, WhatsApp to yourself, Bluetooth...).
2. Open it on the phone. If Android blocks it, allow "Install unknown apps" for the
   app you opened it from (Files / WhatsApp), then install.
   (Or connect the phone with USB debugging on and press the green Run button in Studio.)

C. First use (easy way - nothing to type)
1. On the school computer: School Manager -> Attendance -> "QR Scans" tab ->
   "Guard phone connection".
   Step 1: switch on "Allow guard phones to connect", press Save, then close and
           reopen School Manager once. Run tools\allow_guard_phone_firewall.bat once
           as administrator (right-click -> Run as administrator).
   Step 2: choose the guard account - or press "Create guard account" (one click).
   Step 3: open "Connect a phone with a code": a QR code appears.
2. Phone on the same Wi-Fi (or hotspot) as the computer. Open "School Guard", tap
   "Scan QR to connect", allow the camera, point it at the code on the computer.
   The phone connects and opens the scanner. No address, username or password to type.
3. Point the camera at an ID card. The result covers the screen for a few seconds
   (green = Present, orange = Late, blue = already marked, red = problem).

The phone keeps a connection key (not the password). If the guard account's password is
changed or the account is switched off, the phone is disconnected and shows
"Scan QR to reconnect".

If the computer's Wi-Fi address changes (router gives a new one), the app finds the
computer again by itself. If the phone is not on the same Wi-Fi it shows a "Not connected"
screen and keeps trying every few seconds; it continues by itself as soon as it is back.
A card scanned while "Not connected" is NOT saved - scan it again after reconnecting.

Typing instead (older way, still works): on the first screen tap "Connect by typing the
address instead", type the address shown under "Connect by typing the address instead" on
the QR Scans tab (example http://192.168.100.2:8000), the guard username and password.
"Settings" on the scan screen changes the server or the account.

Troubleshooting
- "Not connected" screen: different Wi-Fi, School Manager closed on the computer, "Allow
  guard phones" not switched on / School Manager not restarted, or the firewall file was
  not run (it opens the connection port and the "find the computer" port).
- "Scan QR to reconnect" appears by itself: the guard's password was changed or the account
  was switched off. Scan a new code from the computer.
- The code on the computer says "expired": press "New code" and scan again (a code works
  for 15 minutes).
- "OLD ID CARD": print the student's ID card again (the old QR is not valid for scanning).
- Gradle sync fails offline: connect the computer to the internet for the first sync.
- Build error you do not understand: copy the red text from the "Build" tab and send it.
