"""Lightweight Notion client for exporting Gemini project info."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests


class NotionClient:
    """Simple wrapper for sending project snapshots to a Notion database."""

    def __init__(self, api_token: Optional[str], database_id: Optional[str]):
        self.api_token = api_token or ""
        self.database_id = database_id or ""
        self.session = requests.Session()

    def is_configured(self) -> bool:
        """Return True when both API token and database ID are present."""

        return bool(self.api_token and self.database_id)

    def build_properties(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Map Gemini results into Notion database properties."""

        project_info = results.get("project_info", {}) or {}
        name = project_info.get("project_name") or project_info.get("name")
        address = (
            project_info.get("project_address")
            or project_info.get("project_location")
            or project_info.get("location")
        )
        status = project_info.get("status") or "In progress"
        properties: Dict[str, Any] = {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": name or "Fire Alarm Project",
                        }
                    }
                ]
            }
        }

        if address:
            properties["Address"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": address,
                        }
                    }
                ]
            }

        if status:
            properties["Status"] = {"status": {"name": status}}

        return properties

    def build_children(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create basic content blocks summarizing the Gemini output."""

        children: List[Dict[str, Any]] = []
        structured_summary = results.get("structured_summary", {}) or {}
        project_info = results.get("project_info", {}) or {}
        fire_alarm_briefing = results.get("fire_alarm_briefing", {}) or {}

        summary_points: List[str] = []

        if project_info.get("scope_summary"):
            summary_points.append(f"Scope: {project_info['scope_summary']}")

        if structured_summary.get("system_overview"):
            summary_points.append(f"System overview: {structured_summary['system_overview']}")

        for bullet in fire_alarm_briefing.get("requirements", [])[:5]:
            summary_points.append(bullet)

        if not summary_points:
            return children

        children.append(
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "Fire Alarm Summary"},
                        }
                    ]
                },
            }
        )

        for point in summary_points:
            children.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": point},
                            }
                        ]
                    },
                }
            )

        return children

    def create_project_page(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Send the given Gemini results to Notion as a new page."""

        if not self.is_configured():
            return {"success": False, "error": "Notion configuration is missing."}

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": self.build_properties(results),
        }

        children = self.build_children(results)
        if children:
            payload["children"] = children

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(
                "https://api.notion.com/v1/pages", json=payload, headers=headers
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "page_id": data.get("id"),
                "url": data.get("url"),
            }
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).error("Failed to push to Notion: %s", exc)
            error_message = getattr(exc, "response", None)
            if error_message is not None:
                try:
                    detail = error_message.json()
                    return {
                        "success": False,
                        "error": detail.get("message")
                        or str(detail)
                        or "Notion API request failed.",
                    }
                except Exception:  # noqa: BLE001
                    pass

            return {"success": False, "error": str(exc) or "Notion API request failed."}
