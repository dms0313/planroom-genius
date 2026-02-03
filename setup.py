#!/usr/bin/env python3
"""
Cross-platform setup script for Planroom Genius
Works on Windows, Linux (Raspberry Pi), and macOS
"""
import os
import sys
import platform
import subprocess
import shutil

def get_platform():
    """Detect the operating system"""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Linux":
        # Check if Raspberry Pi
        try:
            with open('/proc/cpuinfo', 'r') as f:
                if 'Raspberry Pi' in f.read():
                    return "raspberry_pi"
        except:
            pass
        return "linux"
    elif system == "Darwin":
        return "macos"
    else:
        return "unknown"

def run_command(command, description):
    """Run a shell command and handle errors"""
    print(f"\n[{description}]")
    try:
        if isinstance(command, list):
            result = subprocess.run(command, check=True, shell=False)
        else:
            result = subprocess.run(command, check=True, shell=True)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed: {e}")
        return False

def setup_windows():
    """Windows-specific setup"""
    print("\n" + "="*60)
    print("  Windows Setup")
    print("="*60)

    # Check Python
    print("\n[1/5] Checking Python installation...")
    if not shutil.which('python'):
        print("✗ Python not found. Please install Python 3.11+ from python.org")
        return False
    print("✓ Python found")

    # Check Node.js
    print("\n[2/5] Checking Node.js installation...")
    if not shutil.which('node'):
        print("✗ Node.js not found. Please install from nodejs.org")
        return False
    print("✓ Node.js found")

    # Create virtual environment
    print("\n[3/5] Creating Python virtual environment...")
    venv_path = os.path.join("backend", "venv")
    if not os.path.exists(venv_path):
        run_command([sys.executable, "-m", "venv", venv_path], "Creating venv")

    # Install Python dependencies
    print("\n[4/5] Installing Python dependencies...")
    pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
    run_command([pip_path, "install", "--upgrade", "pip"], "Upgrading pip")
    run_command([pip_path, "install", "-r", "backend/requirements.txt"], "Installing Python packages")

    # Install Playwright
    python_path = os.path.join(venv_path, "Scripts", "python.exe")
    run_command([python_path, "-m", "playwright", "install", "chromium"], "Installing Playwright browsers")

    # Install Node dependencies
    print("\n[5/5] Installing Node.js dependencies...")
    os.chdir("frontend")
    run_command("npm install", "Installing Node packages")
    os.chdir("..")

    print("\n" + "="*60)
    print("  Windows Setup Complete!")
    print("="*60)
    print("\nTo start the application, run:")
    print("  start_app.bat")
    return True

def setup_linux():
    """Linux/Raspberry Pi setup"""
    print("\n" + "="*60)
    print("  Linux/Raspberry Pi Setup")
    print("="*60)

    # Update system
    print("\n[1/8] Updating system packages...")
    run_command("sudo apt-get update", "Updating package list")

    # Install Python
    print("\n[2/8] Installing Python 3...")
    run_command("sudo apt-get install -y python3 python3-pip python3-venv", "Installing Python")

    # Install Node.js
    print("\n[3/8] Installing Node.js...")
    if not shutil.which('node'):
        run_command("curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -", "Adding Node.js repo")
        run_command("sudo apt-get install -y nodejs", "Installing Node.js")

    # Install Chromium
    print("\n[4/8] Installing Chromium browser...")
    run_command("sudo apt-get install -y chromium-browser chromium-codecs-ffmpeg", "Installing Chromium")

    # Create virtual environment
    print("\n[5/8] Creating Python virtual environment...")
    venv_path = os.path.join("backend", "venv")
    if not os.path.exists(venv_path):
        run_command(["python3", "-m", "venv", venv_path], "Creating venv")

    # Install Python dependencies
    print("\n[6/8] Installing Python dependencies...")
    pip_path = os.path.join(venv_path, "bin", "pip")
    run_command([pip_path, "install", "--upgrade", "pip"], "Upgrading pip")
    run_command([pip_path, "install", "-r", "backend/requirements.txt"], "Installing Python packages")

    # Install Playwright
    python_path = os.path.join(venv_path, "bin", "python")
    run_command([python_path, "-m", "playwright", "install", "chromium"], "Installing Playwright browsers")
    run_command([python_path, "-m", "playwright", "install-deps"], "Installing Playwright dependencies")

    # Install Node dependencies
    print("\n[8/8] Installing Node.js dependencies...")
    os.chdir("frontend")
    run_command("npm install", "Installing Node packages")
    os.chdir("..")

    # Make scripts executable
    for script in ["start.sh", "stop.sh"]:
        if os.path.exists(script):
            os.chmod(script, 0o755)

    print("\n" + "="*60)
    print("  Linux/Raspberry Pi Setup Complete!")
    print("="*60)
    print("\nTo start the application, run:")
    print("  ./start.sh")
    return True

def main():
    """Main setup entry point"""
    print("\n" + "="*60)
    print("  PLANROOM GENIUS - Cross-Platform Setup")
    print("="*60)

    # Detect platform
    current_platform = get_platform()
    print(f"\nDetected platform: {current_platform}")

    # Confirm with user
    response = input("\nProceed with installation? (y/n): ").strip().lower()
    if response != 'y':
        print("Setup cancelled.")
        return

    # Run platform-specific setup
    if current_platform == "windows":
        success = setup_windows()
    elif current_platform in ["linux", "raspberry_pi"]:
        success = setup_linux()
    else:
        print(f"\nUnsupported platform: {current_platform}")
        success = False

    if success:
        print("\n✓ Setup completed successfully!")
    else:
        print("\n✗ Setup encountered errors. Please check the output above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
