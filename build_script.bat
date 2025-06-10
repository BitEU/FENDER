@echo off
echo Building Vehicle GPS Decoder with PyInstaller...
echo.

REM Create decoders/__init__.py if it doesn't exist
if not exist "decoders\__init__.py" (
    echo Creating decoders\__init__.py...
    echo # Auto-generated __init__.py > decoders\__init__.py
)

REM Clean previous builds
echo Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "__pycache__" rmdir /s /q "__pycache__"
if exist "decoders\__pycache__" rmdir /s /q "decoders\__pycache__"

REM Install required packages if not already installed
echo Installing required packages...
pip install pyinstaller tkinterdnd2 openpyxl

REM Build with PyInstaller using spec file
echo Building application...
pyinstaller build.spec

REM Check if build was successful
if exist "dist\VehicleGPSDecoder.exe" (
    echo.
    echo ================================
    echo BUILD SUCCESSFUL!
    echo ================================
    echo.
    echo The executable has been created in the 'dist' folder:
    echo dist\VehicleGPSDecoder.exe
    echo.
    echo You can now distribute this single file!
    pause
) else (
    echo.
    echo ================================
    echo BUILD FAILED!
    echo ================================
    echo.
    echo Please check the output above for errors.
    pause
)
