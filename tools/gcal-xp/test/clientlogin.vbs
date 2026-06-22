' clientlogin.vbs - prove the Schannel ClientLogin path with the real XP WinINet
' stack (MSXML2.XMLHTTP wraps WinINet, the same stack gcal.exe uses). Exercises:
'   (1) WinINet opens TLS to https://www.google.com (-> 127.0.0.1 via hosts),
'   (2) the gcalsrv Schannel server handshake with a period client,
'   (3) cert trust (a cert error would surface as an Err here),
'   (4) the ClientLogin POST -> "Auth=..." reply.
' Run on XP:  cscript //nologo C:\gcal-xp\clientlogin.vbs
On Error Resume Next
Dim h, url
url = "https://www.google.com/accounts/ClientLogin"
Set h = CreateObject("MSXML2.XMLHTTP")
h.open "POST", url, False
h.setRequestHeader "Content-Type", "application/x-www-form-urlencoded"
h.send "Email=test@example.com&Passwd=secret&service=cl&source=sygnas-test"
If Err.Number <> 0 Then
  WScript.Echo "ERR=" & Err.Number & " hex=" & Hex(Err.Number) & " : " & Err.Description
Else
  WScript.Echo "STATUS=" & h.status & " " & h.statusText
  WScript.Echo "BODY=" & h.responseText
End If
