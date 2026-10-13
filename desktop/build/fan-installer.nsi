Unicode true
!include "FileFunc.nsh"
!ifndef VERSION
!error "VERSION required"
!endif
Name "表情包一键制作"
OutFile "${ROOT}\release\sticker-maker-win-v${VERSION}-setup.exe"
Icon "${ROOT}\build\icon.ico"
RequestExecutionLevel user
SilentInstall normal
SetCompressor /SOLID lzma
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "表情包一键制作"
VIAddVersionKey "FileDescription" "表情包一键制作安装程序"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "捞鱼工作室"
Function .onInit
 InitPluginsDir
 SetOutPath "$PLUGINSDIR"
 File /oname=backend.exe "${ROOT}\release\sticker-maker-win-v${VERSION}-backend.exe"
 File "${ROOT}\build\installer\installer-ui.ps1"
 File "${ROOT}\build\installer\icon.png"
 IfSilent silent interactive
 silent:
  ${GetParameters} $R0
  ExecWait '$\"$PLUGINSDIR\backend.exe$\" $R0' $R1
  SetErrorLevel $R1
  Goto done
 interactive:
  ExecWait '$\"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe$\" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File $\"$PLUGINSDIR\installer-ui.ps1$\" -InstallerPath $\"$PLUGINSDIR\backend.exe$\" -Version $\"${VERSION}$\" -PayloadBytes ${PAYLOAD_BYTES}' $R1
  SetErrorLevel $R1
 done:
 Quit
FunctionEnd
Section
SectionEnd
