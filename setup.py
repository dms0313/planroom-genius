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
    """Detect the operating system and hardware"""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Linux":
        # Check if Raspberry Pi and which model
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
                if 'Raspberry Pi' in cpuinfo:
                    # Check for Pi 5 specifically (BCM2712 SoC)
                    if 'BCM2712' in cpuinfo or 'Raspberry Pi 5' in cpuinfo:
                        return "raspberry_pi_5"
                    return "raspberry_pi"
        except:
            pass
        # Also check device tree model for Pi 5 detection
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read()
                if 'Raspberry Pi 5' in model:
                    return "raspberry_pi_5"
                elif 'Raspberry Pi' in model:
                    return "raspberry_pi"
        except:
            pass
        return "linux"
    elif system == "Darwin":
        return "macos"
    else:
        return "unknown"


def get_pi_info():
    """Get Raspberry Pi hardware info for optimization"""
    # Check multiple indicators for 64-bit
    machine = platform.machine()
    is_64bit = machine in ('aarch64', 'arm64')

    # Also check dpkg architecture (more reliable on Debian/Raspberry Pi OS)
    if not is_64bit:
        try:
            result = subprocess.run(['dpkg', '--print-architecture'],
                                    capture_output=True, text=True)
            if result.returncode == 0 and 'arm64' in result.stdout:
                is_64bit = True
        except:
            pass

    # Also check getconf for kernel bits
    if not is_64bit:
        try:
            result = subprocess.run(['getconf', 'LONG_BIT'],
                                    capture_output=True, text=True)
            if result.returncode == 0 and '64' in result.stdout:
                is_64bit = True
        except:
            pass

    info = {
        "model": "unknown",
        "ram_gb": 0,
        "is_64bit": is_64bit,
        "has_active_cooler": False,
        "machine": machine
    }

    try:
        # Get model info
        with open('/proc/device-tree/model', 'r') as f:
            info["model"] = f.read().strip('\x00')
    except:
        pass

    try:
        # Get RAM info
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    mem_kb = int(line.split()[1])
                    info["ram_gb"] = round(mem_kb / 1024 / 1024, 1)
                    break
    except:
        pass

    # Check for active cooler (fan control available on Pi 5)
    try:
        if os.path.exists('/sys/class/thermal/cooling_device0/type'):
            with open('/sys/class/thermal/cooling_device0/type', 'r') as f:
                if 'fan' in f.read().lower():
                    info["has_active_cooler"] = True
    except:
        pass

    return info

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

