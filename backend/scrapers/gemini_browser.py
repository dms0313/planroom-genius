"""
Gemini-powered browser automation helper.
Uses AI vision to analyze screenshots and guide browser interactions.
Compatible with Playwright page objects.
"""
import os
import sys
import base64
import json
import asyncio
from io import BytesIO

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[GeminiBrowser] google-genai not installed")

# Get API key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


class GeminiBrowser:
    """
    AI-powered browser helper that uses Gemini vision to analyze pages
    and determine what actions to take.
    """

    def __init__(self, page, model="gemini-2.5-flash"):
        """
        Initialize with a Playwright page instance.

        Args:
            page: Playwright page object
            model: Gemini model to use for vision analysis
        """
        self.page = page
        self.model = model
        self.client = None

        if GEMINI_AVAILABLE and GEMINI_API_KEY:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
            print(f"[GeminiBrowser] Initialized with model: {model}")
        else:
            print("[GeminiBrowser] WARNING: Gemini not available")

    async def take_screenshot(self):
        """Take a screenshot and return as base64."""
        screenshot_bytes = await self.page.screenshot()
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def _call_gemini(self, prompt, image_base64):
        """Call Gemini with an image and prompt."""
        if not self.client:
            return None

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(
                        data=base64.b64decode(image_base64),
                        mime_type="image/png"
                    ),
                    types.Part.from_text(text=prompt)
                ]
            )
            return response.text
        except Exception as e:
            print(f"[GeminiBrowser] Gemini error: {e}")
            return None

    async def find_and_click(self, description, max_attempts=3):
        """
        Use Gemini to find an element matching the description and click it.

        Args:
            description: Natural language description of what to click
            max_attempts: Number of retry attempts

        Returns:
            bool: True if clicked successfully
        """
        print(f"[GeminiBrowser] Finding: {description}")

        for attempt in range(max_attempts):
            screenshot = await self.take_screenshot()

            prompt = f"""Analyze this screenshot of a web page.

I need to click on: {description}

Look at the page and find this element. Return a JSON object with:
- "found": true/false - whether you can see the element
- "x": the x coordinate (pixels from left) of the CENTER of the element to click
- "y": the y coordinate (pixels from top) of the CENTER of the element to click
- "confidence": 0-100 how confident you are this is the right element
- "element_text": the visible text of the element (if any)

IMPORTANT:
- Return ONLY valid JSON, no markdown or explanation
- Coordinates should be the CENTER of the clickable element
- If the element is not visible on screen, set found to false

Example response:
{{"found": true, "x": 450, "y": 320, "confidence": 95, "element_text": "View Project Details"}}
"""

            response = self._call_gemini(prompt, screenshot)

            if not response:
                print(f"[GeminiBrowser] No response from Gemini (attempt {attempt + 1})")
                continue

            try:
                # Clean response - remove markdown code blocks if present
                cleaned = response.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                cleaned = cleaned.strip()

                result = json.loads(cleaned)

                if result.get("found") and result.get("confidence", 0) >= 70:
                    x = result["x"]
                    y = result["y"]
                    print(f"[GeminiBrowser] Found at ({x}, {y}) - confidence: {result.get('confidence')}%")
                    print(f"[GeminiBrowser] Element text: {result.get('element_text', 'N/A')}")

                    # Click at coordinates
                    await self.page.mouse.click(x, y)
                    print(f"[GeminiBrowser] Clicked at ({x}, {y})")
                    await asyncio.sleep(1)
                    return True
                else:
                    print(f"[GeminiBrowser] Element not found or low confidence: {result}")

            except json.JSONDecodeError as e:
                print(f"[GeminiBrowser] JSON parse error: {e}")
                print(f"[GeminiBrowser] Raw response: {response[:200]}")

            await asyncio.sleep(1)

        print(f"[GeminiBrowser] Failed to find: {description}")
        return False

    async def extract_project_url(self):
        """
        Use Gemini to extract the project details URL from the current page.

        Returns:
            str: Project URL or None
        """
        screenshot = await self.take_screenshot()

        prompt = """Analyze this screenshot of PlanHub.

I need to navigate to the project details page. Look at the page and tell me:

1. Is there a "View Project Details" button visible? If yes, where is it?
2. Is there a project link or URL visible that would take me to project details?
3. What is the current state of the page? (project list, quick view panel open, details page, etc.)

Return a JSON object with:
- "state": current page state ("list", "quick_view", "details", "unknown")
- "view_details_button": {"visible": true/false, "x": coord, "y": coord} if button exists
- "project_url": extracted URL if visible (or null)
- "recommendation": what action to take next

Return ONLY valid JSON.
"""

        response = self._call_gemini(prompt, screenshot)

        if response:
            try:
                cleaned = response.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                cleaned = cleaned.strip()

                result = json.loads(cleaned)
                print(f"[GeminiBrowser] Page analysis: {result}")
                return result
            except:
                pass

        return None

    async def navigate_to_project_details(self, project_name):
        """
        Use AI to navigate from project list to project details page.

        Args:
            project_name: Name of the project to navigate to

        Returns:
            bool: True if successfully navigated to details page
        """
        print(f"[GeminiBrowser] Navigating to details for: {project_name[:40]}...")

        # Step 1: Click on the project row
        clicked = await self.find_and_click(
            f"the table row or project name containing '{project_name[:30]}'"
        )

        if not clicked:
            print("[GeminiBrowser] Could not click project row")
            return False

        await asyncio.sleep(2)

        # Step 2: Analyze page state and find View Project Details button
        analysis = await self.extract_project_url()

        if analysis:
            state = analysis.get("state", "unknown")
            print(f"[GeminiBrowser] Page state: {state}")

            if state == "details":
                print("[GeminiBrowser] Already on details page!")
                return True

            # If quick view is open, click View Project Details button
            if state == "quick_view" or analysis.get("view_details_button", {}).get("visible"):
                btn_info = analysis.get("view_details_button", {})
                if btn_info.get("visible") and btn_info.get("x") and btn_info.get("y"):
                    print(f"[GeminiBrowser] Clicking View Project Details at ({btn_info['x']}, {btn_info['y']})")
                    await self.page.mouse.click(btn_info["x"], btn_info["y"])
                    await asyncio.sleep(3)
                else:
                    # Use find_and_click as fallback
                    await self.find_and_click("View Project Details button")
                    await asyncio.sleep(3)

        # Verify we're on details page
        current_url = self.page.url
        if '/project/' in current_url and '/list' not in current_url:
            print(f"[GeminiBrowser] Successfully navigated to: {current_url}")
            return True

        # One more attempt to click View Project Details
        print("[GeminiBrowser] Trying once more to find View Project Details...")
        await self.find_and_click("View Project Details button")
        await asyncio.sleep(3)

        current_url = self.page.url
        return '/project/' in current_url and '/list' not in current_url

    async def click_element_by_description(self, description):
        """
        Generic method to click any element described in natural language.

        Args:
            description: What to click (e.g., "the Files tab", "Select All checkbox")

        Returns:
            bool: True if clicked
        """
        return await self.find_and_click(description)

    async def extract_text_from_region(self, description):
        """
        Use Gemini to extract text from a described region of the page.

        Args:
            description: Description of what text to extract

        Returns:
            str: Extracted text or None
        """
        screenshot = await self.take_screenshot()

        prompt = f"""Analyze this screenshot and extract the following information:

{description}

Return ONLY the extracted text value, no explanation or formatting.
If the information is not visible, return "NOT_FOUND".
"""

        response = self._call_gemini(prompt, screenshot)

        if response:
            text = response.strip()
            if text != "NOT_FOUND":
                return text

        return None
