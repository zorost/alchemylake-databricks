"""
AlchemyLake — Governed Creative, inside Databricks.

A Databricks App that runs in your workspace and calls the AlchemyLake platform
over its MCP (Model Context Protocol) endpoint. It lets anyone in your workspace:

  • list the governed data sources bound to your AlchemyLake account
    (built-in Sample Lakehouse, Unity Catalog tables, CSV/Excel/PDF/DOCX
    uploads, Genie-space answers) — and register new uploads right here,
  • generate narrative/copy that is *sealed* to a source — every figure
    traceable to the exact rows the model saw (source · row count · sha256),
    then *verified*: numeric claims checked against platform-computed facts —
    with conversations that continue across turns (Genie included),
  • run Deep Research: a planned multi-step investigation (sub-questions →
    evidence → synthesis) sealed into a PDF dossier + Excel evidence workbook,
  • compose branded PDF reports whose every figure is substituted from the
    deterministic FACTS table, cited, verified, and sealed on the page,
  • run one-click recipe templates (KPI poster, executive one-pager, social
    announcement) against any governed source,
  • generate imagery, video, music, and voice **bound to the same sources** —
    a grounded step derives the figures/arc only from the bound rows (data
    posters, captioned clips, scores that follow the data, spoken data briefs),
  • see the credit wallet the renders are metered against.

Nothing here bypasses governance: the same credit ledger, provenance seals, and
role checks that protect the web app protect every call made from this App.

Auth: paste an AlchemyLake developer key (alk_…) in the sidebar, or set the
ALCHEMYLAKE_API_KEY environment variable / Databricks secret on the app.
Create a key at https://app.alchemylake.com/studio → Developer · MCP & keys.
"""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests
import streamlit as st

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.workspace import ImportFormat

    _DATABRICKS_SDK_AVAILABLE = True
except ImportError:  # local dev without the SDK installed — download still works
    _DATABRICKS_SDK_AVAILABLE = False

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MCP_URL = os.environ.get(
    "ALCHEMYLAKE_MCP_URL", "https://app.alchemylake.com/api/mcp"
)
ENV_API_KEY = os.environ.get("ALCHEMYLAKE_API_KEY", "").strip()
SIGNUP_URL = "https://app.alchemylake.com/sign-up"
DOCS_URL = "https://app.alchemylake.com/docs"
APP_VERSION = "0.4.0"  # keep in step with the MCP serverInfo.version
# The API's own lane ceiling is 540s (apps/api/app/engine.py LANE_TIMEOUT_SECONDS)
# and the Next.js proxy allows up to 300s per hop — this must clear both, or a
# perfectly healthy long-running render (video/music, occasionally 3-4 min)
# gets reported to the user as a client-side failure when it was actually
# still succeeding server-side.
REQUEST_TIMEOUT = 600  # seconds — renders can take a while
WELCOME_GRANT_CREDITS = 50  # keep in step with apps/api/app/config.py
# Prefills the "Save to Databricks" destination so the button works out of
# the box for this deployment's own workspace — a workspace admin points it
# at whatever volume or folder this App's service principal was granted
# (Docs tab → "Save to Databricks"). Still just a starting point: anyone can
# type a different /Volumes/… or /Workspace/… path before saving.
DEFAULT_SAVE_DIR = os.environ.get(
    "ALCHEMYLAKE_SAVE_DIR", "/Volumes/main/default/alchemylake_outputs"
).rstrip("/")

# A bare "◈" glyph isn't a real emoji, so most browsers silently fall back to
# the Streamlit running-man favicon. Use the site's own mark as a local file —
# no network dependency, works even if app.alchemylake.com is unreachable.
_FAVICON_PATH = os.path.join(APP_DIR, "assets", "favicon.png")
PAGE_ICON = _FAVICON_PATH if os.path.exists(_FAVICON_PATH) else "◈"


def _inline_mark_data_uri() -> str:
    """Base64 data URI for the small transparent crest (sidebar + masthead).

    Streamlit's markdown has no server route for local files, so a same-origin
    <img> needs either a public URL or an inlined data URI — the crest is tiny
    (~25KB) and rendered on every page, so inlining avoids an extra request.
    """
    path = os.path.join(APP_DIR, "assets", "mark.png")
    try:
        with open(path, "rb") as f:
            import base64

            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""


_MARK_URI = _inline_mark_data_uri()

st.set_page_config(
    page_title="AlchemyLake · Governed Creative",
    page_icon=PAGE_ICON,
    layout="wide",
)

