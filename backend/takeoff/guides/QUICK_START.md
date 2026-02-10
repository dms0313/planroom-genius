# Quick Start Guide

## Setup (5 minutes)

### 1. Install Dependencies
```bash
cd fire-alarm-analyzer
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
ROBOFLOW_API_KEY=your_key_here
ROBOFLOW_WORKSPACE=your_workspace
ROBOFLOW_PROJECT=your_project
ROBOFLOW_VERSION=1

GEMINI_API_KEY=your_gemini_key_here  # Optional
```

### 3. Run the Application
```bash
python app.py
```

Open browser to: **http://localhost:5000**

## Using the Application

### Step 1: Upload PDF
- Click or drag-and-drop your construction bid set PDF
- Maximum file size: 500MB

### Step 2: Select Pages
- Thumbnails will appear for all pages
- Click to select pages you want to analyze
- Use "Select All" or "Deselect All" buttons

### Step 3: Configure Options
- **Tile Filtering**: Skip blank or edge tiles for speed
- **Performance**: Enable parallel processing and caching
- **Detection**: Adjust confidence threshold (0.1-1.0)

### Step 4: Analyze
- Click **"🔍 Analyze Fire Alarm Systems"** for Roboflow detection
- OR click **"🤖 Analyze with Gemini AI"** for text analysis

### Step 5: View Results
- **Summary Cards**: Total devices, pages analyzed
- **Device Grid**: All detected devices with details
- **Preview Grid**: Annotated pages with detection boxes

### Step 6: Download Results

**DOWNLOAD LINKS ARE IN THE PREVIEW GRID!**

Each page card shows:
- Page number
- Number of devices detected
- **"View" button** - Opens full-screen preview
- **"Download" button** - Downloads annotated PDF ⬅️ THIS IS YOUR DOWNLOAD LINK!

You can also:
- **Export Results (JSON)** - Download all results as JSON
- **Full-screen modal** - Click any preview, then use "📥 Download PDF" button

## Where Are the Download Links?

After analysis completes, scroll down to the **"🖼️ Annotated Pages Preview"** section.

Each page with detections has a card:
```
┌─────────────────────────┐
│ Page 3                  │
│ 12 devices detected     │
│ [View] [Download] ⬅️    │
└─────────────────────────┘
```

The **[Download]** button downloads that specific page as an annotated PDF.

## Troubleshooting

### No thumbnails appearing
- Check PDF file is valid
- Check file size < 500MB
- Check browser console for errors

### "Roboflow not configured" error
- Verify `.env` file exists
- Check API key is correct
- Restart application

### Download not working
- Make sure you analyzed pages first
- Check you're clicking "Download" button in preview grid
- Check browser's download settings

### Slow performance
- Enable "Skip blank tiles"
- Enable "Parallel processing"  
- Enable "Result caching"
- Reduce number of selected pages

## File Structure Quick Reference

```
fire-alarm-analyzer/
├── app.py                 ← Start here (run this)
├── config.py              ← Settings
├── .env                   ← Your API keys
├── templates/index.html   ← Web interface
├── static/
│   ├── css/style.css     ← Styles
│   └── js/main.js        ← Download links created here
└── routes/
    ├── analysis.py        ← Analysis endpoints
    └── preview.py         ← Download PDF endpoint
```

## API Endpoints Reference

- `POST /api/preview_pages` - Generate thumbnails
- `POST /api/analyze` - Run Roboflow analysis
- `GET /api/visualize/<job_id>/<page>` - Get annotated image
- `GET /api/download_annotated_pdf/<job_id>/<page>` - **Download PDF** ⬅️
- `GET /api/export/<job_id>` - Export JSON

## Common Questions

**Q: Where do I get API keys?**
- Roboflow: https://roboflow.com
- Gemini: https://makersuite.google.com/app/apikey

**Q: Can I analyze all pages?**
- Yes! Click "Select All" before analyzing

**Q: Why are there two analyze buttons?**
- Roboflow: Computer vision detection of devices
- Gemini: AI text extraction of specifications

**Q: How do I download all pages?**
- Click "Download" on each page card
- OR use export JSON and process separately

**Q: Can I change detection sensitivity?**
- Yes! Adjust the "Confidence" slider (default: 0.40)

## Next Steps

1. ✅ Test with a sample PDF
2. ✅ Explore different confidence levels
3. ✅ Try both Roboflow and Gemini analysis
4. ✅ Export results for record keeping
5. ✅ Read ARCHITECTURE.md for customization

## Support

- **Documentation**: README.md, ARCHITECTURE.md, MIGRATION_GUIDE.md
- **Code**: All modules have docstrings and comments
- **Issues**: Check browser console and terminal logs
