@echo off
rem Start the ecological control target (Gitea) with a local sqlite store.
rem Requires installers\gitea.exe (see README.md). Work dir is gitignored.
setlocal
set HERE=%~dp0
if not exist "%HERE%installers\gitea.exe" (
  echo gitea.exe missing. Download it first - see README.md in this directory.
  exit /b 2
)
if not exist "%HERE%work\custom\conf" mkdir "%HERE%work\custom\conf"
copy /y "%HERE%app.ini" "%HERE%work\custom\conf\app.ini" >nul
set GITEA_WORK_DIR=%HERE%work
"%HERE%installers\gitea.exe" web --config "%HERE%work\custom\conf\app.ini"
endlocal
