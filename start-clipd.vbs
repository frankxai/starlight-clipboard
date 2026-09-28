Option Explicit
Dim sh, script, fso
Set fso = CreateObject("Scripting.FileSystemObject")
script = fso.GetParentFolderName(WScript.ScriptFullName) & "\clip.py"
If Not fso.FileExists(script) Then WScript.Quit 1
Set sh = CreateObject("WScript.Shell")
sh.Run "pythonw.exe """ & script & """ watch", 0, False
