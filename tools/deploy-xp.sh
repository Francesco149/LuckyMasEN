#!/usr/bin/env bash
# deploy-xp.sh — deploy + drive the LuckyMas patched build on the real XP Time Machine.
#
# Encodes the hard-won recipe so it isn't rediscovered each session:
#  * XP is SMBv1-only  -> smbclient MUST force NT1 (-m NT1 --option='client min protocol=NT1'),
#    or the dialect negotiation just times out.
#  * Admin password is BLANK:  smbclient -U 'Administrator%'   /   netexec -u Administrator -p ''
#  * TWO exec paths — pick the right one:
#      agent()   = curl http://<ip>:8099/run  -> the INTERACTIVE Administrator session.
#                  Reliable stdout, sees the GUI. Use for GUI launch, screenshots, quick cmds,
#                  and anything that must run on the owner's desktop (the cert modal).
#      smbexec() = netexec -x  -> SYSTEM / session-0, BLIND to the GUI; output can be flaky
#                  (it reads back a temp file and sometimes returns stale content). SYSTEM only.
#  * Can't overwrite a RUNNING exe (NT_STATUS_SHARING_VIOLATION) -> kill + del via agent() first.
#  * Editing hosts via chained cmd redirection is unreliable -> pull / filter / push the file.
#  * The mascot is a per-pixel-alpha LAYERED window -> screenshot via PrtScn->clipboard, never BitBlt.
#  * gcalsrv installs its self-signed Root cert on first run -> a protected-root MODAL pops in the
#    interactive session; the owner clicks Yes once (XP has no certutil for a silent install).
#  * Launch.exe needs cwd=C:\lm (it LoadLibrary's gcalcore.dll by name) -> `cd /d C:\lm` before launch.
#
# Usage:  tools/deploy-xp.sh <cmd>        (override XP_IP / AGENT_KEY via env)
#   probe          box state (ping, install path, hosts, C:\lm, gcalsrv)
#   launcher       clone the install -> C:\lm, overlay out/patched launcher + a test Launch.ini
#   server         (re)deploy gcalsrv.exe + clientlogin.vbs + cert; start it (interactive; MODAL!)
#   hosts-off|on   remove / restore the www.google.com redirect (backup kept as hosts.lmbak on XP)
#   clientlogin    headless TLS ClientLogin to https://localhost  (expect STATUS=200, Auth=)
#   launch         start C:\lm\Launch.exe on the desktop (GUI)
#   shot [name]    PrtScn screenshot -> fetch to ./<name>.png
#   all            launcher + hosts-off + server ; then run `launch` and click the cert modal
set -euo pipefail
XP_IP="${XP_IP:-10.0.10.113}"
AGENT_KEY="${AGENT_KEY:-rmprobe2026}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SHARE="//$XP_IP/C\$"
SMBU='Administrator%'
ETC='\WINDOWS\system32\drivers\etc'

agent()  { curl -s -G "http://$XP_IP:8099/run" --data-urlencode "k=$AGENT_KEY" --data-urlencode "c=$1"; echo; }
smbexec(){ nix run nixpkgs#netexec -- smb "$XP_IP" -u Administrator -p '' -x "$1" 2>&1 \
             | grep -vE 'aiosmb|Initializing SMB|protocol database' | sed 's/^SMB .*TIMEMACHINE-XP *//'; }
smb()    { nix shell nixpkgs#samba -c smbclient "$SHARE" -U "$SMBU" \
             -m NT1 --option='client min protocol=NT1' -c "$1"; }

case "${1:-}" in
probe)
  curl -s -m3 "http://$XP_IP:8099/ping" && echo " (agent up @ $XP_IP)"
  agent 'for /d %i in ("C:\Program Files\SYGNAS\*") do @echo INSTALL=%~si & if exist C:\lm (echo LM=yes) else (echo LM=no) & if exist C:\gcal-xp\gcalsrv.exe (echo SRV=deployed) else (echo SRV=no) & tasklist /fi "imagename eq gcalsrv.exe" | findstr gcalsrv & echo --hosts-- & type C:\WINDOWS\system32\drivers\etc\hosts | findstr /r "[0-9][0-9]*\."'
  ;;

