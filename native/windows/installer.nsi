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
!define LANG_REG_ROOT HKCU
!define LANG_REG_KEY "Software\bobbi TV\Installer"
!define LANG_REG_VAL "InstallerLanguage"
!define MUI_LANGDLL_REGISTRY_ROOT "${LANG_REG_ROOT}"
!define MUI_LANGDLL_REGISTRY_KEY "${LANG_REG_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "${LANG_REG_VAL}"
Var LifecycleGuard
Var SavedInstallerLang
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
; Default to Simplified Chinese on fresh install while preserving explicit upgrade preference.
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

LangString DESC_SEC_MAIN ${LANG_SIMPCHINESE} "bobbi TV 原生宿主程序"
LangString DESC_SEC_MAIN ${LANG_ENGLISH} "bobbi TV native host"

LangString MSG_REQUIRE_X64 ${LANG_SIMPCHINESE} "此版本需要 64 位 Windows 10 或更高版本。"
LangString MSG_REQUIRE_X64 ${LANG_ENGLISH} "This candidate requires 64-bit Windows 10 or later."

LangString MSG_CLOSE_BEFORE_UNINSTALL ${LANG_SIMPCHINESE} "卸载前请先关闭正在运行的 bobbi TV。本次未移除任何文件。"
LangString MSG_CLOSE_BEFORE_UNINSTALL ${LANG_ENGLISH} "Close bobbi TV before uninstalling. No files were removed."

LangString MSG_CHOOSE_EMPTY_DIR ${LANG_SIMPCHINESE} "请选择一个新的空版本目录。安装程序绝不会覆盖正在运行的宿主或已有用户配置。"
LangString MSG_CHOOSE_EMPTY_DIR ${LANG_ENGLISH} "Choose a new empty version directory. The installer never overwrites a running host or an existing profile."

LangString MSG_NOT_MANAGED_GENERATION ${LANG_SIMPCHINESE} "此目录不是受管理的安装版本目录。本次未移除任何文件。"
LangString MSG_NOT_MANAGED_GENERATION ${LANG_ENGLISH} "This is not a managed installed host generation. No files were removed."

Function .onInit
  ReadRegStr $SavedInstallerLang "${LANG_REG_ROOT}" "${LANG_REG_KEY}" "${LANG_REG_VAL}"
  ${If} $SavedInstallerLang == ""
    StrCpy $LANGUAGE ${LANG_SIMPCHINESE}
  ${EndIf}
  !insertmacro MUI_LANGDLL_DISPLAY
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "$(MSG_REQUIRE_X64)"
    Abort
  ${EndIf}
FunctionEnd

Function .onInstSuccess
  !insertmacro MUI_LANGDLL_SAVELANGUAGE
FunctionEnd

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
  CreateDirectory "$LOCALAPPDATA\bobbi TV\profile"
  System::Call 'kernel32::CreateFileW(w "$LOCALAPPDATA\bobbi TV\profile\host-lifecycle.lock", i 0xC0000000, i 0, p 0, i 4, i 0x80, p 0) p .r0'
  StrCpy $LifecycleGuard $0
  ${If} $LifecycleGuard == -1
    MessageBox MB_ICONSTOP "$(MSG_CLOSE_BEFORE_UNINSTALL)"
    Abort
  ${EndIf}
FunctionEnd

Function un.onUninstSuccess
  System::Call 'kernel32::CloseHandle(p $LifecycleGuard)'
FunctionEnd

Section "$(DESC_SEC_MAIN)" SEC_MAIN
  IfFileExists "$INSTDIR\*.*" 0 fresh
    MessageBox MB_ICONSTOP "$(MSG_CHOOSE_EMPTY_DIR)"
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
    MessageBox MB_ICONSTOP "$(MSG_NOT_MANAGED_GENERATION)"
    Abort
  done:
SectionEnd
