' Floorball Dashboard Launcher
' Startet start.py ohne sichtbares Terminal-Fenster (WindowStyle = 0)

Dim objShell
Set objShell = CreateObject("WScript.Shell")
objShell.Run "python """ & Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\")) & "start.py""", 0, False
Set objShell = Nothing
