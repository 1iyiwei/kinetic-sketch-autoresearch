"""Thin LLM wrapper that logs every call (for the decision trace).

Two providers, chosen by the model name:
  gpt-5.5, gpt-5.4, ...            OpenAI Responses API (OPENAI_API_KEY)
  tinker:Qwen/Qwen3.6-35B-A3B      any sampleable model on Thinking Machines' Tinker (TINKER_API_KEY);
                                   images go in as image chunks, JSON is asked for in the prompt

Models are set with env vars so they can be swapped without code changes:
  KSA_GEN_MODEL     (default gpt-5.5)   writes animation programs
  KSA_CRITIC_MODEL  (default gpt-5.5)   scores rendered animations
  KSA_GEN_EFFORT / KSA_CRITIC_EFFORT    reasoning effort (default low; for Tinker models, "none" or
                                        "low" turns Qwen's thinking off, "medium"/"high" turns it on)
  KSA_TINKER_MAX_TOKENS                 output cap for Tinker models (default 16000)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
import openai
from openai import AsyncOpenAI

load_dotenv(override=True)  # the project .env wins over a stale shell key

GEN_MODEL = os.getenv("KSA_GEN_MODEL", "gpt-5.5")
CRITIC_MODEL = os.getenv("KSA_CRITIC_MODEL", "gpt-5.5")
GEN_EFFORT = os.getenv("KSA_GEN_EFFORT", "low")
CRITIC_EFFORT = os.getenv("KSA_CRITIC_EFFORT", "low")

_client: AsyncOpenAI | None = None


class FatalAPIError(RuntimeError):
    """Out of credits, bad key, no access: abort the run instead of scoring zeros."""


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
               json_schema: dict | None = None, meter: dict | None = None) -> str:
    if model.startswith("tinker:"):
        return await tinker_call(role=role, model=model, effort=effort, system=system, text=text,
                                 images=images, log=log, tags=tags, json_schema=json_schema, meter=meter)
    content = [{"type": "input_text", "text": text}] + [image_part(p) for p in images]
    t0 = time.time()
    extra = {}
    if json_schema is not None:  # structured output: the reply is guaranteed to parse
        extra["text"] = {"format": {"type": "json_schema", "name": json_schema["name"],
                                    "schema": json_schema["schema"], "strict": True}}
    try:
        resp = await client().responses.create(
            model=model,
            instructions=system,
            input=[{"role": "user", "content": content}],
            reasoning={"effort": effort},
            **extra,
        )
    except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError) as e:
        raise FatalAPIError(f"{model}: {e}") from e
    except openai.RateLimitError as e:
        if "insufficient_quota" in str(e) or "credits" in str(e):
            raise FatalAPIError(f"{model}: out of credits: {e}") from e
        raise
    out = resp.output_text
    u = resp.usage
    _record(role, model, effort, tags, t0, getattr(u, "input_tokens", None), getattr(u, "output_tokens", None),
            images, text, out, log, meter)
    return out


def _record(role, model, effort, tags, t0, n_in, n_out, images, text, out, log, meter):
    if meter is not None:  # per-case compute accounting, for equal-compute comparisons
        m = meter.setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0})
        m["calls"] += 1
        m["input_tokens"] += n_in or 0
        m["output_tokens"] += n_out or 0
        m["seconds"] = round(m["seconds"] + time.time() - t0, 2)
    if log is not None:
        rec = {
            "ts": t0, "role": role, "model": model, "effort": effort, "tags": tags or {},
            "latency_s": round(time.time() - t0, 2),
            "input_tokens": n_in, "output_tokens": n_out,
            "images": [str(p) for p in images], "prompt": text, "response": out,
        }
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(rec) + "\n")


# ---------------------------------------------------------------- Tinker

IMAGE_SLOTS = ("<|image_pad|>", "<image>")  # Qwen, Nemotron-VL: where the template puts an image
_tinker: dict = {}  # base model -> (sampling client, tokenizer)
TINKER_MAX_TOKENS = int(os.getenv("KSA_TINKER_MAX_TOKENS", "16000"))
TINKER_TEMPERATURE = float(os.getenv("KSA_TINKER_TEMPERATURE", "0.7"))


async def _tinker_client(base: str):
    if base not in _tinker:
        import tinker  # optional dependency: only needed for tinker: models
        try:
            sc = await tinker.ServiceClient().create_sampling_client(base_model=base)
        except Exception as e:  # bad key, unknown model
            raise FatalAPIError(f"tinker:{base}: {e}") from e
        _tinker[base] = (sc, sc.get_tokenizer())
    return _tinker[base]


def _tinker_prompt(tok, system: str, text: str, images, thinking: bool):
    """Chat-template the prompt, then splice each image in as an image chunk where the
    template put its <|image_pad|> placeholder."""
    from tinker import types
    content = [{"type": "image"} for _ in images] + [{"type": "text", "text": text}]
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": content}]
    s = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=thinking)
    slot = next((m for m in IMAGE_SLOTS if m in s), IMAGE_SLOTS[0])
    parts = s.split(slot) if images else [s]
    if len(parts) != len(images) + 1:
        raise ValueError(f"chat template produced {len(parts) - 1} image slots for {len(images)} images")
    chunks, n_text = [], 0
    for i, part in enumerate(parts):
        ids = tok.encode(part, add_special_tokens=False)
        n_text += len(ids)
        chunks.append(types.EncodedTextChunk(tokens=ids))
        if i < len(images):
            chunks.append(types.ImageChunk(data=Path(images[i]).read_bytes(), format="png"))
    return types.ModelInput(chunks=chunks), n_text


async def tinker_call(*, role, model, effort, system, text, images=(), log=None, tags=None,
                      json_schema=None, meter=None) -> str:
    from tinker import types
    base = model.removeprefix("tinker:")
    sc, tok = await _tinker_client(base)
    if json_schema is not None:  # no constrained decoding here: ask for it, extract_json parses it
        text += ("\n\nReply with only a JSON object (no prose, no code fence) matching this JSON schema:\n"
                 + json.dumps(json_schema["schema"]))
    thinking = effort in ("medium", "high", "xhigh")
    prompt, n_text = _tinker_prompt(tok, system, text, list(images), thinking)
    t0 = time.time()
    for attempt in range(3):
        try:
            r = await sc.sample_async(prompt=prompt, num_samples=1, sampling_params=types.SamplingParams(
                max_tokens=TINKER_MAX_TOKENS, temperature=TINKER_TEMPERATURE))
            break
        except Exception as e:
            msg = str(e).lower()
            if any(w in msg for w in ("unauthorized", "invalid api key", "401", "403", "billing", "credit")):
                raise FatalAPIError(f"{model}: {e}") from e
            if attempt == 2:
                raise
            await asyncio.sleep(5 * (attempt + 1))
    toks = r.sequences[0].tokens
    out = tok.decode(toks, skip_special_tokens=True)
    out = re.sub(r"^.*?</think>", "", out, flags=re.S).strip()  # drop the reasoning, keep the answer
    _record(role, model, effort, tags, t0, n_text, len(toks), images, text, out, log, meter)
    return out


def extract_block(text: str, lang: str) -> str | None:
    m = re.search(rf"```{lang}\s*\n(.*?)```", text, re.S)
    return m.group(1).strip() if m else None


def extract_json(text: str) -> dict:
    block = extract_block(text, "json")
    candidate = block if block is not None else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(candidate)
