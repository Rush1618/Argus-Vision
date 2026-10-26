#!/usr/bin/env bash
# Argus-Vision: Unified Launch Script (Backend + Frontend)

set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================================="
echo "    Starting Argus-Vision AI Edge Video HUD Console"
echo "=========================================================="

# Cleanup background processes on exit (Ctrl+C)
cleanup() {
    echo ""
    echo "[!] Shutting down Argus-Vision servers..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    trap - SIGINT SIGTERM EXIT
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Start Python Flask AI Vision Backend (Port 5000)
echo "[1/2] Launching Python Flask AI Vision Engine on port 5000..."
cd "$ROOT_DIR/backend"
python3 app.py &
BACKEND_PID=$!

# Wait for backend port 5000 to be ready
echo "      Waiting for vision pipeline to initialize..."
BACKEND_READY=false
for i in {1..20}; do
    if curl -s http://127.0.0.1:5000/api/stats > /dev/null 2>&1; then
        echo "      ✓ Backend API and Optical Stream active on http://127.0.0.1:5000"
        BACKEND_READY=true
        break
    fi
    sleep 0.5
done

if [ "$BACKEND_READY" = false ]; then
    echo "      ✗ ERROR: Backend failed to start or did not respond on http://127.0.0.1:5000 within 10 seconds."
    exit 1
fi

# 2. Start Vite React HUD Frontend (Port 5173)
echo "[2/2] Launching Vite React HUD Dashboard on port 5173..."
cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

# Wait for frontend dev server to be responsive
echo "      Waiting for dashboard dev server..."
FRONTEND_READY=false
for i in {1..20}; do
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        echo "      ✓ Dashboard HUD active on http://localhost:5173"
        FRONTEND_READY=true
        break
    fi
    sleep 0.5
done

echo ""
echo "=========================================================="
if [ "$FRONTEND_READY" = true ]; then
    echo "  ✓ Argus-Vision is fully live and operational!"
    echo "    - Dashboard HUD:   http://localhost:5173"
    echo "    - Optical Stream:  http://127.0.0.1:5000/video_feed"
    echo "    - Telemetry API:   http://127.0.0.1:5000/api/stats"
    echo "  Press Ctrl+C to stop both servers."
else
    echo "  ! Backend is operational on http://127.0.0.1:5000."
    echo "    Vite dashboard starting in background (PID: $FRONTEND_PID)."
fi
echo "=========================================================="

wait
