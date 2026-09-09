Set shell = CreateObject("WScript.Shell")

projectPath = "C:\Users\Mona\Desktop\codes and program\ecobin_2"
pythonw = projectPath & "\.venv\Scripts\pythonw.exe"

shell.CurrentDirectory = projectPath

' Start Flask AI server
shell.Run """" & pythonw & """ """ & projectPath & "\ecobin_server.py""", 0, False

' Wait for Flask server to start
WScript.Sleep 5000

' Start laptop camera
shell.Run """" & pythonw & """ """ & projectPath & "\camera_ecobin.py""", 1, False