#!/usr/bin/env python3
"""
Cross-platform startup script for Planroom Genius
Works on Windows, Linux (Raspberry Pi), and macOS
"""
import os
import sys
import platform
import subprocess
import time
import signal
import socket

# Global process references
backend_process = None
frontend_process = None

def get_platform():
    """Detect the operating system"""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Linux":
        return "linux"
    elif system == "Darwin":
        return "macos"
    return "unknown"

def is_port_in_use(port):
    """Check if a port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_python_executable():
    """Get the path to the Python executable in venv"""
    current_platform = get_platform()
    if current_platform == "windows":
        return os.path.join("backend", "venv", "Scripts", "python.exe")
    else:
        return os.path.join("backend", "venv", "bin", "python")

def get_npm_executable():
    """Get the npm command"""
    current_platform = get_platform()
    if current_platform == "windows":
        return "npm.cmd"
    else:
        return "npm"

def start_backend():
    """Start the backend API server"""
    global backend_process

    print("\n[1/2] Starting backend API server...")

    python_exe = get_python_executable()
    if not os.path.exists(python_exe):
        print(f"✗ Python virtual environment not found at: {python_exe}")
        print("  Please run setup first: python setup.py")
        return False

    try:
        # Check if port is already in use
        if is_port_in_use(8000):
            print("✗ Port 8000 is already in use. Another instance may be running.")
            return False

        # Start backend process
        backend_process = subprocess.Popen(
            [python_exe, "api.py"],
            cwd="backend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Wait a bit and check if process started
        time.sleep(2)
        if backend_process.poll() is not None:
            print("✗ Backend failed to start")
            return False

        print(f"✓ Backend started (PID: {backend_process.pid})")
        return True

    except Exception as e:
        print(f"✗ Failed to start backend: {e}")
        return False

def start_frontend():
    """Start the frontend dev server"""
    global frontend_process

    print("\n[2/2] Starting frontend dev server...")

    npm_cmd = get_npm_executable()

    try:
        # Check if port is already in use
        if is_port_in_use(5173):
            print("✗ Port 5173 is already in use. Another instance may be running.")
            return False

        # Start frontend process
        frontend_process = subprocess.Popen(
            [npm_cmd, "run", "dev", "--", "--host", "0.0.0.0"],
            cwd="frontend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Wait a bit and check if process started
        time.sleep(2)
        if frontend_process.poll() is not None:
            print("✗ Frontend failed to start")
            return False

        print(f"✓ Frontend started (PID: {frontend_process.pid})")
        return True

    except Exception as e:
        print(f"✗ Failed to start frontend: {e}")
        return False

def cleanup():
    """Stop all processes"""
    global backend_process, frontend_process

    print("\n\nStopping services...")

    if backend_process and backend_process.poll() is None:
        print("  Stopping backend...")
        backend_process.terminate()
        try:
            backend_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_process.kill()

    if frontend_process and frontend_process.poll() is None:
        print("  Stopping frontend...")
        frontend_process.terminate()
        try:
            frontend_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            frontend_process.kill()

    print("✓ Services stopped")

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    cleanup()
    sys.exit(0)

def get_local_ip():
    """Get the local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

def main():
    """Main entry point"""
    print("="*60)
    print("  PLANROOM GENIUS - Starting Application")
    print("="*60)

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    if platform.system() != "Windows":
        signal.signal(signal.SIGTERM, signal_handler)

    # Start backend
    if not start_backend():
        print("\n✗ Failed to start backend. Exiting.")
        cleanup()
        sys.exit(1)

    # Wait for backend to be ready
    print("\nWaiting for backend to be ready...")
    time.sleep(3)

    # Start frontend
    if not start_frontend():
        print("\n✗ Failed to start frontend. Cleaning up.")
        cleanup()
        sys.exit(1)

    # Wait for frontend to be ready
    print("\nWaiting for frontend to be ready...")
    time.sleep(3)

    # Get local IP
    local_ip = get_local_ip()

    # Display access information
    print("\n" + "="*60)
    print("  PLANROOM GENIUS IS RUNNING!")
    print("="*60)
    print("\n📊 Dashboard:")
    print(f"   Local:   http://localhost:5173")
    print(f"   Network: http://{local_ip}:5173")
    print("\n🔌 API Server:")
    print(f"   Local:   http://localhost:8000")
    print(f"   Network: http://{local_ip}:8000")
    print(f"   Docs:    http://localhost:8000/docs")
    print("\n⏸️  Press Ctrl+C to stop all services")
    print("="*60 + "\n")

    # Keep the script running
    try:
        while True:
            time.sleep(1)

            # Check if processes are still running
            if backend_process and backend_process.poll() is not None:
                print("\n✗ Backend process died unexpectedly")
                cleanup()
                sys.exit(1)

            if frontend_process and frontend_process.poll() is not None:
                print("\n✗ Frontend process died unexpectedly")
                cleanup()
                sys.exit(1)

    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
