"""One small client for three free AI providers: Google Gemini, Groq and OpenRouter.

All three accept the OpenAI chat-completions format, so the same code works for each.
If one provider fails (free limit reached, server busy), the next one in
AI_PROVIDER_ORDER is tried automatically.
"""
import base64
import json
import time

from openai import OpenAI

from . import config


class NoProviderError(RuntimeError):
    pass


_clients = {}


def _client(name):
    if name not in _clients:
        p = config.PROVIDERS[name]
        _clients[name] = OpenAI(api_key=p["key"], base_url=p["base_url"], timeout=90, max_retries=1)
    return _clients[name]


def chat(messages, tools=None, vision=False, temperature=0.4, json_mode=False):
    """Send messages to the first working provider.

    Returns (assistant_message_dict, provider_name).
    assistant_message_dict has 'content' and optionally 'tool_calls'.
    """
    providers = config.configured_providers()
    if not providers:
        raise NoProviderError(
            "No AI key found. Add GEMINI_API_KEY, GROQ_API_KEY or OPENROUTER_API_KEY to the .env file."
        )
    last_err = None
    for name in providers:
        p = config.PROVIDERS[name]
        model = p["vision_model"] if vision else p["model"]
        kwargs = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        for attempt in range(2):
            try:
                resp = _client(name).chat.completions.create(**kwargs)
                msg = resp.choices[0].message
                out = {"role": "assistant", "content": msg.content or ""}
                if getattr(msg, "tool_calls", None):
                    out["tool_calls"] = [
                        {
                            "id": tc.id or f"call_{i}",
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
                        }
                        for i, tc in enumerate(msg.tool_calls)
                    ]
                return out, name
            except Exception as e:  # noqa: BLE001 - any provider error moves to the next provider
                last_err = e
                text = str(e).lower()
                if json_mode and "response_format" in text:
                    kwargs.pop("response_format", None)
                    continue
                if "429" in text or "rate" in text or "quota" in text:
                    break  # this provider's free limit is used up: try the next one
                if attempt == 0:
                    time.sleep(1.5)
    raise NoProviderError(f"All AI providers failed. Last error: {last_err}")


def ask_json(system, user, vision_image_bytes=None, mime="image/jpeg"):
    """Ask for a JSON answer. Returns a Python dict (or {} if the reply was not JSON)."""
    if vision_image_bytes:
        b64 = base64.b64encode(vision_image_bytes).decode()
        content = [
            {"type": "text", "text": user},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]
    else:
        content = user
    msgs = [{"role": "system", "content": system + "\nReply with one JSON object only."},
            {"role": "user", "content": content}]
    msg, _ = chat(msgs, vision=bool(vision_image_bytes), temperature=0.1, json_mode=True)
    return parse_json(msg["content"])


def parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}
