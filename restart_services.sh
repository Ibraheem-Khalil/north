#!/bin/bash

echo "Restarting NORTH AI Services..."
echo "================================"

# Kill existing processes
echo "Stopping existing services..."
# Kill Python API on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || echo "Backend not running"
# Kill Node frontend on port 5173  
lsof -ti:5173 | xargs kill -9 2>/dev/null || echo "Frontend not running"

# Give processes time to stop
sleep 2

# Start backend
echo ""
echo "Starting backend API..."
cd /c/Users/Admin/Desktop/NORTH
python api.py &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Give backend time to initialize
sleep 3

# Start frontend
echo ""
echo "Starting frontend..."
cd /c/Users/Admin/Desktop/NORTH/frontend
npm run dev &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

echo ""
echo "================================"
echo "Services restarted successfully!"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both services"

# Wait for interrupt
wait