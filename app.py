"""Brew Haven Ops - a productivity agent with a human in the loop.

The agent reads the live inventory sheet and proposes restocks. Nothing is
written back until the manager presses Approve.
"""

import asyncio
import json
import os
import tempfile

import streamlit as st


def _load_secrets():
    """On Cloud Run everything arrives as env vars and the container already
    runs as the right service account. On Streamlit Cloud neither is true, so
    rebuild both from the app's secrets before anything touches Google APIs."""
    try:
        secrets = st.secrets
        _ = "GOOGLE_API_KEY" in secrets  # forces the parse, so a missing file fails here
    except Exception:  # noqa: BLE001 - no secrets file at all (Cloud Run, or local .env)
        return

    for key in ("GOOGLE_API_KEY", "INVENTORY_SHEET_ID"):
        if key in secrets:
            os.environ[key] = secrets[key]

    if "gcp_service_account" in secrets and not os.environ.get("SERVICE_ACCOUNT_FILE"):
        path = os.path.join(tempfile.gettempdir(), "ops-sa.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dict(secrets["gcp_service_account"]), handle)
        os.environ["SERVICE_ACCOUNT_FILE"] = path


_load_secrets()

from agent import OpsChat  # noqa: E402 - must follow _load_secrets()
from sheets_tools import apply_restock, load_inventory  # noqa: E402

st.set_page_config(page_title="Brew Haven Ops", page_icon="📋", layout="wide")

PROMPTS = [
    "What needs restocking today?",
    "How much whole milk do we have left?",
    "Anything running low for the weekend rush?",
]


@st.cache_resource
def get_chat():
    return OpsChat()


def ask(question: str) -> str:
    return asyncio.run(get_chat().ask(question))


def sheet_url():
    return f"https://docs.google.com/spreadsheets/d/{os.environ.get('INVENTORY_SHEET_ID', '')}"


# --- state -------------------------------------------------------------------

st.session_state.setdefault(
    "history",
    [{"role": "assistant", "content": "Morning. Ask me what needs restocking, or about any item."}],
)
st.session_state.setdefault("pending", [])
st.session_state.setdefault("applied", [])

# --- layout ------------------------------------------------------------------

st.title("📋 Brew Haven Ops")
st.caption(
    "An operations agent that watches the inventory sheet. It can propose changes. "
    "Only you can make them."
)

chat_col, side_col = st.columns([3, 2], gap="large")

with chat_col:
    for message in st.session_state.history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    picked = None
    if len(st.session_state.history) == 1:
        for prompt in PROMPTS:
            if st.button(prompt, use_container_width=True):
                picked = prompt

    typed = st.chat_input("Ask about stock...")
    question = typed or picked

    if question:
        st.session_state.history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Reading the sheet..."):
                try:
                    reply = ask(question)
                    for proposal in get_chat().last_proposals:
                        if proposal not in st.session_state.pending:
                            st.session_state.pending.append(proposal)
                except Exception as error:  # noqa: BLE001
                    reply = "I couldn't reach the inventory sheet just now. Try again in a moment."
                    st.caption(f"({type(error).__name__})")
            st.markdown(reply)

        st.session_state.history.append({"role": "assistant", "content": reply})
        st.rerun()

with side_col:
    st.subheader("Waiting for your approval")

    if not st.session_state.pending:
        st.info("No pending proposals. Ask the agent what needs restocking.")
    else:
        for index, proposal in enumerate(list(st.session_state.pending)):
            with st.container(border=True):
                st.markdown(f"**{proposal['item']}** &nbsp; `+{proposal['quantity']} {proposal['unit']}`")
                st.caption(
                    f"{proposal['current_stock']} → {proposal['new_stock']} {proposal['unit']} "
                    f"· supplier: {proposal['supplier']}"
                )
                st.write(proposal["reason"])

                approve, reject = st.columns(2)
                if approve.button("Approve", key=f"ok-{index}", type="primary", use_container_width=True):
                    try:
                        apply_restock(proposal)
                        st.session_state.applied.append(proposal)
                        st.session_state.pending.remove(proposal)
                        st.success(f"Sheet updated: {proposal['item']} is now {proposal['new_stock']}.")
                        st.rerun()
                    except Exception as error:  # noqa: BLE001
                        st.error(f"Could not write to the sheet ({type(error).__name__}).")
                if reject.button("Reject", key=f"no-{index}", use_container_width=True):
                    st.session_state.pending.remove(proposal)
                    st.rerun()

    if st.session_state.applied:
        st.subheader("Applied today")
        for proposal in st.session_state.applied:
            st.markdown(f"- {proposal['item']} → **{proposal['new_stock']} {proposal['unit']}**")

    st.divider()
    st.subheader("Live inventory")
    try:
        records = load_inventory()
        st.dataframe(
            [
                {
                    "Item": r["item"],
                    "Stock": r["stock"],
                    "Reorder at": r["reorder_level"],
                    "Unit": r["unit"],
                }
                for r in records
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(f"[Open the sheet]({sheet_url()})")
    except Exception:  # noqa: BLE001
        st.warning("Inventory sheet is not reachable right now.")

with st.sidebar:
    st.subheader("How this works")
    st.markdown(
        "- Built with **Google ADK** and **Gemini**, deployed on **Cloud Run**\n"
        "- Reads the sheet with the Sheets API `values.get`\n"
        "- Writes with `values.update` — but only after you approve\n"
        "- The agent has no write tool at all. It can only propose."
    )
    st.divider()
    st.caption("Gen AI Academy APAC — Cohort 3, Track 3")
