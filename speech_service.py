"""Speech transcription helpers for AI-assisted daily report workflows.

This module intentionally keeps the speech-to-text logic server-side and
browser-agnostic: the browser may capture microphone audio, but the app is
responsible for mapping the resulting transcript into the canonical
DailyReport fields without creating a parallel write model.
"""

from __future__ import annotations

import re
from typing import Dict, Optional


class SpeechToTextProvider:
    """Normalize raw voice transcripts into safe daily-report fields."""

    MOOD_PATTERNS = {
        "happy": [
            "happy",
            "smiling",
            "cheerful",
            "good mood",
            "pleasant",
            "playing happily",
            "in good mood",
            "well",
        ],
        "sad": [
            "sad",
            "cry",
            "crying",
            "upset",
            "angry",
            "frustrated",
            "not happy",
        ],
        "tired": [
            "sleepy",
            "tired",
            "yawning",
            "needs rest",
            "nap time",
        ],
        "sick": [
            "sick",
            "fever",
            "cough",
            "cold",
            "ill",
            "vomit",
            "runny nose",
            "not feeling well",
        ],
    }

    ACTIVITY_PATTERNS = {
        "art": ["art", "painting", "drawing", "craft", "blocks"],
        "music": ["music", "singing", "song", "dance"],
        "sport": ["sport", "play outside", "running", "ball", "gym"],
        "story": ["story", "reading", "book"],
        "play": ["play", "played", "playing", "free play", "blocks", "toy"],
    }

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "")).strip()

    @classmethod
    def detect_mood(cls, transcript: str) -> str:
        normalized = cls._normalize_text(transcript).lower()
        for mood, patterns in cls.MOOD_PATTERNS.items():
            if any(pattern in normalized for pattern in patterns):
                return mood
        return "normal"

    @classmethod
    def detect_activities(cls, transcript: str) -> str:
        normalized = cls._normalize_text(transcript).lower()
        matched: list[str] = []
        seen: set[str] = set()
        for label, patterns in cls.ACTIVITY_PATTERNS.items():
            if any(pattern in normalized for pattern in patterns):
                activity_name = {
                    "art": "Art & Drawing",
                    "music": "Music",
                    "sport": "Sports",
                    "story": "Stories",
                    "play": "Play & Exploration",
                }[label]
                if activity_name not in seen:
                    matched.append(activity_name)
                    seen.add(activity_name)
        return ", ".join(matched) if matched else ""

    @classmethod
    def extract_health_notes(cls, transcript: str) -> Optional[str]:
        normalized = cls._normalize_text(transcript)
        patterns = [
            r"(?i)health note[s]?\s*[:\-]?\s*(.+?)(?=(?:\.|\n|$))",
            r"(?i)medical note[s]?\s*[:\-]?\s*(.+?)(?=(?:\.|\n|$))",
            r"(?i)symptom[s]?\s*[:\-]?\s*(.+?)(?=(?:\.|\n|$))",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                value = match.group(1).strip(" -:;,")
                if value:
                    return value

        maybe = re.search(r"(?i)\b(cough|fever|cold|vomit|runny nose|mild cough|sick|not feeling well)\b.*", normalized)
        if maybe:
            return maybe.group(0).strip(" .")
        return None

    @classmethod
    def map_transcript_to_daily_report(cls, transcript: str) -> Dict[str, Optional[str]]:
        clean = cls._normalize_text(transcript)
        health_notes = cls.extract_health_notes(clean)
        notes = clean

        if health_notes:
            notes = re.sub(rf"(?i)\bhealth note[s]?\b\s*[:\-]?\s*{re.escape(health_notes)}", "", notes, count=1).strip(" .;-:")
            notes = re.sub(r"\s+", " ", notes)

        mapped = {
            "mood": cls.detect_mood(clean),
            "health_notes": health_notes,
            "notes": notes or None,
            "activities": cls.detect_activities(clean),
        }
        return mapped
