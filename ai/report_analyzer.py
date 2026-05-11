"""Lab report analysis using GPT-4o Vision."""
from typing import Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ai.client import get_vision_model
from utils.logger import logger

_SYSTEM_PROMPT = """You are a medical lab report analyzer. Extract all test results from the image.

Return a JSON object with this structure:
{
  "laboratory_name": "Lab name",
  "test_date": "YYYY-MM-DD",
  "tests": [
    {
      "parameter": "Test name",
      "value": "Numeric value",
      "unit": "Unit",
      "reference_range": "Normal range",
      "status": "normal | low | high | critical"
    }
  ]
}

Status rules:
- normal: value within reference range
- low: below reference range
- high: above reference range
- critical: dangerously outside range

Return null if the image is unreadable."""


async def analyze_report(file_data: dict) -> Optional[dict]:
    """
    Extract structured data from a lab report image.

    Args:
        file_data: dict with keys 'base64' (str) and 'mime_type' (str)

    Returns:
        Parsed report dict or None on failure.
    """
    try:
        llm = get_vision_model()
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{file_data['base64']}"},
                },
                {"type": "text", "text": "Extract all test results from this lab report."},
            ]),
        ])
        chain = prompt | llm | JsonOutputParser()
        return await chain.ainvoke({})
    except Exception:
        logger.exception("Error analyzing report")
        return None


def determine_overall_status(tests: list) -> str:
    """Classify overall report status from individual test statuses."""
    if not tests:
        return "unknown"
    statuses = [t.get("status", "normal") for t in tests]
    if "critical" in statuses:
        return "critical"
    abnormal = sum(1 for s in statuses if s in ("high", "low"))
    if abnormal == 0:
        return "green"
    return "red" if abnormal > len(statuses) * 0.5 else "yellow"
