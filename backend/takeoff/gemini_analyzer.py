"""
Gemini Analyzer Module
Handles AI-powered analysis of fire alarm specifications using Google's Gemini API
"""

from __future__ import annotations

import copy
import io
import logging
import os
import json
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from PIL import Image
from google import genai
from google.genai import types

from google.api_core import exceptions as core_exceptions
from .pdf_processor import PDFProcessor
from .takeoff_config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MODEL_CHOICES,
)

EXTRACTION_MODE = "extraction"
ADVISORY_MODE = "advisory"
ANALYSIS_MODES = (EXTRACTION_MODE, ADVISORY_MODE)

_SHARED_INSTRUCTION_GUARDRAILS = (
    "MANDATORY OUTPUT GUARDRAILS:\n"
    "- Do not invent or infer specific code section numbers, clause IDs, or legal citations that are not explicitly present in the provided documents.\n"
    "- If a requested value cannot be found in the provided documents, output exactly 'unknown' for that value.\n"
    "- Every nontrivial factual claim must include a page citation in the corresponding field/object (e.g., page number or page list).\n"
    "- When estimating device counts, clearly label them as 'estimated from drawings' vs 'specified in schedule.'\n"
    "- Distinguish between what is SHOWN on drawings vs what is only listed in the symbol legend.\n"
)

EXTRACTION_MODE_SYSTEM_INSTRUCTIONS = (
    "You are a senior fire alarm estimator with 20+ years of experience reviewing construction bid documents.\n"
    "You are operating in EXTRACTION MODE — strict factual extraction only.\n"
    "\n"
    "DOMAIN EXPERTISE TO APPLY:\n"
    "- Think like an estimator preparing a competitive bid. Extract everything needed to price the job.\n"
    "- Cross-reference across drawing disciplines: mechanical schedules reveal duct detectors, architectural plans reveal occupancy and area, "
    "electrical plans reveal panel locations and circuit requirements, plumbing plans may show sprinkler tie-ins.\n"
    "- Quantify when possible — don't just say 'smoke detectors required,' count how many are shown on drawings.\n"
    "- Pay attention to keyed notes, general notes, and abbreviation legends — these often contain critical scope details.\n"
    "- Look for items that affect labor: ceiling heights, concealed vs exposed wiring, access difficulties, phasing requirements.\n"
    "\n"
    "Focus only on information explicitly present in the provided documents.\n"
    "Do not provide strategy, competitive positioning, bid advice, value engineering recommendations, or optimization suggestions.\n"
    "Use neutral language and preserve ambiguity from source documents instead of filling gaps.\n\n"
    f"{_SHARED_INSTRUCTION_GUARDRAILS}"
)

ADVISORY_MODE_SYSTEM_INSTRUCTIONS = (
    "You are a senior fire alarm estimator with 20+ years of experience reviewing construction bid documents.\n"
    "You are operating in ADVISORY MODE — factual extraction PLUS estimator guidance.\n"
    "\n"
    "DOMAIN EXPERTISE TO APPLY:\n"
    "- Think like an estimator preparing a competitive bid. Extract everything needed to price the job.\n"
    "- Cross-reference across drawing disciplines: mechanical schedules reveal duct detectors, architectural plans reveal occupancy and area, "
    "electrical plans reveal panel locations and circuit requirements, plumbing plans may show sprinkler tie-ins.\n"
    "- Quantify when possible — don't just say 'smoke detectors required,' count how many are shown on drawings.\n"
    "- Pay attention to keyed notes, general notes, and abbreviation legends — these often contain critical scope details.\n"
    "- Look for items that affect labor: ceiling heights, concealed vs exposed wiring, access difficulties, phasing requirements.\n"
    "\n"
    "First provide strict factual extraction from the provided documents.\n"
    "Then provide estimator advisory guidance, clearly labeled as [ADVISORY]:\n"
    "- Suggest value engineering opportunities (e.g., 'If AHJ allows, horn/strobes could replace speaker/strobes to reduce cost').\n"
    "- Note where alternate manufacturers could save cost or improve schedule.\n"
    "- Flag scope gaps the GC may RFI about or areas where the spec is ambiguous.\n"
    "- Provide rough labor hour guidance when device counts are visible (e.g., 'Approximately 45 devices — typical 2-person crew, 3-4 day install').\n"
    "- Identify coordination risks with other trades (HVAC duct detector access, ceiling grid conflicts, etc.).\n"
    "\n"
    "Any advisory statement must explicitly include uncertainty language and a jurisdiction caveat (AHJ/code cycle/local amendments may differ).\n"
    "Never present advisory content as certain fact.\n\n"
    f"{_SHARED_INSTRUCTION_GUARDRAILS}"
)

SYSTEM_INSTRUCTIONS_BY_MODE = {
    EXTRACTION_MODE: EXTRACTION_MODE_SYSTEM_INSTRUCTIONS,
    ADVISORY_MODE: ADVISORY_MODE_SYSTEM_INSTRUCTIONS,
}

logger = logging.getLogger("fire-alarm-analyzer")


class GeminiPromptBlocked(RuntimeError):
    """Raised when Gemini blocks a prompt due to safety or policy filters."""

    def __init__(self, message: str, prompt_feedback: Any = None):
        super().__init__(message)
        self.prompt_feedback = prompt_feedback


class GeminiRequestFailed(RuntimeError):
    """Raised when Gemini consistently fails to generate a response."""

    def __init__(self, message: str, prompt_feedback: Any = None):
        super().__init__(message)
        self.prompt_feedback = prompt_feedback


@dataclass
class ModelTextResult:
    """Container for Gemini text generation results, including errors."""

    text: Optional[str] = None
    error: Optional[str] = None
    prompt_feedback: Optional[Dict[str, Any]] = None
    blocked: bool = False
    empty_response: bool = False
    model: Optional[str] = None

