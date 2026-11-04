@echo off
REM Build script for Windows with MSVC Build Tools
REM Prerequisites: Visual Studio 2022 Build Tools with C++ workload
REM Usage: compile.bat [debug|release]
REM Source and test lists live in sources.txt and tests.txt.

setlocal enabledelayedexpansion

REM Ensure VS Installer directory is in PATH so vswhere.exe is found by vcvars
if exist "C:\Program Files (x86)\Microsoft Visual Studio\Installer" set "PATH=C:\Program Files (x86)\Microsoft Visual Studio\Installer;%PATH%"
if exist "C:\Program Files\Microsoft Visual Studio\Installer" set "PATH=C:\Program Files\Microsoft Visual Studio\Installer;%PATH%"

set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist %VCVARS% set VCVARS="C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist %VCVARS% set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if not exist %VCVARS% set VCVARS="C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if not exist %VCVARS% set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
if not exist %VCVARS% set VCVARS="C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"

if not exist %VCVARS% (
    echo ERROR: Visual Studio 2022 Build Tools not found.
    echo Install from: https://visualstudio.microsoft.com/downloads/
    exit /b 1
)

set BUILD_TYPE=%1
if "%BUILD_TYPE%"=="" set BUILD_TYPE=release

set CFLAGS=/nologo /W3 /std:c11 /MT
if "%BUILD_TYPE%"=="debug" set CFLAGS=%CFLAGS% /Zi /Od
if "%BUILD_TYPE%"=="release" set CFLAGS=%CFLAGS% /O2

call %VCVARS% > nul
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

cd /d "%~dp0"

set "SRCS="
set "LIBOBJS="
for /f "usebackq eol=# tokens=*" %%s in ("sources.txt") do (
    set "SRCS=!SRCS! %%s"
    set "LIBOBJS=!LIBOBJS! %%~ns.obj"
)

echo Building libengine.lib (%BUILD_TYPE%)...
cl %CFLAGS% /c !SRCS!
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

lib /nologo /out:libengine.lib !LIBOBJS!
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

for /f "usebackq eol=# tokens=1,2 delims=|" %%t in ("tests.txt") do (
    echo Building %%t.exe...
    cl %CFLAGS% /I. /Fe:%%t.exe %%u libengine.lib
    if errorlevel 1 exit /b 1

    echo Running %%t...
    .\%%t.exe
    if errorlevel 1 exit /b 1
)

echo Building engine_c.dll...
REM Delete old DLL first - link fails with LNK1104 if the file is in use
del /Q engine_c.dll 2>nul
link /NOLOGO /DLL /MACHINE:X64 /DEF:engine_c.def /OUT:engine_c.dll !LIBOBJS!
if %ERRORLEVEL% neq 0 (
    echo ERROR: Cannot link engine_c.dll. If the file is in use ^(LNK1104^), close any
    echo        Python processes or terminals that have loaded the DLL, then retry.
    exit /b %ERRORLEVEL%
)

echo Done.
