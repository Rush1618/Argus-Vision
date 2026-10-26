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
for i in {1..15}; do
    if curl -s http://localhost:5000/api/stats > /dev/null 2>&1; then
        echo "      ✓ Backend API and Optical Stream active on http://localhost:5000"
        break
    fi
    sleep 0.5
done

# 2. Start Vite React HUD Frontend (Port 5173)
echo "[2/2] Launching Vite React HUD Dashboard on port 5173..."
cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=========================================================="
echo "  ✓ Argus-Vision is fully live and operational!"
echo "    - Dashboard HUD:   http://localhost:5173"
echo "    - Optical Stream:  http://localhost:5000/video_feed"
echo "    - Telemetry API:   http://localhost:5000/api/stats"
echo "  Press Ctrl+C to stop both servers."
echo "=========================================================="

wait
