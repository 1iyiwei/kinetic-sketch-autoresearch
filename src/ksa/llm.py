"""Thin OpenAI Responses API wrapper that logs every call (for the decision trace).

Models are set with env vars so they can be swapped without code changes:
  KSA_GEN_MODEL     (default gpt-5.5)   writes animation programs
  KSA_CRITIC_MODEL  (default gpt-5.5)   scores rendered animations
  KSA_GEN_EFFORT / KSA_CRITIC_EFFORT    reasoning effort (default low)
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

GEN_MODEL = os.getenv("KSA_GEN_MODEL", "gpt-5.5")
CRITIC_MODEL = os.getenv("KSA_CRITIC_MODEL", "gpt-5.5")
GEN_EFFORT = os.getenv("KSA_GEN_EFFORT", "low")
CRITIC_EFFORT = os.getenv("KSA_CRITIC_EFFORT", "low")

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI()
    return _client


def image_part(path: Path) -> dict:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return {"type": "input_image", "image_url": f"data:image/png;base64,{b64}"}


async def call(*, role: str, model: str, effort: str, system: str, text: str,
               images: list[Path] = (), log: Path | None = None, tags: dict | None = None,
               json_schema: dict | None = None) -> str:
    content = [{"type": "input_text", "text": text}] + [image_part(p) for p in images]
    t0 = time.time()
    extra = {}
    if json_schema is not None:  # structured output: the reply is guaranteed to parse
        extra["text"] = {"format": {"type": "json_schema", "name": json_schema["name"],
                                    "schema": json_schema["schema"], "strict": True}}
    resp = await client().responses.create(
        model=model,
        instructions=system,
        input=[{"role": "user", "content": content}],
        reasoning={"effort": effort},
        **extra,
    )
    out = resp.output_text
    if log is not None:
        u = resp.usage
        rec = {
            "ts": t0, "role": role, "model": model, "effort": effort, "tags": tags or {},
            "latency_s": round(time.time() - t0, 2),
            "input_tokens": getattr(u, "input_tokens", None), "output_tokens": getattr(u, "output_tokens", None),
            "images": [str(p) for p in images], "prompt": text, "response": out,
        }
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    return out


def extract_block(text: str, lang: str) -> str | None:
    m = re.search(rf"```{lang}\s*\n(.*?)```", text, re.S)
    return m.group(1).strip() if m else None


def extract_json(text: str) -> dict:
    block = extract_block(text, "json")
    candidate = block if block is not None else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(candidate)
