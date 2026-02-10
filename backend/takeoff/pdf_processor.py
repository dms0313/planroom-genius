"""
PDF Processing Module - Handles PDF to image conversion and tiling
"""
import logging
import re
from typing import Dict, Iterator, List, Tuple
import fitz  # PyMuPDF
from PIL import Image, ImageFilter, ImageStat

from .takeoff_config import DPI, TILE_SIZE, OVERLAP_PERCENT

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Handles PDF to image conversion and optimized tiling"""
    
    def __init__(self, dpi: int = DPI):
        self.dpi = dpi
    def extract_text_from_pdf(self, pdf_source):
        """
        Extract text content from each PDF page.
        Accepts either a filesystem path or raw PDF bytes.
        """
        try:
            # Determine whether it's a path or a file-like/bytes object
            if isinstance(pdf_source, (bytes, bytearray)):
                doc = fitz.open(stream=pdf_source, filetype="pdf")
            elif hasattr(pdf_source, "read"):  # e.g. Flask FileStorage
                doc = fitz.open(stream=pdf_source.read(), filetype="pdf")
            elif isinstance(pdf_source, str):
                doc = fitz.open(pdf_source)
            else:
                raise TypeError(f"Unsupported pdf_source type: {type(pdf_source)}")

            pages = []
            for i, page in enumerate(doc, start=1):
                raw_text = page.get_text()
                if not isinstance(raw_text, str):
                    raw_text = str(raw_text)

                cleaned_text = self._sanitize_text(raw_text)

                pages.append({
                    "page_number": i,
                    "text": cleaned_text
                })
            doc.close()
            return pages

        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}", exc_info=True)
            return []

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Ensure extracted PDF text is safe for downstream processing."""

        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")

        # Remove control characters except whitespace/newlines
        text = re.sub(r"[^\n\t\r\x20-\x7E]", "", text)
        return text
        
    def pdf_to_images(self, pdf_path: str, selected_pages: List[int] = None) -> List[Image.Image]:
        """
        Convert PDF to list of PIL Images
        
        Args:
            pdf_path: Path to PDF file
            selected_pages: Optional list of page numbers to process (1-indexed)
        
        Returns:
            List of PIL Image objects
        """
        try:
            logger.info(f"Opening PDF: {pdf_path}")
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            images = []
            
            # Determine which pages to process
            if selected_pages:
                pages_to_process = [p-1 for p in selected_pages if 1 <= p <= total_pages]
                logger.info(f"Processing selected pages: {[p+1 for p in pages_to_process]}")
            else:
                pages_to_process = range(total_pages)
                logger.info(f"Processing all {total_pages} pages")
            
            for page_num in pages_to_process:
                try:
                    page = doc[page_num]
                    logger.info(f"Processing page {page_num + 1}/{total_pages}")
                    
                    # Get page size and validate
                    page_size = page.rect.width * page.rect.height
                    if page_size == 0:
                        logger.warning(f"Page {page_num + 1} has zero size, skipping")
                        continue
                    
                    # Render page to image
                    mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                    try:
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                        if not pix or pix.width == 0 or pix.height == 0:
                            logger.warning(f"Invalid pixmap on page {page_num + 1}, skipping")
                            continue
                        
                        # Convert to PIL Image
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        images.append(img)
                        logger.info(f"Successfully processed page {page_num + 1} ({img.width}x{img.height})")
                    except Exception as render_err:
                        logger.error(f"Error rendering page {page_num + 1}: {str(render_err)}")
                        continue
                except Exception as page_err:
                    logger.error(f"Error processing page {page_num + 1}: {str(page_err)}")
                    continue
            
            doc.close()
            logger.info(f"Successfully converted {len(images)} pages")
            return images
            
        except Exception as e:
            logger.error(f"Error converting PDF to images: {str(e)}", exc_info=True)
            return []

    def iter_pdf_images(
        self,
        pdf_path: str,
        selected_pages: List[int] | None = None,
        render_dpi: int | None = None,
    ) -> Iterator[tuple[int, Image.Image]]:
        """Yield pages as PIL images one-at-a-time to keep memory usage low.

        Args:
            pdf_path: Path to the PDF file
            selected_pages: Optional list of 1-based page numbers to process
            render_dpi: Optional DPI override; defaults to the processor's DPI

        Yields:
            Tuples of (page_number, PIL Image)
        """
        try:
            logger.info("Opening PDF for streaming conversion: %s", pdf_path)
            with fitz.open(pdf_path) as doc:
                total_pages = len(doc)

                if selected_pages:
                    pages_to_process = [p - 1 for p in selected_pages if 1 <= p <= total_pages]
                    logger.info("Streaming selected pages: %s", [p + 1 for p in pages_to_process])
                else:
                    pages_to_process = range(total_pages)
                    logger.info("Streaming all %s pages", total_pages)

                render_dpi = render_dpi or self.dpi
                for page_num in pages_to_process:
                    pix = None
                    page = None
                    try:
                        page = doc[page_num]
                        page_size = page.rect.width * page.rect.height
                        if page_size == 0:
                            logger.warning("Page %s has zero size, skipping", page_num + 1)
                            continue

                        mat = fitz.Matrix(render_dpi / 72, render_dpi / 72)
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                        if not pix or pix.width == 0 or pix.height == 0:
                            logger.warning("Invalid pixmap on page %s, skipping", page_num + 1)
                            continue

                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        logger.info(
                            "Streamed page %s/%s (%sx%s)",
                            page_num + 1,
                            total_pages,
                            img.width,
                            img.height,
                        )
                        yield page_num + 1, img
                    except Exception as page_err:  # pragma: no cover - defensive logging
                        logger.error("Error streaming page %s: %s", page_num + 1, page_err)
                        continue
                    finally:
                        try:
                            pix = None
                            page = None
                        except Exception:
                            pass
        except Exception as exc:
            logger.error("Error streaming PDF pages from %s: %s", pdf_path, exc, exc_info=True)
            return
    
    @staticmethod
    def is_blank_tile(tile_image: Image.Image, threshold: float = 0.95,
                     variance_threshold: float = 100) -> bool:
        """
        Check if a tile is mostly blank/empty
        
        Args:
            tile_image: PIL Image tile
            threshold: White pixel ratio threshold
            variance_threshold: Variance threshold for uniformity
        
        Returns:
            True if tile is blank
        """
        gray = tile_image.convert('L')
        stats = ImageStat.Stat(gray)

        # Calculate white pixel ratio using histogram to avoid numpy dependency
        histogram = gray.histogram()
        white_pixels = sum(histogram[241:])  # pixels with value > 240
        total_pixels = tile_image.width * tile_image.height
        white_ratio = white_pixels / total_pixels if total_pixels else 0

        # Variance (low variance = uniform/blank content)
        variance = stats.var[0] if stats.var else 0

        return white_ratio > threshold or variance < variance_threshold
    
    @staticmethod
    def is_edge_tile(x: int, y: int, tile_size: int, img_width: int, 
                     img_height: int, margin: int = 50) -> bool:
        """
        Check if a tile is near the document edge
        
        Args:
            x, y: Tile position
            tile_size: Size of tile
            img_width, img_height: Image dimensions
            margin: Margin size in pixels
        
        Returns:
            True if tile is near edge
        """
        return (x < margin or 
                y < margin or 
                x + tile_size > img_width - margin or 
                y + tile_size > img_height - margin)
    
    @staticmethod
    def calculate_tile_complexity(tile_image: Image.Image) -> float:
        """
        Calculate complexity score for a tile
        Higher score = more content/edges = more likely to contain objects
        
        Args:
            tile_image: PIL Image tile
        
        Returns:
            Complexity score (float)
        """
        gray = tile_image.convert('L')

        # Use edge detection as proxy for content complexity without numpy
        edges_img = gray.filter(ImageFilter.FIND_EDGES)
        stats = ImageStat.Stat(edges_img)
        edge_sum = stats.sum[0] if stats.sum else 0

        # Normalize by total pixel intensity range to keep values comparable
        total_possible = tile_image.width * tile_image.height * 255
        return edge_sum / total_possible if total_possible else 0
    
    def create_tiles(self, image: Image.Image, tile_size: int = TILE_SIZE,
                     overlap: float = OVERLAP_PERCENT,
                     skip_blank: bool = True,
                     skip_edges: bool = False,
                     edge_margin: int = 50,
                     blank_threshold: float = 0.95,
                     prioritize_complex: bool = True) -> Tuple[List[Dict], Dict]:
        """
        Create tiles from image with advanced filtering and prioritization
        
        Args:
            image: PIL Image to tile
            tile_size: Size of each tile
            overlap: Overlap percentage between tiles
            skip_blank: Skip mostly blank tiles
            skip_edges: Skip tiles near document edges
            edge_margin: Margin size for edge detection
            blank_threshold: Threshold for blank detection
            prioritize_complex: Sort tiles by complexity
        
        Returns:
            Tuple of (tiles list, statistics dict)
        """
        tiles = []
        img_width, img_height = image.size

        # If the page is smaller than the configured tile size, fall back to a
        # single tile that covers the whole page. Previously we would generate
        # zero tiles, causing the analyzer to finish instantly with no results.
        if img_width <= tile_size or img_height <= tile_size:
            # The page is smaller than the tile size, so treat the whole page as a single tile.
            # This is a critical fix for a bug where small pages would produce zero tiles,
            # causing the analysis to silently fail with no results.

            # The tile's image is the full page image.
            tile_image = image.crop((0, 0, img_width, img_height))

            # The tile's dimensions match the page's dimensions.
            tiles.append({
                'id': 0,
                'image': tile_image,
                'x': 0,
                'y': 0,
                'width': img_width,
                'height': img_height,
                'complexity': self.calculate_tile_complexity(image) if prioritize_complex else 0
            })

            stats = {
                'total_created': 1,
                'blank_filtered': 0,
                'edge_filtered': 0,
                'kept': 1
            }

            return tiles, stats

        stride = int(tile_size * (1 - overlap))
        
        stats = {
            'total_created': 0,
            'blank_filtered': 0,
            'edge_filtered': 0,
            'kept': 0
        }
        
        tile_id = 0
        
        # Create main grid tiles
        for y in range(0, img_height - tile_size + 1, stride):
            for x in range(0, img_width - tile_size + 1, stride):
                stats['total_created'] += 1
                
                # Check if edge tile (skip if enabled)
                if skip_edges and self.is_edge_tile(x, y, tile_size, img_width, 
                                                     img_height, edge_margin):
                    stats['edge_filtered'] += 1
                    continue
                
                # Extract tile
                tile = image.crop((x, y, x + tile_size, y + tile_size))
                
                # Check if blank tile (skip if enabled)
                if skip_blank and self.is_blank_tile(tile, blank_threshold):
                    stats['blank_filtered'] += 1
                    continue
                
                # Calculate complexity for prioritization
                complexity = self.calculate_tile_complexity(tile) if prioritize_complex else 0
                
                tiles.append({
                    'id': tile_id,
                    'image': tile,
                    'x': x,
                    'y': y,
                    'width': tile_size,
                    'height': tile_size,
                    'complexity': complexity
                })
                tile_id += 1
                stats['kept'] += 1
        
        # Handle right edge tiles
        if img_width % stride != 0:
            x = img_width - tile_size
            for y in range(0, img_height - tile_size + 1, stride):
                if skip_edges and self.is_edge_tile(x, y, tile_size, img_width, 
                                                     img_height, edge_margin):
                    continue
                tile = image.crop((x, y, x + tile_size, y + tile_size))
                if skip_blank and self.is_blank_tile(tile, blank_threshold):
                    continue
                complexity = self.calculate_tile_complexity(tile) if prioritize_complex else 0
                tiles.append({
                    'id': tile_id,
                    'image': tile,
                    'x': x,
                    'y': y,
                    'width': tile_size,
                    'height': tile_size,
                    'complexity': complexity
                })
                tile_id += 1
                stats['kept'] += 1
        
        # Handle bottom edge tiles
        if img_height % stride != 0:
            y = img_height - tile_size
            for x in range(0, img_width - tile_size + 1, stride):
                if skip_edges and self.is_edge_tile(x, y, tile_size, img_width, 
                                                     img_height, edge_margin):
                    continue
                tile = image.crop((x, y, x + tile_size, y + tile_size))
                if skip_blank and self.is_blank_tile(tile, blank_threshold):
                    continue
                complexity = self.calculate_tile_complexity(tile) if prioritize_complex else 0
                tiles.append({
                    'id': tile_id,
                    'image': tile,
                    'x': x,
                    'y': y,
                    'width': tile_size,
                    'height': tile_size,
                    'complexity': complexity
                })
                tile_id += 1
                stats['kept'] += 1
        
        # Bottom-right corner
        if img_width % stride != 0 and img_height % stride != 0:
            x = img_width - tile_size
            y = img_height - tile_size
            if not (skip_edges and self.is_edge_tile(x, y, tile_size, img_width, 
                                                     img_height, edge_margin)):
                tile = image.crop((x, y, x + tile_size, y + tile_size))
                if not (skip_blank and self.is_blank_tile(tile, blank_threshold)):
                    complexity = self.calculate_tile_complexity(tile) if prioritize_complex else 0
                    tiles.append({
                        'id': tile_id,
                        'image': tile,
                        'x': x,
                        'y': y,
                        'width': tile_size,
                        'height': tile_size,
                        'complexity': complexity
                    })
                    stats['kept'] += 1
        
        # Sort by complexity if prioritization enabled
        if prioritize_complex and tiles:
            tiles.sort(key=lambda t: t['complexity'], reverse=True)

        # If all tiles were filtered out (e.g., blank/edge filtering too strict),
        # fall back to a single tile that covers the full page so detection still
        # runs and surfaces useful warnings instead of silently returning 0.
        if not tiles:
            logger.warning(
                "No tiles created after filtering; using full-page fallback tile"
            )
            tiles = [{
                'id': 0,
                'image': image,
                'x': 0,
                'y': 0,
                'width': img_width,
                'height': img_height,
                'complexity': self.calculate_tile_complexity(image) if prioritize_complex else 0
            }]
            stats['kept'] = 1

        return tiles, stats
