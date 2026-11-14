"""Thin OpenAI Responses API wrapper that logs every call (for the decision trace).

Models are set with env vars so they can be swapped without code changes:
  KSA_GEN_MODEL     (default gpt-5.5)   writes animation programs
  KSA_CRITIC_MODEL  (default gpt-5.5)   scores rendered animations
  KSA_GEN_EFFORT / KSA_CRITIC_EFFORT    reasoning effort (default low)

A Tinker model can be the generator (text-only; the SVG source is in the prompt):
  KSA_GEN_MODEL=tinker:Qwen/Qwen3.6-35B-A3B          base open model
  KSA_GEN_MODEL=tinker://<run>/sampler_weights/<n>   fine-tuned checkpoint (see ksa.distill)
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
        return await tinker_call(role=role, model=model, system=system, text=text, log=log, tags=tags,
                                 meter=meter, images=images, json_schema=json_schema)
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
    if meter is not None:  # per-case compute accounting, for equal-compute comparisons
        m = meter.setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0})
        m["calls"] += 1
        m["input_tokens"] += getattr(u, "input_tokens", 0) or 0
        m["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        m["seconds"] = round(m["seconds"] + time.time() - t0, 2)
    if log is not None:
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


TINKER_BASE = os.getenv("KSA_TINKER_BASE", "Qwen/Qwen3.6-35B-A3B")
TINKER_MAX_TOKENS = int(os.getenv("KSA_TINKER_MAX_TOKENS", "12000"))
TINKER_TEMPERATURE = float(os.getenv("KSA_TINKER_TEMPERATURE", "0.7"))
_tinker: dict = {}


def chat_tokens(tokenizer, messages: list[dict], generation_prompt: bool) -> list[int]:
    """The one chat rendering used for both SFT data and sampling (thinking off)."""
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=generation_prompt,
                                         enable_thinking=False)
    return tokenizer.encode(text, add_special_tokens=False)


async def tinker_sampler(model: str):
    """(sampling client, tokenizer) for "tinker:<base model>" or a "tinker://..." checkpoint path."""
    lock = _tinker.setdefault("lock", asyncio.Lock())
    async with lock:
        if model not in _tinker:
            import tinker

            def make():  # the SDK's client constructors are sync-only
                svc = _tinker.get("service") or _tinker.setdefault("service", tinker.ServiceClient())
                if model.startswith("tinker://"):
                    sc = svc.create_sampling_client(model_path=model)
                else:
                    sc = svc.create_sampling_client(base_model=model.removeprefix("tinker:"))
                sc = sc.result() if hasattr(sc, "result") else sc
                return sc, sc.get_tokenizer()

            _tinker[model] = await asyncio.to_thread(make)
    return _tinker[model]


def tinker_input(tok, system: str, text: str, images: list[Path]):
    """Chat prompt as a tinker ModelInput; images go where the template puts <|image_pad|>."""
    import tinker
    if not images:
        ids = chat_tokens(tok, [{"role": "system", "content": system}, {"role": "user", "content": text}], True)
        return tinker.ModelInput.from_ints(ids), len(ids)
    content = [{"type": "image"} for _ in images] + [{"type": "text", "text": text}]
    rendered = tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": content}],
                                       tokenize=False, add_generation_prompt=True, enable_thinking=False)
    pieces = rendered.split("<|image_pad|>")
    chunks, n = [], 0
    for i, piece in enumerate(pieces):
        ids = tok.encode(piece, add_special_tokens=False)
        if ids:
            chunks.append(tinker.types.EncodedTextChunk(tokens=ids))
            n += len(ids)
        if i < len(images):
            chunks.append(tinker.types.ImageChunk(data=images[i].read_bytes(), format="png",
                                            expected_tokens=vision_tokens(images[i])))
            n += vision_tokens(images[i])
    return tinker.ModelInput(chunks=chunks), n


def vision_tokens(path: Path) -> int:
    """Qwen-VL image tokens: 16 px patches merged 2x2, after resizing each side to a multiple of 32."""
    from PIL import Image
    w, h = Image.open(path).size
    return max(1, round(w / 32)) * max(1, round(h / 32))


async def tinker_call(*, role: str, model: str, system: str, text: str, log: Path | None = None,
                      tags: dict | None = None, meter: dict | None = None, images: list[Path] = (),
                      json_schema: dict | None = None) -> str:
    import tinker
    t0 = time.time()
    sc, tok = await tinker_sampler(model)
    if json_schema is not None:
        text += ("\n\nReply with only a JSON object (no prose) matching this JSON schema:\n"
                 + json.dumps(json_schema["schema"]))
    model_input, n_prompt = tinker_input(tok, system, text, list(images))
    try:
        res = await sc.sample(prompt=model_input, num_samples=1,
                                    sampling_params=tinker.SamplingParams(max_tokens=TINKER_MAX_TOKENS,
                                                                          temperature=TINKER_TEMPERATURE))
    except Exception as e:
        if any(k in str(e).lower() for k in ("unauthorized", "api key", "forbidden", "not found")):
            raise FatalAPIError(f"{model}: {e}") from e
        raise
    seq = res.sequences[0]
    out = tok.decode(seq.tokens, skip_special_tokens=True).strip()
    n_in, n_out = n_prompt, len(seq.tokens)
    if meter is not None:
        m = meter.setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0})
        m["calls"] += 1
        m["input_tokens"] += n_in
        m["output_tokens"] += n_out
        m["seconds"] = round(m["seconds"] + time.time() - t0, 2)
    if log is not None:
        rec = {"ts": t0, "role": role, "model": model, "effort": "none", "tags": tags or {},
               "latency_s": round(time.time() - t0, 2), "input_tokens": n_in, "output_tokens": n_out,
               "stop_reason": str(seq.stop_reason), "images": [str(p) for p in images], "prompt": text, "response": out}
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    return out


def slug(model: str) -> str:
    """Filesystem-safe model name, e.g. tinker:Qwen/Qwen3.6-35B-A3B -> tinker-Qwen-Qwen3.6-35B-A3B."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")


def extract_block(text: str, lang: str) -> str | None:
    m = re.search(rf"```{lang}\s*\n(.*?)```", text, re.S)
    return m.group(1).strip() if m else None


def extract_json(text: str) -> dict:
    block = extract_block(text, "json")
    candidate = block if block is not None else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(candidate)
