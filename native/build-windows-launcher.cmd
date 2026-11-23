@echo off
setlocal
call D:\AM6B-Project\toolchains\VS2022\VC\Auxiliary\Build\vcvars64.bat >nul
if errorlevel 1 exit /b 1
if not exist "%~dp0build\windows-launcher" mkdir "%~dp0build\windows-launcher"
pushd "%~dp0build\windows-launcher"
cl /nologo /std:c++17 /utf-8 /O2 /MT /EHsc /DUNICODE /D_UNICODE "%~dp0windows\launcher.cpp" /Fe:bobbi.exe /link /SUBSYSTEM:WINDOWS shell32.lib ole32.lib bcrypt.lib user32.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /utf-8 /O2 /MT /EHsc /DUNICODE /D_UNICODE "%~dp0windows\maintenance.cpp" /Fe:bobbi-maintenance.exe /link /SUBSYSTEM:CONSOLE
set result=%errorlevel%
popd
exit /b %result%
