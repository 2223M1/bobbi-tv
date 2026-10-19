@echo off
setlocal
call "D:\AM6B-Project\toolchains\VS2022\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 exit /b 1
cl.exe /nologo /std:c++17 /EHsc /utf-8 /W4 /I "%~dp0.work\kodi\xbmc" "%~dp0tests\protocol_contracts.cpp" /Fe:"%~dp0build\protocol-contracts.exe" /Fo:"%~dp0build\protocol-contracts.obj"
if errorlevel 1 exit /b 1
"%~dp0build\protocol-contracts.exe" "%~dp0build\test-subtitle-cache"
