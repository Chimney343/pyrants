@echo off
setlocal enabledelayedexpansion
set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
call %VCVARS% > nul
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
cd /d "%~dp0"
cl /nologo /std:c11 /MT /O2 /I. test_dt_ched.c libengine.lib /Fe:test_dt_ched.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
test_dt_ched.exe
