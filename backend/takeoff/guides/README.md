# 🚨 Fire Alarm PDF Analyzer - Version 5

A modular, optimized PDF analysis application that uses computer vision (Roboflow) and AI (Gemini) to detect and analyze fire alarm systems in construction bid documents.

## ✨ Features

- **🎯 Roboflow Detection**: Detect fire alarm devices (smoke detectors, pull stations, etc.) using computer vision
- **🤖 Gemini AI Analysis**: Extract specifications, notes, and project details using AI
- **⚡ Performance Optimizations**:
  - Blank tile filtering (1.5-3x speedup)
  - Edge tile filtering (1.2-1.5x speedup)
  - Parallel processing (2-8x speedup)
  - Result caching for identical tiles
  - Smart prioritization of content-rich tiles
- **📊 Page Selection**: Choose specific pages to analyze
- **🖼️ Visual Results**: View annotated pages with detected devices
- **📥 Export**: Download results as JSON or annotated PDFs

## 📁 Project Structure

```
fire-alarm-analyzer/
├── app.py                      # Main application entry point
├── config.py                   # Configuration and environment variables
├── models.py                   # Data models (FireAlarmDevice, PageAnalysis)
├── requirements.txt            # Python dependencies
├── .env.example               # Environment variables template
├── README.md                   # This file
├── modules/                    # Core processing modules
│   ├── __init__.py
│   ├── pdf_processor.py       # PDF → image conversion and tiling
│   ├── roboflow_detector.py   # Roboflow API integration and caching
│   ├── gemini_analyzer.py     # Gemini AI text analysis
│   └── visualizer.py          # Detection visualization and NMS
├── routes/                     # Flask API endpoints
│   ├── __init__.py
│   ├── analysis.py            # Analysis endpoints
│   └── preview.py             # Preview and download endpoints
├── templates/                  # HTML templates
│   └── index.html             # Main web interface
└── static/                     # Static assets
    ├── css/
    │   └── style.css          # Styles
    └── js/
        └── main.js            # Client-side logic
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd fire-alarm-analyzer
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```env
# Required for Roboflow detection
ROBOFLOW_API_KEY=your_roboflow_api_key
ROBOFLOW_WORKSPACE=your_workspace
ROBOFLOW_PROJECT=your_project
ROBOFLOW_VERSION=1

# Optional for Gemini AI analysis
GEMINI_API_KEY=your_gemini_key

# Optional
PORT=5000
```

### 3. Run the Application

```bash
python app.py
```

Open your browser to: `http://localhost:5000`

## 🔧 Configuration

### config.py

All configuration settings are centralized in `config.py`:

```python
# Processing Settings
TILE_SIZE = 640                # Size of detection tiles
DPI = 350                      # PDF rendering resolution
OVERLAP_PERCENT = 0.25         # Tile overlap percentage
DEFAULT_CONFIDENCE = 0.40      # Detection confidence threshold
MAX_WORKERS = 4                # Parallel processing workers
MAX_CACHE_SIZE = 1000          # Tile cache size

# Flask Settings
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max upload
PORT = 5000
```

## 📦 Module Details

### 1. PDF Processor (`modules/pdf_processor.py`)

Handles PDF to image conversion and intelligent tiling:

```python
from modules import PDFProcessor

processor = PDFProcessor(dpi=350)

# Convert PDF to images
images = processor.pdf_to_images('document.pdf', selected_pages=[1, 2, 3])

# Create optimized tiles
tiles, stats = processor.create_tiles(
    image,
    skip_blank=True,      # Skip mostly blank tiles
    skip_edges=False,     # Skip document edges
    prioritize_complex=True  # Process content-rich tiles first
)
```

### 2. Roboflow Detector (`modules/roboflow_detector.py`)

Handles object detection with caching and parallel processing:

```python
from modules import RoboflowDetector

detector = RoboflowDetector(api_key, workspace, project, version)

# Parallel detection with caching
detections, stats = detector.process_all_tiles_parallel(
    tiles,
    confidence=0.40,
    max_workers=4,
    use_cache=True
)
```

**Features:**
- LRU tile cache to avoid reprocessing identical tiles
- Parallel processing for faster analysis
- Automatic coordinate transformation
- Retry logic with exponential backoff

### 3. Visualizer (`modules/visualizer.py`)

Draws detection boxes and performs Non-Maximum Suppression:

