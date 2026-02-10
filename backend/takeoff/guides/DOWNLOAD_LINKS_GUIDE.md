# 📥 Download Links - Complete Guide

## Where Are the Download Links?

After you analyze your PDF, download links appear in **TWO PLACES**:

### 1. Preview Grid Cards (Main Download Location)

After analysis, scroll to the **"🖼️ Annotated Pages Preview"** section.

```
Visual Layout:
┌─────────────────────────────────────────────────────┐
│  🖼️ Annotated Pages Preview                        │
│  Click any image to view in full screen             │
│                                                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐      │
│  │ Page 1    │  │ Page 3    │  │ Page 7    │      │
│  │ 5 devices │  │ 12 devices│  │ 8 devices │      │
│  │           │  │           │  │           │      │
│  │ [View] [Download] ← Click here to download!      │
│  └───────────┘  └───────────┘  └───────────┘      │
└─────────────────────────────────────────────────────┘
```

### 2. Full-Screen Modal

Click any preview card → Opens full-screen view → Click **"📥 Download PDF"** button

```
┌─────────────────────────────────────────────────────┐
│  X (close)                                          │
│                                                      │
│         [Large preview of annotated page]           │
│                                                      │
│              Page 3                                  │
│         [📥 Download PDF] ← Alternative download     │
└─────────────────────────────────────────────────────┘
```

## How the Download System Works

### Frontend (static/js/main.js)

When analysis completes, JavaScript creates download buttons:

```javascript
// Line ~200 in main.js
data.page_analyses.forEach(page => {
    if (page && page.devices.length > 0) {
        const previewCard = document.createElement('div');
        previewCard.className = 'preview-card';
        previewCard.innerHTML = `
            <div class="preview-card-title">Page ${page.page_number}</div>
            <div class="preview-card-info">${page.devices.length} devices detected</div>
            <div class="preview-actions">
                <button class="preview-btn view" 
                    onclick="viewPage('${data.job_id}', ${page.page_number})">
                    View
                </button>
                <button class="preview-btn download" 
                    onclick="downloadPage('${data.job_id}', ${page.page_number})">
                    Download ⬅️ THIS BUTTON!
                </button>
            </div>
        `;
        previewGrid.appendChild(previewCard);
    }
});
```

### Download Function (static/js/main.js)

```javascript
// Line ~240 in main.js
async function downloadPage(jobId, pageNum) {
    // 1. Fetch annotated PDF from backend
    const response = await fetch(`/api/download_annotated_pdf/${jobId}/${pageNum}`);
    
    // 2. Create blob from response
    const blob = await response.blob();
    
    // 3. Create temporary download link
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annotated_page_${pageNum}.pdf`;
    
    // 4. Trigger download
    document.body.appendChild(a);
    a.click();  // ⬅️ This starts the download!
    
    // 5. Cleanup
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}
```

### Backend Endpoint (routes/preview.py)

```python
# Line ~90 in preview.py
@app.route("/api/download_annotated_pdf/<job_id>/<int:page_num>")
def download_annotated_pdf(job_id, page_num):
    # 1. Get analysis results
    job = analysis_jobs[job_id]
    
    # 2. Load PDF page
    doc = fitz.open(job['pdf_path'])
    page = doc[page_num - 1]
    
    # 3. Render to image at 180 DPI
    pix = page.get_pixmap(matrix=mat)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    # 4. Draw detection boxes
    for device in devices:
        draw.rectangle([x, y, x+w, y+h], outline="red", width=3)
        draw.text((x, y), label, fill="red")
    
    # 5. Convert image back to PDF
    pdf_output = fitz.open()
    img_pdf = fitz.open("pdf", annotated_image.tobytes("ppm"))
    pdf_output.insert_pdf(img_pdf)
    
    # 6. Return PDF file
    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=True,  # ⬅️ Forces download
        download_name=f'annotated_page_{page_num}.pdf'
    )
```

## Download Flow Diagram

```
User clicks "Download" button
         ↓
downloadPage(jobId, pageNum) called (main.js)
         ↓
Fetch: GET /api/download_annotated_pdf/abc123/3
         ↓
Backend: download_annotated_pdf() function (preview.py)
         ↓
