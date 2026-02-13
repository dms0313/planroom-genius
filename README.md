# Planroom Genius v2.0

AI-Powered Construction Lead Intelligence for Fire Alarm & Low Voltage Projects

**Cross-Platform:** Works on Windows, Raspberry Pi, and Linux

---

## 🚀 Quick Start

### One-Command Setup

**Windows:**
```cmd
python setup.py
```

**Linux/Raspberry Pi:**
```bash
python3 setup.py
```

### One-Command Start

**Windows:**
```cmd
start_app.bat
```
or
```cmd
python start.py
```

**Linux/Raspberry Pi:**
```bash
./start.sh
```
or
```bash
python3 start.py
```

---

## 📋 System Requirements

### Windows
- Windows 10/11
- Python 3.11+
- Node.js 20+
- 4GB RAM minimum

### Raspberry Pi 5 (Recommended)
- Raspberry Pi 5 (4GB or 8GB RAM)
- Raspberry Pi OS Bookworm (64-bit) - **Required**
- Active Cooler recommended for sustained workloads
- Internet connection
- 16GB+ microSD (Class 10/U3/A2) or NVMe SSD
- 8GB free storage

### Raspberry Pi 4
- Raspberry Pi 4 (4GB+ RAM recommended)
- Raspberry Pi OS (64-bit)
- Internet connection
- 8GB free storage

### Linux
- Ubuntu 20.04+ / Debian 11+
- Python 3.11+
- Node.js 20+
- 4GB RAM minimum

---

## 🛠️ Installation

### Windows Installation