# --------------------------------------------------------------------------- #
# Brand styling (Lapis Plate — matches app.alchemylake.com)
# --------------------------------------------------------------------------- #

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
      :root {
        --gold:#e4c067; --gold-bright:#f0d289; --gold-deep:#b69137; --lapis:#1e2e96;
        --abyss:#0d1338; --basalt:#172478; --pit:#121c5e; --umber:#26379f;
        --ivory:#f3eddf; --sand:rgba(243,237,223,0.72); --mutedsand:rgba(243,237,223,0.5);
        --hairline:rgba(243,237,223,0.30); --cypress:#63c79b; --periwinkle:#9db0ff;
        --paper:#f2ecdc;
      }

      /* ── the printed plate: ivory paper frame around the whole app ── */
      .stApp {
        border: 10px solid var(--paper);
        background:
          radial-gradient(ellipse 90% 55% at 50% -10%, rgba(228,192,103,0.10), transparent 60%),
          var(--abyss);
        color: var(--ivory);
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
      }
      header[data-testid="stHeader"] { background: transparent; }
      #MainMenu, footer { visibility: hidden; }

      h1, h2, h3 { font-family: 'Cormorant Garamond', Georgia, serif !important;
                   letter-spacing: 0.05em; color: var(--ivory) !important;
                   font-weight: 600; text-transform: uppercase; }
      ::selection { background: rgba(228,192,103,0.4); color: var(--pit); }
      a { color: var(--periwinkle); }

      /* ── sidebar: sunken pit panel with hairline rule ── */
      section[data-testid="stSidebar"] {
        background: var(--pit);
        border-right: 1px solid var(--hairline);
      }
      section[data-testid="stSidebar"] .stMarkdown p { color: var(--sand); }

      /* Sidebar type scale: Streamlit's stock sizing (h1 ~36px, input and
         paragraph text ~16px) is tuned for the wide main canvas, not this
         ~21rem rail — it reads oversized and out of step with the rest of
         the app's small-caps mono scale (tabs, kicker, foot all sit at
         11-12.5px). Bring the utility text down to match; the wallet figure
         alone keeps display size (see the stMetric rules below). */
      section[data-testid="stSidebar"] h1 {
        font-size: 19px !important; line-height: 1.3 !important;
        margin: 2px 0 8px !important;
      }
      section[data-testid="stSidebar"] p,
      section[data-testid="stSidebar"] li,
      section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
      section[data-testid="stSidebar"] .stCaption,
      section[data-testid="stSidebar"] small {
        font-size: 11px !important; line-height: 1.55 !important;
      }
      /* Endpoint + developer-key fields: readable technical strings under a
         small-caps label one notch below them. */
      section[data-testid="stSidebar"] .stTextInput input {
        font-size: 12px !important;
        padding-top: 9px !important;
        padding-bottom: 9px !important;
      }
      section[data-testid="stSidebar"] .stTextInput label,
      section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        font-size: 11px !important;
        letter-spacing: 0.15em !important;
      }
      /* Wallet figure — the one display number in the rail, so it alone keeps
         headline size. Streamlit 1.57 renders the value as markdown: the
         digits sit in a <p> INSIDE [data-testid="stMetricValue"], so sizing
         only the container loses to the sidebar-wide `p { font-size: 11px
         !important }` rule above (a direct hit on the <p> beats anything the
         ancestor passes down by inheritance). Size the container AND every
         descendant so the digits themselves carry the size. */
      section[data-testid="stSidebar"] [data-testid="stMetric"] {
        margin-top: 6px;
      }
      section[data-testid="stSidebar"] [data-testid="stMetricValue"],
      section[data-testid="stSidebar"] [data-testid="stMetricValue"] p,
      section[data-testid="stSidebar"] [data-testid="stMetricValue"] * {
        font-size: 46px !important;
        line-height: 1.08 !important;
        font-family: 'Cormorant Garamond', Georgia, serif !important;
        font-weight: 600 !important;
        color: var(--gold-bright) !important;
      }
      section[data-testid="stSidebar"] [data-testid="stMetricLabel"],
      section[data-testid="stSidebar"] [data-testid="stMetricLabel"] p {
        font-size: 11px !important;
        letter-spacing: 0.16em !important;
      }
      section[data-testid="stSidebar"] .stButton>button {
        font-size: 12px !important;
        padding-top: 9px !important;
        padding-bottom: 9px !important;
      }
      section[data-testid="stSidebar"] [data-testid="stExpander"] summary,
      section[data-testid="stSidebar"] [data-testid="stExpander"] summary p,
      section[data-testid="stSidebar"] [data-testid="stExpander"] summary span {
        font-size: 11px !important;
      }
      /* Sidebar hairline "hint" — the fine print under the key field. Meant
         to be read once, not to compete with the field above it. Set as a
         small engraved note with real breathing room before the button row
         below it, so the fine print never crowds "Check connection". */
      section[data-testid="stSidebar"] .al-hint {
        font-size: 9.5px !important; line-height: 1.6 !important;
        color: var(--mutedsand) !important;
        margin: 10px 0 18px !important;
        padding: 8px 10px !important;
        border: 1px solid var(--hairline) !important;
        border-left: 2px solid var(--gold-deep) !important;
        background: rgba(13,19,56,0.55) !important;
      }
      section[data-testid="stSidebar"] .al-hint code { font-size: 9px !important; }

      /* ── inputs: engraved sunken fields, sharp corners ── */
      .stTextInput input, .stTextArea textarea, .stNumberInput input {
        background: var(--pit) !important;
        border: 1px solid var(--hairline) !important;
        border-radius: 0 !important;
        color: var(--ivory) !important;
        font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
        caret-color: var(--gold);
      }
      .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: var(--gold) !important;
        box-shadow: 0 0 0 1px var(--gold) !important;
      }
      .stTextInput label, .stTextArea label, .stSelectbox label, .stNumberInput label {
        font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
        font-size: 11px !important; text-transform: uppercase;
        letter-spacing: 0.14em; color: var(--sand) !important;
      }
      [data-baseweb="select"] > div {
        background: var(--pit) !important;
        border: 1px solid var(--hairline) !important;
        border-radius: 0 !important;
        color: var(--ivory) !important;
        font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
      }
      [data-baseweb="popover"] [role="listbox"] {
        background: var(--basalt) !important;
        border: 1px solid var(--hairline) !important;
        border-radius: 0 !important;
      }
      [data-baseweb="menu"] [role="option"] { color: var(--ivory) !important; }

      /* ── tabs: this IS the app — the craft menu gets room to breathe ── */
      .stTabs [data-baseweb="tab-list"] { gap: 30px; border-bottom: 1px solid var(--hairline); }
      .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
        font-size: 12.5px; text-transform: uppercase; letter-spacing: 0.15em;
        color: var(--sand); font-weight: 500;
        padding: 8px 3px 15px;
      }
      .stTabs [data-baseweb="tab"]:hover { color: var(--ivory); }
      .stTabs [aria-selected="true"] { color: var(--gold-bright) !important; }
      .stTabs [data-baseweb="tab-highlight"] { background-color: var(--gold); height: 2px; }
      .stTabs [data-baseweb="tab-border"] { background-color: var(--hairline); }
      .stTabs { margin-top: 4px; }
      .stTabs [data-baseweb="tab-panel"] { padding-top: 22px; }

      /* ── buttons: the gold plate button, engraved hover ── */
      .stButton>button, .stDownloadButton>button, .stLinkButton>a {
        border-radius: 0 !important; border: 1px solid var(--gold) !important;
        background: var(--gold) !important; color: var(--abyss) !important;
        font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em;
        font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
        font-size: 12px;
        transition: background .15s ease, color .15s ease;
      }
      .stButton>button:hover, .stDownloadButton>button:hover, .stLinkButton>a:hover {
        background: transparent !important; color: var(--ivory) !important;
      }
      .stButton>button:active { background: var(--gold-deep) !important; }

      /* ── alerts: basalt plates with a gold spine ── */
      div[data-testid="stAlert"], .stAlert {
        background: var(--basalt) !important;
        border: 1px solid var(--hairline) !important;
        border-left: 3px solid var(--gold) !important;
        border-radius: 0 !important;
        color: var(--ivory) !important;
        font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
      }
      div[data-testid="stAlert"] p { color: var(--ivory) !important; }

      /* ── code, dataframes, dividers, captions, spinner ── */
      .stCode, pre, code {
        background: var(--pit) !important;
        border-radius: 0 !important;
        color: var(--gold-bright) !important;
      }
      pre { border: 1px solid var(--hairline) !important; }
      [data-testid="stDataFrame"] { border: 1px solid var(--hairline); }
      hr { border-color: var(--hairline) !important; }
      [data-testid="stCaptionContainer"], .stCaption, small { color: var(--sand) !important; }
      .stSpinner > div > div { border-top-color: var(--gold) !important; }
      [data-testid="stMetricValue"] { color: var(--gold-bright); font-family: 'Cormorant Garamond', serif; }
      [data-testid="stMetricLabel"] { color: var(--sand); text-transform: uppercase;
                                      letter-spacing: 0.14em; font-size: 11px; }
      [data-testid="stExpander"] details { border: 1px solid var(--hairline); border-radius: 0; }
      [data-testid="stExpander"] summary p {
        font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
        font-size: 12.5px !important; text-transform: uppercase;
        letter-spacing: 0.1em; color: var(--sand) !important;
      }

      /* The native "Press Enter to apply" hint is absolutely positioned and,
         in the narrow sidebar, lands on top of the input's own text/icon
         instead of below it. Flow it under the field instead of over it. */
      [data-testid="InputInstructions"] {
        position: static !important;
        display: block !important;
        margin-top: 4px !important;
        padding: 0 !important;
        white-space: normal !important;
        text-align: left !important;
      }

      /* ── brand pieces ── */
      .al-seal { border:1px solid rgba(228,192,103,0.5); background:rgba(228,192,103,0.08);
                 padding:12px 16px; font-family:'IBM Plex Mono',ui-monospace,monospace;
                 font-size:12px; white-space:pre-wrap; color:var(--gold-bright); }
      .al-kicker { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px;
                   text-transform:uppercase; letter-spacing:0.20em; color:var(--gold); }
      .al-banner { border:1px solid rgba(228,192,103,0.45); background:rgba(23,36,120,0.55);
                   padding:14px 18px; margin:8px 0 4px; font-size:12.5px; color:var(--sand);
                   line-height:1.7; }
      .al-banner strong { color:var(--ivory); }
      .al-foot { border-top:1px solid var(--hairline); margin-top:34px; padding-top:18px;
                 color:var(--sand); font-family:'IBM Plex Mono',ui-monospace,monospace;
                 font-size:11px; letter-spacing:0.05em; line-height:1.95; }
      .al-foot a { color:var(--periwinkle); text-decoration:none; }
      .al-foot a:hover { text-decoration:underline; }

      /* wordmark block — the site's centered masthead */
      .al-mast { text-align:center; padding: 6px 0 2px; }
      .al-mast .al-word {
        font-family:'Cormorant Garamond',Georgia,serif; font-weight:600;
        font-size: 52px; text-transform: uppercase; letter-spacing: 0.16em;
        line-height: 1.04; color: var(--ivory);
      }
      .al-mast svg { margin: 6px 4px 0; opacity: 0.9; }
      .al-mast-crest { width:66px; height:66px; margin:0 auto 2px; display:block; opacity:0.96; }

      /* one-line tagline under the band — small on purpose, the masthead
         above it already carries the weight */
      .al-tagline { text-align:center; font-size:12.5px; color:var(--sand);
                    margin: 0 0 6px; letter-spacing: 0.02em; }

      /* sidebar masthead — the brand crest front and center at the top of
         the rail, wordmark beneath it, closed by a gold hairline. Same crest
         as app.alchemylake.com; sized to be seen, not squeezed inline. */
      .al-side-head { text-align:center; padding: 4px 0 0; }
      .al-side-head img { width:46px; height:46px; display:block; margin:0 auto 7px;
                          opacity:0.97; filter: drop-shadow(0 0 10px rgba(228,192,103,0.22)); }
      .al-side-mark { font-family:'Cormorant Garamond',Georgia,serif; font-weight:600;
                       font-size: 23px; text-transform: uppercase; letter-spacing: 0.16em;
                       line-height: 1.14; color: var(--ivory); margin: 0; }
      .al-side-mark span { color: var(--gold-bright); }
      .al-side-rule { height:1px; margin:11px auto 13px; width:72%;
                      background: linear-gradient(90deg, transparent,
                                  rgba(228,192,103,0.55), transparent); }

      /* enterprise control card — the shared shell for every lane's
         source/format panel and every result's download+save actions */
      .al-card { border: 1px solid var(--hairline); background: rgba(23,36,120,0.35);
                 padding: 18px 20px; }
      .al-card + .al-card { margin-top: 12px; }
      .al-card-label { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10.5px;
                        text-transform: uppercase; letter-spacing: 0.18em;
                        color: var(--mutedsand); margin-bottom: 12px; }
      .al-result-card { border: 1px solid rgba(228,192,103,0.35);
                         background: rgba(18,28,94,0.5); padding: 16px 18px 18px;
                         margin: 16px 0 6px; }
      .al-result-label { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10.5px;
                          text-transform: uppercase; letter-spacing: 0.16em;
                          color: var(--gold-bright); margin-bottom: 10px; }

      /* the ticker band from the marketing plate */
      .al-band { overflow:hidden; border-top:1px solid var(--hairline);
                 border-bottom:1px solid var(--hairline); padding:10px 0; margin:14px 0 4px; }
      .al-band-track { display:inline-flex; white-space:nowrap;
                       font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px;
                       text-transform:uppercase; letter-spacing:0.16em; color:var(--sand);
                       animation: al-roll 32s linear infinite; }
      .al-band-track span { padding-right: 3.4em; }
      @keyframes al-roll { to { transform: translateX(-50%); } }

      .al-ember { height:2px; margin:10px auto 0; width:120px;
                  background:linear-gradient(90deg,#f2c14e,#f0d289); }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# MCP (JSON-RPC 2.0) client
# --------------------------------------------------------------------------- #


class MCPError(Exception):
    pass


def mcp_call(method: str, params: dict[str, Any] | None, api_key: str, url: str) -> Any:
    """Send one JSON-RPC request to the AlchemyLake MCP endpoint."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }
    try:
        resp = requests.post(
            url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:  # network / DNS / timeout
        raise MCPError(f"Could not reach AlchemyLake at {url}: {exc}") from exc

    if resp.status_code >= 400:
        raise MCPError(f"HTTP {resp.status_code}: {resp.text[:400]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise MCPError(f"Non-JSON response: {resp.text[:400]}") from exc

    if "error" in data:
        raise MCPError(str(data["error"].get("message", data["error"])))
    return data.get("result")


def tool_call(name: str, arguments: dict[str, Any], api_key: str, url: str) -> tuple[str, bool]:
    """Call an MCP tool; return (text, is_error)."""
    result = mcp_call(
        "tools/call", {"name": name, "arguments": arguments}, api_key, url
    )
    content = (result or {}).get("content", [])
    text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
    return text, bool((result or {}).get("isError"))


# --------------------------------------------------------------------------- #
# Sidebar — connection & wallet
# --------------------------------------------------------------------------- #

def _remember_key_in_browser() -> None:
    """Auto-fill the developer-key field from this browser's storage, and keep
    that storage in sync as the user types. Pure client-side: the key never
    passes through a URL or a server-side store, only this browser's
    localStorage, scoped to this app's origin. Clearing the field forgets it.
    """
    st.components.v1.html(
        """
        <script>
        (function () {
          const STORE_KEY = "alchemylake_dev_key";
          const doc = window.parent.document;
          // aria-label (not [type]) so this keeps working regardless of the
          // widget's type= (plain text today; would still match if it ever
          // changed back to password).
          const input = doc.querySelector('input[aria-label^="Developer key"]');
          if (!input) return;

          if (!input.value) {
            const saved = window.parent.localStorage.getItem(STORE_KEY);
            if (saved) {
              const setter = Object.getOwnPropertyDescriptor(
                window.parent.HTMLInputElement.prototype, "value"
              ).set;
              setter.call(input, saved);
              input.dispatchEvent(new Event("input", { bubbles: true }));
              // Auto-restoring never "pressed Enter", so Streamlit's own
              // input widget would otherwise sit in an uncommitted state and
              // keep showing its "Press Enter to apply" hint. Commit it the
              // same way a real Enter keypress would.
              ["keydown", "keyup"].forEach(function (type) {
                input.dispatchEvent(new KeyboardEvent(type, {
                  key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true,
                }));
              });
            }
          }

          if (!input.dataset.alSynced) {
            input.dataset.alSynced = "1";
            input.addEventListener("input", function (e) {
              const v = e.target.value;
              if (v) window.parent.localStorage.setItem(STORE_KEY, v);
              else window.parent.localStorage.removeItem(STORE_KEY);
            });
          }
        })();
        </script>
        """,
        height=0,
    )


def _check_wallet(key: str, url: str) -> None:
    try:
        text, is_err = tool_call("get_wallet", {}, key, url)
    except MCPError as exc:
        text, is_err = str(exc), True
    st.session_state["wallet_text"] = "" if is_err else text
    st.session_state["wallet_error"] = text if is_err else ""
    st.session_state["wallet_checked_for"] = key


with st.sidebar:
    _mark_img = f'<img src="{_MARK_URI}" alt="AlchemyLake crest">' if _MARK_URI else ""
    st.markdown(
        f'<div class="al-side-head">{_mark_img}'
        '<div class="al-side-mark">Alchemy <span>Lake</span></div>'
        '<div class="al-side-rule"></div></div>'
        '<div class="al-kicker" style="margin:0 0 12px">Connection</div>',
        unsafe_allow_html=True,
    )

    mcp_url = st.text_input("MCP endpoint", value=DEFAULT_MCP_URL)
    api_key = st.text_input(
        "Developer key (alk_…)",
        value=ENV_API_KEY,
        type="default",
        help="Create one in Studio → Developer · MCP & keys. "
        "Or set ALCHEMYLAKE_API_KEY as an app secret.",
    )
    if not ENV_API_KEY:
        _remember_key_in_browser()
        st.markdown(
            '<p class="al-hint">Kept in <em>this browser</em> only, until you clear '
            "or replace it — never stored on our server, sent only as your own "
            "call's <code>Authorization</code> header.</p>",
            unsafe_allow_html=True,
        )

    if st.button("Check connection", use_container_width=True):
        if not api_key:
            st.warning("Paste a developer key first.")
        else:
            _check_wallet(api_key, mcp_url)
            if not st.session_state.get("wallet_error"):
                st.success("Connected — key accepted.")

    # Re-verify automatically whenever the active key changes (including a
    # browser-restored key right after a refresh) — no button click needed.
    if api_key and st.session_state.get("wallet_checked_for") != api_key:
        _check_wallet(api_key, mcp_url)

    wallet_error = st.session_state.get("wallet_error", "")
    wallet_text = st.session_state.get("wallet_text", "")
    if wallet_error:
        st.error(wallet_error)
    elif wallet_text:
        digits = re.findall(r"\d+", wallet_text)
        if digits:
            st.metric("Credits in wallet", digits[0])
        else:
            st.caption(wallet_text)

    st.divider()
    with st.expander("New here? Get a free key"):
        st.markdown(
            f"[Sign up free]({SIGNUP_URL}) — **{WELCOME_GRANT_CREDITS} credits on "
            "us**, no card required, then forge a key at **Studio → Developer · "
            "MCP & keys** and paste it above.\n\n"
            "An **alk_…** key ties every render made from this App to your "
            "account, wallet, and Vault:\n"
            "- Shown **once** at creation — store it safely\n"
            "- Only a SHA-256 hash is kept server-side; revoke it anytime\n"
            "- Runs it authorizes spend **your** credits, land in **your** Vault\n\n"
            f"No key yet? [Studio → Developer]({DOCS_URL}#developers) · "
            f"[Full docs]({DOCS_URL})"
        )


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

_ICON_WAVE = (
    '<svg width="15" height="15" viewBox="0 0 15 15" fill="none">'
    '<circle cx="7.5" cy="7.5" r="6.7" stroke="#f3eddf"/>'
    '<path d="M2.5 9.2c1.6-1.2 3.2-1.2 5-.2s3.4 1 5 .1" stroke="#f3eddf" stroke-width=".9"/></svg>'
)
_ICON_SUN = (
    '<svg width="15" height="15" viewBox="0 0 15 15" fill="none">'
    '<path d="M7.5 1v2.4M7.5 11.6V14M1 7.5h2.4M11.6 7.5H14M3 3l1.7 1.7M10.3 10.3 12 12'
    'M12 3l-1.7 1.7M4.7 10.3 3 12" stroke="#f3eddf" stroke-width=".9"/>'
    '<circle cx="7.5" cy="7.5" r="2.6" stroke="#f3eddf" stroke-width=".9"/></svg>'
)

_TICKER = (
    f"New accounts start with {WELCOME_GRANT_CREDITS} free credits ✦ Every lane binds to "
    "governed data ✦ Analyst 1 credit (6 with Council) ✦ Report 10 ✦ Deep Research 18 ✦ "
    "Podcast 25 ✦ Presentation 40 ✦ Video Briefing 40 ✦ Infographic 45 ✦ Music 50 ✦ "
    "Failed runs refunded ✦ Numbers verified, not trusted ✦ "
    "Governed data in, sealed deliverables out ✦ "
)

# Shared with the "Where your data goes" expander down by the footer — kept as
# a collapsed dropdown there instead of a banner up here, so the fold is
# spent on the craft menu, not on a residency notice most sessions won't need.
_DATA_RESIDENCY_HTML = (
    "This App runs in <em>your</em> Databricks workspace under SSO. Today it calls the "
    "AlchemyLake platform over MCP, so the specific rows you bind — and your prompt — are "
    "sent to AlchemyLake and its model providers to produce and seal each render, and are "
    "<strong>never used for training</strong>. For a <strong>no-egress deployment</strong> "
    "where inference runs entirely inside your workspace (Databricks Foundation Model APIs + "
    f'your own Model Serving), see <a href="{DOCS_URL}#residency">Data security &amp; residency</a>.'
)

_mast_crest = f'<img class="al-mast-crest" src="{_MARK_URI}" alt="">' if _MARK_URI else ""
st.markdown(
    f"""
    <div class="al-mast">
      {_mast_crest}
      <div class="al-kicker">Governed creative · inside your lakehouse</div>
      <div class="al-word">Alchemy<br>Lake</div>
      <div>{_ICON_WAVE}{_ICON_SUN}</div>
      <div class="al-kicker" style="color:#f0d289;margin-top:6px">Truth, made visible</div>
      <div class="al-ember"></div>
    </div>
    <div class="al-band"><div class="al-band-track">
      <span>{_TICKER}</span><span>{_TICKER}</span>
    </div></div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="al-tagline">The data your lake has already trusted.</div>',
    unsafe_allow_html=True,
)

if not api_key:
    st.info(
        f"**No developer key yet?** [Sign up free]({SIGNUP_URL}) — "
        f"**{WELCOME_GRANT_CREDITS} credits on us**, no card required — then paste your "
        "**developer key (alk_…)** in the left sidebar to begin. Already have an "
        f"account? Create a key at [{DOCS_URL}#developers]({DOCS_URL}#developers)."
    )

(
    tab_render,
    tab_research,
    tab_image,
    tab_report,
    tab_deck,
    tab_video,
    tab_music,
    tab_voice,
    tab_recipes,
    tab_sources,
    tab_docs,
    tab_about,
) = st.tabs(
    [
        # Same order as the craft menu at app.alchemylake.com/studio — Analyst
        # first, then Deep Research, then the six lanes in that exact sequence.
        # Templates has no equivalent there (it's a Databricks-only shortcut),
        # so it sits after the lanes and just before Sources rather than
        # breaking up that order.
        "Analyst",
        "Deep Research",
        "Infographic",
        "Report",
        "Presentation",
        "Video Briefing",
        "Music",
        "Podcast",
        "Templates",
        "Sources",
        "Docs",
        "About / Install",
    ]
)

# --------------------------------------------------------------------------- #
# Sources (shared load)
# --------------------------------------------------------------------------- #


def load_sources(api_key: str, url: str) -> list[dict[str, Any]]:
    text, is_err = tool_call("list_governed_sources", {}, api_key, url)
    if is_err:
        raise MCPError(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    # API returns either a list or {"sources": [...]}
    if isinstance(data, dict):
        return data.get("sources", [])
    return data if isinstance(data, list) else []


# Origin → (sort rank, short badge). Workspace tables lead, demo data trails —
# the same catalog order the web sidebar uses.
_ORIGIN_ORDER = {
    "unity_catalog": (0, "workspace"),
    "genie": (1, "genie"),
    "uploaded": (2, "upload"),
    "sample_lakehouse": (3, "sample"),
}


def source_options(sources: list[dict[str, Any]], unbound_label: str) -> dict[str, str]:
    """Selectbox labels for the governed sources, grouped by origin.

    Unity Catalog entries show the short table name with its catalog.schema
    path so ten tables from three schemas stay tellable-apart; everything
    else shows its name with an origin badge and row count.
    """

    def rank(s: dict[str, Any]) -> tuple[int, str]:
        r, _ = _ORIGIN_ORDER.get(str(s.get("origin", "")), (9, "?"))
        return (r, str(s.get("name", "")))

    options: dict[str, str] = {unbound_label: ""}
    for s in sorted(sources, key=rank):
        origin = str(s.get("origin", "?"))
        _, badge = _ORIGIN_ORDER.get(origin, (9, origin))
        name = str(s.get("name", s.get("id", "")))
        rows = s.get("row_count")
        rows_txt = f" · {rows:,} rows" if isinstance(rows, int) else ""
        parts = name.split(".")
        if origin == "unity_catalog" and len(parts) >= 3:
            label = f"◈ {parts[-1]} — {'.'.join(parts[:-1])}{rows_txt}"
        else:
            label = f"{name} · {badge}{rows_txt}"
        # Selectbox keys must be unique; collide only on identical names.
        while label in options:
            label += " ·"
        options[label] = str(s.get("id", ""))
    return options


def _source_picker(key: str) -> str:
    """Governed-source selector shared by every lane (same session cache).

    Defined here — before any tab body runs — because Streamlit executes the
    script top to bottom and the Deep Research tab is the first caller.
    """
    if st.button("Load governed sources", key=f"{key}_load", use_container_width=True):
        try:
            st.session_state["sources"] = load_sources(api_key, mcp_url)
        except MCPError as exc:
            st.error(str(exc))
    sources = st.session_state.get("sources", [])
    options = source_options(sources, "— Unbound (free prompt) —")
    choice = st.selectbox("Bound source", list(options.keys()), key=f"{key}_src")
    source_id = options[choice]
    if source_id:
        picked = next((s for s in sources if s.get("id") == source_id), {})
        st.markdown(
            f'<div class="al-kicker">rows: {picked.get("row_count", "?")} · '
            f'origin: {picked.get("origin", "?")}</div>',
            unsafe_allow_html=True,
        )
    return source_id


# --------------------------------------------------------------------------- #
# Deliverable actions — download + Save to Databricks (every lane, one look)
# --------------------------------------------------------------------------- #
#
# Every render returns a short-lived signed URL (the platform's asset store
# expires them); a raw link is fine to click once but is the wrong shape for
# "keep this" inside a Databricks workspace. So every deliverable gets the
# same two actions: a real browser download (bytes fetched once, cached, and
# handed to Streamlit directly — not a navigation to a link that will 404
# after it expires) and an explicit save into Unity Catalog or workspace
# files, using this App's own identity.
#
# Auth model: Databricks injects DATABRICKS_CLIENT_ID/SECRET for this App's
# service principal automatically — WorkspaceClient() picks them up with zero
# extra config, no separate sign-in. That means a save runs as *the App*, not
# literally as the person clicking the button; a workspace admin grants that
# one service principal access to whichever volume(s) or workspace folder(s)
# should be reachable from here (see the Docs tab → "Save to Databricks").

_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def _guess_filename(url: str, default_stem: str = "alchemylake-render") -> str:
    name = os.path.basename(urlparse(url).path)
    return name or default_stem


@st.cache_data(show_spinner=False, ttl=1800, max_entries=64)
def _fetch_bytes(url: str) -> bytes:
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.content


@st.cache_resource
def _workspace_client() -> "WorkspaceClient":
    return WorkspaceClient()


def _save_to_databricks(data: bytes, dest_path: str) -> str:
    """Write bytes to a Unity Catalog volume (``/Volumes/catalog/schema/volume/…``)
    or a workspace path (``/Workspace/…`` or ``/Users/…``), whichever the path
    looks like. Returns the normalized path actually written."""
    dest_path = dest_path.strip()
    if not dest_path:
        raise ValueError("Give it a destination path first.")
    w = _workspace_client()
    if dest_path.startswith("/Volumes/"):
        w.files.upload(dest_path, io.BytesIO(data), overwrite=True)
        return dest_path
    if dest_path.startswith("/Workspace/"):
        dest_path = dest_path[len("/Workspace") :]
    if not dest_path.startswith("/"):
        dest_path = "/" + dest_path
    w.workspace.upload(dest_path, io.BytesIO(data), format=ImportFormat.AUTO, overwrite=True)
    return dest_path


def asset_actions(
    *,
    key: str,
    url: str | None = None,
    data: bytes | None = None,
    filename: str = "",
    file_label: str = "",
) -> None:
    """Download + Save-to-Databricks controls for one rendered file.

    Pass either `url` (fetched once, then cached) or `data` directly (e.g. a
    chat transcript that never had a URL). `filename` should include the
    extension; inferred from the URL when omitted.
    """
    if data is None and url:
        try:
            data = _fetch_bytes(url)
        except requests.RequestException as exc:
            st.caption(f"Couldn't prepare a download ({exc}).")
            if url:
                st.link_button("Open in a new tab", url)
            return
    if data is None:
        return

    filename = filename or _guess_filename(url or "")
    ext = os.path.splitext(filename)[1].lower()
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")

    card = st.container(border=True)
    with card:
        st.markdown(
            f'<div class="al-result-label">{file_label or filename}</div>',
            unsafe_allow_html=True,
        )
        open_col, dl_col = st.columns(2)
        with open_col:
            if url:
                st.link_button("Open in a new tab", url, use_container_width=True)
        with dl_col:
            st.download_button(
                "Download",
                data=data,
                file_name=filename,
                mime=mime,
                key=f"{key}_dl",
                use_container_width=True,
            )

        if _DATABRICKS_SDK_AVAILABLE:
            path = st.text_input(
                "Save to Databricks",
                key=f"{key}_path",
                value=f"{DEFAULT_SAVE_DIR}/{filename}",
                placeholder="/Workspace/Shared/AlchemyLake/… or /Volumes/catalog/schema/volume/…",
                help="A Unity Catalog volume path (starts with /Volumes/…) or a "
                "workspace path (starts with /Workspace/… or /Users/…). Runs as "
                "this App's own identity — a workspace admin grants it access to "
                "whichever destinations should be reachable here.",
            )
            if st.button("Save to Databricks", key=f"{key}_save"):
                try:
                    saved_path = _save_to_databricks(data, path)
                    st.success(f"Saved to `{saved_path}`.")
                except Exception as exc:  # noqa: BLE001 — surface any SDK error as-is
                    st.error(
                        f"Couldn't save: {exc}. If this is a permission error, ask "
                        "a workspace admin to grant this App's service principal "
                        'access to that path (Docs tab → "Save to Databricks").'
                    )
        else:
            st.caption("Install `databricks-sdk` in this App's environment to enable Save to Databricks.")


# --------------------------------------------------------------------------- #
# Tab: Analyst — narrative sealed to a governed source
# --------------------------------------------------------------------------- #

with tab_render:
    st.subheader("Analyst — Bind → Transmute → Seal")
    st.caption(
        "Pick a governed source, describe what you want written, and the model is "
        "constrained to figures derivable from that data. The result carries a "
        "provenance seal."
    )

    col_l, col_r = st.columns([2, 1], gap="large")

    with col_r:
        source_card = st.container(border=True)
        with source_card:
            st.markdown('<div class="al-card-label">Source</div>', unsafe_allow_html=True)
            if st.button("Load governed sources", key="load_render", use_container_width=True):
                try:
                    st.session_state["sources"] = load_sources(api_key, mcp_url)
                except MCPError as exc:
                    st.error(str(exc))

            sources = st.session_state.get("sources", [])
            options = source_options(sources, "— Unbound (no source) —")
            choice = st.selectbox("Bound source", list(options.keys()))
            source_id = options[choice]
            compare_id = ""
            if source_id:
                picked = next((s for s in sources if s.get("id") == source_id), {})
                rows = picked.get("row_count", "?")
                st.markdown(
                    f'<div class="al-kicker">rows: {rows} · origin: {picked.get("origin","?")}</div>',
                    unsafe_allow_html=True,
                )
                # Comparative run: a second governed source; the platform
                # computes both dossiers plus deterministic deltas and the
                # analyst narrates the contrast — figures still verified.
                cmp_options = {
                    "— no comparison —": "",
                    **{
                        label: sid
                        for label, sid in source_options(sources, "—").items()
                        if sid and sid != source_id
                    },
                }
                cmp_choice = st.selectbox(
                    "Compare with (optional)",
                    list(cmp_options.keys()),
                    help="The analyst receives both sources' verified facts plus "
                    "platform-computed deltas (trend vs trend, latest totals, "
                    "YoY) — ask it to contrast them.",
                )
                compare_id = cmp_options[cmp_choice]

            st.markdown(
                '<div class="al-card-label" style="margin-top:16px">Panel</div>',
                unsafe_allow_html=True,
            )
            council = st.checkbox(
                "Model Council",
                key="render_council",
                help="Fans the same prompt out to a multi-model panel, then a "
                "judge synthesizes the best answer — 6 credits instead of 1, "
                "slower, for higher-stakes copy.",
            )

            # Conversation continuity: every chat response carries a
            # thread_id; passing it back keeps one analyst session — and for
            # Genie sources, one *Genie conversation*, so follow-ups
            # ("now break that down by region") resolve in context instead
            # of starting cold.
            thread_id = st.session_state.get("analyst_thread_id", "")
            if thread_id:
                st.markdown(
                    '<div class="al-kicker" style="margin-top:10px">'
                    "conversation · continuing</div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Follow-ups stay in context (Genie sources keep one "
                    "governed conversation in your workspace)."
                )
                if st.button("Start a new conversation", key="render_new_thread"):
                    st.session_state["analyst_thread_id"] = ""
                    st.session_state["analyst_result"] = None
                    st.rerun()

    with col_l:
        direction_card = st.container(border=True)
        with direction_card:
            st.markdown('<div class="al-card-label">Direction</div>', unsafe_allow_html=True)
            prompt = st.text_area(
                "Prompt",
                height=190,
                label_visibility="collapsed",
                placeholder="e.g. A 3-bullet executive summary of the latest quarter's "
                "ridership with exact figures and the single biggest mover.",
            )
            btn_label = "Transmute (6 credits)" if council else "Transmute (1 credit)"
            if st.button(btn_label, key="render_btn", use_container_width=True):
                if not api_key:
                    st.warning("Paste a developer key in the sidebar first.")
                elif not prompt.strip():
                    st.warning("Write a prompt first.")
                else:
                    args: dict[str, Any] = {"prompt": prompt.strip()}
                    if source_id:
                        args["source_id"] = source_id
                    if compare_id:
                        args["compare_source_id"] = compare_id
                    if council:
                        args["council"] = True
                    if st.session_state.get("analyst_thread_id"):
                        args["thread_id"] = st.session_state["analyst_thread_id"]
                    with st.spinner("Transmuting under governance…"):
                        try:
                            text, is_err = tool_call(
                                "render_governed_chat", args, api_key, mcp_url
                            )
                        except MCPError as exc:
                            text, is_err = str(exc), True
                    if is_err:
                        st.session_state["analyst_result"] = None
                        st.error(text)
                    else:
                        # Capture the session id the platform returns so the
                        # next question continues this conversation.
                        m = re.search(r"\(thread_id:\s*([A-Za-z0-9_-]+)", text)
                        if m:
                            st.session_state["analyst_thread_id"] = m.group(1)
                            text = re.sub(
                                r"\n*\(thread_id:[^)]*\)", "", text
                            ).strip()
                        st.session_state["analyst_result"] = {
                            "text": text,
                            "stamp": datetime.now().strftime("%Y%m%d-%H%M"),
                        }
                        st.rerun()

            # Rendered from session_state, not inline under the button — see
            # the note in render_media_lane() on why Save-to-Databricks needs
            # this to survive its own click's rerun.
            analyst_result = st.session_state.get("analyst_result")
            if analyst_result:
                body, _, seal = analyst_result["text"].partition("\n---\n")
                st.markdown(body)
                if seal:
                    st.markdown(
                        f'<div class="al-seal">{seal.strip()}</div>', unsafe_allow_html=True
                    )
                stamp = analyst_result["stamp"]
                asset_actions(
                    key="analyst",
                    data=body.strip().encode("utf-8"),
                    filename=f"alchemylake-analyst-{stamp}.md",
                    file_label="Transcript (.md)",
                )

# --------------------------------------------------------------------------- #
# Tab: Deep Research — planned multi-step investigation → sealed dossier
# --------------------------------------------------------------------------- #

with tab_research:
    st.subheader("Deep Research — a planned, multi-step investigation")
    st.caption(
        "Bind a source (required). The platform decomposes your brief into "
        "sub-questions and answers each with real evidence — Genie sources "
        "get governed SQL follow-ups inside your own Databricks workspace "
        "(one continuing Genie conversation); uploads, Unity Catalog tables "
        "and samples are interrogated through the deterministic facts engine. "
        "You get a sealed research dossier: executive summary, one finding "
        "per step, method note, recommendations, watchlist — as a PDF plus "
        "an Excel evidence workbook. 18 credits."
    )
    col_l, col_r = st.columns([2, 1], gap="large")
    with col_r:
        research_card = st.container(border=True)
        with research_card:
            st.markdown('<div class="al-card-label">Source</div>', unsafe_allow_html=True)
            research_source = _source_picker("research")
            if research_source and research_source.startswith("genie:"):
                st.markdown(
                    '<div class="al-kicker" style="margin-top:8px">'
                    "genie · governed SQL steps</div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Each research step runs as a Genie question in your "
                    "workspace (≈1.5 DBU each, billed to your Databricks "
                    "account — first 150 DBUs/user/month are free there)."
                )
    with col_l:
        research_dir_card = st.container(border=True)
        with research_dir_card:
            st.markdown('<div class="al-card-label">Brief</div>', unsafe_allow_html=True)
            research_prompt = st.text_area(
                "Brief",
                height=150,
                key="research_prompt",
                label_visibility="collapsed",
                placeholder="e.g. Why did Q3 dip and what should we do about it? "
                "Investigate the trend, the biggest movers, seasonality, and "
                "concentration risk.",
            )
            research_run = st.button(
                "Run Deep Research (18 credits)",
                key="research_btn",
                use_container_width=True,
            )
    if research_run:
        if not api_key:
            st.warning("Paste a developer key in the sidebar first.")
        elif not research_source:
            st.warning("Deep Research must bind a governed source — pick one on the right.")
        elif not research_prompt.strip():
            st.warning("Write a research brief first.")
        else:
            with st.spinner(
                "Planning sub-questions, gathering evidence step by step, "
                "synthesizing the dossier… (this is the platform's longest "
                "lane — a few minutes is normal)"
            ):
                try:
                    text, is_err = tool_call(
                        "render_deep_research",
                        {
                            "prompt": research_prompt.strip(),
                            "source_id": research_source,
                        },
                        api_key,
                        mcp_url,
                    )
                except MCPError as exc:
                    text, is_err = str(exc), True
            if is_err:
                st.session_state["research_result"] = None
                st.error(text)
            else:
                st.session_state["research_result"] = text

    # Rendered from session_state — see the note in render_media_lane() on why
    # Save-to-Databricks needs this to survive its own click's rerun.
    research_result = st.session_state.get("research_result")
    if research_result:
        body, _, seal = research_result.partition("\n---\n")
        lines = body.splitlines()
        r_assets: list[tuple[str, str]] = []
        shown = body
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith("http"):
                if ".xlsx" in line.lower():
                    label = "Excel evidence workbook"
                elif not r_assets:
                    label = "Research dossier (PDF)"
                else:
                    label = lines[i - 1].strip().rstrip(":") if i else "Result file"
                r_assets.append((label, line))
                shown = shown.replace(line, "")
        remainder = shown.strip()
        if remainder:
            with st.expander("Findings summary — from the sealed dossier", expanded=True):
                st.markdown(remainder)
        if seal:
            st.markdown(f'<div class="al-seal">{seal.strip()}</div>', unsafe_allow_html=True)
        for i, (label, url) in enumerate(r_assets):
            asset_actions(key=f"research_{i}", url=url, file_label=label)

# --------------------------------------------------------------------------- #
# Media lanes: imagery, video, music, voice
# --------------------------------------------------------------------------- #


# Style/format libraries — ids must match apps/api/app/atelier.py exactly.
VIDEO_STYLES = {
    "consultant_walkthrough": "Consultant Walkthrough",
    "newsroom_segment": "Newsroom Segment",
    "executive_standup": "Executive Stand-Up",
    "documentary_deepdive": "Documentary Deep-Dive",
    "field_report": "Field Report",
    "social_recap": "Social Recap",
}
MUSIC_STYLES = {
    "cinematic_score": "Cinematic Score",
    "corporate_uplift": "Corporate Uplift",
    "ambient_dataviz": "Ambient Data Fields",
    "electronic_pulse": "Electronic Pulse",
    "orchestral_arc": "Orchestral Arc",
    "lofi_data_study": "Lo-Fi Data Study",
}
PODCAST_STYLES = {
    "two_host_interview": "Two-Host Interview",
    "skeptics_debate": "Skeptic's Debate",
    "executive_standup": "Executive Stand-Up",
    "narrative_deepdive": "Narrative Deep-Dive",
    "plain_language_walkthrough": "Plain-Language Walkthrough",
}


def render_media_lane(
    tab: Any,
    *,
    kind: str,
    tool: str,
    credits: int,
    show,
    placeholder: str,
    bound_note: str,
    unbound_note: str = "it's a straight creative render of your prompt — no data, no verification.",
    note: str = "",
    styles: dict[str, str] | None = None,
    style_label: str = "Format",
) -> None:
    """One media lane: bind a governed source → grounded render → sealed asset.

    With a source bound, a grounded step derives the figures/arc ONLY from that
    source's rows before the render; the grounded brief/script comes back for
    audit and the seal records source · rows · data sha256. Left unbound, every
    lane still runs — `unbound_note` sets expectations for what that free-form
    version actually produces (e.g. Podcast unbound is a single voice reading
    your prompt, not the two-host show binding unlocks). Metered by the same
    ledger; auto-refund on provider error or safety block, exactly like the
    web Studio.

    `styles`, if given, is an {id: label} map (matching the API's style ids
    exactly) rendered as a selectbox; "Auto" lets the expert panel choose.
    """
    with tab:
        st.subheader(kind)
        caption = (
            f"Generate {kind.lower()} ({credits} credits). Left unbound, "
            f"{unbound_note} Bind a governed source to make it data-bound: {bound_note}"
        )
        if note:
            caption += " " + note
        st.caption(caption)
        key = kind.lower().replace(" ", "_")
        col_l, col_r = st.columns([2, 1], gap="large")
        with col_r:
            source_card = st.container(border=True)
            with source_card:
                st.markdown('<div class="al-card-label">Source</div>', unsafe_allow_html=True)
                source_id = _source_picker(key)
                style_id = ""
                if styles:
                    choice = st.selectbox(
                        style_label, ["Auto"] + list(styles.values()), key=f"{key}_style"
                    )
                    if choice != "Auto":
                        style_id = next(k for k, v in styles.items() if v == choice)
        with col_l:
            direction_card = st.container(border=True)
            with direction_card:
                st.markdown('<div class="al-card-label">Direction</div>', unsafe_allow_html=True)
                prompt = st.text_area(
                    f"{kind} prompt",
                    height=150,
                    key=f"{key}_prompt",
                    placeholder=placeholder,
                    label_visibility="collapsed",
                )
                run = st.button(
                    f"Render {kind} ({credits} credits)",
                    key=f"{key}_btn",
                    use_container_width=True,
                )
        if run:
            if not api_key:
                st.warning("Paste a developer key in the sidebar first.")
            elif not prompt.strip():
                st.warning(f"Write a prompt for the {kind} lane first.")
            else:
                args: dict[str, Any] = {"prompt": prompt.strip()}
                if source_id:
                    args["source_id"] = source_id
                if style_id:
                    args["style"] = style_id
                with st.spinner(
                    "Grounding to the bound source, then rendering…"
                    if source_id
                    else "Rendering… video and music can take 1–3 minutes."
                ):
                    try:
                        text, is_err = tool_call(tool, args, api_key, mcp_url)
                    except MCPError as exc:
                        text, is_err = str(exc), True
                if is_err:
                    st.session_state[f"{key}_result"] = None
                    st.error(text)
                else:
                    st.session_state[f"{key}_result"] = {
                        "text": text,
                        "stamp": datetime.now().strftime("%Y%m%d-%H%M"),
                    }

        # Rendered from session_state (not inline under `if run:`) so the Save
        # to Databricks / Download buttons below survive their own reruns —
        # a widget nested inside an `if <other button>:` block never sees its
        # own click, because that outer condition is False on every rerun
        # except the one that fired the outer button itself.
        result = st.session_state.get(f"{key}_result")
        if result:
            body, _, seal = result["text"].partition("\n---\n")
            url_lines = [l.strip() for l in body.splitlines() if l.strip().startswith("http")]
            if url_lines:
                show(url_lines[0])
            # Grounded brief/script (returned on bound renders) — audit it.
            _, marker, brief = body.partition("(data-derived):\n")
            if marker and brief.strip():
                with st.expander("Grounded brief — figures derived from the bound source"):
                    st.markdown(brief.strip())
            if seal:
                st.markdown(f'<div class="al-seal">{seal.strip()}</div>', unsafe_allow_html=True)
            for i, one_url in enumerate(url_lines):
                asset_actions(
                    key=f"{key}_{i}",
                    url=one_url,
                    file_label=kind if len(url_lines) == 1 else f"{kind} · file {i + 1}",
                )


render_media_lane(
    tab_image,
    kind="Infographic",
    tool="render_infographic",
    credits=45,
    show=lambda u: st.image(u, use_container_width=True),
    placeholder="e.g. A KPI poster for the exec review — bold headline stat, insight callouts.",
    bound_note=(
        "the Insight Engine analyzes the rows (trend, outliers, shares) and an "
        "expert panel designs the layout — headline stat, insight callouts, and a "
        "branded provenance strip rendered into the image."
    ),
    unbound_note=(
        "the model turns your words into a designed image (inventing plausible "
        "supporting visuals if you're abstract) — nothing is pulled from data."
    ),
    note="Free-tier images carry a visible watermark + an embedded provenance manifest.",
)

render_media_lane(
    tab_video,
    kind="Video Briefing",
    tool="render_video_briefing",
    credits=40,
    show=lambda u: st.video(u),
    placeholder="e.g. A 45-second briefing of this quarter — lead with the trend, end on the leader.",
    bound_note=(
        "the platform composes an animated data video — real charts as scenes, "
        "spoken narration grounded in the verified figures, motion and crossfades."
    ),
    unbound_note="it renders as cinematic text-to-video from your prompt alone.",
    styles=VIDEO_STYLES,
    style_label="Format (Auto lets the showrunner choose)",
)

render_media_lane(
    tab_music,
    kind="Music",
    tool="render_music",
    credits=50,
    show=lambda u: st.audio(u),
    placeholder="e.g. ~30s score of this quarter's trajectory, warm and confident.",
    bound_note=(
        "the data is sonified — tempo from momentum, major/minor from trend "
        "direction, movements from the period arc — and a sonic legend plus a "
        "data-motif WAV (the literal melody of the rows) ship alongside."
    ),
    unbound_note="it's a straight generative track from your prompt — no sonification.",
    styles=MUSIC_STYLES,
    style_label="Genre (Auto lets the composer choose)",
)

render_media_lane(
    tab_voice,
    kind="Podcast",
    tool="render_podcast",
    credits=25,
    show=lambda u: st.audio(u),
    placeholder="e.g. A quick briefing on this quarter — what happened and what to watch.",
    styles=PODCAST_STYLES,
    style_label="Format (Auto lets the producer choose)",
    bound_note=(
        "a two-host episode (analyst × interviewer) is written around the "
        "verified facts, performed with two voices, stitched into one file; the "
        "transcript returns alongside the audio."
    ),
    unbound_note="it's a single voice reading your prompt aloud — not the two-host show.",
)

# --------------------------------------------------------------------------- #
# Tab: Report (branded PDF — verified numbers, citations, sealed on the page)
# --------------------------------------------------------------------------- #

with tab_report:
    st.subheader("Report — PDF dossier + Excel evidence workbook")
    st.caption(
        "Bind a source (required). The Insight Engine computes the statistics "
        "by code; the model writes narrative around fact IDs and never authors "
        "a number. You get an enterprise PDF (cover, KPI band, chart sections, "
        "statistical appendix, citations, methodology) plus an Excel evidence "
        "workbook with the raw rows, facts, pivot, and correlations. 10 credits."
    )
    col_l, col_r = st.columns([2, 1], gap="large")
    with col_r:
        report_card = st.container(border=True)
        with report_card:
            st.markdown('<div class="al-card-label">Source</div>', unsafe_allow_html=True)
            report_source = _source_picker("report")
    with col_l:
        report_dir_card = st.container(border=True)
        with report_dir_card:
            st.markdown('<div class="al-card-label">Direction</div>', unsafe_allow_html=True)
            report_prompt = st.text_area(
                "Direction",
                height=150,
                key="report_prompt",
                label_visibility="collapsed",
                placeholder="e.g. Executive brief for the board — lead with the "
                "strongest region, flag the biggest decline, end with one action.",
            )
            report_run = st.button(
                "Compose report (10 credits)", key="report_btn", use_container_width=True
            )
    if report_run:
        if not api_key:
            st.warning("Paste a developer key in the sidebar first.")
        elif not report_source:
            st.warning("Reports must bind a governed source — pick one on the right.")
        elif not report_prompt.strip():
            st.warning("Give the report a direction first.")
        else:
            with st.spinner("Binding facts, composing, verifying, sealing…"):
                try:
                    text, is_err = tool_call(
                        "render_report",
                        {"prompt": report_prompt.strip(), "source_id": report_source},
                        api_key,
                        mcp_url,
                    )
                except MCPError as exc:
                    text, is_err = str(exc), True
            if is_err:
                st.session_state["report_result"] = None
                st.error(text)
            else:
                st.session_state["report_result"] = text

    # Rendered from session_state — see the note in render_media_lane() on why
    # Save-to-Databricks needs this to survive its own click's rerun.
    report_result = st.session_state.get("report_result")
    if report_result:
        body, _, seal = report_result.partition("\n---\n")
        lines = body.splitlines()
        shown = body
        assets = []
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith("http"):
                label = lines[i - 1].strip().rstrip(":") if i else "Sealed PDF"
                if not assets:
                    label = "Sealed PDF"
                elif ".xlsx" in line.lower():
                    label = "Excel evidence workbook"
                assets.append((label, line))
                shown = shown.replace(line, "")
        st.markdown(shown.strip())
        if seal:
            st.markdown(f'<div class="al-seal">{seal.strip()}</div>', unsafe_allow_html=True)
        for i, (label, url) in enumerate(assets):
            asset_actions(key=f"report_{i}", url=url, file_label=label)

# --------------------------------------------------------------------------- #
# Tab: Presentation (downloadable .pptx — speaker notes + Q&A under every slide)
# --------------------------------------------------------------------------- #

with tab_deck:
    st.subheader("Presentation — a PowerPoint you can present cold")
    st.caption(
        "Bind a source (required). The expert panel designs the deck from the "
        "statistical dossier: cover art, hero stats, real charts — and under "
        "every slide, a read-aloud presenter script plus likely Q&A in the "
        "notes pane. 40 credits for 5 slides, +4 per extra slide (up to 20)."
    )
    col_l, col_r = st.columns([2, 1], gap="large")
    with col_r:
        deck_card = st.container(border=True)
        with deck_card:
            st.markdown('<div class="al-card-label">Source</div>', unsafe_allow_html=True)
            deck_source = _source_picker("deck")
            st.markdown(
                '<div class="al-card-label" style="margin-top:16px">Shape</div>',
                unsafe_allow_html=True,
            )
            deck_slides = st.slider("Slides", 5, 20, 5, key="deck_slides")
            deck_title = st.text_input(
                "Deck title (optional)", key="deck_title", placeholder="e.g. Q2 Momentum"
            )
    with col_l:
        deck_dir_card = st.container(border=True)
        with deck_dir_card:
            st.markdown('<div class="al-card-label">Direction</div>', unsafe_allow_html=True)
            deck_prompt = st.text_area(
                "Direction",
                height=150,
                key="deck_prompt",
                label_visibility="collapsed",
                placeholder="e.g. Board review of the quarter — lead with growth, "
                "address the weakest region head-on, end with priorities.",
            )
            deck_cost = 40 + max(0, deck_slides - 5) * 4
            deck_run = st.button(
                f"Compose deck ({deck_cost} credits)", key="deck_btn", use_container_width=True
            )
    if deck_run:
        if not api_key:
            st.warning("Paste a developer key in the sidebar first.")
        elif not deck_source:
            st.warning("Presentations must bind a governed source — pick one on the right.")
        elif not deck_prompt.strip():
            st.warning("Give the deck a direction first.")
        else:
            deck_args: dict[str, Any] = {
                "prompt": deck_prompt.strip(),
                "source_id": deck_source,
                "slides": deck_slides,
            }
            if deck_title.strip():
                deck_args["title"] = deck_title.strip()
            with st.spinner(
                "Analyzing the rows, designing slides, drawing charts, writing "
                "speaker notes… (a minute or two)"
            ):
                try:
                    text, is_err = tool_call(
                        "render_presentation", deck_args, api_key, mcp_url
                    )
                except MCPError as exc:
                    text, is_err = str(exc), True
            if is_err:
                st.session_state["deck_result"] = None
                st.error(text)
            else:
                st.session_state["deck_result"] = text

    # Rendered from session_state — see the note in render_media_lane() on why
    # Save-to-Databricks needs this to survive its own click's rerun.
    deck_result = st.session_state.get("deck_result")
    if deck_result:
        body, _, seal = deck_result.partition("\n---\n")
        url_line = next((l.strip() for l in body.splitlines() if l.startswith("http")), "")
        st.markdown(body.replace(url_line, "").strip())
        if seal:
            st.markdown(f'<div class="al-seal">{seal.strip()}</div>', unsafe_allow_html=True)
        if url_line:
            asset_actions(key="deck", url=url_line, file_label="Presentation (.pptx)")

# --------------------------------------------------------------------------- #
# Tab: Templates (one-click recipes via list_recipes / run_recipe)
# --------------------------------------------------------------------------- #
#
# A "template" (the API calls it a recipe) is a shortcut: it pre-selects a
# lane (image / report / deck / chat / audio / video) and a specific expert
# art direction, so instead of writing your own brief you just bind a source
# and click. The catalog below mirrors apps/api/app/recipes.py + the credits
# on each lane's tab exactly (same hand-synced convention as VIDEO_STYLES /
# MUSIC_STYLES / PODCAST_STYLES above) — kept local so this tab renders a
# real, priced catalog instantly instead of an empty state behind a "Load"
# button and a literal "? cr" placeholder (list_recipes doesn't return
# pricing; only the rate card, which this App doesn't call directly, has it).

RECIPE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "kpi_poster", "name": "KPI Poster", "kind": "image", "credits": 45,
        "deliverable": "Image — PNG poster",
        "tagline": "A boardroom-wall poster with the headline stat front and center.",
    },
    {
        "id": "one_pager", "name": "Executive One-Pager", "kind": "report", "credits": 10,
        "deliverable": "PDF + Excel evidence workbook",
        "tagline": "A branded PDF brief: headline, narrative, chart, citations, seal.",
    },
    {
        "id": "social_copy", "name": "Social Announcement", "kind": "chat", "credits": 1,
        "deliverable": "Text — LinkedIn post",
        "tagline": "A LinkedIn-ready post grounded in the real figures.",
    },
    {
        "id": "board_deck", "name": "Board Deck", "kind": "deck", "credits": 40,
        "deliverable": "Presentation — .pptx, 5 slides",
        "tagline": "A ready-to-present PPTX: charts, speaker notes, Q&A prep.",
    },
    {
        "id": "data_briefing", "name": "Audio Briefing", "kind": "voice", "credits": 25,
        "deliverable": "Audio — 2-host podcast + transcript",
        "tagline": "A two-host podcast that interrogates this period's numbers.",
    },
    {
        "id": "boardroom_briefing", "name": "Boardroom Briefing", "kind": "video", "credits": 40,
        "deliverable": "Video — .mp4",
        "tagline": "A crisp video briefing: headline, trend, mix, close — narrated like a consultant.",
    },
    {
        "id": "data_score", "name": "Data Score", "kind": "music", "credits": 50,
        "deliverable": "Audio — score + data-motif WAV",
        "tagline": "Your data as a cinematic score — tempo from momentum, key from trend.",
    },
    {
        "id": "campaign_pack", "name": "Campaign Pack", "kind": "pack", "credits": 56,
        "deliverable": "3 files — poster + PDF + post",
        "tagline": "Poster + one-pager + social copy from the same sealed source, one click.",
        "pieces": ["kpi_poster", "one_pager", "social_copy"],
    },
]
RECIPE_BY_ID = {r["id"]: r for r in RECIPE_CATALOG}


