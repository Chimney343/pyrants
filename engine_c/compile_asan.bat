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

set SRCS=intern.c arena.c rng.c state.c moves.c rules.c helpers.c phases.c scoring.c generic_runtime.c actions.c selection.c player_view.c loader.c cJSON.c view.c describe.c saveload.c rollout.c

call %VCVARS% > nul
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

cd /d "%~dp0"

echo Building libengine_asan.lib (AddressSanitizer)...
cl %CFLAGS% /c %SRCS%
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

lib /nologo /out:libengine_asan.lib *.obj
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_engine_asan.exe...
cl %CFLAGS% /I. /Fe:test_engine_asan.exe test_engine.c test_intern_c.c libengine_asan.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running tests under ASan...
.\test_engine_asan.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_view_asan.exe...
cl %CFLAGS% /I. /Fe:test_view_asan.exe tests\test_view.c libengine_asan.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running view tests under ASan...
.\test_view_asan.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_describe_asan.exe...
cl %CFLAGS% /I. /Fe:test_describe_asan.exe tests\test_describe.c libengine_asan.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running describe tests under ASan...
.\test_describe_asan.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_generic_actions_asan.exe...
cl %CFLAGS% /I. /Fe:test_generic_actions_asan.exe tests\test_generic_actions.c libengine_asan.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running generic action tests under ASan...
.\test_generic_actions_asan.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_saveload_asan.exe...
cl %CFLAGS% /I. /Fe:test_saveload_asan.exe tests\test_saveload.c libengine_asan.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running saveload tests under ASan...
.\test_saveload_asan.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_rollout_asan.exe...
cl %CFLAGS% /I. /Fe:test_rollout_asan.exe tests\test_rollout.c libengine_asan.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running rollout tests under ASan...
.\test_rollout_asan.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_catalog_assembly_asan.exe...
cl %CFLAGS% /I. /Fe:test_catalog_assembly_asan.exe tests\test_catalog_assembly.c libengine_asan.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running catalog assembly tests under ASan...
.\test_catalog_assembly_asan.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building engine_c_asan.dll...
del /Q test_engine.obj test_intern_c.obj test_view.obj test_describe.obj test_generic_actions.obj test_saveload.obj test_catalog_assembly.obj test_rollout.obj 2>nul
del /Q engine_c_asan.dll 2>nul
cl %CFLAGS% /LD /Fe:engine_c_asan.dll *.obj /link /DEF:engine_c.def /INCREMENTAL:NO
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
    echo          engine_c_asan.dll — loading it from Python will fail with
    echo          "Could not find module ... or one of its dependencies".
)

echo Done. Point the Python bindings at it with:
echo   set PYRANTS_ENGINE_DLL=%~dp0engine_c_asan.dll
