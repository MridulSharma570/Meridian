"""Streamlit API key management page — six independent encrypted slots."""
from __future__ import annotations

import streamlit as st

from app import services
from app.ui.components import card_end, card_start, badge
from app.ui.theme import hero


def render() -> None:
    hero("API Keys & Providers",
         "Six independent, Fernet-encrypted key slots. Use one key everywhere or mix free "
         "and paid providers. No key is required — Meridian runs fully on its local engine.",
         "SECURE CONFIGURATION")
    payload = services.settings_payload()
    st.info(f"🔐 {payload['encryption']} · only masked keys are ever shown in the UI · "
            f"{payload['configured_count']} / {len(payload['slots'])} slots configured")

    with st.expander("⚡ Quick setup — apply one key to every agent slot"):
        labels = {p["key"]: p["label"] for p in payload["providers"]}
        c1, c2, c3 = st.columns([1.2, 2, 1])
        with c1:
            all_prov = st.selectbox("Provider", list(labels.keys()),
                                    format_func=lambda k: labels[k], key="all_prov")
        with c2:
            all_key = st.text_input("API key", type="password", key="all_key")
        with c3:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            if st.button("Apply to all", use_container_width=True):
                if all_key.strip():
                    try:
                        r = services.apply_key_to_all(all_prov, all_key.strip())
                        st.success(f"Key encrypted and applied to {r['slots_updated']} slots.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                else:
                    st.error("Paste a key first.")

    st.markdown("### Agent key slots")
    cols = st.columns(2)
    for i, slot in enumerate(payload["slots"]):
        with cols[i % 2]:
            card_start(f"{slot['icon']}  {slot['name']}", slot["description"])
            st.markdown(badge("CONFIGURED", "ok") if slot["configured"] else badge("NO KEY"),
                        unsafe_allow_html=True)
            if slot["configured"]:
                st.code(f"{slot['masked_key']}  ·  {slot['provider']}  ·  {slot['model']}")
            provider_keys = [p["key"] for p in payload["providers"]]
            labels = {p["key"]: f"[{p['group']}] {p['label']}" for p in payload["providers"]}
            default_idx = provider_keys.index(slot["provider"]) if slot["provider"] in provider_keys else 0
            prov = st.selectbox("Provider", provider_keys, index=default_idx,
                                format_func=lambda k: labels[k], key=f"prov_{slot['slot']}")
            spec = next(p for p in payload["providers"] if p["key"] == prov)
            model = st.selectbox("Model", spec["models"], key=f"model_{slot['slot']}")
            key = st.text_input("API key (blank keeps the stored one)", type="password",
                                placeholder=spec["key_hint"], key=f"key_{slot['slot']}")
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("Save", key=f"save_{slot['slot']}", use_container_width=True):
                    if key.strip():
                        try:
                            services.save_key(slot["slot"], prov, key.strip(), model)
                            st.success("Saved & encrypted")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                    else:
                        st.error("Enter a key")
            with b2:
                if st.button("Test", key=f"test_{slot['slot']}", use_container_width=True):
                    with st.spinner("Testing…"):
                        r = services.test_key(slot["slot"])
                    if r["ok"]:
                        st.success(f"{r['provider']} · {r['latency_ms']} ms")
                    else:
                        st.warning(r["error"])
            with b3:
                if st.button("Remove", key=f"del_{slot['slot']}", use_container_width=True):
                    services.delete_key(slot["slot"])
                    st.rerun()
            st.caption(f"[Get a key ↗]({spec['signup_url']})")
            card_end()

    st.markdown("### Provider catalogue")
    st.dataframe([{"Provider": p["label"], "Tier": p["group"],
                   "Default model": p["default_model"], "Signup": p["signup_url"]}
                  for p in payload["providers"]], use_container_width=True, hide_index=True)
