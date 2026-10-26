@echo off
REM School Manager - let the guard's phone reach this computer (run ONCE as Administrator).
REM Right-click this file -> "Run as administrator".
REM
REM The default School Manager port is 8000. If you changed it, type the same number below.

set PORT=8000
set /p PORT=Port number [8000]: 

netsh advfirewall firewall delete rule name="School Manager Guard App" >nul 2>&1
netsh advfirewall firewall add rule name="School Manager Guard App" dir=in action=allow protocol=TCP localport=%PORT% profile=any

REM Lets the phone FIND the computer by itself when the computer's Wi-Fi address changes.
netsh advfirewall firewall delete rule name="School Manager Guard App (find computer)" >nul 2>&1
netsh advfirewall firewall add rule name="School Manager Guard App (find computer)" dir=in action=allow protocol=UDP localport=50555 profile=any

if %errorlevel%==0 (
    echo.
    echo Done. Port %PORT% is now open for the guard phone on your Wi-Fi / hotspot.
) else (
    echo.
    echo FAILED. Close this window, right-click the file and choose "Run as administrator".
)
pause
