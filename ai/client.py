import asyncio
import time

from openai import AsyncOpenAI

from config.settings import settings
from utils.logger import logger


class AIServiceError(Exception):
    def __init__(self, message, original_error=None):
        self.original_error = original_error
        super().__init__(message)


class AIClient:
    def __init__(self):
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )

    async def complete(
        self,
        messages: list,
        system_prompt: str = None,
        temperature: float = None,
        trace_name: str = "ai_completion",
    ) -> str:
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        temp = temperature if temperature is not None else settings.temperature
        _delays = [1, 2, 4]
        last_error = None

        for attempt in range(4):
            try:
                start = time.monotonic()
                response = await self._client.chat.completions.create(
                    model=settings.model,
                    messages=messages,
                    temperature=temp,
                )
                latency = time.monotonic() - start
                usage = response.usage
                logger.bind(
                    trace=trace_name,
                    model=settings.model,
                    latency_ms=round(latency * 1000),
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                ).info("AI completion")
                return response.choices[0].message.content

            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    delay = _delays[attempt]
                    logger.warning(
                        f"AI completion attempt {attempt + 1} failed ({exc}); "
                        f"retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)

        raise AIServiceError(
            f"AI service unavailable after 4 attempts: {last_error}",
            original_error=last_error,
        )

    async def analyze_report(
        self,
        extracted_text: str,
        patient_conditions: list,
        trace_name: str = "analyze_report",
    ) -> str:
        system_prompt = (
            "You are a medical data extraction assistant for Remedi Chronic Care, "
            "a Sri Lankan healthcare platform.\n\n"
            "Extract lab test results from the provided text and return ONLY valid JSON "
            "with no markdown, no explanation.\n\n"
            "Return this exact structure:\n"
            "{\n"
            '  "lab_name": "string or null",\n'
            '  "test_date": "YYYY-MM-DD or null",\n'
            '  "results": [\n'
            "    {\n"
            '      "parameter": "test name",\n'
            '      "value": "numeric value as string",\n'
            '      "unit": "unit string",\n'
            '      "reference_range": "e.g. 70-100 or <200",\n'
            '      "status": "normal | elevated | low | critical"\n'
            "    }\n"
            "  ],\n"
            '  "critical_flags": ["list of parameter names that are critical"],\n'
            '  "extraction_notes": "any issues with extraction or null"\n'
            "}"
        )

        user_message = (
            f"Patient conditions: {', '.join(patient_conditions)}\n\n"
            f"Lab report text:\n{extracted_text}\n\n"
            "Extract all test results from this report.\n"
            "Pay special attention to values outside reference ranges.\n"
            "For critical values use the patient conditions as context."
        )

        return await self.complete(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            trace_name="analyze_lab_report",
        )


ai_client = AIClient()
