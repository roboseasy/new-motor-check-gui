#!/usr/bin/env bash
#
# Build script for STS3215 Motor Check GUI
# Creates a standalone executable and optionally an AppImage.
#
# Usage:
#   ./build.sh              # Build standalone executable only
#   ./build.sh --appimage   # Build standalone executable + AppImage
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="sts3215-motor-test"
APP_DISPLAY_NAME="STS3215 Motor Test"
DIST_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "========================================="
echo " Building ${APP_DISPLAY_NAME}"
echo "========================================="

# ---- 1. Check dependencies ------------------------------------------------
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.10+."
    exit 1
fi

echo "[1/4] Setting up virtual environment and dependencies..."
VENV_DIR="${BUILD_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
    uv venv "${VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"
UV_HTTP_TIMEOUT=300 uv pip install pyinstaller pyqt6 pyserial st3215 --quiet

# ---- 2. Run PyInstaller ---------------------------------------------------
echo "[2/4] Running PyInstaller..."
cd "${SCRIPT_DIR}"
pyinstaller --clean --noconfirm motor_check_gui.spec

EXECUTABLE="${DIST_DIR}/${APP_NAME}"
if [ ! -f "${EXECUTABLE}" ]; then
    echo "ERROR: PyInstaller failed — executable not found at ${EXECUTABLE}"
    exit 1
fi

echo "    Executable created: ${EXECUTABLE}"
ls -lh "${EXECUTABLE}"

# ---- 3. Optionally create AppImage ----------------------------------------
if [ "${1:-}" = "--appimage" ]; then
    echo "[3/4] Building AppImage..."

    APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"
    rm -rf "${APPDIR}"
    mkdir -p "${APPDIR}/usr/bin"
    mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

    # Copy executable
    cp "${EXECUTABLE}" "${APPDIR}/usr/bin/${APP_NAME}"
    chmod +x "${APPDIR}/usr/bin/${APP_NAME}"

    # Copy icon if exists
    if [ -f "${SCRIPT_DIR}/icon.png" ]; then
        cp "${SCRIPT_DIR}/icon.png" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
        cp "${SCRIPT_DIR}/icon.png" "${APPDIR}/${APP_NAME}.png"
    fi

    # Create .desktop file
    cat > "${APPDIR}/${APP_NAME}.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=${APP_DISPLAY_NAME}
Exec=${APP_NAME}
Icon=${APP_NAME}
Categories=Utility;Development;
Comment=STS3215 Servo Motor Test and Configuration Tool
DESKTOP

    # Create AppRun
    cat > "${APPDIR}/AppRun" <<'APPRUN'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/sts3215-motor-test" "$@"
APPRUN
    chmod +x "${APPDIR}/AppRun"

    # Download appimagetool if not present
    APPIMAGETOOL="${BUILD_DIR}/appimagetool"
    if [ ! -f "${APPIMAGETOOL}" ]; then
        echo "    Downloading appimagetool..."
        ARCH=$(uname -m)
        curl -fsSL -o "${APPIMAGETOOL}" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
        chmod +x "${APPIMAGETOOL}"
    fi

    # Build the AppImage
    APPIMAGE_OUT="${DIST_DIR}/${APP_NAME}-$(uname -m).AppImage"
    ARCH=$(uname -m) "${APPIMAGETOOL}" "${APPDIR}" "${APPIMAGE_OUT}"

    echo "    AppImage created: ${APPIMAGE_OUT}"
    ls -lh "${APPIMAGE_OUT}"
else
    echo "[3/4] Skipping AppImage (use --appimage flag to enable)"
fi

# ---- 4. Done --------------------------------------------------------------
echo "[4/4] Build complete!"
echo ""
echo "Output files:"
echo "  Executable: ${EXECUTABLE}"
if [ "${1:-}" = "--appimage" ]; then
    echo "  AppImage:   ${DIST_DIR}/${APP_NAME}-$(uname -m).AppImage"
fi
echo ""
echo "To run: ${EXECUTABLE}"
