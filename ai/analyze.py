import json
import base64
import httpx
import os
from dataclasses import dataclass
from openai import OpenAI


LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11435/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-no-key-required")
SKIP_AI = os.getenv("LLM_SKIP", False)


@dataclass
class AnalysisResult:
    growth_stage: str
    health: float
    disease: str
    recommended_params: dict


SYSTEM_PROMPT = """Ты эксперт-агроном. Проанализируй фото растения.
Верни СТРОГИЙ JSON без пояснений, в полях с числом используй одно число а не диапазон:
{
    "growth_stage": "стадия роста",
    "health": 0.0-1.0,
    "disease": "здоров/название болезни",
    "recommended_temp": 20-30,
    "recommended_humidity": 40-80,
    "recommended_ec": 1.0-3.0,
    "recommended_ph": 5.5-6.5,
    "light_duration": 12-18
}
"""


def encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def analyze(image_bytes: bytes, sensor_data: dict) -> AnalysisResult:
    if SKIP_AI:
        print("[analyze] Warning: AI skip")
        return AnalysisResult(
            growth_stage="Бебебе",
            health=0.77,
            disease="Здоров",
            recommended_params={
                "temp": 77,
                "humidity": 60,
                "ec": 0.77,
                "ph": 7.7,
                "light_duration": 14,
            },
        )
    print(f"Prompt to {LLM_BASE_URL}")
    client = OpenAI(
        base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=httpx.Timeout(120000.0)
    )

    b64 = encode_image(image_bytes)
    user_prompt = f"""Данные датчиков: {json.dumps(sensor_data)}
Проанализируй растение на фото."""
    print(f"Prompt: {user_prompt}")
    response = client.chat.completions.create(
        model="local-model",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    print(f"response ready!")
    try:
        content = "{'temp': 25.0, 'humidity': 70.0, 'ec': 1.5, 'ph': 6.0}"
        print(f"{response.choices}")
        data = json.loads(response.choices[0].message.content)
        print(f"Result: {data}")
        return AnalysisResult(
            growth_stage=data.get("growth_stage", "Не определено"),
            health=float(data.get("health", 0.5)),
            disease=data.get("disease", "healthy"),
            recommended_params={
                "temp": data.get("recommended_temp", 25),
                "humidity": data.get("recommended_humidity", 60),
                "ec": data.get("recommended_ec", 1.8),
                "ph": data.get("recommended_ph", 6.0),
                "light_duration": data.get("light_duration", 14),
            },
        )
    except Exception as e:
        print(f"An error occurred: {e}")
