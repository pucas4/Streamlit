"""Claude-powered summarization: plain-English post recaps and chat digests
that flag whenever a message looks like a real portfolio/position change."""

from __future__ import annotations

import json

import anthropic

POST_MODEL = "claude-sonnet-5"
CHAT_MODEL = "claude-haiku-4-5-20251001"  # cheap/fast -- chat volume can be high

_POST_SYSTEM_PROMPT = """You explain a paid investing newsletter post to a subscriber \
who doesn't have time to read the whole thing carefully. Write in plain, everyday \
English -- no jargon without a one-line explanation of what it means.

Structure your response as:
TL;DR: one or two sentences, what's the headline takeaway.
What he's saying: 3-6 bullet points covering the actual content/argument.
Positions & numbers mentioned: any specific tickers, allocations, prices, or \
portfolio percentages he calls out. Say "None mentioned" if there aren't any.
Why it matters: one or two sentences on the practical implication for a subscriber.

Keep the whole thing tight -- this is a summary, not a rewrite."""

_CHAT_SYSTEM_PROMPT = """You monitor an investing newsletter author's paid chat for \
his subscribers. You'll get a numbered batch of chat messages (could be from the \
author or from other subscribers replying to him). For EACH message, decide:

1. is_position_change: true only if the message describes the AUTHOR taking a real \
investing action or stating a real change -- buying, selling, trimming, adding, \
changing an allocation/target/stop, opening or closing a position. false for \
general commentary, questions, other subscribers chatting, jokes, market color \
with no stated action, etc.
2. plain_english: a one-sentence, jargon-free translation of what the message means \
in practice for someone following along. If it's not from the author or isn't \
substantive, a short neutral gist is fine.

Respond with ONLY a JSON array, one object per input message, in the same order, \
each shaped exactly like:
{"is_position_change": bool, "plain_english": "..."}
No prose before or after the JSON."""


def get_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def _extract_text(response) -> str:
    """Claude responses can include a ThinkingBlock before the actual TextBlock --
    content[0] isn't reliably the text, so scan for the first block that has one."""
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            return text.strip()
    raise ValueError("Claude response had no text content")


def summarize_post(client: anthropic.Anthropic, title: str, subtitle: str, text: str) -> str:
    text = text[:20000]  # keep prompts bounded; posts are rarely longer than this
    user_content = f"Title: {title}\nSubtitle: {subtitle}\n\nFull post text:\n{text}"
    response = client.messages.create(
        model=POST_MODEL,
        max_tokens=800,
        thinking={"type": "disabled"},
        system=_POST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return _extract_text(response)


def analyze_chat_batch(client: anthropic.Anthropic, messages: list[dict]) -> list[dict]:
    """
    messages: list of {"author": str, "created_at": str, "body": str}
    Returns the same list with "plain_english" and "is_position_change" added to each dict.
    Processes in chunks of 25 to keep prompts small and one bad chunk from losing everything.
    """
    results: list[dict] = []
    chunk_size = 25
    for start in range(0, len(messages), chunk_size):
        chunk = messages[start : start + chunk_size]
        numbered = "\n".join(
            f"{i+1}. [{m['author']}]: {m['body']}" for i, m in enumerate(chunk)
        )
        response = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=200 * len(chunk),
            thinking={"type": "disabled"},
            system=_CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": numbered}],
        )
        raw = _extract_text(response)
        try:
            parsed = json.loads(raw)
            if len(parsed) != len(chunk):
                raise ValueError("length mismatch")
        except (json.JSONDecodeError, ValueError):
            parsed = [
                {"is_position_change": False, "plain_english": "(analysis failed for this message)"}
                for _ in chunk
            ]

        for original, analysis in zip(chunk, parsed):
            results.append({**original, **analysis})

    return results