launcher)
  echo ">>> clone install -> C:\\lm (short path dodges the JP dir name)"
  smbexec 'rd /s /q C:\lm 2>nul & for /d %i in ("C:\Program Files\SYGNAS\*") do xcopy "%~si\launcher" C:\lm\ /E /I /Y >nul & echo CLONED'
  echo ">>> overlay the patched launcher (localhost binaries + EN .Xvi) + a test Launch.ini"
  stage="$(mktemp -d)"
  cp "$REPO"/out/patched/app/launcher/gcalcore.dll "$REPO"/out/patched/app/launcher/gcal.exe \
     "$REPO"/out/patched/app/launcher/*.Xvi "$stage/"
  printf '%s\r\n' \
    '[Window]' 'X=480' 'Y=140' 'TopMost=1' \
    '[Data]' 'Chara=hiyori.Xvi' 'Folder=C:\lm' \
    '[Calendar]' 'Boot=1' '[Mail]' 'Boot=0' \
    '[Launch]' \
    'Exec000=C:\lm\calc\WinCalcImas.exe'   'Title000=iM@S Calculator' \
    'Exec001=C:\lm\calc\WinCalcLucky.exe'  'Title001=Lucky Star Calculator' \
    'Exec002=C:\lm\gcal.exe'               'Title002=Google Calendar' \
    'Exec003=C:\lm\copy\MinkIt.exe'        'Title003=Copy Animation' \
    'Exec004=C:\lm\wallpaper.html'         'Title004=Wallpaper Picker' \
    'Exec009=C:\WINDOWS\system32\desk.cpl' 'Title009=Display Properties' \
    > "$stage/Launch.ini"
  smb "prompt OFF; lcd $stage; cd \\lm; mput *"
  rm -rf "$stage"
  ;;

server)
  echo ">>> kill + delete any running gcalsrv (avoids SHARING_VIOLATION on overwrite)"
  agent 'taskkill /f /im gcalsrv.exe 2>nul & del /f /q C:\gcal-xp\gcalsrv.exe 2>nul & echo CLEARED'
  smbexec 'mkdir C:\gcal-xp 2>nul & echo OK'
  echo ">>> push gcalsrv.exe + clientlogin.vbs + cert"
  stage="$(mktemp -d)"
  cp "$REPO"/tools/gcal-xp/gcalsrv.exe "$REPO"/tools/gcal-xp/test/clientlogin.vbs \
     "$REPO"/tools/gcal-emu/certs/xp-google.der "$stage/"
  smb "prompt OFF; lcd $stage; cd \\gcal-xp; mput *"
  rm -rf "$stage"
  echo ">>> start gcalsrv INTERACTIVELY (so the cert modal can be clicked)"
  agent 'C:\probe\nircmd.exe exec show C:\gcal-xp\gcalsrv.exe & echo STARTED'
  echo ">>> NOW click YES on the protected-root cert dialog on the XP desktop."
  ;;

hosts-off)
  tmp="$(mktemp -d)"
  smb "cd $ETC; lcd $tmp; get hosts hosts.cur"
  grep -vi 'www.google.com' "$tmp/hosts.cur" > "$tmp/hosts.new"
  smb "cd $ETC; lcd $tmp; prompt OFF; put hosts.cur hosts.lmbak; put hosts.new hosts"
  rm -rf "$tmp"; echo "removed the www.google.com redirect (backup: $ETC\\hosts.lmbak)"
  ;;

hosts-on)
  smb "cd $ETC; prompt OFF; get hosts.lmbak /tmp/hosts.restore && put /tmp/hosts.restore hosts" \
    && echo "restored hosts from hosts.lmbak"
  ;;

clientlogin)
  agent 'cscript //nologo C:\gcal-xp\clientlogin.vbs'
  ;;

launch)
  agent 'cd /d C:\lm & C:\probe\nircmd.exe exec show C:\lm\Launch.exe & echo LAUNCHED'
  ;;

shot)
  name="${2:-shot}"
  agent 'C:\probe\nircmd.exe sendkeypress 0x2c'; sleep 1
  agent 'C:\probe\nircmd.exe clipboard saveimage C:\gcal-xp\shot.png'; sleep 1
  smb "cd \\gcal-xp; lcd $(pwd); get shot.png $name.png"
  echo "saved ./$name.png"
  ;;

all)
  "$0" launcher; "$0" hosts-off; "$0" server
  echo ">>> after clicking the cert modal, run:  $0 clientlogin   then   $0 launch"
  ;;

*)
  sed -n '2,40p' "$0"; exit 2
  ;;
esac