def _show_recipe_result(text: str, *, key_prefix: str) -> None:
    """Render one run_recipe result: asset(s) (typed by extension), grounded
    brief, seal, and (Download + Save to Databricks) — shared by the
    single-template and pack flows.

    Some pieces (e.g. the one-pager, which is a `report` under the hood)
    return more than one asset URL — a document plus an Excel evidence
    workbook. Every `http…` line gets its own control, not just the first.
    An extension we don't recognize (e.g. a local-dev HTML fallback for a
    PDF) still gets a labeled action card, labeled from whatever text
    preceded the URL (mirroring the Report tab), instead of silently trying
    — and failing — to show it as an image.
    """
    body, _, seal = text.partition("\n---\n")
    lines = body.splitlines()
    url_lines: list[str] = []
    url_labels: list[str] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line.startswith("http"):
            continue
        low = line.lower()
        if ".pdf" in low:
            label = "Sealed PDF"
        elif ".pptx" in low:
            label = "Presentation (.pptx)"
        elif ".xlsx" in low:
            label = "Excel evidence workbook"
        elif any(x in low for x in (".mp4", ".webm")):
            st.video(line)
            label = "Video"
        elif any(x in low for x in (".mp3", ".wav", ".m4a")):
            st.audio(line)
            label = "Audio"
        elif any(x in low for x in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
            st.image(line, use_container_width=True)
            label = "Image"
        else:
            label = lines[i - 1].strip().rstrip(":") if i else "Result file"
        url_lines.append(line)
        url_labels.append(label)
    remainder = body
    for url_line in url_lines:
        remainder = remainder.replace(url_line, "")
    remainder = remainder.strip()
    if remainder:
        with st.expander("Grounded brief — figures derived from the bound source"):
            st.markdown(remainder)
    if seal:
        st.markdown(f'<div class="al-seal">{seal.strip()}</div>', unsafe_allow_html=True)
    for i, (line, label) in enumerate(zip(url_lines, url_labels)):
        asset_actions(key=f"{key_prefix}_{i}", url=line, file_label=label)


def _run_one_recipe(recipe_id: str, source_id: str, extra: str) -> tuple[str, bool]:
    """Call run_recipe once; returns (text, is_error) for the caller to store
    in session_state and render outside the button block."""
    args: dict[str, Any] = {"recipe": recipe_id, "source_id": source_id}
    if extra.strip():
        args["prompt"] = extra.strip()
    try:
        return tool_call("run_recipe", args, api_key, mcp_url)
    except MCPError as exc:
        return str(exc), True


with tab_recipes:
    st.subheader("Templates — one-click deliverables")
    st.markdown(
        "A **template** locks in a lane (image, PDF, deck, audio, video, or "
        "post) plus an expert art direction someone already designed for that "
        "deliverable shape — so instead of writing your own brief from "
        "scratch, you bind a source and click. Every figure still comes only "
        "from that source's platform-computed facts, and the result is "
        "verified and sealed exactly like every other lane."
    )

    st.markdown("###### Choose a template")
    st.session_state.setdefault("selected_recipe", RECIPE_CATALOG[0]["id"])
    grid_cols = st.columns(4)
    for i, r in enumerate(RECIPE_CATALOG):
        with grid_cols[i % 4]:
            is_selected = st.session_state["selected_recipe"] == r["id"]
            border = "border:1px solid var(--gold);" if is_selected else ""
            st.markdown(
                f'<div class="al-banner" style="min-height:172px;{border}">'
                f'<div class="al-kicker" style="color:var(--gold-bright)">{r["name"]}</div>'
                f'<div style="margin:6px 0 10px;font-size:12px;min-height:52px">{r["tagline"]}</div>'
                f'<div style="font-size:11px;color:var(--sand)">{r["deliverable"]}</div>'
                f'<div style="font-size:11px;color:var(--gold-bright);margin-top:2px">'
                f'{r["credits"]} credits</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Selected ✓" if is_selected else "Use this",
                key=f"pick_{r['id']}",
                use_container_width=True,
                disabled=is_selected,
            ):
                st.session_state["selected_recipe"] = r["id"]
                st.rerun()

    st.divider()

    picked = RECIPE_BY_ID[st.session_state["selected_recipe"]]
    is_pack = picked["kind"] == "pack"
    st.markdown(
        f"###### Run: {picked['name']} — {picked['deliverable']} · "
        f"{picked['credits']} credits"
    )
    if is_pack:
        piece_names = ", ".join(RECIPE_BY_ID[p]["name"] for p in picked["pieces"])
        st.caption(
            f"Runs its pieces one after another against the same bound source: "
            f"{piece_names}. Each piece is sealed and verified individually."
        )

    col_l, col_r = st.columns([2, 1], gap="large")
    with col_r:
        recipe_card = st.container(border=True)
        with recipe_card:
            st.markdown('<div class="al-card-label">Source</div>', unsafe_allow_html=True)
            recipe_source = _source_picker("recipe")
    with col_l:
        recipe_dir_card = st.container(border=True)
        with recipe_dir_card:
            st.markdown('<div class="al-card-label">Extra direction</div>', unsafe_allow_html=True)
            recipe_extra = st.text_area(
                "Extra direction (optional)",
                key=f"recipe_extra_{picked['id']}",
                height=110,
                label_visibility="collapsed",
                placeholder="audience, tone, emphasis…",
            )
            run_label = (
                f"Run Campaign Pack ({picked['credits']} credits total)"
                if is_pack
                else f"Run {picked['name']} ({picked['credits']} credits)"
            )
            recipe_run = st.button(run_label, key="recipe_run_btn", use_container_width=True)

    if recipe_run:
        if not api_key:
            st.warning("Paste a developer key in the sidebar first.")
        elif not recipe_source:
            st.warning("Templates bind a governed source — pick one on the right.")
        elif is_pack:
            pack_results: dict[str, tuple[str, bool]] = {}
            for piece_id in picked["pieces"]:
                piece = RECIPE_BY_ID[piece_id]
                with st.spinner(f"Running {piece['name']} under governance…"):
                    pack_results[piece_id] = _run_one_recipe(
                        piece_id, recipe_source, recipe_extra
                    )
            st.session_state["recipe_pack_result"] = (picked["id"], pack_results)
            st.session_state["recipe_single_result"] = None
        else:
            with st.spinner("Running the template under governance…"):
                result = _run_one_recipe(picked["id"], recipe_source, recipe_extra)
            st.session_state["recipe_single_result"] = (picked["id"], result)
            st.session_state["recipe_pack_result"] = None

    # Rendered from session_state — see the note in render_media_lane() on why
    # Save-to-Databricks needs this to survive its own click's rerun.
    pack_result = st.session_state.get("recipe_pack_result")
    single_result = st.session_state.get("recipe_single_result")
    if pack_result and pack_result[0] == picked["id"]:
        for piece_id in picked["pieces"]:
            piece = RECIPE_BY_ID[piece_id]
            text, is_err = pack_result[1][piece_id]
            st.markdown(f"**{piece['name']}** — {piece['deliverable']}")
            if is_err:
                st.error(text)
            else:
                _show_recipe_result(text, key_prefix=f"pack_{piece_id}")
    elif single_result and single_result[0] == picked["id"]:
        text, is_err = single_result[1]
        if is_err:
            st.error(text)
        else:
            _show_recipe_result(text, key_prefix=f"recipe_{picked['id']}")

# --------------------------------------------------------------------------- #
# Tab: Sources
# --------------------------------------------------------------------------- #

with tab_sources:
    st.subheader("Governed sources bound to your account")

    upload_card = st.container(border=True)
    with upload_card:
        st.markdown(
            '<div class="al-card-label">Bring your own data</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "CSV, Excel (.xlsx/.xls), PDF, Word, text or Markdown — up to 6MB. "
            "Tables are extracted and registered as a governed source; "
            "documents with no table bind as a sectioned corpus (headings, "
            "word counts, excerpts). Either way, every lane works on it — "
            "reports, decks, videos, podcasts, deep research — no Databricks "
            "required."
        )
        uploaded = st.file_uploader(
            "Upload a file",
            type=["csv", "tsv", "xlsx", "xlsm", "xls", "pdf", "docx", "txt", "md"],
            key="src_upload",
            label_visibility="collapsed",
        )
        if uploaded is not None and st.button(
            f"Register “{uploaded.name}” as a governed source",
            key="src_upload_btn",
            use_container_width=True,
        ):
            if not api_key:
                st.warning("Paste a developer key in the sidebar first.")
            else:
                import base64 as _b64

                raw = uploaded.getvalue()
                if len(raw) > 6 * 1024 * 1024:
                    st.error("That file is over the 6MB upload cap.")
                else:
                    with st.spinner("Parsing, sealing, registering…"):
                        try:
                            text, is_err = tool_call(
                                "upload_source",
                                {
                                    "filename": uploaded.name,
                                    "content_base64": _b64.b64encode(raw).decode(),
                                },
                                api_key,
                                mcp_url,
                            )
                        except MCPError as exc:
                            text, is_err = str(exc), True
                    if is_err:
                        st.error(text)
                    else:
                        st.success(text)
                        try:
                            st.session_state["sources"] = load_sources(api_key, mcp_url)
                        except MCPError:
                            pass

    if st.button("Refresh sources", key="refresh_sources"):
        try:
            st.session_state["sources"] = load_sources(api_key, mcp_url)
        except MCPError as exc:
            st.error(str(exc))
    sources = st.session_state.get("sources", [])
    if sources:
        def _rank(s: dict[str, Any]) -> tuple[int, str]:
            r, _ = _ORIGIN_ORDER.get(str(s.get("origin", "")), (9, "?"))
            return (r, str(s.get("name", "")))

        rows = [
            {
                "source": s.get("name", ""),
                "origin": _ORIGIN_ORDER.get(str(s.get("origin", "")), (9, s.get("origin", "?")))[1],
                "rows": s.get("row_count", ""),
                "columns": ", ".join(s.get("columns", []))[:80],
                "id": s.get("id", ""),
            }
            for s in sorted(sources, key=_rank)
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption(
            f"{len(rows)} governed sources — workspace tables first, demo data last. "
            "Bind any of them from the pickers on each lane."
        )
    else:
        st.caption("No sources loaded yet. Press **Refresh sources** (needs a key).")

# --------------------------------------------------------------------------- #
# Tab: Docs — a self-contained copy, so this works even if a locked-down
# network can reach this in-workspace App but not the public website.
# --------------------------------------------------------------------------- #

with tab_docs:
    st.subheader("Documentation")
    st.caption(
        f"This tab is self-contained — it works even if {DOCS_URL} isn't reachable "
        "from your network. It's the same material, condensed for this App."
    )

    with st.expander("Quick start", expanded=True):
        st.markdown(
            f"""
1. **Get a key.** [Sign up free]({SIGNUP_URL}) ({WELCOME_GRANT_CREDITS} credits, no
   card) if you don't have an account, then forge a developer key at
   Studio → Developer · MCP & keys.
2. **Paste it** in this App's left sidebar. It's remembered in this browser until
   you clear it.
3. **Pick a tab** — Analyst for narrative, Infographic/Report/Presentation/Video
   Briefing/Music/Podcast for the media and document lanes, or Templates for
   one-click deliverables.
4. **Load governed sources** on the right of any tab, bind one (or leave
   unbound for a free-form prompt), write your direction, and run.
5. **Read the seal** under the result — source, row count, sha256, and (where
   numbers are involved) a verification score.
6. **Download or save it** — every deliverable gets a real download button
   plus a "Save to Databricks" action straight into a workspace folder or a
   Unity Catalog volume (see "Save to Databricks", below).
            """
        )

    with st.expander("Save to Databricks — admin setup"):
        st.markdown(
            f"""
Every result has a **Save to Databricks** action next to its download button.
It writes the file using this App's own identity (its service principal),
not the identity of whoever clicked the button — so a workspace admin has to
grant that one service principal access before saves will succeed.

**One-time setup, either destination or both:**

- **Unity Catalog volume** — `GRANT WRITE VOLUME, READ VOLUME ON VOLUME
  <catalog>.<schema>.<volume> TO `<this App's service principal>`` (SQL
  editor or Catalog Explorer → the volume → Permissions).
- **Workspace folder** — share the folder with this App's service principal
  (or its run-as user) with **Can Edit**, from the folder's ⋯ menu →
  Share, or `databricks workspace update-permissions`.

Point this App at your own destination by setting the **`ALCHEMYLAKE_SAVE_DIR`**
environment variable on the App (App → Edit → Environment variables) to a
`/Volumes/catalog/schema/volume` or `/Workspace/…` path — it becomes the
pre-filled default in every Save box, though anyone can still type a
different path before saving. Current default: `{DEFAULT_SAVE_DIR}`.
            """
        )

    with st.expander("Credits & the free tier"):
        st.markdown(
            f"""
Every account starts with **{WELCOME_GRANT_CREDITS} free credits** — no card
required. Top up 500 more for $5 from Studio when you run out.

| Lane | Credits |
|---|---|
| Analyst (chat) | 1 |
| Analyst + Model Council | 6 |
| Report (PDF + Excel) | 10 |
| Deep Research (PDF dossier + Excel) | 18 |
| Podcast | 25 |
| Presentation (5 slides) | 40 (+4 / extra slide) |
| Video Briefing | 40 |
| Infographic | 45 |
| Music | 50 |

A failed render (provider error or a safety block) is **automatically
refunded** — you're never charged for a run that didn't produce anything.
            """
        )

    with st.expander("The eight lanes, briefly"):
        st.markdown(
            """
Binding a source runs the **Insight Engine** — trend with fit quality, outliers,
correlations, segment shares, concentration, pivots, all computed by code — and
an **expert panel** (statistician, visualization lead, technical writer,
enterprise consultant, plus the lane's craft specialist) designs the deliverable
around those verified facts.

- **Analyst (chat)** — narrative/copy; every figure verified against the
  platform-computed facts when bound. Conversations continue: follow-ups keep
  their context, and Genie sources keep one governed Genie conversation in
  your workspace across turns.
- **Deep Research** — a planned multi-step investigation of one source: the
  brief is decomposed into sub-questions, each answered with real evidence
  (governed Genie SQL for Genie sources; the deterministic facts engine for
  uploads/UC/samples), then synthesized into a sealed dossier — PDF + Excel
  evidence workbook.
- **Infographic** — a designed data poster: headline stat, insight callouts,
  branded provenance strip rendered into the image.
- **Report** — an enterprise PDF dossier (cover, KPI band, chart sections,
  statistical appendix, citations, methodology) **plus an Excel evidence
  workbook** (raw rows · facts · statistics · pivot · correlations).
- **Presentation** — a downloadable .pptx: cover art, hero stats, real charts —
  and a read-aloud presenter script + Q&A prep under every slide. 5–20 slides.
- **Video Briefing** — an animated data video composed by the platform: chart
  scenes, spoken narration, motion and crossfades. Six formats to pick from
  (consultant walkthrough, newsroom segment, executive stand-up, documentary
  deep-dive, field report, social recap) — or Auto lets the showrunner choose.
- **Music** — the data sonified (tempo ↔ momentum, mode ↔ trend) with a sonic
  legend and a data-motif WAV — the literal melody of the rows. Six genres
  (cinematic score, corporate uplift, ambient, electronic pulse, orchestral,
  lo-fi) style the instrumentation only — tempo/key/arc always stay data-true.
- **Podcast** — a two-host audio episode grounded in the verified facts,
  transcript included. Five formats: interview, skeptic's debate, executive
  stand-up, narrative deep-dive, plain-language walkthrough.
- **Templates** — one-click recipes (KPI poster, exec one-pager, board deck,
  audio briefing, boardroom video briefing, data score, social copy, campaign
  pack).

Binding is optional on every lane except Report, Presentation, and Templates
(data deliverables by definition). Unbound runs are free-form prompts — still
governed and metered, just not tied to a source.
            """
        )

    with st.expander("Use cases by lane, across industries"):
        st.caption(
            f"Every example below runs on a free Dawn Grant — {WELCOME_GRANT_CREDITS} "
            "credits, no card required."
        )
        st.markdown(
            """
**Analyst (chat) · 1 credit (6 with Model Council)**
- *Financial services* — FP&A binds the certified loan-performance table and
  drafts the monthly board narrative; delinquency and NIM commentary quoted
  from the actual ledger.
- *Public sector / transit* — bind monthly ridership and draft the
  board-meeting performance narrative, numbers riders would recognize.
- *Retail / CPG* — a category manager binds weekly POS data for the
  Monday-morning sell-through brief to regional VPs.
- *SaaS* — RevOps binds the MRR/churn table for the Monday leadership-sync
  exec summary.

**Report · 10 credits (PDF dossier + Excel evidence workbook)**
- *Investor relations* — quarterly KPIs become a sealed dossier with a
  statistical appendix; the Excel workbook carries the raw rows and pivot for
  anyone who wants to check.
- *Manufacturing* — a plant quality manager's weekly report to line
  supervisors, every figure checked against the certified table.
- *Public sector / compliance* — a quarterly compliance report for
  regulators, a sha256 of the exact data baked into the file.
- *Nonprofit* — a funder-facing impact report whose numbers are already
  sealed to source before a grant officer fact-checks them.

**Presentation · 40 credits (5 slides, +4/extra)**
- *FP&A* — bind the quarterly KPI table and walk into the board meeting with
  a finished .pptx: charts, a read-aloud script under every slide, and Q&A
  prep for the questions the CFO will ask.
- *Consulting* — the Monday steering-committee deck generated from the
  engagement's metrics; the notes carry the talk track, so anyone can present.
- *Sales* — the QBR deck with the exact numbers the CRM shows.

**Templates · posters, one-pagers, social, campaign packs**
- *Marketing* — the campaign-pack recipe: poster, report, and social copy
  from one bound table, in one call, numbers matching to the decimal.
- *HR / people analytics* — a quarterly people-ops one-pager for the
  leadership offsite, bound to attrition and eNPS data.
- *Sales ops* — a QBR KPI poster for the regional kickoff with the exact
  figures the CRM shows.
- *Events* — a day-two attendance recap poster for social, minutes after
  doors close.

**Infographic · 45 credits**
- *DTC / e-commerce* — a milestone social post where the actual sales number
  renders correctly *in* the image, not as a caption guess.
- *Real estate* — a market-update poster with the real median price and
  days-on-market, bound to MLS data.
- *ESG / sustainability* — an ESG-report cover infographic with the
  certified year-over-year emissions reduction.
- *Manufacturing / ops* — a plant-floor poster of "45 days without a
  recordable incident," pulled from the safety log.

**Video Briefing · 40 credits (animated data video, six formats)**
- *Executive comms* — a 45-second all-hands opener in the Executive Stand-Up
  format: the real charts animate on screen while a narrator lands the
  verified figures.
- *Product / growth marketing* — a Newsroom Segment walking through the
  actual adoption curve, chart by chart, broadcast energy.
- *Field ops / safety* — a Field Report toolbox-talk opener with the real
  safety streak visualized and narrated.
- *Investor relations* — a Documentary Deep-Dive earnings-day recap, exact
  reported figures, safe to post the moment the release goes out.

**Music · 50 credits (sonification)**
- *Brand / marketing* — a launch-video bed whose tempo and arc literally
  follow the growth curve (the sonic legend explains the mapping).
- *Internal comms* — an all-hands opening sting in a major key because the
  quarter actually trended up.
- *Content / data art* — the data-motif WAV is the dataset played as melody —
  one note per period, pitch mapped to value.

**Podcast · 25 credits (two-host briefing)**
- *Executive comms* — a 3-minute analyst × interviewer episode about the
  week's numbers for the leadership commute.
- *Accessibility / inclusive comms* — an audio version of the same sealed
  report — same numbers, same seal, a different modality.
- *Field ops* — a spoken brief for site managers to play at shift-change.
- *Customer success* — a Friday audio digest of usage and NPS for the
  account team.
            """
        )

    with st.expander("Developer keys & MCP, in depth"):
        st.markdown(
            """
A developer key (`alk_…`) is a bearer credential: it maps every call to your
account, spends **your** credits, and lands results in **your** Vault. Keys
are shown once at creation, SHA-256 hashed at rest, and revocable individually
from Studio.

The same key works three ways:

1. **This App** — paste it in the sidebar, or bind it as a Databricks secret
   (`ALCHEMYLAKE_API_KEY`) so the whole workspace shares one without anyone
   pasting anything — see `app.yaml` in the bundle for the exact steps.
2. **Any MCP agent** (Genie / Agent Bricks, Claude, Cursor) — register
   `https://app.alchemylake.com/api/mcp` as an MCP server with
   `Authorization: Bearer alk_…`; all thirteen tools appear automatically
   (including `upload_source` for bring-your-own files and
   `render_deep_research` for sealed dossiers).
3. **Raw JSON-RPC** — from a notebook, job, or shell, via `requests`/`curl`.
4. **The REST API + CLI** — the same key drives
   `https://app.alchemylake.com/api/public/v1` (OpenAPI published) and the
   `alchemylake` CLI (`npx alchemylake render report --source …`).
            """
        )

    with st.expander("Security, governance & where compute runs"):
        st.markdown(
            """
- **Nothing bypasses governance.** The same credit ledger, provenance seals,
  role checks, and safety screening that protect the web Studio protect every
  call made from this App or any MCP agent.
- **Data residency — connected mode (default, all lanes today):** this App
  runs on Databricks Apps compute under your workspace's SSO, but the actual
  AI rendering happens on the AlchemyLake platform, not on Databricks compute.
  Only the specific rows you bind (and your prompt) are sent off-workspace to
  produce and seal the render — full tables never move, and nothing is ever
  used to train a model.
- **No-egress mode (enterprise / regulated path):** text runs on Databricks
  Foundation Model APIs and imagery on a Model Serving endpoint inside *your*
  workspace, so no prompt or row ever leaves your tenant, and inference is
  billed as your own Databricks compute. This is configured with the Zorost
  team per workspace (needs Foundation Model APIs / Model Serving enabled) —
  email [info@zorost.com](mailto:info@zorost.com) to set it up.
- **Safety:** every prompt is screened before any credit is charged; blocked
  runs are refunded automatically.
            """
        )

    with st.expander("Troubleshooting"):
        st.markdown(
            """
| Symptom | Likely fix |
|---|---|
| "Paste a developer key first" | Forge one in Studio → Developer, then paste it in the sidebar. |
| Connection check fails / 401 | The key was revoked or mistyped — forge a new one. |
| A media render seems stuck | Video/Music can take 1–3 minutes — the spinner is normal; don't refresh. |
| Templates/Report button is disabled | Those lanes require a bound source — load and pick one on the right. |
| The developer key disappeared | Check whether an admin set `ALCHEMYLAKE_API_KEY` as a workspace secret — a configured key always overrides a pasted one, and isn't stored per-browser. |
            """
        )

    st.caption(f"Looking for more? The full, always-current docs live at {DOCS_URL}.")

# --------------------------------------------------------------------------- #
# Tab: About / Install
# --------------------------------------------------------------------------- #

with tab_about:
    st.subheader("What this is")
    st.markdown(
        """
**AlchemyLake** is a governed creative platform: it turns governed data into
governed media, with every generation metered by a credit ledger and sealed to
the exact source rows it used. Databricks turns data *in* (parse, analyze,
chart); AlchemyLake turns it *out* — the activation layer the Lakehouse lacks:

- **Analyst (chat)** — narrative/copy whose every figure is derivable from the bound
  rows, then **verified** against platform-computed facts (score on the seal).
  Follow-ups continue the same conversation — Genie sources included.
- **Deep Research** — a planned multi-step investigation (sub-questions →
  evidence → synthesis) sealed into a PDF dossier + Excel evidence workbook.
- **Report** — an enterprise PDF dossier (KPI band, chart sections, statistical
  appendix, citations, methodology) + an **Excel evidence workbook**.
- **Presentation** — a downloadable **.pptx** with a read-aloud presenter script
  and Q&A prep under every slide; 5–20 slides, real charts from the rows.
- **Templates** — one-click recipes (KPI poster, exec one-pager, board deck,
  audio briefing, boardroom video briefing, data score, social copy, campaign
  pack).
- **Infographic** — designed data posters with the real figures rendered in and
  a branded provenance strip.
- **Video Briefing** — animated data videos in one of six formats: chart
  scenes, narration, motion.
- **Music** — sonified scores in one of six genres (tempo ↔ momentum, mode ↔
  trend) + data-motif WAV.
- **Podcast** — two-host audio briefings in one of five formats, grounded in
  the verified facts, transcript included.

Bind any governed source to any lane; the seal records source · rows · data sha256.
Sources can be the Sample Lakehouse, allowlisted Unity Catalog tables, your own
CSV/Excel uploads, or a bound Genie-space answer.

This Databricks App is a thin, in-workspace client for that platform. It talks
to AlchemyLake's **MCP endpoint**, so it inherits the platform's governance:
credit metering, provenance seals, verification, approval gates, and role checks.

**Two ways to run AlchemyLake with Databricks**

1. **Inside Databricks (this App):** deploy this bundle to your workspace and give
   analysts a governed render surface next to their data — SSO-authenticated,
   no data leaves except the rows you bind.
2. **From any agent (MCP):** register `https://app.alchemylake.com/api/mcp` as an
   external MCP server for Genie / Agent Bricks, Claude, or Cursor. Thirteen tools
   (`list_governed_sources`, `upload_source`, `render_governed_chat`,
   `render_deep_research`, `render_report`, `render_presentation`,
   `render_infographic`, `render_video_briefing`, `render_music`,
   `render_podcast`, `list_recipes`, `run_recipe`, `get_wallet`)
   appear automatically — so a Genie answer can become a sealed board deck,
   dossier, or infographic in one agent turn.
        """
    )

    st.subheader("How to use it")
    st.markdown(
        f"""
1. Paste a developer key in the left sidebar — or [sign up free]({SIGNUP_URL})
   first if you don't have one yet ({WELCOME_GRANT_CREDITS} credits, no card).
2. Open a tab: **Analyst** for narrative, **Report** for a branded PDF,
   **Templates** for a one-click deliverable, or a media lane.
3. On the right, **load governed sources** and pick one to bind — or leave it
   unbound for a free-form prompt.
4. Write your direction on the left and click render. Bound runs derive their
   figures only from the rows you picked; unbound runs are a free prompt.
5. Read the **seal** printed under the result — it names the source, row
   count, and a sha256 of the data, plus a verification score wherever
   numeric claims were checked.
6. **Download it, or save it straight into Databricks** — a workspace folder
   or a Unity Catalog volume — from the buttons under the result.

Everything here is metered the same way as the web Studio, from the same
credit wallet, into the same Vault.
        """
    )

    st.subheader("Why this is a big deal")
    st.markdown(
        """
Most generative tools treat your data as a suggestion — the model *reads*
context and then *writes* whatever numbers feel right. AlchemyLake's core
promise is the opposite: **the model never authors a figure.** Every number in
a bound render is pulled deterministically from the rows you selected,
substituted exactly, cited back to its source, and — for narrative and report
lanes — checked against the platform's own computed facts before it ships.
That's what the **seal** and **verification score** on every result actually
mean: not "an AI probably got this right," but "this exact figure traces back
to this exact row."

Inside Databricks specifically, that closes the gap between the Lakehouse
(where governed data lives) and everything a business actually publishes with
it — decks, board narratives, campaign copy, KPI posters — without anyone
copy-pasting numbers into a slide by hand, and without the numbers drifting
from what the data actually says.
        """
    )

    st.subheader("Where the compute runs")
    st.markdown(
        """
This App's own UI runs on lightweight Databricks Apps compute in your
workspace, under SSO. The AI rendering itself, by default, runs on the
AlchemyLake platform (not on Databricks compute) — only the rows you bind and
your prompt leave the workspace for that specific call, and never for
training. If your workspace has Foundation Model APIs / Model Serving enabled
and no-egress mode configured with the Zorost team, text (and imagery, where
supported) can instead run entirely on your own Databricks compute so nothing
leaves the tenant. See the **Docs** tab → *Security, governance & where
compute runs* for the full breakdown.
        """
    )

    st.subheader("Developer keys — and how to get one easily")
    st.markdown(
        f"""
**Fastest path:** [sign up free]({SIGNUP_URL}) ({WELCOME_GRANT_CREDITS} credits,
no card) → **Studio → Developer · MCP & keys** → *Forge a new key* → paste it
in this App's sidebar. Takes under a minute.

A **developer key** (`alk_…`) is a bearer credential for the AlchemyLake API and
MCP surface. It maps every call to one account: its **credit wallet** pays for the
render, its **Vault** stores the result, and its governed sources are the ones a
render may bind. Keys are forged in **Studio → Developer** (shown once, SHA-256
hashed at rest, revocable individually). Use it three ways:

1. **This App** — paste it in the sidebar (remembered in your browser until you
   clear it), or bind it as a Databricks secret via `ALCHEMYLAKE_API_KEY` in
   `app.yaml` so the whole workspace shares one without anyone pasting anything.
2. **Any MCP agent** (Genie / Agent Bricks, Claude, Cursor) — register the server:
        """
    )
    st.code(
        '{\n'
        '  "mcpServers": {\n'
        '    "alchemylake": {\n'
        '      "url": "https://app.alchemylake.com/api/mcp",\n'
        '      "headers": { "Authorization": "Bearer alk_YOUR_KEY" }\n'
        '    }\n'
        '  }\n'
        '}',
        language="json",
    )
    st.markdown("3. **Raw JSON-RPC** — from a notebook, job, or shell:")
    st.code(
        "curl -s https://app.alchemylake.com/api/mcp \\\n"
        '  -H "Authorization: Bearer alk_YOUR_KEY" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        "  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\","
        "\"params\":{\"name\":\"get_wallet\",\"arguments\":{}}}'",
        language="bash",
    )
    st.subheader("Install (one command)")
    st.code(
        "git clone https://github.com/zorost/alchemylake-databricks\n"
        "cd alchemylake-databricks\n"
        "databricks bundle deploy -t prod\n"
        "databricks bundle run alchemylake_app -t prod",
        language="bash",
    )
    st.caption(f"Full documentation: {DOCS_URL}")


# --------------------------------------------------------------------------- #
# Footer — brand, version, licensing, residency (always visible under the tabs)
# --------------------------------------------------------------------------- #

with st.expander("Where your data goes"):
    st.markdown(_DATA_RESIDENCY_HTML, unsafe_allow_html=True)

st.markdown(
    f'<div class="al-foot">'
    f'<strong style="color:#f3eddf">AlchemyLake</strong> &middot; v{APP_VERSION} '
    f'&middot; Truth, made visible.<br>'
    f'A product of <a href="https://zorost.com">Zorost Intelligence</a> '
    f'&middot; <a href="https://zorost.com">zorost.com</a> '
    f'&middot; <a href="mailto:info@zorost.com">info@zorost.com</a><br>'
    f'Licensing &mdash; the App is proprietary; the open engine is FSL-1.1 (converts to '
    f'Apache-2.0); the SDK &amp; MCP client are Apache-2.0. '
    f'<a href="{DOCS_URL}#licensing">Licensing</a> &middot; '
    f'<a href="https://github.com/zorost/alchemylake-databricks/blob/main/LICENSE">LICENSE</a>.<br>'
    f'Your data stays in your lakehouse &mdash; only the rows you bind are used, and never '
    f'for training. <a href="{DOCS_URL}#residency">Data security &amp; residency &rarr;</a>'
    f'</div>',
    unsafe_allow_html=True,
)
