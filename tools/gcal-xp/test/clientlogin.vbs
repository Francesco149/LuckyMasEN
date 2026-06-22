' clientlogin.vbs - prove the Schannel ClientLogin path with the real XP WinINet
' stack (MSXML2.XMLHTTP wraps WinINet, the same stack gcal.exe uses). Exercises:
'   (1) WinINet opens TLS to https://<host>/accounts/ClientLogin,
'   (2) the gcalsrv Schannel server handshake with a period client,
'   (3) cert trust + name match (a cert error surfaces as an Err here),
'   (4) the ClientLogin POST -> "Auth=..." reply.
'
' Default host is "localhost" — the deliverable byte-patches gcalcore.dll/gcal.exe so the
' client connects to localhost (no hosts redirect; the cert is CN=localhost). Pass a host
' to test the legacy hosts-redirect path instead:
'   cscript //nologo C:\gcal-xp\clientlogin.vbs              ' -> https://localhost/...
'   cscript //nologo C:\gcal-xp\clientlogin.vbs www.google.com
On Error Resume Next
Dim h, url, host
host = "localhost"
If WScript.Arguments.Count > 0 Then host = WScript.Arguments(0)
url = "https://" & host & "/accounts/ClientLogin"
Set h = CreateObject("MSXML2.XMLHTTP")
h.open "POST", url, False
h.setRequestHeader "Content-Type", "application/x-www-form-urlencoded"
h.send "Email=test@example.com&Passwd=secret&service=cl&source=sygnas-test"
If Err.Number <> 0 Then
  WScript.Echo "URL=" & url
  WScript.Echo "ERR=" & Err.Number & " hex=" & Hex(Err.Number) & " : " & Err.Description
Else
  WScript.Echo "URL=" & url
  WScript.Echo "STATUS=" & h.status & " " & h.statusText
  WScript.Echo "BODY=" & h.responseText
End If