1. **Install Prerequisites**
   - [Python 3.11+](https://www.python.org/downloads/)
   - [Node.js 20+](https://nodejs.org/)

2. **Clone Repository**
   ```cmd
   git clone https://github.com/yourusername/planroom-genius.git
   cd planroom-genius
   ```

3. **Run Setup**
   ```cmd
   python setup.py
   ```

4. **Configure Environment**
   ```cmd
   copy .env.example .env
   notepad .env
   ```

   Add your credentials:
   ```env
   PLANHUB_LOGIN=your_email@example.com
   PLANHUB_PW=your_password
   ```

5. **Start Application**
   ```cmd
   start_app.bat
   ```

### Raspberry Pi 5 Installation (Recommended)

1. **Prepare your Pi 5**
   - Flash Raspberry Pi OS Bookworm (64-bit) using Raspberry Pi Imager
   - Enable SSH during OS setup for headless access
   - Install Active Cooler for best performance
   - Boot and connect via SSH or terminal

2. **Clone Repository**
   ```bash
   git clone https://github.com/yourusername/planroom-genius.git
   cd planroom-genius
   ```

3. **Run Pi 5 Quick Setup**
   ```bash
   chmod +x pi5-setup.sh
   ./pi5-setup.sh
   ```

   The Pi 5 setup script automatically:
   - Detects Pi 5 hardware and validates 64-bit OS
   - Checks RAM and cooling configuration
   - Installs Python 3.11+ with venv (Bookworm requirement)
   - Installs Node.js 20 LTS
   - Installs Chromium with ARM64 dependencies
   - Configures Playwright for ARM64
   - Sets up optimized headless mode

4. **Configure Environment**
   ```bash
   nano .env
   ```

   Add your credentials:
   ```env
   PLANHUB_LOGIN=your_email@example.com
   PLANHUB_PW=your_password
   HEADLESS=false
   ```

5. **Start Application**
   ```bash
   ./start.sh
   ```

6. **Access from any device on your network**
   ```bash
   # Find your Pi's IP
   hostname -I
   # Access dashboard at http://YOUR_PI_IP:5173
   ```

### Linux/Raspberry Pi 4 Installation

1. **Update System**
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   ```

2. **Clone Repository**
   ```bash
   git clone https://github.com/yourusername/planroom-genius.git
   cd planroom-genius
   ```

3. **Run Setup (includes all dependencies)**
   ```bash
   python3 setup.py
   ```

   Setup will automatically install:
   - Python 3 + pip + venv
   - Node.js 20
   - Chromium browser
   - All Python packages
   - All Node packages

4. **Configure Environment**
   ```bash
   cp .env.example .env
   nano .env
   ```

   Add your credentials:
   ```env
   PLANHUB_LOGIN=your_email@example.com
   PLANHUB_PW=your_password
   HEADLESS=true
   ```

5. **Start Application**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

---

## 🌐 Accessing the Application

### Local Access
- **Dashboard:** http://localhost:5173
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

### Network Access (Raspberry Pi/Server)
Replace `YOUR_IP` with your device's IP address:
- **Dashboard:** http://YOUR_IP:5173
- **API:** http://YOUR_IP:8000

Find your IP:
- **Windows:** `ipconfig`
- **Linux/Pi:** `hostname -I`

---

## ⚙️ Configuration

### Environment Variables

Edit `.env` file:

```env
# PlanHub Credentials
PLANHUB_LOGIN=your_email@example.com
PLANHUB_PW=your_password

# Chrome Settings
CHROME_PROFILE_NAME=Profile 2
HEADLESS=false  # Set to true for headless mode (Pi/Server)

# Automation (backend/config.py)
LOCATION_ZIP=64030
LOCATION_RADIUS=125
```

### Platform-Specific Settings

**Raspberry Pi / Headless Server:**
- Set `HEADLESS=true` in `.env`
- Reduces memory usage
- Runs browser without GUI

**Windows Desktop:**
- Set `HEADLESS=false` for debugging
- Watch browser automation in real-time

---

## 🔥 Features

### Two-Pass Scraping System
1. **Pass 1:** Extract project metadata
   - Project name, company, location
   - Bid date, contact info
   - Filters out expired projects

2. **Pass 2:** Download files
   - Navigates to each project
   - Downloads all documents
   - Saves locally for offline access

### Supported Planrooms
- **BuildingConnected**
  - Unlimited projects
  - Virtual table handling
  - Auto-scroll and extraction

- **PlanHub**
  - Fire Alarm projects
  - 125-mile radius (MO/KS)
  - Uses saved browser filters

### Web Dashboard
- Click-to-view company details popup
- Local file downloads
- One-click duplicate removal
- Automated scanning schedule
- Real-time updates

---

## 📁 Project Structure

```
planroom-genius/
├── setup.py                # Cross-platform setup script
├── start.py               # Cross-platform startup script
├── start.sh               # Linux/Pi wrapper (calls start.py)
├── start_app.bat          # Windows wrapper (calls start.py)
├── .env.example           # Example configuration
├── .gitignore             # Git ignore rules
├── README.md              # This file
│
├── backend/
│   ├── api.py             # FastAPI server
│   ├── config.py          # Configuration
│   ├── requirements.txt   # Python dependencies
│   ├── scrapers/          # Scraper modules
│   │   ├── base_scraper.py
│   │   └── planhub.py
│   ├── services/          # Business logic
│   │   ├── scheduler.py
│   │   └── storage.py
│   └── buildingconnected_table_scraper.py
│
└── frontend/
    ├── package.json       # Node dependencies
    ├── vite.config.js     # Vite configuration
    ├── tailwind.config.js # Tailwind CSS
    └── src/
        ├── main.jsx       # React entry
        └── Dashboard.jsx  # Main UI
```

---

## 🔧 Troubleshooting

### Windows Issues

**Python not found:**
```cmd
# Add Python to PATH or use full path
C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe setup.py
```

**Port already in use:**
```cmd
# Check what's using port 8000 or 5173
netstat -ano | findstr :8000
# Kill the process (replace PID)
taskkill /PID <PID> /F
```

### Raspberry Pi 5 Issues

**Playwright fails to install:**
```bash
# Install missing ARM64 dependencies
sudo apt-get install -y libgbm1 libxkbcommon0 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxcomposite1
```

**pip install fails with "externally-managed-environment":**
```bash
# Bookworm requires virtual environments - use venv
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

**High CPU temperature under load:**
```bash
# Check temperature
vcgencmd measure_temp

# If over 80C, install Active Cooler
# The Active Cooler keeps Pi 5 under 65C during sustained loads
```

**Running out of storage:**
```bash
# Check disk usage
df -h

# Clear Playwright cache if needed
rm -rf ~/.cache/ms-playwright
backend/venv/bin/python -m playwright install chromium
```

### Raspberry Pi 4/Linux Issues

**Chromium crashes:**
```bash
# Increase GPU memory (Pi 4 only, not needed on Pi 5)
sudo nano /boot/config.txt
# Add: gpu_mem=256
sudo reboot
```

**Out of memory:**
```bash
# Increase swap (especially for 2GB/4GB models)
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Set: CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

**Permission denied:**
```bash
# Make scripts executable
chmod +x start.sh
chmod +x setup.py
chmod +x start.py
chmod +x pi5-setup.sh
```

### Common Issues (All Platforms)

**Browser profile issues:**
```bash
# Clear profile and re-login
rm -rf backend/planroom_agent_storage*  # Linux/Mac
# OR
rmdir /s backend\planroom_agent_storage*  # Windows
```

**Duplicates in database:**
- Click "REMOVE DUPES" button in dashboard
- Or manually delete `backend/leads_db.json`

---

## 🔄 Updating

```bash
# Pull latest changes
git pull origin main

# Re-run setup (updates dependencies)
python setup.py  # or python3 setup.py

# Restart application
./start.sh  # or start_app.bat
```

---

## 🤖 Running as a Service (Linux/Pi)

### Quick Install (Recommended for Pi 5)

```bash
# Run the install script - it auto-configures for your user/paths
chmod +x install-service.sh
./install-service.sh
```

The script will:
- Create a customized systemd service for your installation
- Ask to enable auto-start on boot
- Optionally start the service immediately

### Manual Systemd Service Setup

```bash
# Copy the service file
sudo cp planroom-genius.service /etc/systemd/system/

# Edit paths if needed (default assumes /home/pi/planroom-genius)
sudo nano /etc/systemd/system/planroom-genius.service

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable planroom-genius
sudo systemctl start planroom-genius
```

### Service Commands

```bash
# Check status
sudo systemctl status planroom-genius

# View logs
sudo journalctl -u planroom-genius -f

# Restart after updates
sudo systemctl restart planroom-genius

# Stop service
sudo systemctl stop planroom-genius

# Disable auto-start
sudo systemctl disable planroom-genius
```

---

## 🎯 Usage

### Manual Scan
1. Open dashboard: http://localhost:5173
2. Click "SCAN PLANROOMS" button
3. Wait for Pass 1 (data extraction)
4. Wait for Pass 2 (file downloads)
5. Download files appear with green button

### Automatic Scanning
- Runs every 6 hours by default
- Configurable in `backend/services/scheduler.py`
- Change schedule:
  ```python
  schedule.every(12).hours.do(job_wrapper)  # 12 hours
  ```

### Remove Duplicates
1. Click "REMOVE DUPES" in dashboard
2. Shows how many duplicates were merged
3. Automatically refreshes table

---

## 📊 API Endpoints

- `GET /leads` - Get all leads
- `POST /sync-leads` - Trigger scan
- `POST /clear-leads` - Clear database
- `POST /refresh-leads` - Clear + scan
- `POST /deduplicate-leads` - Remove duplicates
- `GET /downloads/{file}` - Download files

Full documentation: http://localhost:8000/docs

---

## 🛡️ Security Notes

- `.env` file contains credentials - NEVER commit to git
- Browser profiles store login sessions
- All sensitive data is gitignored
- Use strong passwords for planroom accounts

---

## 📝 Development

### Code Structure
- **Backend:** Python + FastAPI + Pyppeteer
- **Frontend:** React + Vite + TailwindCSS
- **Automation:** Deterministic Puppeteer scrapers
- **Storage:** JSON file database

### Adding New Planrooms
1. Create scraper in `backend/scrapers/`
2. Extend `BaseScraper` class
3. Implement `scrape_all_projects()` method
4. Add configuration in `backend/config.py`
5. Register in `backend/services/scheduler.py`

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test on both Windows and Linux
5. Submit pull request

---

## 📄 License

Proprietary - Internal Use Only

---

## 🆘 Support

For issues:
- Check logs in backend console
- Review `backend/leads_db.json` for data
- Verify `.env` configuration
- Check browser profile permissions

---

## 🎉 Why Cross-Platform?

### Single Repository Benefits
✅ **One codebase** - Easier maintenance
✅ **Simultaneous updates** - Bug fixes for all platforms
✅ **Feature parity** - Same features everywhere
✅ **Better testing** - Test once, deploy anywhere

### Platform Detection
The application automatically detects your operating system and:
- Uses correct Python executable paths
- Selects appropriate package managers
- Applies platform-specific optimizations
- Handles file paths correctly

### No Separate Builds
- No `pi5_build` directory needed
- Setup script handles platform differences
- Single set of source code
- Deploy directly from git

---

**Built with ❤️ for Fire Alarm & Low Voltage Professionals**
