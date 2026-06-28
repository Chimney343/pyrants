@echo off
REM Build script for Windows with MSVC Build Tools
REM Prerequisites: Visual Studio 2022 Build Tools with C++ workload
REM Usage: compile.bat [debug|release]

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

set SRCS=intern.c arena.c rng.c state.c moves.c rules.c helpers.c phases.c scoring.c generic_runtime.c actions.c selection.c player_view.c loader.c cJSON.c view.c describe.c saveload.c

call %VCVARS% > nul
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

cd /d "%~dp0"

echo Building libengine.lib (%BUILD_TYPE%)...
cl %CFLAGS% /c %SRCS%
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

lib /nologo /out:libengine.lib *.obj
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_engine.exe...
cl %CFLAGS% /Fe:test_engine.exe test_engine.c test_intern_c.c libengine.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running tests...
.\test_engine.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_view.exe...
cl %CFLAGS% /I. /Fe:test_view.exe tests\test_view.c libengine.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running view tests...
.\test_view.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_describe.exe...
cl %CFLAGS% /I. /Fe:test_describe.exe tests\test_describe.c libengine.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running describe tests...
.\test_describe.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_generic_actions.exe...
cl %CFLAGS% /I. /Fe:test_generic_actions.exe tests\test_generic_actions.c libengine.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running generic action tests...
.\test_generic_actions.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building test_saveload.exe...
cl %CFLAGS% /I. /Fe:test_saveload.exe tests\test_saveload.c libengine.lib
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Running saveload tests...
.\test_saveload.exe
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo Building engine_c.dll...
REM Remove test object files so DLL only links library objects
del /Q test_engine.obj test_intern_c.obj test_view.obj test_describe.obj test_generic_actions.obj test_saveload.obj 2>nul
REM Delete old DLL first — link fails with LNK1104 if the file is in use
del /Q engine_c.dll 2>nul
link /DLL /DEF:engine_c.def /OUT:engine_c.dll *.obj
if %ERRORLEVEL% neq 0 (
    echo ERROR: Cannot link engine_c.dll. If the file is in use ^(LNK1104^), close any
    echo        Python processes or terminals that have loaded the DLL, then retry.
    exit /b %ERRORLEVEL%
)

echo Done.
