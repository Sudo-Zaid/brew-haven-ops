"""Ops, the Brew Haven operations assistant.

It watches the inventory sheet and proposes restocks. It cannot write to the
sheet itself - every change goes through a human.
"""

import asyncio
import os
import re
import uuid

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from sheets_tools import check_inventory, find_items_below_reorder_level, propose_restock

load_dotenv()
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "0")

APP_NAME = "brew_haven_ops"
MODEL = "gemini-3.1-flash-lite"

INSTRUCTION = """
You are Ops, the operations assistant for Brew Haven, a coffee shop with
branches in Rawalpindi and Islamabad. You help the manager keep stock levels
healthy.

How you work:
- Always read the live sheet with your tools before saying anything about
  stock. Never answer from memory or from an earlier turn.
- When something is at or below its reorder level, call propose_restock with
  a sensible quantity and a one-line reason.
- A sensible quantity brings the item comfortably above its reorder level,
  not exactly to it. Round to whole units the supplier would actually ship.
- You cannot change the sheet. propose_restock only creates a proposal that
  a human approves or rejects. Never say you have updated, ordered or
  restocked anything - say you have proposed it.
- If the manager asks you to make a change directly, explain that every
  change needs their approval first, then create the proposal.
- Be brief. Two or three sentences, and use the item names exactly as they
  appear in the sheet.
"""

root_agent = Agent(
    name="brew_haven_ops",
    model=MODEL,
    description="Operations assistant that monitors inventory and proposes restocks.",
    instruction=INSTRUCTION,
    tools=[check_inventory, find_items_below_reorder_level, propose_restock],
)


class OpsChat:
    """One manager conversation, with its own ADK session."""

    def __init__(self, user_id: str = "manager"):
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            app_name=APP_NAME,
            agent=root_agent,
            session_service=self._session_service,
        )
        self._user_id = user_id
        self._session_id = f"s-{uuid.uuid4().hex[:12]}"
        self._started = False
        self.last_proposals = []

    async def _ensure_session(self):
        if not self._started:
            await self._session_service.create_session(
                app_name=APP_NAME,
                user_id=self._user_id,
                session_id=self._session_id,
            )
            self._started = True

    async def ask(self, message: str, _retries: int = 1) -> str:
        """One turn. The free tier meters requests and input tokens, so a busy
        turn can trip a 429 that clears on its own - wait it out once."""
        try:
            return await self._ask_once(message)
        except Exception as error:  # noqa: BLE001
            text = str(error)
            if _retries > 0 and "RESOURCE_EXHAUSTED" in text:
                delay = re.search(r"retry in ([0-9.]+)s", text, re.I)
                await asyncio.sleep(min(float(delay.group(1)) + 2 if delay else 30, 65))
                return await self.ask(message, _retries - 1)
            raise

    async def _ask_once(self, message: str) -> str:
        await self._ensure_session()
        self.last_proposals = []
        content = types.Content(role="user", parts=[types.Part(text=message)])

        reply = ""
        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=self._session_id,
            new_message=content,
        ):
            for part in (event.content.parts if event.content else []) or []:
                response = getattr(part, "function_response", None)
                if response and response.name == "propose_restock":
                    payload = response.response or {}
                    if payload.get("status") == "awaiting_approval":
                        self.last_proposals.append(payload["proposal"])

            if event.is_final_response() and event.content and event.content.parts:
                reply = "".join(p.text or "" for p in event.content.parts)

        return reply.strip() or "Sorry, I didn't catch that."


if __name__ == "__main__":
    import asyncio

    async def _demo():
        chat = OpsChat()
        print(await chat.ask("what needs restocking today?"))
        for proposal in chat.last_proposals:
            print("PENDING:", proposal)

    asyncio.run(_demo())
