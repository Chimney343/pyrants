@echo off
REM AddressSanitizer build of the C engine, for catching memory-safety bugs
REM (buffer overflows, use-after-free, etc.) that a normal test run can't see.
REM Produces separate _asan-suffixed artifacts so the normal release build
REM (compile.bat) is untouched.
REM
REM Usage: compile_asan.bat
REM Then either:
REM   - run the C unit tests directly (test_engine_asan.exe etc.), or
REM   - point the Python bindings at engine_c_asan.dll via:
REM       set PYRANTS_ENGINE_DLL=<repo>\engine_c\engine_c_asan.dll
REM     and run pytest as usual.
REM Source and test lists live in sources.txt and tests.txt.

setlocal enabledelayedexpansion

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

REM /MTd (debug static CRT) + /Zi (debug symbols, for symbolized ASan stack
REM traces) + /Od (no optimization, so line numbers in reports are accurate)
REM + /fsanitize=address. Incompatible with /RTC1, which we don't use anyway.
set CFLAGS=/nologo /W3 /std:c11 /MTd /Zi /Od /fsanitize=address

call %VCVARS% > nul
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

cd /d "%~dp0"

set "SRCS="
set "LIBOBJS="
for /f "usebackq eol=# tokens=*" %%s in ("sources.txt") do (
    set "SRCS=!SRCS! %%s"
    set "LIBOBJS=!LIBOBJS! %%~ns.obj"
)

echo Building libengine_asan.lib (AddressSanitizer)...
cl %CFLAGS% /I. /c !SRCS!
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

lib /nologo /out:libengine_asan.lib !LIBOBJS!
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

for /f "usebackq eol=# tokens=1,2 delims=|" %%t in ("tests.txt") do (
    echo Building %%t_asan.exe...
    cl %CFLAGS% /I. /Fe:%%t_asan.exe %%u libengine_asan.lib
    if errorlevel 1 exit /b 1

    echo Running %%t under ASan...
    .\%%t_asan.exe
    if errorlevel 1 exit /b 1
)

echo Building engine_c_asan.dll...
del /Q engine_c_asan.dll 2>nul
cl %CFLAGS% /LD /Fe:engine_c_asan.dll !LIBOBJS! /link /DEF:engine_c.def /INCREMENTAL:NO /MACHINE:X64
if %ERRORLEVEL% neq 0 (
    echo ERROR: Cannot link engine_c_asan.dll. If the file is in use, close any
    echo        Python processes or terminals that have loaded it, then retry.
    exit /b %ERRORLEVEL%
)

REM The ASan instrumentation itself always lives in a separate runtime DLL
REM (even with /MTd), which python.exe won't find on its own PATH. Copy it
REM next to engine_c_asan.dll so the OS loader picks it up automatically.
copy /Y "%VCToolsInstallDir%bin\Hostx64\x64\clang_rt.asan_dynamic-x86_64.dll" . > nul
if %ERRORLEVEL% neq 0 (
    echo WARNING: could not copy clang_rt.asan_dynamic-x86_64.dll next to
    echo          engine_c_asan.dll - loading it from Python will fail with
    echo          "Could not find module ... or one of its dependencies".
)

echo Done. Point the Python bindings at it with:
echo   set PYRANTS_ENGINE_DLL=%~dp0engine_c_asan.dll