1. Retrieve job data
2. Open PDF page
3. Render to image (180 DPI)
4. Draw detection boxes on image
5. Convert annotated image to PDF
         ↓
Return PDF with headers:
  Content-Type: application/pdf
  Content-Disposition: attachment; filename="annotated_page_3.pdf"
         ↓
Browser receives PDF blob
         ↓
JavaScript creates temporary <a> tag
         ↓
Programmatically clicks link
         ↓
Browser downloads file: annotated_page_3.pdf ✅
```

## Testing the Download Links

### Test 1: Verify Links Appear

1. Upload a PDF
2. Select pages
3. Click "Analyze Fire Alarm Systems"
4. Wait for analysis to complete
5. Scroll to "🖼️ Annotated Pages Preview"
6. **Expected**: Each page with devices shows [View] [Download] buttons

### Test 2: Download Single Page

1. Find a page card in the preview grid
2. Click the **"Download"** button
3. **Expected**: Browser downloads `annotated_page_X.pdf`

### Test 3: Modal Download

1. Click **"View"** on any page card
2. Full-screen modal opens
3. Click **"📥 Download PDF"** button
4. **Expected**: Same as Test 2

### Test 4: Multiple Downloads

1. Click "Download" on Page 1 → Downloads `annotated_page_1.pdf`
2. Click "Download" on Page 3 → Downloads `annotated_page_3.pdf`
3. Click "Download" on Page 5 → Downloads `annotated_page_5.pdf`
4. **Expected**: Three separate PDF files in downloads folder

## Troubleshooting

### Problem: No download buttons visible

**Cause**: No devices detected on any page

**Solution**:
- Check PDF contains fire alarm symbols
- Lower confidence threshold (try 0.30)
- Verify Roboflow model is working

### Problem: Download button doesn't respond

**Check**:
1. Open browser console (F12)
2. Look for JavaScript errors
3. Check network tab for failed requests

**Common fixes**:
- Hard refresh page (Ctrl+Shift+R)
- Clear browser cache
- Check job_id is valid

### Problem: Download fails with error

**Check backend logs**:
```bash
python app.py
# Look for errors in terminal
```

**Common errors**:
- "Job not found" → Analysis expired, re-analyze
- "Page not analyzed" → Page wasn't selected
- "PDF error" → PDF file corrupted

### Problem: Downloaded PDF is blank

**Cause**: Detection coordinates not scaled properly

**Check** in `routes/preview.py`:
```python
# Should have these lines:
training_dpi = 350
render_dpi = 180
scale_factor = render_dpi / training_dpi  # Should be ~0.51

# Coordinates should be scaled:
x = float(device['x']) * scale_factor
y = float(device['y']) * scale_factor
```

## Customizing Downloads

### Change PDF Filename

Edit `routes/preview.py` line 192:
```python
download_name=f'fire_alarm_page_{page_num}.pdf'  # Custom name
```

### Change Image Quality

Edit `routes/preview.py` line 141:
```python
render_dpi = 300  # Higher quality (larger file)
```

### Add Watermark

Edit `routes/preview.py` after line 171:
```python
# Add watermark
draw.text((10, 10), "MyCompany Analysis", fill="blue", font=font)
```

### Include Multiple Pages

Create new route that combines pages:
```python
@app.route("/api/download_all/<job_id>")
def download_all_pages(job_id):
    pdf_output = fitz.open()
    for page_num in analyzed_pages:
        # Process each page
        # Add to pdf_output
    return send_file(pdf_output.tobytes(), ...)
```

## API for Download Links

If building a custom frontend:

```javascript
// Get download URL
const downloadUrl = `/api/download_annotated_pdf/${jobId}/${pageNum}`;

// Option 1: Direct browser download
window.location.href = downloadUrl;

// Option 2: Fetch and process
const response = await fetch(downloadUrl);
const blob = await response.blob();
// Do something with blob...

// Option 3: Open in new tab
window.open(downloadUrl, '_blank');
```

## Summary

**Download links are created in**: `static/js/main.js` (displayResults function)

**Download handled by**: `routes/preview.py` (download_annotated_pdf endpoint)

**Location in UI**: Preview grid cards and full-screen modal

**File format**: PDF with detection boxes drawn in red

**Filename format**: `annotated_page_X.pdf` where X is page number

The download system is fully functional and ready to use! 🎉
