"""Shared sidebar widget for LLM provider/model selection.

Renders once in the sidebar and writes the user's choice to ``st.session_state``
under three keys consumed by both the Experiment Lab and the Prediction Lab:

* ``llm_provider`` — canonical key: ``openai`` / ``anthropic`` / ``google`` / ``azure_foundry``
* ``llm_model``    — model id (e.g. ``gpt-4o``, ``claude-sonnet-4-6``)
* ``llm_api_key``  — resolved from the matching env var

A "Test connection" button issues a minimal request and reports success or the
exact error so configuration problems are visible before launching long runs.
"""
from __future__ import annotations

import os
import streamlit as st

from app.services.llm_provider import (
    PROVIDER_MODELS,
    DEFAULT_MODEL,
    normalize_provider,
    test_connection,
)

_PROVIDER_LABELS = ["OpenAI", "Anthropic (Claude)", "Google (Gemini)", "Azure AI Foundry"]
_LABEL_TO_KEY = {
    "OpenAI": "openai",
    "Anthropic (Claude)": "anthropic",
    "Google (Gemini)": "google",
    "Azure AI Foundry": "azure_foundry",
}
_KEY_TO_LABEL = {v: k for k, v in _LABEL_TO_KEY.items()}

_ENV_VAR_PRIMARY = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "azure_foundry": "AZURE_FOUNDRY_API_KEY",
}
_ENV_VAR_FALLBACKS = {
    "google": ("GEMINI_API_KEY",),
}


def _resolve_api_key(provider: str) -> str:
    key = os.environ.get(_ENV_VAR_PRIMARY[provider], "")
    if not key:
        for fb in _ENV_VAR_FALLBACKS.get(provider, ()):
            key = os.environ.get(fb, "")
            if key:
                break
    return key


def render_llm_settings_sidebar() -> dict:
    """Render the LLM-config block in the sidebar and update session_state.

    Returns the resolved config as ``{"provider": ..., "model": ..., "api_key": ...}``.
    """
    st.sidebar.subheader("🤖 LLM Settings")

    default_label = _KEY_TO_LABEL.get(
        st.session_state.get("llm_provider", "openai"), "OpenAI"
    )
    provider_label = st.sidebar.selectbox(
        "Provider",
        _PROVIDER_LABELS,
        index=_PROVIDER_LABELS.index(default_label),
        key="sidebar_llm_provider_label",
        help="Used by both Experiment Lab and Prediction Lab. "
             "Key is read from .env (OPENAI_API_KEY / ANTHROPIC_API_KEY / "
             "GOOGLE_API_KEY / AZURE_FOUNDRY_API_KEY + AZURE_FOUNDRY_ENDPOINT).",
    )
    provider = _LABEL_TO_KEY[provider_label]

    api_key = _resolve_api_key(provider)
    models = PROVIDER_MODELS[provider]
    default_model = DEFAULT_MODEL[provider]
    # Preserve last-chosen model per provider across reruns
    last_model_key = f"sidebar_llm_model_{provider}"
    if last_model_key not in st.session_state:
        st.session_state[last_model_key] = default_model
    if st.session_state[last_model_key] not in models:
        st.session_state[last_model_key] = default_model
    model_label = "Deployment" if provider == "azure_foundry" else "Model"
    model = st.sidebar.selectbox(
        model_label,
        models,
        index=models.index(st.session_state[last_model_key]),
        key=last_model_key,
        help=("Deployment name as shown on the Foundry resource "
              "'Model deployments' page." if provider == "azure_foundry" else None),
    )

    key_status = "✅ key loaded" if api_key else f"⚠️ no `{_ENV_VAR_PRIMARY[provider]}` in env"
    st.sidebar.caption(key_status)

    if provider == "azure_foundry":
        endpoint = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
        ep_status = (f"🔗 `{endpoint}`" if endpoint
                     else "⚠️ no `AZURE_FOUNDRY_ENDPOINT` in env")
        st.sidebar.caption(ep_status)

    test_clicked = st.sidebar.button(
        "🔌 Test connection",
        key="sidebar_test_llm_conn",
        use_container_width=True,
        disabled=not api_key,
    )
    if test_clicked:
        with st.spinner(f"Pinging {provider}/{model}…"):
            ok, msg = test_connection(provider, api_key, model)
        if ok:
            st.sidebar.success(msg)
        else:
            st.sidebar.error(msg)

    # Publish to session_state for downstream tabs.
    st.session_state["llm_provider"] = provider
    st.session_state["llm_model"] = model
    st.session_state["llm_api_key"] = api_key

    return {"provider": provider, "model": model, "api_key": api_key}


def get_llm_config() -> dict:
    """Read the current LLM config from session state. Defaults to OpenAI/gpt-4o
    if the sidebar hasn't run yet (defensive — should not happen in normal flow).
    """
    provider = st.session_state.get("llm_provider", "openai")
    return {
        "provider": provider,
        "model": st.session_state.get("llm_model", DEFAULT_MODEL.get(provider, "gpt-4o")),
        "api_key": st.session_state.get("llm_api_key", _resolve_api_key(provider)),
    }
