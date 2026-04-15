"""Ask-Lenny service: answer questions by proxying OpenAI tool-calls to the
Lenny's Podcast MCP server.

The MCP's search_transcripts returns matches sorted alphabetically by guest name
(not by relevance) with excerpts that aren't always anchored on the query term.
We work around this by fetching a large set and re-ranking client-side before
handing the result to the LLM.
"""
import json
import logging
import re

from src.config import LLM_MODEL
from src.llm import client
from src.lenny_mcp import LennyMCPClient

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 20
SEARCH_FETCH_LIMIT = 300
SEARCH_RETURN_LIMIT = 50

SYSTEM_PROMPT = (
    "You answer questions using Lenny's Podcast transcripts, accessed via the "
    "provided tools. Always call search_transcripts (or list_episodes/get_episode "
    "when more appropriate) before answering — never answer from prior knowledge. "
    "Cite guests by name in your answer. If the tools return nothing useful, say so "
    "plainly. Keep answers tight: a short synthesis, then 3-6 bullet takeaways."
)

_EPISODE_SPLIT = re.compile(r"\n---\n+")
_HEADING = re.compile(r"^## \d+\. (.+)$", re.MULTILINE)


def _rerank_search(raw: str, query: str, top_n: int = SEARCH_RETURN_LIMIT) -> str:
    """Re-rank alphabetical MCP search output by query-term density in each excerpt."""
    if not raw.startswith("Found "):
        return raw

    header, _, body = raw.partition("\n\n")
    blocks = _EPISODE_SPLIT.split(body)

    terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
    if not terms:
        return raw

    scored: list[tuple[int, int, str, str]] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        heading_match = _HEADING.search(block)
        guest = heading_match.group(1) if heading_match else "(unknown)"
        lower = block.lower()
        score = sum(lower.count(term) for term in terms)
        scored.append((score, len(scored), guest, block))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top = [s for s in scored if s[0] > 0][:top_n]
    if not top:
        top = scored[:top_n]

    lines = [f"Found {len(top)} relevant episodes for \"{query}\" "
             f"(re-ranked from {len(scored)} matches by query-term density):\n"]
    for i, (score, _, guest, block) in enumerate(top, 1):
        rewritten = _HEADING.sub(f"## {i}. {guest} (score={score})", block, count=1)
        lines.append(rewritten)
    return "\n\n---\n\n".join(lines)


def _mcp_tools_to_openai(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def ask_lenny(question: str) -> dict:
    """Run a tool-calling loop: user question -> LLM -> MCP tool calls -> answer.

    Returns a dict with 'answer' and 'tool_calls' (list of {name, arguments, result_preview}).
    """
    with LennyMCPClient() as mcp:
        openai_tools = _mcp_tools_to_openai(mcp.list_tools())

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        tool_call_log: list[dict] = []

        for round_idx in range(MAX_TOOL_ROUNDS):
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto" if round_idx < MAX_TOOL_ROUNDS - 1 else "none",
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                return {"answer": msg.content or "", "tool_calls": tool_call_log}

            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info("lenny tool call: %s(%s)", tc.function.name, args)
                try:
                    if tc.function.name == "search_transcripts":
                        query = args.get("query", "")
                        fetch_args = {**args, "limit": SEARCH_FETCH_LIMIT}
                        raw = mcp.call_tool("search_transcripts", fetch_args)
                        result_text = _rerank_search(raw, query)
                    else:
                        result_text = mcp.call_tool(tc.function.name, args)
                except Exception as e:
                    result_text = f"Tool call failed: {e}"
                    logger.exception("lenny MCP call failed")

                tool_call_log.append({
                    "name": tc.function.name,
                    "arguments": args,
                    "result_preview": result_text[:400],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

        return {"answer": "(no answer — tool-call budget exhausted)", "tool_calls": tool_call_log}