class GeminiFireAlarmAnalyzer:
    """AI-powered fire alarm specification analyzer using Gemini"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini analyzer"""
        self.api_key = api_key or GEMINI_API_KEY
        self.client: Optional[genai.Client] = None
        self.current_model = GEMINI_MODEL
        self.available_models = GEMINI_MODEL_CHOICES
        self.pdf_processor = PDFProcessor()
        self.initialization_error: Optional[str] = None
        self.last_prompt_feedback: Optional[Dict[str, Any]] = None
        self.max_retries = int(os.environ.get("GEMINI_MAX_RETRIES", "2"))
        self.request_timeout = int(os.environ.get("GEMINI_REQUEST_TIMEOUT_SECONDS", "240"))
        self.max_image_pages = int(os.environ.get("GEMINI_MAX_IMAGE_PAGES", "15"))
        self.image_render_dpi = int(os.environ.get("GEMINI_IMAGE_DPI", "200"))
        self.image_max_dimension = int(os.environ.get("GEMINI_IMAGE_MAX_DIMENSION", "1400"))
        self.image_jpeg_quality = int(os.environ.get("GEMINI_IMAGE_JPEG_QUALITY", "80"))
        self.tried_models: List[str] = []
        self.default_analysis_mode = ADVISORY_MODE
        self.analysis_mode = self.default_analysis_mode
        self.default_system_instructions = SYSTEM_INSTRUCTIONS_BY_MODE[self.default_analysis_mode]
        self.system_instructions = self.default_system_instructions

        if self.api_key:
            self._initialize_model(self.current_model)
        else:
            self.initialization_error = "GEMINI_API_KEY not found. AI Analysis will be disabled."
            logger.warning(self.initialization_error)

    def _initialize_model(self, model_name: str) -> bool:
        """Configure the Gemini client with the requested model."""

        if not self.api_key:
            self.initialization_error = "GEMINI_API_KEY not found. AI Analysis will be disabled."
            logger.warning(self.initialization_error)
            return False

        try:
            self.client = genai.Client(api_key=self.api_key)
            self.current_model = model_name
            self.initialization_error = None
            if model_name not in self.tried_models:
                self.tried_models.append(model_name)
            logger.info(f"✅ Gemini AI initialized successfully with {model_name}")
            return True
        except Exception as exc:  # pragma: no cover - depends on runtime credentials
            self.client = None
            self.initialization_error = str(exc)
            logger.error("Failed to initialize Gemini: %s", self.initialization_error)
            return False

    def update_model(self, model_name: str) -> bool:
        """Switch the active Gemini text model at runtime."""

        target = model_name or self.current_model
        return True if target == self.current_model else self._initialize_model(target)

    def _build_generation_config(self) -> Dict[str, Any]:
        """Return the config dict expected by the Gemini SDK."""

        return {
            "candidate_count": 1,
        }

    def _current_generation_settings(self) -> Dict[str, Any]:
        """Return the runtime generation settings used for Gemini requests."""

        return {
            "model": self.current_model,
            "generation_config": self._build_generation_config(),
            "max_retries": self.max_retries,
            "request_timeout_seconds": self.request_timeout,
        }
    
    def is_available(self) -> bool:
        """Return True if Gemini model is initialized and ready."""
        return self.client is not None

    @staticmethod
    def _parse_json(raw_text: str, default: Any) -> Any:
        """Safely parse JSON from Gemini responses"""
        if not raw_text:
            return default
        
        # Clean up markdown code blocks
        cleaned = re.sub(r"^```(?:json)?", "", raw_text.strip(), flags=re.IGNORECASE | re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE)
        
        # Find the first valid JSON object or array
        match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if not match:
            logger.warning(f"No JSON object or array found in Gemini response: {cleaned}")
            return default
            
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.error(f"Failed to parse JSON: {exc}. Raw string was: {json_str}")
            # Try to fix common issues like trailing commas
            json_str = re.sub(r",\s*([\]\}])", r"\1", json_str)
            try:
                return json.loads(json_str)
            except Exception:
                logger.error("Failed to parse JSON even after attempting fixes.")
                return default

    @staticmethod
    def _normalize_claim_text(claim: Any) -> str:
        return re.sub(r"\s+", " ", str(claim or "").strip().lower())

    def _validate_high_impact_claims(self, payload: Any) -> Any:
        """Drop or flag high-impact claims that do not include required evidence."""
        if not isinstance(payload, dict):
            return payload

        high_impact = payload.get('high_impact_claims')
        if not isinstance(high_impact, dict):
            return payload

        evidence = high_impact.get('evidence')
        if not isinstance(evidence, dict):
            evidence = {}

        warnings = high_impact.get('validation_warnings')
        if not isinstance(warnings, list):
            warnings = []

        claim_fields = ('required_vendors', 'required_manufacturers', 'code_requirements', 'deal_breakers')
        sanitized_evidence: Dict[str, List[Dict[str, Any]]] = {}

        for field in claim_fields:
            claims = high_impact.get(field)
            if not isinstance(claims, list):
                claims = []

            field_evidence = evidence.get(field)
            if not isinstance(field_evidence, list):
                field_evidence = []

            valid_claims: List[str] = []
            valid_evidence: List[Dict[str, Any]] = []

            for claim in claims:
                normalized_claim = self._normalize_claim_text(claim)
                if not normalized_claim:
                    continue

                match = None
                for item in field_evidence:
                    if not isinstance(item, dict):
                        continue
                    evidence_claim = self._normalize_claim_text(item.get('claim'))
                    page = item.get('page')
                    quote = str(item.get('quote') or '').strip()
                    if evidence_claim != normalized_claim:
                        continue
                    if not isinstance(page, int) or page < 1 or not quote:
                        continue
                    match = {
                        'claim': str(claim).strip(),
                        'page': page,
                        'quote': quote[:200],
                    }
                    break

                if match:
                    valid_claims.append(str(claim).strip())
                    valid_evidence.append(match)
                else:
                    warnings.append(f"Dropped {field} claim without evidence: {claim}")

            high_impact[field] = valid_claims
            sanitized_evidence[field] = valid_evidence

        high_impact['evidence'] = sanitized_evidence
        high_impact['validation_warnings'] = warnings[:50]
        payload['high_impact_claims'] = high_impact
        return payload

    def update_system_instructions(self, instructions: str) -> None:
        """Update the system instructions used for Gemini prompts."""
        self.system_instructions = instructions

    def update_analysis_mode(self, mode: str) -> bool:
        """Switch the analyzer between extraction and advisory mode."""
        normalized_mode = (mode or "").strip().lower()
        if normalized_mode not in ANALYSIS_MODES:
            return False

        self.analysis_mode = normalized_mode
        self.default_system_instructions = SYSTEM_INSTRUCTIONS_BY_MODE[normalized_mode]
        self.system_instructions = self.default_system_instructions
        return True

    def _add_system_instruction(self, prompt: str) -> str:
        """Prefix prompts with the system instruction for SDKs without native support."""
        instructions = (self.system_instructions or "").strip()
        if not instructions:
            return prompt
        return f"{instructions}\n\n{prompt}"

    @staticmethod
    def _normalize_candidate_parts(candidate: Any) -> List[str]:
        """Return a list of text parts from a Gemini candidate payload."""

        parts = None

        if isinstance(candidate, dict):
            content = candidate.get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
            parts = parts or candidate.get("parts")
        else:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else getattr(candidate, "parts", None)

        if not parts:
            return []

        normalized: List[str] = []
        for part in parts:
            text_value = None
            if isinstance(part, str):
                text_value = part
            elif isinstance(part, dict):
                text_value = part.get("text")
            else:
                text_value = getattr(part, "text", None)

            if text_value and isinstance(text_value, str) and text_value.strip():
                normalized.append(text_value.strip())

        return normalized

    @classmethod
    def _extract_candidate_text(cls, response: Any) -> Optional[str]:
        """Extract the first non-empty text from Gemini response candidates."""

        candidates = getattr(response, "candidates", None)
        if not candidates:
            return None

        for candidate in candidates:
            # Some SDKs expose text directly on the candidate
            direct_text = getattr(candidate, "text", None)
            if not direct_text and isinstance(candidate, dict):
                direct_text = candidate.get("text")
            if direct_text and isinstance(direct_text, str) and direct_text.strip():
                return direct_text.strip()

            for part_text in cls._normalize_candidate_parts(candidate):
                if part_text.strip():
                    return part_text.strip()

        return None

    @staticmethod
    def _format_prompt_feedback(prompt_feedback: Any) -> Optional[Dict[str, Any]]:
        """Convert Gemini prompt feedback to a JSON-serializable dict."""

        if not prompt_feedback:
            return None

        formatted: Dict[str, Any] = {}

        block_reason = getattr(prompt_feedback, "block_reason", None)
        if block_reason is not None:
            formatted["block_reason"] = str(block_reason)

        safety_ratings = getattr(prompt_feedback, "safety_ratings", None)
        if safety_ratings:
            formatted["safety_ratings"] = [
                {
                    "category": str(getattr(rating, "category", "")),
                    "probability": getattr(rating, "probability", None),
                }
                for rating in safety_ratings
                if getattr(rating, "category", None) is not None
            ]

        feedback_detail = getattr(prompt_feedback, "block_reason_message", None)
        if feedback_detail:
            formatted["detail"] = str(feedback_detail)

        return formatted or None

    def _build_block_message(self, prompt_feedback: Any) -> str:
        """Return a user-friendly message when Gemini blocks the prompt."""

        formatted = self._format_prompt_feedback(prompt_feedback)
        if not formatted:
            return "Gemini request was blocked by safety filters."

        parts = []
        if formatted.get("block_reason"):
            parts.append(f"block_reason={formatted['block_reason']}")
        if formatted.get("detail"):
            parts.append(str(formatted["detail"]))
        if formatted.get("safety_ratings"):
            parts.append(f"safety_ratings={formatted['safety_ratings']}")

        return "Gemini request was blocked: " + "; ".join(parts)

    def _generate_model_text(
        self, prompt: str, images: Optional[List[Dict[str, Any]]] = None
    ) -> "ModelTextResult":
        """Call Gemini with retries and return structured results."""

        if not self.client:
            logger.error("Gemini model is not initialized.")
            return ModelTextResult(
                error="Gemini model is not initialized.",
                empty_response=True,
            )

        last_error: Optional[Exception] = None
        last_result: Optional[ModelTextResult] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Prepare contents
                contents = []
                if prompt:
                    contents.append(types.Content(parts=[types.Part.from_text(text=prompt)]))
                
                if images:
                     # Images in the old code were dicts like {"inline_data": ...}
                     # New SDK expects types.Part.from_bytes or similar if we want to be strict,
                     # but let's see how they were constructed.
                     # The old code passed `[text_part, *images]`.
                     # We need to adapt the image dicts to the new SDK or pass them if compatible (unlikely).
                     # Let's assume for now we need to convert.
                     # Actually, to be safe and quick, let's construct the request content carefully.
                     pass 
                
                # Adapting to new SDK signature
                # contents can be a list of Content objects or valid parts.
                
                # Reconstructing the loop body for the new SDK:
                
                request_contents = []
                request_contents.append(prompt) # The new SDK handles strings directly often, but let's use the list for mix.
                
                if images:
                    # images was a list of dicts: {"inline_data": {"mime_type": ..., "data": ...}}
                    # We need to convert these to types.Part
                    for img in images:
                        inline = img.get("inline_data", {})
                        if inline:
                            request_contents.append(types.Part.from_bytes(
                                data=inline.get("data"),
                                mime_type=inline.get("mime_type")
                            ))

                response = self.client.models.generate_content(
                    model=self.current_model,
                    contents=request_contents,
                    config=types.GenerateContentConfig(
                        candidate_count=1,
                        # temperature=..., # uses defaults if not set
                        safety_settings=[
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                             types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                        ]
                    )
                )

                if not response:
                    logger.error("Gemini returned no response object.")
                    last_result = ModelTextResult(
                        error="Gemini returned no response object.",
                        empty_response=True,
                        model=self.current_model,
                    )
                    last_error = GeminiRequestFailed(last_result.error)
                    break

                prompt_feedback = getattr(response, "prompt_feedback", None)
                formatted_feedback = self._format_prompt_feedback(prompt_feedback)
                if formatted_feedback:
                    self.last_prompt_feedback = formatted_feedback

                try:
                    response_text = response.text
                except Exception:
                    response_text = None

                if response_text and isinstance(response_text, str) and response_text.strip():
                    return ModelTextResult(
                        text=response_text.strip(),
                        prompt_feedback=formatted_feedback,
                        model=self.current_model,
                    )

                candidate_text = self._extract_candidate_text(response)
                if candidate_text:
                    return ModelTextResult(
                        text=candidate_text,
                        prompt_feedback=formatted_feedback,
                        model=self.current_model,
                    )

                block_reason = getattr(prompt_feedback, "block_reason", None)
                message = (
                    self._build_block_message(prompt_feedback)
                    if block_reason is not None
                    else "Gemini returned an empty response without text or candidates."
                )

                last_result = ModelTextResult(
                    error=message,
                    prompt_feedback=formatted_feedback,
                    blocked=block_reason is not None,
                    empty_response=True,
                    model=self.current_model,
                )

                if block_reason is not None:
                    last_error = GeminiPromptBlocked(message, prompt_feedback)
                    logger.error("Gemini request blocked: %s", message)
                    break

                logger.warning(
                    "Gemini returned empty response (attempt %s/%s): %s",
                    attempt,
                    self.max_retries,
                    message,
                )
                last_error = GeminiRequestFailed(message, prompt_feedback)
                if attempt < self.max_retries:
                    time.sleep(1.5 * attempt)
                    continue

            except GeminiPromptBlocked as exc:
                last_error = exc
                self.last_prompt_feedback = self._format_prompt_feedback(
                    getattr(exc, "prompt_feedback", None)
                )
                last_result = ModelTextResult(
                    error=str(exc),
                    prompt_feedback=self.last_prompt_feedback,
                    blocked=True,
                    model=self.current_model,
                )
                logger.error("Gemini request blocked: %s", exc)
                break
            except Exception as exc:  # pragma: no cover - relies on remote API
                last_error = exc

                if isinstance(exc, (core_exceptions.PermissionDenied, core_exceptions.Forbidden)) or (
                    hasattr(exc, "code") and getattr(exc, "code") == 403
                ):
                    permission_msg = (
                        "Gemini API returned 403 (permission denied). Check your API key, "
                        "Google Cloud project access, and that the Gemini model is enabled for this project."
                    )
                    logger.error(permission_msg)
                    self.initialization_error = permission_msg

                    fallback_model = self._next_fallback_model()
                    if fallback_model:
                        logger.warning(
                            "Attempting fallback Gemini model after 403: %s -> %s",
                            self.current_model,
                            fallback_model,
                        )
                        if self._initialize_model(fallback_model):
                            logger.info("Retrying Gemini request with fallback model %s", fallback_model)
                            continue

                    self.client = None
                    last_error = permission_msg
                    break

                logger.warning(
                    "Gemini request failed (attempt %s/%s): %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(1.5 * attempt)

        if isinstance(last_error, GeminiPromptBlocked):
            return last_result or ModelTextResult(
                error=str(last_error),
                prompt_feedback=self.last_prompt_feedback,
                blocked=True,
                model=self.current_model,
            )

        fallback_model = self._next_fallback_model()
        if fallback_model:
            logger.warning(
                "Switching to fallback Gemini model %s after repeated failure: %s",
                fallback_model,
                last_error,
            )
            if self._initialize_model(fallback_model):
                fallback_result = self._generate_model_text(prompt, images=images)
                if fallback_result.text or fallback_result.error:
                    return fallback_result

        if last_result:
            return last_result

        logger.error(
            "Gemini request failed after %s attempts: %s", self.max_retries, last_error
        )
        raise GeminiRequestFailed(
            f"Gemini request failed after {self.max_retries} attempts: {last_error}",
            getattr(last_error, "prompt_feedback", None),
        )

    def _next_fallback_model(self) -> Optional[str]:
        """Return the next available model that has not yet been tried."""

        for model_name in self.available_models:
            if model_name not in self.tried_models:
                return model_name
        return None

    @staticmethod
    def _unique_page_order(page_numbers: List[int]) -> List[int]:
        """Return ordered, de-duplicated list of page numbers"""

        seen = set()
        ordered = []
        for page in page_numbers:
            if page not in seen:
                seen.add(page)
                ordered.append(page)
        return ordered

    @staticmethod
    def _has_fire_alarm_signals(text_lower: str) -> bool:
        """Detect whether the text contains clear fire alarm indicators."""

        keywords = [
            "fire alarm",
            "fire-alarm",
            "fa ",
            "fa-",
            "-fa-",
            "1-fa-",
            "facp",
            "notification device",
            "horn strobe",
            "speaker strobe",
            "pull station",
            "annunciator",
            "riser diagram",
            "smoke detector",
            "heat detector",
            "manual station",
            "nac",
            "life safety",
            "smoke alarm",
            "duct smoke detector",
            "fac",
            "smoke control",
            "FA101",
            "code footprint",
            "fire protection system",
            "nfpa 72",
            "nfpa",
            "ibc",
            "fire marshal",
            "fire alarm system",
            "fire alarm riser",
            "fa1.",
            # Sheet label patterns for FA drawing numbering schemes
            "-fa-",
            "1-fa-",
            # FA-specific page titles (not generic low-voltage/tech/comms titles)
            "fire protection plan",
            "life safety plan",
            # FA device types specific enough to signal FA content
            "addressable module",
            "monitor module",
            "initiating device",
            "notification appliance",
            "audible/visual",
            "combination detector",
            "beam detector",
            "linear heat",
            "tamper switch",
            "supervisory device",
            # FACP model numbers — pages listing existing panels
            "sk-6808", "sk6808", "sk 6808",  # Silent Knight 6808
            "sk-6820", "sk6820", "sk 6820",  # Silent Knight 6820
            "6820evs", "6808evs",            # Silent Knight EVS variants
            "4100es",                      # Simplex
            "cerberus", "desigo", "fc2005",# Siemens
            "fsp502", "fsp1004", "est3",   # EST/Edwards
            "nfw-", "nfs-",               # Notifier
            "es-500", "es-200", "es-100",  # FireLite
        ]

        return any(keyword in text_lower for keyword in keywords)

    @staticmethod
    def _is_landscaping_page(text_lower: str) -> bool:
        """Return True if the page looks like landscaping/irrigation content."""

        landscaping_keywords = [
            "landscape",
            "landscaping",
            "planting plan",
            "irrigation",
            "tree protection",
            "shrub",
            "turf",
        ]

        return any(keyword in text_lower for keyword in landscaping_keywords)

    @staticmethod
    def _is_site_work_page(text_lower: str) -> bool:
        """Return True if the page is primarily site/civil work."""

        site_keywords = [
            "site plan",
            "site work",
            "civil plan",
            "grading",
            "erosion control",
            "stormwater",
            "utility plan",
            "paving plan",
        ]

        return any(keyword in text_lower for keyword in site_keywords)

    @staticmethod
    def _is_engineering_page(text_lower: str) -> bool:
        """Return True if the page appears to be structural/engineering only."""

        engineering_keywords = [
            "structural",
            "foundation plan",
            "beam schedule",
            "column schedule",
            "truss",
            "engineering calculation",
            "structural general notes",
        ]

        return any(keyword in text_lower for keyword in engineering_keywords)

    @staticmethod
    def _is_architectural_page(text_lower: str) -> bool:
        """Return True if the page is part of the architectural set."""

        architectural_keywords = [
            "architectural",
            "floor plan",
            "reflected ceiling plan",
            "door schedule",
            "finish schedule",
            "partition schedule",
            "wall section",
            "a-",
        ]

        return any(keyword in text_lower for keyword in architectural_keywords)

    @staticmethod
    def _is_plumbing_page(text_lower: str) -> bool:
        """Return True if the page is plumbing-focused."""

        plumbing_keywords = [
            "plumbing",
            "sanitary",
            "storm drain",
            "domestic water",
            "water heater",
            "vent stack",
        ]

        return any(keyword in text_lower for keyword in plumbing_keywords)

    @staticmethod
    def _is_lighting_page(text_lower: str) -> bool:
        """Return True if the page is primarily a lighting/fixture plan (exclude these unless FA present)."""
        lighting_keywords = [
            "lighting plan",
            "fixture plan",
            "photometric",
            "luminaire",
            "site lighting",
            "lighting schedule",
            "fixture schedule",
        ]
        return any(keyword in text_lower for keyword in lighting_keywords)

    @staticmethod
    def _is_electrical_overview_page(text_lower: str) -> bool:
        """Return True for electrical overview/power/special systems sheets."""

        electrical_keywords = [
            "electrical",
            "e-",
            "e101",
            "one line",
            "single line",
            "power plan",
            "special systems",
            "electrical overview",
            "panel schedule",
            "life safety",
            "fire strategy",
            "electrical general notes",
            "electrical notes",
            "general electrical notes"
        ]

        return any(keyword in text_lower for keyword in electrical_keywords)

    @staticmethod
    def _is_mechanical_fire_related_page(text_lower: str) -> bool:
        """Return True for mechanical sheets mentioning fire alarm devices or general notes."""

        mechanical_fire_keywords = [
            "duct detector",
            "smoke detector",
            "smoke damper",
            "fire smoke damper",
            "fsd",
            "fire alarm control panel",
            "f.a.c.p",
            "facp",
            "rtu",
            "fan shutdown",
            "fire alarm control",
            "mechanical general notes",
            "hvac general notes",
            "general mechanical notes",
            "general hvac notes",
        ]

        return any(keyword in text_lower for keyword in mechanical_fire_keywords)

    @staticmethod
    def _is_demolition_page(text_lower: str) -> bool:
        """Return True if the page is a demolition plan (exclude unless FA/Electrical present)."""
        demo_keywords = [
            "demolition plan",
            "removal plan",
            "ad-",  # Architectural Demo
            "sd-",  # Structural Demo
            "id-",  # Interior Demo
            "cd-",  # Civil Demo
            "demo note",
            "demolition note",
        ]
        return any(keyword in text_lower for keyword in demo_keywords)

    def _filter_pages_for_gemini(
        self, pages_text: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove non-fire-alarm sections before passing context to Gemini."""

        if not pages_text:
            return []

        filtered_pages: List[Dict[str, Any]] = []
        dropped_reasons: List[str] = []
        priority_kept: List[str] = []

        for page in pages_text:
            text = page.get("text", "") or ""
            text_lower = text.lower()
            page_number = page.get("page_number")

            # Updated: Keep all electrical pages (including lighting) if they match our broad definition
            if self._is_electrical_page(text_lower):
                filtered_pages.append(page)
                priority_kept.append(f"Page {page_number}: electrical/special systems/lighting/code context")
                continue

            # Keep HVAC floor plans (already filtered to exclude pure schedules by _is_mechanical_page)
            if self._is_mechanical_page(text_lower):
                filtered_pages.append(page)
                priority_kept.append(f"Page {page_number}: mechanical floor plan")
                continue

            # Check for explicit lighting/fixture plans - if it fell through electrical check (unlikely), exclude if no FA
            if self._is_lighting_page(text_lower) and not self._has_fire_alarm_signals(text_lower):
                dropped_reasons.append(f"Page {page_number}: lighting/fixture plan without fire alarm content")
                continue

            # Fallback for mechanical pages with FA info that aren't plans (e.g. notes or schedules)
            if self._is_mechanical_fire_related_page(text_lower):
                filtered_pages.append(page)
                priority_kept.append(f"Page {page_number}: mechanical fire devices/notes/schedule")
                continue

            if self._is_landscaping_page(text_lower):
                dropped_reasons.append(f"Page {page_number}: landscaping")
                continue

            if self._is_site_work_page(text_lower):
                dropped_reasons.append(f"Page {page_number}: site work")
                continue

            if self._is_engineering_page(text_lower):
                dropped_reasons.append(f"Page {page_number}: structural/engineering")
                continue

            if self._is_architectural_page(text_lower) and not self._has_fire_alarm_signals(text_lower):
                dropped_reasons.append(f"Page {page_number}: architectural without fire alarm content")
                continue

            if self._is_demolition_page(text_lower) and not self._has_fire_alarm_signals(text_lower):
                dropped_reasons.append(f"Page {page_number}: demolition without fire alarm content")
                continue

            if self._is_plumbing_page(text_lower) and not self._has_fire_alarm_signals(text_lower):
                dropped_reasons.append(f"Page {page_number}: plumbing without fire alarm content")
                continue

            filtered_pages.append(page)

        if dropped_reasons:
            logger.info(
                "Filtered %s pages before Gemini transmission: %s",
                len(dropped_reasons),
                "; ".join(dropped_reasons[:20]),
            )
            if len(dropped_reasons) > 20:
                logger.info("Additional pages filtered (not listed): %s", len(dropped_reasons) - 20)
        else:
            logger.info("No pages filtered before Gemini transmission.")

        if priority_kept:
            logger.info("Kept %s priority context pages: %s", len(priority_kept), "; ".join(priority_kept))

        # Ensure at least the first couple of pages are retained for cover/context details.
        if pages_text:
            minimum_context = 2
            existing_numbers = {page.get("page_number") for page in filtered_pages}
            ordered_pages = sorted(
                pages_text,
                key=lambda p: (p.get("page_number") is None, p.get("page_number") or 0),
            )

            for page in ordered_pages[:minimum_context]:
                number = page.get("page_number")
                if number not in existing_numbers:
                    filtered_pages.append(page)
                    existing_numbers.add(number)
                    priority_kept.append(f"Page {number}: forced context include")

        if priority_kept:
            logger.info("Final priority pages included: %s", "; ".join(priority_kept))

        return filtered_pages

    def _filter_spec_book_sections(
        self, spec_pages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Keep only the Division 28 addressable fire alarm control panel section."""

        if not spec_pages:
            return []

        division_28_pattern = re.compile(r"division\s*28|\b28\s*\d{2}\b", re.IGNORECASE)
        addressable_panel_pattern = re.compile(
            r"addressable\s+fire\s+alarm\s+control\s+(?:panel|unit)"
            r"|addressable\s+facp",
            re.IGNORECASE,
        )

        sorted_pages = sorted(
            spec_pages,
            key=lambda page: (page.get("page_number") is None, page.get("page_number")),
        )

        division_28_indices: List[int] = []
        panel_indices: List[int] = []

        for idx, page in enumerate(sorted_pages):
            text = page.get("text", "") or ""
            lower = text.lower()

            if division_28_pattern.search(lower):
                division_28_indices.append(idx)

            if addressable_panel_pattern.search(lower):
                panel_indices.append(idx)

        # Favor the addressable control panel subsection. If found, capture nearby pages for context.
        focus_indices: set[int] = set(panel_indices)
        adjacency_window = 2
        for idx in list(panel_indices):
            start = max(0, idx - adjacency_window)
            end = min(len(sorted_pages) - 1, idx + adjacency_window)
            focus_indices.update(range(start, end + 1))

        # If we did not see an explicit panel header, fall back to Division 28 pages that mention fire alarm terms.
        if not focus_indices and division_28_indices:
            fire_alarm_terms = ["fire alarm", "facp", "notification", "initiating device"]
            for idx in division_28_indices:
                text = (sorted_pages[idx].get("text") or "").lower()
                if any(term in text for term in fire_alarm_terms):
                    focus_indices.add(idx)

        filtered: List[Dict[str, Any]] = []
        for idx in sorted(focus_indices):
            page = sorted_pages[idx]
            filtered.append(
                {
                    "page_number": page.get("page_number"),
                    "text": page.get("text", "") or "",
                }
            )
            if len(filtered) >= 12:
                break

        if filtered:
            logger.info(
                "Prepared %s Division 28 spec pages for Gemini (addressable FACP focus): %s",
                len(filtered),
                ", ".join(str(p.get("page_number")) for p in filtered[:15]),
            )
        else:
            logger.info("No Division 28 addressable FACP sections found in spec book; skipping spec context.")

        return filtered

    @staticmethod
    def _compile_spec_excerpt(
        spec_sections: Optional[List[Dict[str, Any]]],
        char_limit: int = 16000,
    ) -> str:
        """Create a bounded text block from relevant spec sections."""

        if not spec_sections:
            return ""

        excerpts: List[str] = []
        remaining = char_limit

        for section in spec_sections:
            text = (section.get("text") or "").strip()
            if not text or remaining <= 0:
                continue

            snippet = text if len(text) <= remaining else text[:remaining]
            header = f"[Spec Page {section.get('page_number')}]\n"
            block = f"{header}{snippet}"
            if len(block) > remaining:
                block = block[:remaining]

            excerpts.append(block)
            remaining -= len(block)

            if remaining <= 0:
                break

        return "\n\n".join(excerpts)

    @staticmethod
    def _image_guidance_text(
        image_payload: Optional[List[Dict[str, Any]]],
        image_pages: Optional[List[int]] = None,
    ) -> str:
        """Describe attached images so prompts instruct Gemini to use drawings."""

        if not image_payload:
            return ""

        if image_pages:
            mapped_pages = ", ".join(f"Page {page}" for page in image_pages)
            return (
                "\n\nIMAGE CONTEXT: The referenced PDF pages are attached as rendered "
                f"PNG images ({mapped_pages}). Rely on the drawings in these images instead "
                "of any OCR text when extracting details."
            )

        return (
            "\n\nIMAGE CONTEXT: PDF pages are attached as rendered PNG images. "
            "Treat these images as a SINGLE COHESIVE SET of construction documents. "
            "Synthesize your findings across ALL provided images rather than analyzing each page in isolation. "
            "Use the drawings directly rather than relying on OCR text."
        )

    def _select_pages_for_image_transmission(
        self, pages_text: List[Dict[str, Any]]
    ) -> List[int]:
        """Pick a small, relevant set of pages to send as images."""

        if not pages_text:
            return []

        # 1. Identify critical pages
        cover_pages = [
            page.get("page_number")
            for page in pages_text[:3]
            if page.get("page_number") is not None
        ]

        electrical_pages: List[int] = []
        mechanical_pages: List[int] = []
        fire_alarm_pages: List[int] = []

        for page in pages_text:
            text_lower = (page.get("text") or "").lower()
            page_number = page.get("page_number")
            if page_number is None:
                continue

            # Prioritize pages specifically mentioning fire alarm systems
            if self._has_fire_alarm_signals(text_lower):
                fire_alarm_pages.append(page_number)
            elif self._is_electrical_page(text_lower):
                electrical_pages.append(page_number)
            elif self._is_mechanical_page(text_lower):
                mechanical_pages.append(page_number)

        # 2. Build prioritized list
        # Order: Context(3) -> Fire Alarm -> Electrical -> Mechanical
        
        # Start with context
        final_list = list(cover_pages)
        
        # Add Fire Alarm pages (Highest priority)
        for p in fire_alarm_pages:
            if p not in final_list:
                final_list.append(p)
        
        # Add Electrical pages (Medium priority)
        for p in electrical_pages:
            if p not in final_list:
                final_list.append(p)
                
        # Add Mechanical pages (Lower priority, but important for ducts)
        for p in mechanical_pages:
            if p not in final_list:
                final_list.append(p)
                
        # 3. Apply Limit
        limit = self.max_image_pages
        if len(final_list) > limit:
            logger.info("Capping image pages from %s to %s", len(final_list), limit)
            final_list = final_list[:limit]
            
        # 4. Sort for reading order
        ordered_unique = self._unique_page_order(final_list)

        logger.info(
            "Attaching %s page images to Gemini (max %s): %s",
            len(ordered_unique),
            limit,
            ordered_unique,
        )
        return ordered_unique

    @staticmethod
    def _is_electrical_page(text_lower: str) -> bool:
        """Return True for any electrical/fire alarm page (Power, Lighting, Systems)."""

        electrical_markers = [
            "electrical",
            "power",
            "lighting",
            "special systems",
            "fire alarm",
            "symbol list",
            "legend",
            "abbreviation",
            "low voltage",
            "communications",
            "telecom",
            "technology",
            "E101"
        ]

        has_marker = any(keyword in text_lower for keyword in electrical_markers)
        # Check for drawing/sheet identifiers to avoid pure specs if mixed in
        has_plan_context = any(k in text_lower for k in ["plan", "sheet", "drawing", "level", "detail", "riser", "schedule"])

        return has_marker and has_plan_context

    @staticmethod
    def _is_mechanical_page(text_lower: str) -> bool:
        """Return True for mechanical/HVAC floor plans OR schedules."""

        mechanical_keywords = {
            "mechanical",
            "hvac",
            "duct",
            "damper",
            "air handler",
            "rtu",
            "ahu",
            "diffuser",
            "vav",
            "mechanical roof plan",
            "schedule",
            "equipment list"
        }

        if not any(keyword in text_lower for keyword in mechanical_keywords):
            return False

        # Must be a floor plan/layout OR a schedule
        is_plan = any(k in text_lower for k in ["plan", "layout", "level", "floor", "drawing"])
        is_schedule = any(k in text_lower for k in ["schedule", "table", "equipment list", "matrix"])
        
        return is_plan or is_schedule

    @staticmethod
    def _has_unique_fire_alarm_details(text_lower: str) -> bool:
        """Detect pages that call out unique fire alarm details worth imaging."""

        detail_keywords = [
            "fire alarm detail",
            "fa detail",
            "fire alarm riser",
            "fa riser",
            "sequence of operations",
            "device schedule",
            "notification schedule",
            "nac schedule",
            "fire alarm control panel",
            "addressable panel",
            "fa panel",
            "fire alarm layout",
            "riser diagram",
        ]

        return any(keyword in text_lower for keyword in detail_keywords)

    def _find_fire_alarm_section_pages(
        self, pages_text: List[Dict[str, Any]]
    ) -> List[int]:
        """Locate pages that belong to the fire alarm section for image transmission."""

        # Deprecated in favor of _select_pages_for_image_transmission's refined rules.
        return self._select_pages_for_image_transmission(pages_text)

    def _build_image_payload(self, pdf_path: str, page_numbers: List[int]) -> List[Dict[str, Any]]:
        """Render selected pages to downscaled JPEG bytes for Gemini vision context."""

        if not page_numbers:
            return []

        payload: List[Dict[str, Any]] = []
        total_bytes = 0

        logger.info(
            "Rendering %s pages for Gemini at %sdpi (max %spx, JPEG q%s)",
            len(page_numbers),
            self.image_render_dpi,
            self.image_max_dimension,
            self.image_jpeg_quality,
        )

        for page_number, image in self.pdf_processor.iter_pdf_images(
            pdf_path, selected_pages=page_numbers, render_dpi=self.image_render_dpi
        ):
            buffer = None
            try:
                # Downscale to reduce upload size and speed up transmission.
                max_dimension = self.image_max_dimension
                image = image.convert("RGB")
                image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

                buffer = io.BytesIO()
                image.save(
                    buffer,
                    format="JPEG",
                    quality=self.image_jpeg_quality,
                    optimize=True,
                    progressive=True,
                )
                jpeg_bytes = buffer.getvalue()
                total_bytes += len(jpeg_bytes)
                payload.append({"inline_data": {"mime_type": "image/jpeg", "data": jpeg_bytes}})
            except Exception as exc:
                logger.warning(
                    "Skipping image for page %s due to render error: %s", page_number, exc
                )
                continue
            finally:
                try:
                    if hasattr(image, "close"):
                        image.close()
                    if buffer is not None:
                        buffer.close()
                except Exception:
                    pass

        if payload:
            logger.info(
                "Prepared %s JPEG images for Gemini (%0.2f MB)",
                len(payload),
                total_bytes / 1_000_000,
            )

        return payload

    def _run_analysis_pipeline(
        self,
        pages_text: List[Dict[str, Any]],
        image_payload: Optional[List[Dict[str, Any]]] = None,
        image_pages: Optional[List[int]] = None,
        spec_sections: Optional[List[Dict[str, Any]]] = None,
        spec_source_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute the core Gemini analysis steps once text has been extracted."""

        if not pages_text:
            return {
                'success': False,
                'error': 'Failed to extract text from PDF'
            }

        # Helper to safely run a step without crashing the pipeline
        def safe_step(func, *args, default=None):
            try:
                return func(*args)
            except (GeminiPromptBlocked, GeminiRequestFailed) as e:
                logger.warning(f"Step {func.__name__} failed/blocked: {e}")
                return copy.deepcopy(default)
            except Exception as e:
                logger.error(f"Step {func.__name__} unexpected error: {e}")
                return copy.deepcopy(default)

        # Step 1: Identify fire alarm relevant pages (Rule-based, rarely fails)
        logger.info("Identifying fire alarm pages...")
        fa_pages = self._identify_fire_alarm_pages(pages_text)

        # Step 1b: Supplement with TOC-referenced FA pages so that pages whose
        # extracted text is sparse (e.g. mostly graphical) are still included.
        toc_fa_pages = self._extract_toc_fa_page_numbers(pages_text)
        if toc_fa_pages:
            merged = sorted(set(fa_pages) | set(toc_fa_pages))
            added = sorted(set(toc_fa_pages) - set(fa_pages))
            if added:
                logger.info(
                    "TOC scan added %s additional FA page(s) not caught by keyword rules: %s",
                    len(added),
                    added,
                )
            fa_pages = merged

        # Step 3: Prepare a lean subset of pages to reduce token usage
        focused_pages = self._prioritize_pages_for_ai(pages_text, fa_pages)

        logger.info("Running consolidated Gemini extraction...")
        composite_defaults = self._composite_response_defaults()
        composite_response = safe_step(
            self._run_consolidated_extraction,
            focused_pages,
            fa_pages,
            spec_sections,
            image_payload,
            image_pages,
            default=composite_defaults,
        ) or composite_defaults

        # Extract original fields
        project_info = composite_response.get('project_info', {}) or {}
        codes = composite_response.get('code_requirements', {}) or {'fire_alarm_codes': []}
        fa_notes = composite_response.get('fire_alarm_notes', []) or []
        mechanical_devices = composite_response.get('mechanical_devices', {}) or {
            'duct_detectors': [],
            'dampers': [],
            'high_airflow_units': [],
        }
        device_layout_review = composite_response.get('device_layout_review', {}) or {
            'primary_fa_page': {},
            'unusual_placements': [],
            'co_detection': {'needed': None, 'reason': None},
        }
        specifications = composite_response.get('specifications', {}) or {}
        possible_pitfalls = composite_response.get('possible_pitfalls', []) or []
        estimating_notes = composite_response.get('estimating_notes', []) or []

        # Extract new standardized fields
        scope_summary = composite_response.get('scope_summary', None)
        project_details = composite_response.get('project_details', {}) or {}
        fire_alarm_details = composite_response.get('fire_alarm_details', {}) or {}
        hvac_mechanical = composite_response.get('hvac_mechanical', {}) or {}
        competitive_advantages = composite_response.get('competitive_advantages', []) or []
        high_impact_claims = composite_response.get('high_impact_claims', {}) or {}
        estimating_insights = composite_response.get('estimating_insights', []) or []

        # Step 9: If the documents show no FA content, derive code-based expectations
        logger.info("Deriving code-based expectations (if no fire alarm content is shown)...")
        code_based_expectations = safe_step(
            self._derive_code_based_expectations,
            focused_pages,
            codes,
            default={},
        ) if not fa_pages else {}

        # Build results with both original and new fields
        results = {
            'success': True,
            # Original fields
            'project_info': project_info,
            'code_requirements': codes,
            'fire_alarm_pages': fa_pages,
            'fire_alarm_notes': fa_notes,
            'mechanical_devices': mechanical_devices,
            'device_layout_review': device_layout_review,
            'specifications': specifications,
            'possible_pitfalls': possible_pitfalls,
            'estimating_notes': estimating_notes,
            'code_based_expectations': code_based_expectations,
            # New standardized fields
            'scope_summary': scope_summary,
            'project_details': project_details,
            'fire_alarm_details': fire_alarm_details,
            'hvac_mechanical': hvac_mechanical,
            'competitive_advantages': competitive_advantages,
            'estimating_insights': estimating_insights,
            'project_tags': composite_response.get('project_tags', []) or [],
            # Common fields
            'spec_book_context': None,
            'total_pages': len(pages_text),
            'analysis_timestamp': datetime.now().isoformat(),
        }

        if spec_sections:
            results['spec_book_context'] = {
                'pages_considered': len(spec_sections),
                'pages_sent_to_gemini': [page.get('page_number') for page in spec_sections],
                'source': 'spec_pdf',
                'sources': spec_source_files,
            }

        # Even if we had blocks, we return success=True so the UI shows what we DID get
        if self.last_prompt_feedback:
            results['prompt_feedback'] = self.last_prompt_feedback

        logger.info("Gemini analysis completed successfully (with potential partial blocks)")
        return results

    def _composite_response_defaults(self) -> Dict[str, Any]:
        """Default empty shell for consolidated Gemini extraction."""

        return {
            # Original fields (keep for backward compatibility)
            'project_info': {},
            'code_requirements': {'fire_alarm_codes': []},
            'fire_alarm_notes': [],
            'mechanical_devices': {
                'duct_detectors': [],
                'dampers': [],
                'high_airflow_units': [],
            },
            'device_layout_review': {
                'primary_fa_page': {},
                'unusual_placements': [],
                'co_detection': {'needed': None, 'reason': None},
            },
            'specifications': {},
            'possible_pitfalls': [],
            'estimating_notes': [],
            # New standardized fields
            'scope_summary': None,
            'project_details': {
                'project_name': None,
                'project_address': None,
                'new_or_existing': None,
                'project_type': None,
                'building_type': None,
                'applicable_codes': [],
                'occupancy_type': None,
                'square_footage': None,
                'number_of_floors': None,
                'construction_type': None,
                'bid_date': None,
            },
            'fire_alarm_details': {
                'fire_alarm_required': None,
                'sprinkler_status': None,
                'panel_status': None,
                'existing_panel_manufacturer': None,
                'layout_page_provided': None,
                'voice_required': None,
                'co_required': None,
                'co_reasoning': None,
                'fire_doors_present': None,
                'fire_barriers_present': None,
                'general_notes': [],
                'device_count_estimate': None,
                'wiring_info': None,
                'monitoring_requirements': None,
                'integration_points': [],
                'sequence_of_operations': [],
            },
            'hvac_mechanical': {
                'hvac_equipment': [],
                'duct_detectors': [],
                'fire_smoke_dampers_present': None,
                'smoke_dampers_present': None,
                'access_control_doors': [],
                'elevator_recall': None,
                'kitchen_hood_suppression': None,
            },
            'competitive_advantages': [],
            'project_tags': [],
            'estimating_insights': [],
        }

    def _compile_page_context(
        self,
        pages_text: List[Dict[str, Any]],
        max_chars: int = 80000,
        fa_pages: Optional[List[int]] = None,
    ) -> str:
        """Flatten prioritized pages into a single context block with page labels.

        FA-identified pages are always included first so they are never squeezed
        out by text-heavy cover/TOC pages.  Remaining budget is filled by other pages
        in their original order.
        """

        fa_page_set: set = set(fa_pages or [])

        fa_blocks: List[str] = []
        other_blocks: List[str] = []

        for page in pages_text:
            page_number = page.get('page_number')
            text = (page.get('text') or '').strip()
            if not text:
                continue
            block = f"PAGE {page_number}:\n{text}"
            if page_number in fa_page_set:
                fa_blocks.append(block)
            else:
                other_blocks.append(block)

        result_blocks: List[str] = []
        used = 0

        # Pass 1 — guarantee all FA pages are included (up to 60 % of budget)
        fa_budget = int(max_chars * 0.60)
        for block in fa_blocks:
            if used + len(block) > fa_budget:
                # Truncate the last block rather than drop it entirely
                remaining = fa_budget - used
                if remaining > 300:
                    result_blocks.append(block[:remaining])
                    used += remaining
                break
            result_blocks.append(block)
            used += len(block)

        # Pass 2 — fill remaining budget with non-FA pages
        for block in other_blocks:
            remaining = max_chars - used
            if remaining <= 0:
                break
            if len(block) > remaining:
                if remaining > 300:
                    result_blocks.append(block[:remaining])
                break
            result_blocks.append(block)
            used += len(block)

        logger.info(
            "Page context: %s FA blocks + %s other blocks = %s chars (limit %s)",
            len(fa_blocks),
            len(other_blocks),
            used,
            max_chars,
        )

        return "\n\n".join(result_blocks)

    def _run_consolidated_extraction(
        self,
        pages_text: List[Dict[str, Any]],
        fa_pages: List[int],
        spec_sections: Optional[List[Dict[str, Any]]],
        image_payload: Optional[List[Dict[str, Any]]],
        image_pages: Optional[List[int]],
    ) -> Dict[str, Any]:
        """Combine project info, codes, notes, mechanical, and specs into one Gemini call."""

        context_text = self._compile_page_context(pages_text, fa_pages=fa_pages)
        spec_excerpt = self._compile_spec_excerpt(spec_sections)
        image_note = self._image_guidance_text(image_payload, image_pages)

        prompt = self._add_system_instruction(
            f"""You are a senior fire alarm estimator with 20+ years of experience. Using the consolidated project context and optional spec excerpts, extract
all requested details in a single structured JSON response. Your goal is to produce everything an estimator needs to prepare a competitive bid.

CRITICAL INSTRUCTION: Synthesize findings from ALL provided pages and images. Do not analyze pages in isolation.
Cross-reference information across sheets (e.g., if a device is shown on Page 5 but the key note is on Page 3, combine that info).
Treat the provided content as a complete package. Cross-reference mechanical schedules with electrical plans to find duct detector requirements.
Check architectural plans for occupancy types, ceiling heights, and areas that affect device spacing and labor.

IMPORTANT — DO NOT FLAG PAGES AS MISSING: This PDF is a complete construction document set. Every sheet listed in the Sheet Index or Table of Contents IS present in this PDF. Do NOT state that any page is "missing from the provided PDF." If content for a specific sheet is not visible in the extracted text context, note only that "details were not captured in the provided context" — never say the sheet or page is absent. The drawings contain all sheets listed in their index.

FIRE ALARM PAGE TITLES: Fire alarm devices and systems are frequently shown on pages whose titles do NOT say "Fire Alarm." Common page titles that contain fire alarm content include: "Power Plan," "Special Systems," "Special Systems Plan," "Systems Plan," "Fire Protection Plan," "Life Safety Plan," "Low Voltage Plan," "Technology Plan," "Communications Plan," and pages labeled with sheet numbers containing "FA," "FS," or "LS." If the sheet index references sheets with these titles alongside fire alarm sheets, assume fire alarm content exists across multiple drawing types. Additionally, almost every drawing set that lists fire alarm sheets in its index does in fact include the full fire alarm scope in the PDF — treat the presence of FA sheet entries in the index as strong evidence the scope is present, even if the visible page text is sparse.

ESTIMATOR MINDSET: Think about what affects pricing and labor:
- Device counts directly affect material and labor costs
- Wiring class (A vs B) dramatically changes wire quantities
- Ceiling heights over 10' require lifts or scaffolding
- Concealed wiring in finished spaces vs exposed in warehouses changes labor significantly
- Phased construction requires temporary systems and multiple inspections
- Existing system tie-ins require compatibility research and may limit manufacturer choice

Keep answers concise and only include information directly supported by the provided pages. Always cite page numbers when referencing notes, devices, or layouts. Fire alarm-focused
pages identified by rules: {fa_pages}. Drawings are the primary source—use spec excerpts only as backup context and only for
Division 28 addressable fire alarm control panel requirements.

PROJECT PAGES (WITH PAGE LABELS):
{context_text}

SPEC EXCERPTS (IF ANY):
{spec_excerpt or 'No spec excerpts provided.'}

{image_note}

Return a JSON object with these keys:

ORIGINAL FIELDS (maintain backward compatibility):
- project_info: {{project_name, project_address, project_location, project_type, applicable_codes, fire_alarm_required, sprinkler_status, scope_summary, voice_required, project_number, owner, architect, engineer}}
- code_requirements: {{fire_alarm_codes: array of strings, code_notes: string or null}}
- fire_alarm_notes: array of objects {{page, note_type, content}}
- mechanical_devices: {{duct_detectors: array, dampers: array, high_airflow_units: array}}
- device_layout_review: {{primary_fa_page: {{page, reason}}, unusual_placements: array, co_detection: {{needed, reason}}}}
- specifications: {{CONTROL_PANEL, DEVICES, NOTIFICATION_DEVICES, SYSTEM_TYPE, WIRING_CLASS, COMMUNICATION, POWER_REQUIREMENTS, MONITORING, INTEGRATION, SPRINKLER_SYSTEM, APPROVED_MANUFACTURERS, AUDIO_SYSTEM, EXISTING_SYSTEM_PANEL_MODEL}}
- possible_pitfalls: array of project-specific conflicts, omissions, or risks an estimator should flag (no canned checklists). Be SPECIFIC — reference actual page numbers, device types, and spec sections. Examples of good pitfalls: "Spec calls for Notifier (proprietary) but drawings show Gamewell symbols — clarify with engineer (Pg E2.1 vs Spec 283111.2.1)" or "Duct detector shown on RTU-3 but no junction box detail provided for above-ceiling access (Pg M2.1)"
- estimating_notes: array of coordination or estimating notes tailored to this project (do not duplicate pitfalls; keep concise and case-specific). Focus on items that affect COST: labor complexity, material quantities, coordination needs, permit/inspection requirements.
- high_impact_claims: {{required_vendors, required_manufacturers, code_requirements, deal_breakers, evidence, validation_warnings}}

NEW STANDARDIZED FIELDS (for improved organization):
1. scope_summary: A concise 2-4 sentence summary of the project scope from a fire alarm perspective. Include building type, approximate size if stated, system type, and key scope elements.
   Example: "New construction of a 45,000 SF daycare center in Overland Park, KS. Project requires a new addressable fire alarm system with notification appliances (horn/strobes), smoke detection, sprinkler monitoring, duct detector interfaces for 4 RTUs, and HVAC shutdown integration. Voice evacuation is not required. System must be compatible with city-mandated monitoring protocol."

2. project_details: {{
   - project_name: Name on title/cover page
   - project_address: Street address or city/state reference
   - new_or_existing: "new", "existing to remain", "retrofit", etc.
   - project_type: "Remodel", "Tenant Improvement", "New Construction", "Tenant Build Out", "White Box/Shell", etc.
   - building_type: "middle school", "high school", "open warehouse", "office space", "manufacturing", "childcare center", etc.
   - applicable_codes: array of code references (e.g., ["NFPA 72-2019", "IBC 2018", "NFPA 101-2018"])
   - occupancy_type: IBC occupancy classification (e.g., "B - Business", "E - Educational", "A-3 - Assembly")
   - square_footage: Building area in SF if stated on cover page, plans, or specs. Return null if not found.
   - number_of_floors: Number of stories/floors. Return null if not found.
   - construction_type: IBC construction type (I-V) if mentioned. Return null if not found.
   - bid_date: Bid due date if visible on cover page or in project info. Return null if not found.
}}

3. fire_alarm_details: {{
   - fire_alarm_required: "yes" or "no"
   - sprinkler_status: "yes" or "no"
   - panel_status: "new", "existing to remain", "retrofit", etc.
   - existing_panel_manufacturer: Manufacturer name (and model if shown) for any existing fire alarm panel referenced in the drawings, schedules, or notes. Include model number when visible. Recognize these model numbers even when the brand is not written — Silent Knight: SK-6808, SK6808, SK 6808, SK-6820, SK6820, SK 6820, 6820EVS, 6808EVS, any model ending in EVS; Gamewell-FCI: 7100 series; FireLite: ES-50x, ES-100x, ES-1000x; Siemens: Cerberus, FC2005, Desigo; EST/Edwards: FSP502, FSP1004, FireShield, EST3, EST4, iO Series; Notifier: NFW-xxx, NFS-xxx; Simplex: 4100ES, 4010; Honeywell; Bosch; Mircom; Johnson Controls / JCI. Return null if no existing panel is mentioned.
   - layout_page_provided: "Yes" or "No". If yes, include page number.
   - voice_required: "yes" or "no"
   - co_required: "YES", "NO", or "UNCLEAR" based on occupancy (e.g., residential vs business) and gas/fuel sources.
   - co_reasoning: Brief explanation of why CO is/is not required (e.g., "Business occupancy with no fuel-burning appliances").
   - fire_doors_present: "yes" or "no"
   - fire_barriers_present: "yes" or "no"
   - general_notes: array of strings. Copy any General Notes or Keyed Notes that strictly pertain to fire alarm. Cite page number for each (e.g., "Key Note 4: Connect duct detector to FACP (Pg M1.1)").
   - device_count_estimate: object with approximate counts by device type extracted from drawings/schedules. Keys: smoke_detectors, heat_detectors, pull_stations, horn_strobes, speaker_strobes, duct_detectors, monitor_modules, control_modules, relay_modules, beam_detectors, other. Use integer values. Set to null if counts cannot be reasonably estimated. Label source as "counted_from_drawings" or "from_device_schedule".
   - wiring_info: object {{class: "A" or "B" or null, pathway: "conduit" or "cable_tray" or "open" or null, notes: string or null}}. Extract wiring class and pathway requirements from specs or notes.
   - monitoring_requirements: string describing central station monitoring needs (e.g., "UL-listed central station monitoring required per spec", "Proprietary monitoring", or null)
   - integration_points: array of strings listing other building systems the fire alarm must interface with (e.g., ["elevator recall", "HVAC shutdown", "access control release", "sprinkler monitoring", "kitchen hood suppression", "BMS/BAS", "mass notification"])
   - sequence_of_operations: array of objects {{trigger: string, action: string, page: number or null}} describing relay/shutdown sequences mentioned in notes or riser diagrams. Example: {{trigger: "Duct detector alarm on RTU-1", action: "Shut down RTU-1 via control relay", page: 5}}
}}

4. hvac_mechanical: {{
   - hvac_equipment: array of objects with {{model: string, cfm: number, over_2000_cfm: boolean, page: number}}
   - duct_detectors: array of objects with {{rtu_name: string, cfm: number, notes: string, page: number}}. Extract specifically which RTU (e.g., RTU-1) needs a detector.
   - fire_smoke_dampers_present: "yes" or "no" or null
   - smoke_dampers_present: "yes" or "no" or null
   - access_control_doors: array of objects with {{location: string, door_count: number, electric_strike_release_required: boolean, page: number}}
   - elevator_recall: object {{required: "yes" or "no" or null, shunt_trip: "yes" or "no" or null, elevator_count: number or null, page: number or null}} or null. Extract elevator recall and shunt trip requirements if shown.
   - kitchen_hood_suppression: object {{present: "yes" or "no" or null, fa_tie_in_required: "yes" or "no" or null, page: number or null}} or null. Note if kitchen hood suppression system requires fire alarm tie-in.
}}

5. competitive_advantages: array of strings containing advice or recommendations to gain an edge over competing bidders

6. project_tags: array of objects {{ "label": string, "color": string, "hover": string }}.
   - GENERATE TAGS BASED ON THESE RULES:
     - MANUFACTURERS:
       - "Gamewell-FCI", "Silent Knight", "Firelite" -> color: "green", hover: "Preferred Manufacturer"
       - "Simplex", "Notifier", "EST", "Edwards", "GE", "Kiddie" -> color: "red", hover: "Proprietary/Restricted Manufacturer"
     - DEAL BREAKERS:
       - "Buy American", "BABA", "AIS" -> color: "red", hover: "Buy American Act Requirement"
       - "Union Required", "PLA", "Prevailing Wage" -> color: "orange", hover: "Labor Requirement"
       - "Minority/Women Owned Req" -> color: "red", hover: "WBE/MBE Requirement"
     - SCOPE:
       - "New System" -> color: "blue", hover: "New Construction"
       - "Existing to Remain" -> color: "yellow", hover: "Existing System"
       - "Design Build" -> color: "purple", hover: "Design Build Contract"
       - "Phased" -> color: "orange", hover: "Phased Project"
       - "No FA" -> color: "gray", hover: "No Fire Alarm Scope Found"
       - "Voice" -> color: "blue", hover: "Voice Evacuation Required"
     - LOCATION TYPE:
       - "Apartment", "Multi-Family" -> color: "teal", hover: "Residential"
       - "Retail", "Mercantile" -> color: "teal", hover: "Retail"
       - "Warehouse", "Industrial" -> color: "teal", hover: "Industrial"
       - "Office" -> color: "teal", hover: "Commercial Office"
       - "School", "Education", "University" -> color: "teal", hover: "Educational"
       - "Hospital", "Healthcare" -> color: "teal", hover: "Healthcare"
       - "Government", "Military" -> color: "teal", hover: "Government"

7. estimating_insights: array of objects {{ "category": string, "detail": string, "impact": string }}.
   Categories: "material", "labor", "coordination", "schedule", "risk", "cost_driver".
   Provide specific, actionable insights that affect pricing. Examples:
   - {{category: "labor", detail: "Exposed structure in warehouse — surface-mount devices reduce install time", impact: "Lower labor cost"}}
   - {{category: "cost_driver", detail: "Class A wiring specified — doubles wire quantities vs Class B", impact: "Higher material cost"}}
   - {{category: "coordination", detail: "4 duct detectors required — coordinate access panels with HVAC contractor above ceiling grid", impact: "Schedule coordination needed"}}
   - {{category: "risk", detail: "Spec requires ES-200XP panels but no approved equal — sole source pricing applies", impact: "No competitive pricing"}}

CRITICAL RULES:
- If a field is unknown, use null, an empty array, or an empty object as appropriate.
- Do not invent devices or notes; prioritize project-specific content only.
- Keep strings short (<= 280 characters) and preserve key terminology from the source pages.
- Remember: Just because the symbol legend shows a device type doesn't mean it's actually shown in the drawings. Only report what is ACTUALLY present.
- HVAC equipment over 2,000 CFM must be flagged with over_2000_cfm: true
- Extract Keyed/General Notes accurately with page citations.
- Do not repeat the same pitfall or note in multiple fields; deduplicate wording and cite context briefly when helpful.
- MANUFACTURER DETECTION: Keyed notes and general notes are the PRIMARY source of required manufacturer specifications on construction documents. Always scan them for phrases like "system to be [Brand]", "shall be [Brand] [Model]", "[Brand] or approved equal", "basis of design: [Brand]", "connect to existing [Brand]", or "compatible with [Brand]". Recognized Edwards/EST model numbers include: EST3, EST4, FSP502, FSP1004, FireShield, iO Series. When found, add to both high_impact_claims.required_manufacturers AND specifications.APPROVED_MANUFACTURERS.
- For EVERY item in required_vendors, required_manufacturers, code_requirements, and deal_breakers, you MUST include one matching evidence object with the same claim text, page number, and short quote/snippet from the documents.
- If there is no evidence, omit the claim from that list.
- NEVER add a pitfall or note stating that fire alarm drawing sheets are "missing from the provided PDF" or "not included in the PDF." The PDF is a complete set. If a sheet's content was not captured in the extracted text context, that is a context limitation, not a missing document. Omit any such note entirely.
- For device_count_estimate: count devices visible on floor plans and schedules, not just from the symbol legend. Clearly note the source.
- For sequence_of_operations: extract ONLY sequences explicitly stated in the documents. Do not infer standard sequences.
"""
        )

        default_response = self._composite_response_defaults()

        try:
            result = self._generate_model_text(prompt, images=image_payload)
            if not result.text:
                default_response['error'] = result.error
                default_response['prompt_feedback'] = result.prompt_feedback
                return default_response

            parsed = self._validate_high_impact_claims(self._parse_json(result.text, default_response))
            return parsed if isinstance(parsed, dict) else default_response
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as exc:
            logger.error("Error during consolidated extraction: %s", exc)
            default_response['error'] = str(exc)
            return default_response

    def analyze_pdf_text(self, pages_text: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run Gemini analysis when page text has already been extracted."""

        if not self.client:
            return {
                'success': False,
                'error': 'Gemini AI not initialized. Check API key.'
            }

        try:
            self.last_prompt_feedback = None
            filtered_pages = self._filter_pages_for_gemini(pages_text)

            if not filtered_pages:
                return {
                    'success': False,
                    'error': 'All pages were filtered out before Gemini analysis.'
                }

            return self._run_analysis_pipeline(filtered_pages)
        except GeminiPromptBlocked as exc:
            logger.error("Gemini analysis blocked: %s", exc)
            return {
                'success': False,
                'error': str(exc),
                'prompt_feedback': self.last_prompt_feedback
            }
        except GeminiRequestFailed as exc:
            logger.error("Gemini analysis failed after retries: %s", exc)
            return {
                'success': False,
                'error': str(exc),
                'prompt_feedback': self.last_prompt_feedback
            }
        except Exception as e:
            logger.error(f"Error during Gemini analysis: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'prompt_feedback': self.last_prompt_feedback
            }

    def answer_follow_up_question(
        self,
        question: str,
        prior_results: Optional[Dict[str, Any]] = None,
        pdf_path: Optional[str] = None,
        spec_pdf_path: Optional[str] = None,
        additional_spec_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Use Gemini to answer follow-up questions with project context."""

        if not self.client:
            return {'success': False, 'error': 'Gemini AI not initialized. Check API key.'}

        if not question or not question.strip():
            return {'success': False, 'error': 'A follow-up question is required.'}

        context_blocks: List[str] = []

        if prior_results:
            condensed = {
                'project_info': prior_results.get('project_info'),
                'high_level_overview': prior_results.get('high_level_overview'),
                'fire_alarm_briefing': prior_results.get('fire_alarm_briefing'),
                'specifications': prior_results.get('specifications'),
                'device_layout_review': prior_results.get('device_layout_review'),
            }
            try:
                context_blocks.append(f"PRIOR GEMINI SUMMARY:\n{json.dumps(condensed, ensure_ascii=False)[:6000]}")
            except Exception:
                pass

        if pdf_path:
            try:
                pages_text = self.pdf_processor.extract_text_from_pdf(pdf_path)
                filtered_pages = self._filter_pages_for_gemini(pages_text)
                excerpt = "\n\n".join(
                    [
                        f"PAGE {page.get('page_number')}:\n{page.get('text','')[:1200]}"
                        for page in filtered_pages[:8]
                    ]
                )
                if excerpt:
                    context_blocks.append(f"PAGE EXCERPTS:\n{excerpt}")
            except Exception as exc:
                logger.error("Failed to build follow-up context from PDF: %s", exc)

        spec_paths: List[str] = []
        if spec_pdf_path:
            spec_paths.append(spec_pdf_path)
        if additional_spec_paths:
            spec_paths.extend([path for path in additional_spec_paths if path])

        if spec_paths:
            try:
                combined_sections: List[Dict[str, Any]] = []
                for path in spec_paths:
                    spec_pages = self.pdf_processor.extract_text_from_pdf(path)
                    combined_sections.extend(self._filter_spec_book_sections(spec_pages))

                spec_excerpt = self._compile_spec_excerpt(combined_sections, char_limit=4000)
                if spec_excerpt:
                    context_blocks.append(f"SPEC EXCERPT:\n{spec_excerpt}")
            except Exception as exc:
                logger.error("Failed to build follow-up context from spec: %s", exc)

        context_text = "\n\n".join(context_blocks)

        prompt = f"""You are continuing as the fire alarm estimator AI. Answer the user's follow-up question using the project context.

FOLLOW-UP QUESTION:
{question.strip()}

CONTEXT:
{context_text[:16000]}

Expectations:
- Provide a concise, actionable answer.
- Cite specific page numbers when referencing device locations or notes.
- If device placement seems unusual, explain why it may be shown that way.
- Always state whether CO detection is required, not required, or unclear, and why.

Return JSON with keys: answer (string), referenced_pages (array of ints), co_detection (object with needed + reason), and notes (array of strings for any unusual placements or clarifications).
"""

        try:
            result = self._generate_model_text(self._add_system_instruction(prompt))
            if result.text:
                parsed = self._parse_json(
                    result.text,
                    {
                        'answer': '',
                        'referenced_pages': [],
                        'co_detection': {'needed': None, 'reason': None},
                        'notes': [],
                    },
                )
                return {'success': True, 'response': parsed}

            return {
                'success': False,
                'error': result.error or 'Empty response from Gemini',
                'prompt_feedback': result.prompt_feedback,
            }
        except GeminiPromptBlocked as exc:
            return {
                'success': False,
                'error': str(exc),
                'prompt_feedback': self._format_prompt_feedback(exc.prompt_feedback),
            }
        except GeminiRequestFailed as exc:
            return {
                'success': False,
                'error': str(exc),
                'prompt_feedback': self.last_prompt_feedback,
            }
        except Exception as exc:
            logger.error("Follow-up question failed: %s", exc, exc_info=True)
            return {'success': False, 'error': str(exc)}

    def analyze_pdf(
        self,
        pdf_path: str,
        include_images: bool = True,
        spec_pdf_path: Optional[str] = None,
        additional_spec_paths: Optional[List[str]] = None,
        analysis_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive fire alarm analysis of construction bid set PDF
        """
        if not self.client:
            return {
                'success': False,
                'error': 'Gemini AI not initialized. Check API key.'
            }

        try:
            self.last_prompt_feedback = None
            if analysis_mode and not self.update_analysis_mode(analysis_mode):
                return {
                    'success': False,
                    'error': f"Invalid analysis mode '{analysis_mode}'. Allowed modes: {', '.join(ANALYSIS_MODES)}"
                }

            logger.info(f"Starting Gemini analysis of PDF: {pdf_path}")

            pages_text = self.pdf_processor.extract_text_from_pdf(pdf_path)
            filtered_pages = self._filter_pages_for_gemini(pages_text)

            spec_sections: List[Dict[str, Any]] = []
            spec_paths: List[str] = []
            if spec_pdf_path:
                spec_paths.append(spec_pdf_path)
            if additional_spec_paths:
                spec_paths.extend([path for path in additional_spec_paths if path])

            spec_source_files = [os.path.basename(path) for path in spec_paths]

            for path in spec_paths:
                try:
                    spec_pages = self.pdf_processor.extract_text_from_pdf(path)
                    spec_sections.extend(self._filter_spec_book_sections(spec_pages))
                except Exception as exc:
                    logger.error("Failed to process spec attachment %s: %s", path, exc)

            if not filtered_pages:
                return {
                    'success': False,
                    'error': 'All pages were filtered out before Gemini analysis.'
                }

            image_pages: List[int] = []
            image_payload: Optional[List[Dict[str, Any]]] = None
            image_error: Optional[str] = None
            if include_images:
                image_pages = self._select_pages_for_image_transmission(filtered_pages)
                try:
                    image_payload = self._build_image_payload(pdf_path, image_pages)
                except Exception as exc:  # pragma: no cover - defensive guard for heavy PDFs
                    image_error = f"Failed to render images for Gemini: {exc}"
                    logger.error(image_error, exc_info=True)
                    image_payload = None

            results = self._run_analysis_pipeline(
                filtered_pages,
                image_payload,
                image_pages,
                spec_sections,
                spec_source_files,
            )

            results["generation_settings"] = self._current_generation_settings()

            if include_images:
                results['image_pages_sent'] = image_pages
                results['images_attached_to_gemini'] = bool(image_payload)
                if image_error:
                    results['image_error'] = image_error

            results['analysis_mode'] = self.analysis_mode

            return results
        except GeminiPromptBlocked as exc:
            logger.error("Gemini analysis blocked: %s", exc)
            return {
                'success': False,
                'error': str(exc),
                'prompt_feedback': self.last_prompt_feedback
            }
        except GeminiRequestFailed as exc:
            logger.error("Gemini analysis failed after retries: %s", exc)
            return {
                'success': False,
                'error': str(exc),
                'prompt_feedback': self.last_prompt_feedback
            }
        except Exception as e:
            logger.error(f"Error during Gemini analysis: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'prompt_feedback': self.last_prompt_feedback
            }
    
    def _analyze_cover_pages(
        self,
        cover_pages: List[Dict],
        image_payload: Optional[List[Dict[str, Any]]] = None,
        image_pages: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Analyze cover pages for project information"""

        cover_text = "\n\n".join([p['text'] for p in cover_pages])

        image_note = self._image_guidance_text(image_payload, image_pages)

        prompt = f"""Analyze these construction bid set cover pages and extract ONLY the high-level project details that matter to a fire alarm estimator.

COVER PAGES TEXT:
{cover_text[:15000]}

{image_note}

Extract the following information:
1. PROJECT NAME: Official name of the project
2. PROJECT ADDRESS OR LOCATION: Street address or city/state reference
3. PROJECT TYPE: (e.g., School, Hospital, Office Building, High-Rise, etc.)
4. APPLICABLE CODES: List any specific code versions mentioned (e.g., "IBC 2018", "NFPA 72-2016").
5. FIRE ALARM REQUIRED: State "Yes", "No", or "Unknown" based on the documents.
6. SPRINKLER STATUS: Indicate if the building is sprinkled and if FA must monitor it.
7. SCOPE SUMMARY: Brief summary of the overall project scope.
8. VOICE REQUIRED: State "Yes", "No", or "Unknown" based on the documents.

        Format your response as JSON with these keys: project_name, project_address, project_location, project_type, applicable_codes, fire_alarm_required, sprinkler_status, scope_summary, voice_required.
        If information is not found, use null.
        """

        try:
            result = self._generate_model_text(prompt, images=image_payload)
            if result.text:
                return self._parse_json(result.text, {})

            return {
                'error': result.error or 'Gemini returned an empty response.',
                'prompt_feedback': result.prompt_feedback,
            }
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as e:
            logger.error(f"Error analyzing cover pages: {str(e)}")
            return {'error': str(e)}

    def _identify_fire_alarm_pages(self, pages_text: List[Dict]) -> List[int]:
        """Identify which pages contain fire alarm information"""
        
        fa_pages = []
        fa_keywords = [
            'fire alarm', 'fa device', 'smoke detector', 'heat detector',
            'pull station', 'notification device', 'horn strobe', 'speaker strobe',
            'fire alarm control', 'facp', 'control panel', 'annunciator',
            'special systems', 'power plan', 'electrical plan',
            'life safety plan', 'fire alarm general notes', 'fire alarm riser',
            'special systems plan', 'fire protection plan', 'fa', 'nfpa', 'ann',
            'low voltage', 'telecom', 'security', 'data', 'technology', 'communications',
            'lv ', ' t-', 'tn-', 'ty-', 'ts-'
        ]
        
        for page in pages_text:
            page_text_lower = page['text'].lower()
            
            # primary check
            if any(keyword in page_text_lower for keyword in fa_keywords):
                # exclusion check for typical non-relevant text if needed, 
                # but for now we want to be inclusive for Low Voltage
                if 'mounting height' not in page_text_lower or \
                   'fire alarm' in page_text_lower or 'low voltage' in page_text_lower:
                    fa_pages.append(page['page_number'])
        
        return sorted(list(set(fa_pages))) # Return unique, sorted list

    def _extract_toc_fa_page_numbers(self, pages_text: List[Dict]) -> List[int]:
        """
        Scan the first several pages for a Sheet Index / Table of Contents that lists
        fire-alarm-related sheets, then return the PDF page numbers of those sheets so
        they can be force-included even when their own extracted text is sparse.

        Strategy: the TOC page itself references FA sheets by sheet label (e.g. 1-FA-0001).
        The actual FA drawing page will typically have that same label somewhere in its
        extracted text.  We collect the labels from the TOC, then scan ALL pages looking
        for any page whose text contains one of those labels.
        """

        # Sheet-label patterns that indicate fire alarm content in a TOC row
        fa_toc_patterns = re.compile(
            r"""
            \b(?:
              (?:fa|fs|ls)[-_]?\d              |  # FA-001, FS-1, LS-2
              \d+-fa-\d                         |  # 1-FA-0001
              fire\s+alarm                      |  # "fire alarm" sheet title
              fire\s+protection                 |  # "fire protection" sheet title
              special\s+systems                 |  # "special systems" sheet title
              life\s+safety                     |  # "life safety" sheet title
              power\s+plan                         # "power plan" (sometimes hosts FA)
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        )

        # Sheet label extractor — grabs things like "1-FA-0001", "E-FA-101", "FA-001"
        label_extractor = re.compile(
            r"\b(?:\w+-)?fa-\w+|\bfs-\w+|\bls-\w+",
            re.IGNORECASE,
        )

        # Only scan the first 8 pages for a TOC
        toc_pages = pages_text[:8]
        toc_found = False
        collected_labels: set = set()

        for page in toc_pages:
            text = page.get("text") or ""
            text_lower = text.lower()

            # Does this look like a sheet index?
            is_toc = (
                "sheet index" in text_lower
                or "drawing index" in text_lower
                or "sheet list" in text_lower
                or "drawing list" in text_lower
                or "index of drawings" in text_lower
                or "list of drawings" in text_lower
                or "table of contents" in text_lower
            )

            if not is_toc:
                continue

            toc_found = True
            # Does the TOC mention FA sheets at all?
            if fa_toc_patterns.search(text_lower):
                # Extract specific label strings so we can match them to pages later
                for match in label_extractor.finditer(text):
                    collected_labels.add(match.group(0).lower())

        if not toc_found or not collected_labels:
            return []

        logger.info(
            "TOC references %s FA-related sheet labels: %s",
            len(collected_labels),
            ", ".join(sorted(collected_labels)[:20]),
        )

        # Find which PDF pages carry those labels in their extracted text
        referenced_pages: List[int] = []
        for page in pages_text:
            page_text_lower = (page.get("text") or "").lower()
            page_num = page.get("page_number")
            if page_num is None:
                continue
            if any(label in page_text_lower for label in collected_labels):
                referenced_pages.append(page_num)

        logger.info(
            "TOC-referenced FA pages found in PDF: %s",
            referenced_pages[:30],
        )
        return referenced_pages

    def _prioritize_pages_for_ai(
        self,
        pages_text: List[Dict[str, Any]],
        fa_pages: List[int],
        max_pages: int = 40,
    ) -> List[Dict[str, Any]]:
        """Return a trimmed list of representative pages to keep prompts fast."""

        prioritized: List[Dict[str, Any]] = []
        seen_pages = set()

        def add_page(page: Dict[str, Any]):
            page_number = page.get('page_number')
            if page_number in seen_pages:
                return
            seen_pages.add(page_number)
            prioritized.append(page)

        # 1. Always include the first few pages for project context (Cover/Index)
        for page in pages_text[:4]:
            add_page(page)

        # 2. Bring in ALL pages the rule-based detector tagged as fire alarm/low voltage
        # We prioritize these above all else.
        for page in pages_text:
            if page.get('page_number') in fa_pages:
                add_page(page)

        # 3. Explicitly grab Electrical (E-series) and MEP pages if not already caught
        # Look for "E-" in page labels if available, or "Electrical" in text
        # Also include MEP, ME, Mechanical and Electrical sections
        electrical_keywords = {
            'electrical', 'lighting', 'power', 'E-', 'E0', 'E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8', 'E9',
            'mep', 'me-', 'me1', 'me2', 'me3', 'mechanical and electrical'
        }
        for page in pages_text:
            if len(seen_pages) >= max_pages:
                break
            if page.get('page_number') in seen_pages:
                continue
            text = (page.get('text') or '').lower()
            if any(k in text for k in electrical_keywords):
                 add_page(page)

        # 4. Grab mechanical/HVAC-heavy pages because they often influence FA scope
        mechanical_keywords = {'mechanical', 'hvac', 'duct', 'damper', 'air handler', 'rtu', 'ahu', 'M-', 'M0', 'M1'}
        for page in pages_text:
            if len(seen_pages) >= max_pages:
                break
            if page.get('page_number') in seen_pages:
                continue
            text = (page.get('text') or '').lower()
            if any(keyword in text for keyword in mechanical_keywords):
                add_page(page)

        # 5. Fill remaining slots with the earliest pages to preserve document order
        for page in pages_text:
            if len(prioritized) >= max_pages:
                break
            add_page(page)

        return prioritized[:max_pages]
    
    def _extract_code_requirements(
        self,
        pages_text: List[Dict],
        image_payload: Optional[List[Dict[str, Any]]] = None,
        image_pages: Optional[List[int]] = None,
    ) -> Dict[str, List[str]]:
        """Extract fire-alarm-specific codes and standards"""

        code_pages = "\n\n".join([p['text'] for p in pages_text[:10]])  # Focus on front matter

        image_note = self._image_guidance_text(image_payload, image_pages)

        prompt = f"""Identify only the fire alarm and life-safety codes cited in this project.

DOCUMENT TEXT:
{code_pages[:10000]}

{image_note}

Extract a concise list of the exact editions referenced for:
• FIRE ALARM CODES AND STANDARDS (e.g., NFPA 72-2019, NFPA 101-2018, UL 864).
• BUILDING CODES (e.g., IBC 2018, CBC 2019) if they are relevant to Life Safety.

Also, briefly note if you detect any CONFLICTS between cited codes (e.g., citing an outdated NFPA version vs a newer IBC).

        Return JSON with:
        - fire_alarm_codes: array of strings (e.g. ["NFPA 72-2016", "IBC 2015"])
        - code_notes: string (optional, for any conflicts or observations)
        """

        try:
            result = self._generate_model_text(prompt, images=image_payload)
            if not result.text:
                return {
                    'fire_alarm_codes': [],
                    'error': result.error,
                    'prompt_feedback': result.prompt_feedback,
                }

            data = self._parse_json(result.text, {})
            if isinstance(data, dict) and 'fire_alarm_codes' not in data:
                # Backwards compatibility with older schema
                fire_alarm_codes = data.get('fire_alarm_standards') or []
                return {'fire_alarm_codes': fire_alarm_codes}
            return data
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as e:
            logger.error(f"Error extracting codes: {str(e)}")
            return {'fire_alarm_codes': [], 'error': str(e)}
    
    def _extract_fire_alarm_notes(
        self,
        pages_text: List[Dict],
        fa_pages: List[int],
        image_payload: Optional[List[Dict[str, Any]]] = None,
        image_pages: Optional[List[int]] = None,
    ) -> List[Dict[str, str]]:
        """Extract fire alarm general notes from electrical pages"""
        
        fa_text = "\n\n".join([
            f"PAGE {p['page_number']}:\n{p['text']}" 
            for p in pages_text 
            if p['page_number'] in fa_pages
        ])
        
        if not fa_text:
            return []
        
        image_note = self._image_guidance_text(image_payload, image_pages)

        prompt = f"""Analyze these electrical/fire alarm pages and extract ONLY the PROJECT-SPECIFIC fire alarm notes.

PAGES TEXT:
{fa_text[:15000]}

{image_note}

Extract fire alarm notes that are:
✓ Panel, annunciator, or riser room locations and access instructions
✓ Critical system requirements or specialty devices (e.g., elevator recall interfaces, suppression system tie-ins, beam/aspirating detection, smoke control interfaces)
✓ Unique installation constraints that affect layout or pricing (e.g., weatherproof requirements for garage devices, conduit routing requirements, monitoring of fire pump or generator)
✓ Coordination notes with other trades that the fire alarm contractor must address
✓ Code Compliance Notes that are specific to this project (e.g., "System must meet NFPA 72-2019 spacing")

DO NOT extract:
✗ Standard NFPA mounting heights (unless non-standard)
✗ Generic "shall comply with" statements
✗ Standard distance from walls/ceilings
✗ Boilerplate code compliance text
✗ General electrical notes not related to fire alarm
✗ Locations of typical field devices (e.g., individual smoke detectors, horn/strobes) unless the note calls out a unique or critical device
✗ Any mention of fire stopping, fire sealing, or other references to construction trades outside of the fire alarm scope

Format as JSON array with objects containing:
- page: page number
- note_type: (e.g., "System Requirement", "Device Specification", "Installation Note", "Code Compliance")
- content: the actual note text

Example:
[{{"page": 5, "note_type": "System Requirement", "content": "All devices shall be addressable"}}]
"""

        try:
            result = self._generate_model_text(prompt, images=image_payload)
            if not result.text:
                return []
            parsed_notes = self._parse_json(result.text, [])
            if not isinstance(parsed_notes, list):
                return []

            unique_notes = []
            seen_contents = set()

            for note in parsed_notes:
                if not isinstance(note, dict):
                    continue

                content = (note.get('content') or note.get('note') or note.get('text') or '').strip()
                if not content:
                    continue

                normalized = re.sub(r"\s+", " ", content).lower()
                if normalized in seen_contents:
                    continue
                seen_contents.add(normalized)

                unique_notes.append({
                    'page': note.get('page'),
                    'note_type': note.get('note_type'),
                    'content': content,
                })

            return unique_notes
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as e:
            logger.error(f"Error extracting FA notes: {str(e)}")
            return []
    
    def _extract_mechanical_fa_devices(
        self,
        pages_text: List[Dict],
        image_payload: Optional[List[Dict[str, Any]]] = None,
        image_pages: Optional[List[int]] = None,
    ) -> Dict[str, List[Dict]]:
        """Extract duct detectors and fire/smoke dampers from mechanical pages"""
        
        mech_pages = []
        for page in pages_text:
            page_lower = page['text'].lower()
            if any(keyword in page_lower for keyword in [
                'mechanical', 'hvac', 'duct', 'damper', 'air handler', 'rtu', 'ahu', "fsd", "smoke damper", "fire damper", "fire smoke damper"
            ]):
                mech_pages.append(page)
        
        if not mech_pages:
            return {'duct_detectors': [], 'dampers': []}
        
        mech_text = "\n\n".join([
            f"PAGE {p['page_number']}:\n{p['text']}" 
            for p in mech_pages
        ])
        
        image_note = self._image_guidance_text(image_payload, image_pages)

        prompt = f"""Analyze these mechanical pages and extract fire alarm-related devices.

Always check the HVAC schedule to see if any equipment moves more than 2000 CFM. Those units should be listed with airflow and
whether a duct detector/relay is required.
For dampers, flag only NON-FUSIBLE-LINK types that require fire alarm control; fused-link dampers do NOT need relays.

MECHANICAL PAGES TEXT:
{mech_text[:15000]}

{image_note}

Extract:
1. DUCT DETECTORS: Location, type, airflow (if given), specifications
2. FIRE/SMOKE DAMPERS: Location, type (state if non-fusible link), required fire alarm action/relay
3. HIGH AIRFLOW HVAC: Any HVAC equipment over 2000 CFM from the schedule with airflow, ID, and whether a duct detector or relay is
   required.

   Synthesize your findings across all mechanical pages to ensure no duplicate devices are listed unless they are distinct.
   If a schedule is on one page and the plan view on another, combine the information.

For each device, extract:
- page: page number
- device_type: specific type (e.g., "Duct Smoke Detector", "Fire Damper")
- location: where it's located (e.g., "RTU-1", "all transfer ducts")
- quantity: if specified
- airflow_cfm: airflow if provided (use number only)
- damper_type: state "non-fusible link" or "fusible link" when mentioned
- requires_duct_detector: Yes/No if airflow is over 2000 CFM
- fire_alarm_action/specifications: any specific requirements (e.g., "provide relay to FACP")

Format as JSON with keys:
- duct_detectors: array of duct detector objects
- dampers: array of damper objects
- high_airflow_units: array of HVAC equipment over 2000 CFM

Only return devices that require fire alarm integration. Ignore generic HVAC notes or mechanical requirements that do not involve fire alarm monitoring or control. If none found, use empty arrays.
"""

        try:
            result = self._generate_model_text(prompt, images=image_payload)
            if not result.text:
                return {
                    'duct_detectors': [],
                    'dampers': [],
                    'high_airflow_units': [],
                    'error': result.error,
                    'prompt_feedback': result.prompt_feedback,
                }
            return self._parse_json(
                result.text,
                {'duct_detectors': [], 'dampers': [], 'high_airflow_units': []},
            )
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as e:
            logger.error(f"Error extracting mechanical devices: {str(e)}")
            return {'duct_detectors': [], 'dampers': [], 'high_airflow_units': [], 'error': str(e)}

    def _review_device_layout(
        self,
        pages_text: List[Dict[str, Any]],
        fa_pages: List[int],
        image_payload: Optional[List[Dict[str, Any]]] = None,
        image_pages: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Review device placement, page numbers, and CO detection needs."""

        fa_text = "\n\n".join(
            [f"PAGE {p['page_number']}:\n{p['text']}" for p in pages_text if p.get('page_number') in fa_pages]
        )

        if not fa_text:
            return {}

        image_note = self._image_guidance_text(image_payload, image_pages)

        prompt = f"""Review these fire alarm/electrical pages. Identify where devices are called out and flag unusual placements.

PAGES TEXT:
{fa_text[:16000]}

{image_note}

Review the ENTIRE SET of provided pages to understand the overall fire alarm design intent.

Extract the following and ALWAYS provide page numbers where available:
1) PRIMARY DEVICE PAGE: Identify the single page/sheet where the most fire alarm devices are shown or called out. Provide the page number and a short reason (e.g., "main FA floor plan" or "device matrix"). Do NOT list each device individually.
2) UNUSUAL PLACEMENTS: If devices appear in atypical locations (e.g., notification appliance inside mechanical room, detector outdoors), capture the placement and the stated reason or probable intent.
3) CO DETECTION CHECK: State whether carbon monoxide detection is required or explicitly not required, and why (e.g., fuel-burning equipment, parking garage, or explicit note).

Return JSON with:
{{
  "primary_fa_page": {{"page": 1, "reason": "Main FA device layout"}},
  "unusual_placements": [{{"page": 2, "device_type": "Strobe", "placement": "Mechanical room", "reason": "Owner request for internal alarm"}}],
  "co_detection": {{"needed": "Yes/No/Unknown", "reason": "why"}}
}}
"""

        try:
            result = self._generate_model_text(prompt, images=image_payload)
            if not result.text:
                return {
                    'primary_fa_page': {},
                    'unusual_placements': [],
                    'co_detection': {'needed': None, 'reason': None},
                    'error': result.error,
                    'prompt_feedback': result.prompt_feedback,
                }
            return self._parse_json(
                result.text,
                {'primary_fa_page': {}, 'unusual_placements': [], 'co_detection': {'needed': None, 'reason': None}},
            )
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as exc:
            logger.error("Error during device layout review: %s", exc)
            return {'primary_fa_page': {}, 'unusual_placements': [], 'co_detection': {'needed': None, 'reason': str(exc)}}

    def _extract_specifications(
        self,
        pages_text: List[Dict],
        fa_pages: List[int],
        image_payload: Optional[List[Dict[str, Any]]] = None,
        image_pages: Optional[List[int]] = None,
        spec_sections: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Extract fire alarm system specifications"""
        
        fa_text = "\n\n".join([
            f"PAGE {p['page_number']}:\n{p['text']}"
            for p in pages_text
            if p['page_number'] in fa_pages
        ])

        general_notes_text = "\n\n".join([
            f"PAGE {p['page_number']}:\n{p['text']}"
            for p in pages_text
            if 'general note' in p.get('text', '').lower()
        ])

        spec_text = self._compile_spec_excerpt(spec_sections)

        combined_text = "\n\n".join(filter(None, [
            "FIRE ALARM PAGES:\n" + fa_text if fa_text else "",
            "GENERAL NOTES (include these when checking for existing panels):\n" + general_notes_text if general_notes_text else "",
            "SPEC BOOK FIRE ALARM EXCERPTS:\n" + spec_text if spec_text else "",
        ])).strip()

        if not combined_text:
            return {}

        image_note = self._image_guidance_text(image_payload, image_pages)

        prompt = f"""Extract fire alarm system specifications from these pages and spec book excerpts. Always review fire alarm related notes AND any
general notes to see if the plans list the manufacturer/model of an existing fire alarm control panel. IMPORTANT: Keyed notes and general notes
frequently specify required manufacturers using phrases like "system to be [Brand]", "shall be [Brand] [Model]", "basis of design: [Brand]", or
"compatible with [Brand] system". Always scan all notes for these patterns and include any found brands in APPROVED_MANUFACTURERS. Recognized
Edwards/EST models include EST3, EST4, FSP502, FSP1004, FireShield, iO Series.

SOURCE TEXT:
{combined_text[:15000]}

{image_note}

Extract:
1. CONTROL PANEL: Manufacturer, model, features.
2. DEVICES: Types of devices required (smoke, heat, pull stations, etc.).
3. NOTIFICATION DEVICES: Types (horns, strobes, speakers, low frequency sounders).
4. SYSTEM TYPE: (e.g., Addressable, Conventional, Voice Evac).
5. WIRING CLASS: (e.g., Class A, Class B, Style 4, Style 6, Style 7).
6. COMMUNICATION: How system communicates (Ethernet, phone line, cellular, radio).
7. POWER REQUIREMENTS: Backup battery (e.g. 24hr + 5min), UPS requirements.
8. MONITORING: Central station monitoring requirements.
9. INTEGRATION: Integration with other systems (access control, BMS, elevator, suppression).
10. SPRINKLER SYSTEM: State whether the building has a sprinkler system and how the fire alarm must monitor it.
11. APPROVED MANUFACTURERS: List any specific fire alarm manufacturers/brands the specifications call out (return an array).
12. AUDIO / VOICE SYSTEM: Specify if a voice evacuation or audio system is required, optional, or explicitly not required.
13. EXISTING SYSTEM PANEL MODEL: If the drawings mention an existing fire alarm panel to remain, capture the exact
    manufacturer and model number from any fire alarm notes or general notes. Return null if nothing is referenced.

Format as JSON with these keys: CONTROL_PANEL, DEVICES, NOTIFICATION_DEVICES, SYSTEM_TYPE, WIRING_CLASS, COMMUNICATION, POWER_REQUIREMENTS, MONITORING, INTEGRATION, SPRINKLER_SYSTEM, APPROVED_MANUFACTURERS, AUDIO_SYSTEM, EXISTING_SYSTEM_PANEL_MODEL.
        Use null if not found. APPROVED_MANUFACTURERS should be an array if provided.
        """

        try:
            result = self._generate_model_text(prompt, images=image_payload)
            if not result.text:
                return {'error': result.error, 'prompt_feedback': result.prompt_feedback}
            return self._parse_json(result.text, {})
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as e:
            logger.error(f"Error extracting specifications: {str(e)}")
            return {'error': str(e)}

    def _derive_code_based_expectations(
        self,
        pages_text: List[Dict[str, Any]],
        codes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Infer likely fire alarm requirements when drawings show no FA content."""

        if not pages_text:
            return {}

        cited_codes = []
        if isinstance(codes, dict):
            cited_codes = codes.get('fire_alarm_codes') or []

        front_matter = "\n\n".join([
            f"PAGE {p.get('page_number')}:\n{p.get('text','')}" for p in pages_text[:6]
        ])[:15000]

        prompt = f"""The project documents below do not show any explicit fire alarm design or general notes. Based on the
building description, occupancy hints, and the referenced codes, infer what the fire alarm scope would likely need to
include to meet code minimums.

CITED CODES: {', '.join(cited_codes) if cited_codes else 'No fire alarm codes explicitly cited'}

PROJECT TEXT (front matter & summaries):
{front_matter}

Return JSON with:
- expected_scope: array of short bullet strings describing the minimum FA system/features likely required by the cited code(s)
- assumptions: array of assumptions you had to make (occupancy, area, construction type, etc.)
- notes: array of advisories or next steps to confirm with the AHJ
- code_path: string summarizing which code/edition you relied upon (or "Unknown")
"""

        try:
            result = self._generate_model_text(self._add_system_instruction(prompt))
            if not result.text:
                return {'error': result.error, 'prompt_feedback': result.prompt_feedback}
            parsed = self._parse_json(
                result.text,
                {
                    'expected_scope': [],
                    'assumptions': [],
                    'notes': [],
                    'code_path': None,
                },
            )
            return parsed if isinstance(parsed, dict) else {}
        except GeminiPromptBlocked:
            raise
        except GeminiRequestFailed:
            raise
        except Exception as exc:
            logger.error("Error deriving code-based expectations: %s", exc)
            return {}

    # ---------------------------------------------------------------------
    # Derived summary blocks for UI consumption
    # ---------------------------------------------------------------------
    def _build_high_level_overview(self, project_info: Dict[str, Any], specifications: Dict[str, Any]) -> Dict[str, Any]:
        """Create a concise project snapshot for the estimator-focused UI."""

        sprinkler_status = project_info.get('sprinkler_status') or self._get_spec_value(specifications, 'SPRINKLER_SYSTEM')
        fire_alarm_required = project_info.get('fire_alarm_required')

        return {
            'project_name': project_info.get('project_name') or project_info.get('name'),
            'project_address': project_info.get('project_address') or project_info.get('project_location') or project_info.get('location'),
            'project_type': project_info.get('project_type'),
            'fire_alarm_required': fire_alarm_required or 'Unknown',
            'sprinkler_status': sprinkler_status,
            'scope_summary': project_info.get('scope_summary'),
            'project_number': project_info.get('project_number'),
        }

    def _build_fire_alarm_briefing(
        self,
        codes: Dict[str, Any],
        specifications: Dict[str, Any],
        fire_alarm_notes: List[Dict[str, Any]],
        device_layout_review: Optional[Dict[str, Any]] = None,
        code_based_expectations: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compile key requirements and notes for the fire alarm scope."""

        requirement_items: List[str] = []
        for label in [
            'SYSTEM_TYPE',
            'COMMUNICATION',
            'MONITORING',
            'AUDIO_SYSTEM',
            'APPROVED_MANUFACTURERS',
            'CONTROL_PANEL',
        ]:
            value = self._get_spec_value(specifications, label)
            if value:
                pretty_label = label.replace('_', ' ').title()
                requirement_items.append(f"{pretty_label}: {value}")

        equipment_items: List[str] = []

        codes_list = []
        if isinstance(codes, dict) and isinstance(codes.get('fire_alarm_codes'), list):
            codes_list = codes['fire_alarm_codes']

        co_detection = (device_layout_review or {}).get('co_detection') or {}
        if co_detection.get('needed'):
            co_note = f"CO detection: {co_detection.get('needed')}"
            if co_detection.get('reason'):
                co_note += f" ({co_detection['reason']})"
            requirement_items.append(co_note)

        if code_based_expectations:
            scope = code_based_expectations.get('expected_scope') or []
            if scope:
                requirement_items.append(
                    "Code-based expected scope (no FA shown): " + "; ".join(scope[:4])
                )
            assumptions = code_based_expectations.get('assumptions') or []
            if assumptions:
                requirement_items.extend([f"Assumption: {item}" for item in assumptions[:3]])


        return {
            'requirements': requirement_items,
            'equipment': equipment_items,
            'codes': codes_list,
            'notes': fire_alarm_notes or (code_based_expectations.get('notes') if code_based_expectations else []) or [],
        }

    def _get_spec_value(self, specifications: Dict[str, Any], key: str) -> Optional[Any]:
        """Retrieve a specification value with flexible casing."""

        if not specifications or not key:
            return None

        direct = specifications.get(key)
        if direct:
            return direct

        lower = key.lower()
        if lower in specifications:
            return specifications[lower]

        upper = key.upper()
        if upper in specifications:
            return specifications[upper]

        return None

    def _build_structured_summary(
        self,
        project_info: Dict[str, Any],
        specifications: Dict[str, Any],
        codes: Dict[str, Any],
        fire_alarm_notes: List[Dict[str, Any]],
        mechanical_devices: Dict[str, List[Dict[str, Any]]],
        device_layout_review: Optional[Dict[str, Any]] = None,
        code_based_expectations: Optional[Dict[str, Any]] = None,
        possible_pitfalls: Optional[List[str]] = None,
        provided_estimating_notes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a structured summary with pitfalls and estimator notes."""

        section_list: List[Dict[str, Any]] = []
        pitfalls: List[str] = []
        estimating_notes: List[str] = []

        def add_unique(target: List[str], message: Optional[str]):
            if message and isinstance(message, str):
                text = message.strip()
                if text and text not in target:
                    target.append(text)

        def add_pitfall(message: Optional[str]):
            add_unique(pitfalls, message)

        def add_estimator_note(message: Optional[str]):
            add_unique(estimating_notes, message)

        for pitfall in possible_pitfalls or []:
            add_pitfall(pitfall)

        for note in provided_estimating_notes or []:
            add_estimator_note(note)

        # Project snapshot section
        overview_bullets = []
        if project_info.get('project_type'):
            overview_bullets.append(f"Type: {project_info['project_type']}")
        if project_info.get('project_address') or project_info.get('project_location'):
            overview_bullets.append(
                f"Location: {project_info.get('project_address') or project_info.get('project_location')}"
            )
        if project_info.get('scope_summary'):
            overview_bullets.append(f"Scope: {project_info['scope_summary']}")
        if project_info.get('project_number'):
            overview_bullets.append(f"Project # {project_info['project_number']}")

        if overview_bullets:
            section_list.append(
                {
                    'title': 'Project Snapshot',
                    'bullets': overview_bullets,
                    'summary': project_info.get('scope_summary'),
                }
            )

        # Specification highlights
        spec_bullets = []
        for label in [
            'CONTROL_PANEL',
            'SYSTEM_TYPE',
            'COMMUNICATION',
            'MONITORING',
            'AUDIO_SYSTEM',
            'APPROVED_MANUFACTURERS',
        ]:
            value = self._get_spec_value(specifications, label)
            if value:
                pretty = label.replace('_', ' ').title()
                spec_bullets.append(f"{pretty}: {value}")

        if spec_bullets:
            section_list.append(
                {
                    'title': 'Specifications',
                    'bullets': spec_bullets,
                    'summary': 'Key fire alarm specification calls.',
                }
            )

        # Codes
        fire_codes = []
        if isinstance(codes, dict) and isinstance(codes.get('fire_alarm_codes'), list):
            fire_codes = codes.get('fire_alarm_codes') or []

        if fire_codes:
            section_list.append(
                {
                    'title': 'Fire Alarm Codes',
                    'bullets': fire_codes,
                    'summary': 'Codes and editions cited for the fire alarm scope.',
                }
            )

        # Fire alarm notes
        if fire_alarm_notes:
            note_bullets = []
            for note in fire_alarm_notes:
                page = note.get('page')
                content = note.get('content')
                note_type = note.get('note_type')
                if content:
                    prefix = f"Page {page}: " if page is not None else ""
                    label = f"[{note_type}] " if note_type else ""
                    note_bullets.append(f"{prefix}{label}{content}")

            if note_bullets:
                section_list.append(
                    {
                        'title': 'Fire Alarm Notes',
                        'bullets': note_bullets,
                        'summary': 'Project-specific fire alarm notes pulled from the drawings.',
                    }
                )

        # Mechanical devices
        mech_bullets = []
        for device_type, devices in (mechanical_devices or {}).items():
            if not isinstance(devices, list):
                continue
            for device in devices:
                if isinstance(device, str):
                    device = {'device_type': device}
                elif not isinstance(device, dict):
                    continue
                label = device.get('device_type') or device.get('type') or device_type
                location = device.get('location') or device.get('equipment_id')
                qty = device.get('quantity')
                details = device.get('specifications') or device.get('specs')
                airflow = device.get('airflow_cfm')
                damper_type = device.get('damper_type')
                fa_action = device.get('fire_alarm_action')
                requires_dd = device.get('requires_duct_detector')

                parts = [label]
                if location:
                    parts.append(f"at {location}")
                if qty:
                    parts.append(f"qty: {qty}")
                if airflow:
                    parts.append(f"airflow: {airflow} CFM")
                if damper_type:
                    parts.append(str(damper_type))
                if requires_dd:
                    parts.append(f"duct detector: {requires_dd}")
                if details:
                    parts.append(str(details))
                if fa_action:
                    parts.append(str(fa_action))

                mech_bullets.append(" - ".join(parts))

        if mech_bullets:
            section_list.append(
                {
                    'title': 'Mechanical-Linked Devices',
                    'bullets': mech_bullets,
                    'summary': 'Duct detectors and fire/smoke dampers that need FA integration.',
                }
            )

        # Device layout review (locations, unusual placements, CO detection)
        if device_layout_review:
            layout_bullets: List[str] = []

            if not isinstance(device_layout_review, dict):
                layout_bullets.append(str(device_layout_review))
                device_layout_review = {}

            primary_page = device_layout_review.get('primary_fa_page') or {}
            if isinstance(primary_page, dict) and primary_page:
                page = primary_page.get('page')
                reason = primary_page.get('reason') or primary_page.get('note')
                text = f"Most fire alarm devices shown on page {page if page is not None else '?'}"
                if reason:
                    text += f" – {reason}"
                layout_bullets.append(text)

            unusual_entries = device_layout_review.get('unusual_placements', [])
            if unusual_entries and not isinstance(unusual_entries, (list, tuple)):
                unusual_entries = [unusual_entries]

            for unusual in unusual_entries or []:
                if isinstance(unusual, dict):
                    page = unusual.get('page')
                    device_label = unusual.get('device_type') or 'Device'
                    placement = unusual.get('placement')
                    reason = unusual.get('reason') or unusual.get('impact')
                    prefix = f"Page {page}: " if page is not None else ""
                    parts = [f"Unusual placement for {device_label}"]
                    if placement:
                        parts.append(str(placement))
                    if reason:
                        parts.append(str(reason))
                    layout_bullets.append(prefix + " - ".join(parts))
                else:
                    layout_bullets.append(str(unusual))

            co_detection = device_layout_review.get('co_detection') or {}
            if not isinstance(co_detection, dict):
                co_detection = {}
            co_needed = co_detection.get('needed')
            co_reason = co_detection.get('reason')
            if co_needed:
                text = f"CO detection needed: {co_needed}"
                if co_reason:
                    text += f" ({co_reason})"
                layout_bullets.append(text)

            if layout_bullets:
                section_list.append(
                    {
                        'title': 'Device Placement Review',
                        'bullets': layout_bullets,
                        'summary': 'Where devices are called out, unusual placements, and CO monitoring needs.',
                    }
                )

        # Pitfalls and estimator notes are provided directly by Gemini responses or
        # code-based expectations. Avoid injecting template questions or boilerplate
        # so the content stays project-specific.

        if code_based_expectations:
            for advisory in code_based_expectations.get('notes', []):
                add_estimator_note(advisory)

            for item in code_based_expectations.get('expected_scope', []) or []:
                add_estimator_note(f"Code-expected scope: {item}")

        sections_obj = {'estimating_notes': estimating_notes}

        return {
            'project_summary': project_info.get('scope_summary') or project_info.get('project_type'),
            'section_list': section_list,
            'pitfalls': pitfalls,
            'sections': sections_obj,
        }