def setup_raspberry_pi_5():
    """Raspberry Pi 5-specific setup with optimizations"""
    print("\n" + "="*60)
    print("  Raspberry Pi 5 Setup (Optimized)")
    print("="*60)

    # Get Pi info
    pi_info = get_pi_info()
    print(f"\nDetected: {pi_info['model']}")
    print(f"RAM: {pi_info['ram_gb']} GB")
    print(f"Architecture: {pi_info.get('machine', 'unknown')}")
    print(f"64-bit OS: {'Yes' if pi_info['is_64bit'] else 'No'}")
    print(f"Active Cooler: {'Detected' if pi_info['has_active_cooler'] else 'Not detected'}")

    if not pi_info['is_64bit']:
        print("\n⚠️  WARNING: 64-bit OS is recommended for best performance!")
        print("   Consider reinstalling with Raspberry Pi OS (64-bit)")

    if pi_info['ram_gb'] < 4:
        print("\n⚠️  WARNING: 4GB+ RAM recommended for browser automation")

    # Update system
    print("\n[1/10] Updating system packages...")
    run_command("sudo apt-get update", "Updating package list")
    run_command("sudo apt-get upgrade -y", "Upgrading packages")

    # Install Python 3.11+ with full venv support (required for Bookworm)
    print("\n[2/10] Installing Python 3 with venv support...")
    run_command(
        "sudo apt-get install -y python3 python3-pip python3-venv python3-full",
        "Installing Python with venv"
    )

    # Install Node.js 20 LTS
    print("\n[3/10] Installing Node.js 20 LTS...")
    if not shutil.which('node'):
        run_command(
            "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -",
            "Adding Node.js repo"
        )
        run_command("sudo apt-get install -y nodejs", "Installing Node.js")
    else:
        # Check Node version
        result = subprocess.run(['node', '--version'], capture_output=True, text=True)
        print(f"   Node.js already installed: {result.stdout.strip()}")

    # Install Chromium and dependencies for Playwright on Pi 5
    print("\n[4/10] Installing Chromium and browser dependencies...")
    run_command(
        "sudo apt-get install -y chromium-browser chromium-codecs-ffmpeg-extra",
        "Installing Chromium"
    )

    # Install additional Playwright dependencies for ARM64
    print("\n[5/10] Installing Playwright system dependencies...")
    run_command(
        "sudo apt-get install -y libgbm1 libxkbcommon0 libatk1.0-0 libatk-bridge2.0-0 "
        "libcups2 libdrm2 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 "
        "libasound2 libpango-1.0-0 libcairo2 libatspi2.0-0 libgtk-3-0",
        "Installing browser dependencies"
    )

    # Create virtual environment
    print("\n[6/10] Creating Python virtual environment...")
    venv_path = os.path.join("backend", "venv")
    if os.path.exists(venv_path):
        print("   Removing existing venv...")
        shutil.rmtree(venv_path)

    # Use --system-site-packages for better Pi compatibility
    run_command(
        ["python3", "-m", "venv", "--system-site-packages", venv_path],
        "Creating venv with system packages"
    )

    # Install Python dependencies
    print("\n[7/10] Installing Python dependencies...")
    pip_path = os.path.join(venv_path, "bin", "pip")
    run_command([pip_path, "install", "--upgrade", "pip", "wheel", "setuptools"], "Upgrading pip")
    run_command([pip_path, "install", "-r", "backend/requirements.txt"], "Installing Python packages")

    # Install Playwright with Chromium only (saves space on Pi)
    print("\n[8/10] Setting up Playwright for ARM64...")
    python_path = os.path.join(venv_path, "bin", "python")
    run_command(
        [python_path, "-m", "playwright", "install", "chromium"],
        "Installing Playwright Chromium"
    )
    run_command(
        [python_path, "-m", "playwright", "install-deps", "chromium"],
        "Installing Playwright Chromium dependencies"
    )

    # Install Node dependencies
    print("\n[9/10] Installing Node.js dependencies...")
    original_dir = os.getcwd()
    os.chdir("frontend")
    run_command("npm install", "Installing Node packages")
    os.chdir(original_dir)

    # Pi 5 optimizations
    print("\n[10/10] Applying Pi 5 optimizations...")

    # Make scripts executable
    for script in ["start.sh", "stop.sh", "start.py", "setup.py"]:
        if os.path.exists(script):
            os.chmod(script, 0o755)

    # Create Pi 5 optimized .env if not exists
    if not os.path.exists('.env'):
        if os.path.exists('.env.example'):
            shutil.copy('.env.example', '.env')
            print("   Created .env from .env.example")
        else:
            with open('.env', 'w') as f:
                f.write("# Planroom Genius - Pi 5 Configuration\n")
                f.write("GEMINI_API_KEY=your_gemini_api_key_here\n")
                f.write("SITE_LOGIN=your_email@domain.com\n")
                f.write("SITE_PW=your_password\n")
                f.write("BIDPLANROOM_EMAIL=your_email@domain.com\n")
                f.write("BIDPLANROOM_PW=your_password\n")
                f.write("LOYD_LOGIN=your_email@domain.com\n")
                f.write("LOYD_PW=your_password\n")
                f.write("HEADLESS=true\n")
                f.write("USE_GOOGLE_DRIVE=false\n")
            print("   Created .env template")

    # Ensure HEADLESS=true is set for Pi
    with open('.env', 'r') as f:
        env_content = f.read()
    if 'HEADLESS=true' not in env_content:
        with open('.env', 'a') as f:
            f.write("\n# Raspberry Pi 5 - headless mode\n")
            f.write("HEADLESS=true\n")

    # Check and configure swap if low RAM
    if pi_info['ram_gb'] <= 4:
        print("\n   Checking swap configuration for 4GB model...")
        try:
            with open('/etc/dphys-swapfile', 'r') as f:
                if 'CONF_SWAPSIZE=2048' not in f.read():
                    print("   💡 TIP: Consider increasing swap to 2GB:")
                    print("      sudo nano /etc/dphys-swapfile")
                    print("      Set CONF_SWAPSIZE=2048")
                    print("      sudo dphys-swapfile setup && sudo dphys-swapfile swapon")
        except:
            pass

    print("\n" + "="*60)
    print("  Raspberry Pi 5 Setup Complete!")
    print("="*60)
    print("\n🎉 Your Pi 5 is ready for Planroom Genius!")
    print("\n📋 Next steps:")
    print("   1. Configure your credentials:")
    print("      nano .env")
    print("   2. Start the application:")
    print("      ./start.sh")
    print("\n💡 Pi 5 Tips:")
    print("   - Active Cooler recommended for sustained workloads")
    print("   - App runs headless by default (HEADLESS=true)")
    print("   - Access dashboard from any device on your network")

    if pi_info['has_active_cooler']:
        print("   - ✓ Active cooler detected - great for performance!")

    return True


def setup_linux():
    """Linux/Raspberry Pi setup"""
    print("\n" + "="*60)
    print("  Linux/Raspberry Pi Setup")
    print("="*60)

    # Update system
    print("\n[1/8] Updating system packages...")
    run_command("sudo apt-get update", "Updating package list")

    # Install Python with full venv support (Bookworm requirement)
    print("\n[2/8] Installing Python 3...")
    run_command(
        "sudo apt-get install -y python3 python3-pip python3-venv python3-full",
        "Installing Python"
    )

    # Install Node.js
    print("\n[3/8] Installing Node.js...")
    if not shutil.which('node'):
        run_command("curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -", "Adding Node.js repo")
        run_command("sudo apt-get install -y nodejs", "Installing Node.js")

    # Install Chromium
    print("\n[4/8] Installing Chromium browser...")
    run_command("sudo apt-get install -y chromium-browser chromium-codecs-ffmpeg", "Installing Chromium")

    # Install Playwright dependencies
    run_command(
        "sudo apt-get install -y libgbm1 libxkbcommon0",
        "Installing browser dependencies"
    )

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
    print("\n[7/8] Installing Playwright...")
    python_path = os.path.join(venv_path, "bin", "python")
    run_command([python_path, "-m", "playwright", "install", "chromium"], "Installing Playwright browsers")
    run_command([python_path, "-m", "playwright", "install-deps"], "Installing Playwright dependencies")

    # Install Node dependencies
    print("\n[8/8] Installing Node.js dependencies...")
    original_dir = os.getcwd()
    os.chdir("frontend")
    run_command("npm install", "Installing Node packages")
    os.chdir(original_dir)

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
    elif current_platform == "raspberry_pi_5":
        success = setup_raspberry_pi_5()
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