```python
from modules import DetectionVisualizer

visualizer = DetectionVisualizer()

# Remove overlapping detections
filtered = visualizer.remove_overlapping_detections(detections, iou_threshold=0.5)

# Draw bounding boxes
annotated_image = visualizer.draw_detections(image, filtered)
```

### 4. Gemini Analyzer (`modules/gemini_analyzer.py`)

Extracts text-based specifications using Gemini AI:

```python
from modules import GeminiAnalyzer

analyzer = GeminiAnalyzer()

# Analyze PDF text
results = analyzer.analyze_pdf_text(pages_text)
# Returns: project_info, code_requirements, fa_pages, fa_notes, etc.
```

## 🌐 API Endpoints

### Status Check
```
GET /api/check_status
```
Returns API configuration status

### Preview Pages
```
POST /api/preview_pages
Body: multipart/form-data with 'pdf' file
```
Generates page thumbnails for selection

### Analyze PDF (Roboflow)
```
POST /api/analyze
Body: multipart/form-data
  - pdf: PDF file
  - selected_pages: "1,2,3" (optional)
  - skip_blank: "true"/"false"
  - skip_edges: "true"/"false"
  - use_parallel: "true"/"false"
  - use_cache: "true"/"false"
  - confidence: "0.40"
```

### Analyze PDF (Gemini)
```
POST /api/analyze_gemini
Body: multipart/form-data with 'pdf' file
```

### Visualize Page
```
GET /api/visualize/<job_id>/<page_num>
```
Returns annotated JPEG image

### Download Annotated PDF
```
GET /api/download_annotated_pdf/<job_id>/<page_num>
```
Returns annotated PDF file

### Export Results
```
GET /api/export/<job_id>
```
Returns JSON results file

## 🏗️ Architecture Benefits

### Modularity
- **Separation of Concerns**: Each module has a single responsibility
- **Easy Testing**: Test modules independently
- **Maintainability**: Changes to one module don't affect others

### Scalability
- **Parallel Processing**: Utilize multiple CPU cores
- **Caching**: Avoid redundant computations
- **Configurable**: Adjust performance settings easily

### Extensibility
- **Add New Detectors**: Implement new detection backends
- **Custom Visualizations**: Create different visualization styles
- **Additional Analyzers**: Add more AI analysis engines

## 🔍 Usage Examples

### Basic Analysis
```python
from app import analyzer

# Analyze PDF with default settings
images = analyzer.pdf_processor.pdf_to_images('bid_set.pdf')
tiles, stats = analyzer.pdf_processor.create_tiles(images[0])
detections, proc_stats = analyzer.roboflow_detector.process_all_tiles_parallel(tiles)
```

### Custom Analysis Pipeline
```python
# Configure custom processing
tiles, stats = analyzer.pdf_processor.create_tiles(
    image,
    tile_size=1024,           # Larger tiles
    overlap=0.30,             # More overlap
    skip_blank=True,
    skip_edges=True,
    edge_margin=100           # Larger margin
)

# Process with custom confidence
detections, _ = analyzer.roboflow_detector.process_all_tiles_parallel(
    tiles,
    confidence=0.50,          # Higher confidence
    max_workers=8,            # More workers
    use_cache=True
)
```

## 📊 Performance Metrics

The application tracks performance metrics:

```json
{
  "processing_stats": {
    "cache_stats": {
      "hits": 150,
      "misses": 50,
      "hit_rate": 75.0,
      "size": 200
    },
    "total_time": 12.5,
    "processed": 200,
    "objects_found": 45
  }
}
```

## 🐛 Troubleshooting

### Roboflow not initializing
- Check API key in `.env`
- Verify workspace and project names
- Check internet connection

### Out of memory errors
- Reduce `DPI` in config.py
- Enable `skip_blank=True`
- Reduce `MAX_WORKERS`
- Lower `TILE_SIZE`

### Slow performance
- Enable `use_parallel=True`
- Enable `use_cache=True`
- Enable `skip_blank=True`
- Increase `MAX_WORKERS` (if CPU allows)

## 📝 Development

### Adding a New Module

1. Create module file in `modules/`
2. Add to `modules/__init__.py`
3. Import in `app.py`
4. Update `README.md`

### Adding a New Route

1. Create function in appropriate route file
2. Register in route file's `register_*_routes()` function
3. Update API documentation

## 📄 License

This project is for internal use in the fire alarm and security systems industry.

## 🤝 Contributing

Contact the development team for contribution guidelines.

## 📧 Support

For issues or questions, please contact the project maintainers.
