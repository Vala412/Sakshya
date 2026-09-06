"""Chat completion with structured output, for the explanation layer.

One method, deliberately: `chat(messages, output_format)` -> a validated
instance of `output_format`. There is no free-text chat method here on
purpose -- every caller must declare the shape it expects back, so a
malformed or off-topic model response fails at the parse boundary (a
pydantic ValidationError) instead of silently propagating as prose that
looks like an answer.
"""

from __future__ import annotations

from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from pydantic import BaseModel

from gstrecon.rag.config import get_settings
from gstrecon.rag.openai_client import get_openai_client


async def chat[OutputT: BaseModel](
    messages: list[EasyInputMessageParam], output_format: type[OutputT]
) -> OutputT:
    """Structured chat completion over `{"role", "content"}` messages.

    Uses the Responses API's `parse()` (not plain `create()`): the response
    is coerced to `output_format` server-side and validated client-side by
    the SDK, so a response that doesn't fit the schema raises here rather
    than being handed to the caller as an unvalidated dict.
    """
    client = get_openai_client()
    response = await client.responses.parse(
        model=get_settings().openai_chat_model,
        # The SDK types `input` as list[<30-member union>] | str | Omit;
        # list is invariant, so our narrower list[EasyInputMessageParam] --
        # the one message shape this project actually sends -- doesn't
        # structurally match even though EasyInputMessageParam is itself
        # one of the union's members. Runtime behavior is unaffected: the
        # SDK only ever reads {"role", "content"} off each dict.
        input=messages,  # type: ignore[arg-type]
        text_format=output_format,
    )
    if response.output_parsed is None:
        raise ValueError("Model response could not be parsed into the requested schema.")
    return response.output_parsed
