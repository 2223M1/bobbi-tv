; SPDX-License-Identifier: GPL-2.0-or-later
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!ifndef HOST_STAGE
  !error "A verified frozen HOST_STAGE is required"
!endif
!ifndef OUTPUT
  !error "OUTPUT is required"
!endif
!define VERSION "0.2.0-private.1"
!ifndef BUILD_SEQUENCE
  !define BUILD_SEQUENCE "2026101901"
!endif
!define INSTALLKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\bobbiTV-${VERSION}-${BUILD_SEQUENCE}"
Var LifecycleGuard
Name "bobbi TV ${VERSION}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\bobbi TV\${VERSION}-${BUILD_SEQUENCE}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${HOST_STAGE}\host\LICENSE.md"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "This candidate requires 64-bit Windows 10 or later."
    Abort
  ${EndIf}
FunctionEnd

Function un.onInit
  CreateDirectory "$LOCALAPPDATA\bobbi TV\profile"
  System::Call 'kernel32::CreateFileW(w "$LOCALAPPDATA\bobbi TV\profile\host-lifecycle.lock", i 0xC0000000, i 0, p 0, i 4, i 0x80, p 0) p .r0'
  StrCpy $LifecycleGuard $0
  ${If} $LifecycleGuard == -1
    MessageBox MB_ICONSTOP "Close bobbi TV before uninstalling. No files were removed."
    Abort
  ${EndIf}
FunctionEnd

Function un.onUninstSuccess
  System::Call 'kernel32::CloseHandle(p $LifecycleGuard)'
FunctionEnd

Section "bobbi TV native host" SEC_MAIN
  IfFileExists "$INSTDIR\*.*" 0 fresh
    MessageBox MB_ICONSTOP "Choose a new empty version directory. The installer never overwrites a running host or an existing profile."
    Abort
  fresh:
  SetOutPath "$INSTDIR"
  File /r "${HOST_STAGE}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\bobbi TV"
  CreateShortcut "$SMPROGRAMS\bobbi TV\bobbi TV ${VERSION}-${BUILD_SEQUENCE}.lnk" "$INSTDIR\bobbi.exe"
  WriteRegStr HKCU "${INSTALLKEY}" "DisplayName" "bobbi TV ${VERSION}"
  WriteRegStr HKCU "${INSTALLKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${INSTALLKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${INSTALLKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${INSTALLKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${INSTALLKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  ; Program generations only. Shared account/profile settings are never removed.
  IfFileExists "$INSTDIR\bobbi-build.json" 0 invalid
  IfFileExists "$INSTDIR\portable.flag" invalid 0
  RMDir /r "$INSTDIR\host"
  RMDir /r "$INSTDIR\maintenance"
  Delete "$INSTDIR\bobbi.exe"
  Delete "$INSTDIR\bobbi-maintenance.exe"
  Delete "$INSTDIR\bobbi-build.json"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\bobbi TV\bobbi TV ${VERSION}-${BUILD_SEQUENCE}.lnk"
  RMDir "$SMPROGRAMS\bobbi TV"
  DeleteRegKey HKCU "${INSTALLKEY}"
  Goto done
  invalid:
    MessageBox MB_ICONSTOP "This is not a managed installed host generation. No files were removed."
    Abort
  done:
SectionEnd
