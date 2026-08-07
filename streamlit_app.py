import csv
import hashlib
import io
import json
from datetime import datetime, timezone

import streamlit as st

from src import storage, summarizer
from src.substack_client import (
    SubstackAuthError,
    cookies_to_header,
    extract_chat_messages,
    fetch_chat_raw,
    fetch_post_content,
    fetch_recent_posts,
)

st.set_page_config(page_title="Trader Joe Digest", page_icon="📈", layout="wide")
st.markdown(
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-title" content="TJ Digest">',
    unsafe_allow_html=True,
)

REQUIRED_SECRETS = ["ANTHROPIC_API_KEY", "SUBSTACK_PUBLICATION_URL", "SUBSTACK_COOKIES_JSON"]


def get_secret(key: str, default=None):
    """st.secrets.get() raises instead of returning a default when no secrets.toml
    exists at all (brand-new setup) -- this makes it behave like a normal dict."""
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def missing_secrets() -> list[str]:
    return [k for k in REQUIRED_SECRETS if not get_secret(k)]


def require_password() -> None:
    configured = get_secret("APP_ACCESS_PASSWORD")
    if not configured:
        return  # no password configured -- skip the gate
    if st.session_state.get("authed"):
        return
    st.title("📈 Trader Joe Digest")
    pw = st.text_input("Password", type="password")
    if st.button("Enter"):
        if pw == configured:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


def render_setup_screen(missing: list[str]) -> None:
    st.title("📈 Trader Joe Digest")
    st.warning("Setup isn't finished yet -- some required secrets are missing.")
    for key in REQUIRED_SECRETS:
        status = "✅" if key not in missing else "❌"
        st.write(f"{status} `{key}`")
    st.info(
        "Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (local) "
        "or paste these into your Streamlit Community Cloud app's **Secrets** panel, "
        "then reload. Full instructions are in the README."
    )
    st.stop()


require_password()
missing = missing_secrets()
if missing:
    render_setup_screen(missing)

storage.init_db()
client = summarizer.get_client(st.secrets["ANTHROPIC_API_KEY"])
PUB_URL = st.secrets["SUBSTACK_PUBLICATION_URL"]
COOKIE_HEADER = cookies_to_header(json.loads(st.secrets["SUBSTACK_COOKIES_JSON"]))

def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


st.title("📈 Trader Joe Digest")
st.caption("Plain-English recaps of posts and chat from your paid subscription.")

tab_posts, tab_chat, tab_setup = st.tabs(["📨 Posts", "💬 Chat & Position Changes", "⚙️ Setup / Status"])

# ---------------------------------------------------------------- Posts tab
with tab_posts:
    col1, col2 = st.columns([3, 1])
    with col1:
        n = st.number_input("How many recent posts to check", min_value=1, max_value=30, value=5)
    with col2:
        st.write("")
        st.write("")
        fetch_clicked = st.button("Fetch & summarize new posts", type="primary")

    if fetch_clicked:
        progress = st.progress(0.0, text="Fetching post list...")
        try:
            recent = fetch_recent_posts(PUB_URL, limit=int(n))
        except Exception as e:
            st.error(f"Couldn't reach Substack: {e}")
            recent = []

        new_count = 0
        for i, meta in enumerate(recent):
            progress.progress((i + 1) / max(len(recent), 1), text=f"Checking: {meta.title}")
            if storage.post_exists(meta.slug):
                continue
            try:
                full = fetch_post_content(PUB_URL, meta.slug, COOKIE_HEADER)
                summary = summarizer.summarize_post(client, full["title"], full["subtitle"], full["text"])
                storage.upsert_post(
                    slug=full["slug"], title=full["title"], subtitle=full["subtitle"],
                    url=full["url"], post_date=full["post_date"], audience=full["audience"],
                    summary=summary,
                )
                new_count += 1
            except SubstackAuthError as e:
                st.error(str(e))
                break
            except Exception as e:
                st.warning(f"Skipped '{meta.title}': {e}")
        progress.empty()
        st.success(f"Done -- {new_count} new post(s) summarized.")

    posts = storage.get_all_posts()
    if not posts:
        st.info("No posts summarized yet. Click the button above to fetch some.")
    for post in posts:
        badge = "🔒 Paid post" if post["audience"] == "only_paid" else "🌐 Public post"
        with st.expander(f"{post['title']}  —  {post['post_date'][:10] if post['post_date'] else ''}"):
            st.caption(badge)
            st.markdown(post["summary"])
            st.markdown(f"[Read the original post]({post['url']})")

# ----------------------------------------------------------------- Chat tab
with tab_chat:
    st.subheader("Get chat messages in")
    mode = st.radio(
        "How do you want to bring chat messages in?",
        ["Paste in (reliable)", "Automatic fetch (experimental)"],
        horizontal=True,
    )

    if mode == "Paste in (reliable)":
        st.caption(
            "Copy/paste chat text from the Substack app -- one message per line works fine. "
            "Include the author's name if you can, e.g. `Joe: trimmed my NVDA position today`."
        )
        pasted = st.text_area("Paste chat messages here", height=200)
        if st.button("Analyze pasted chat"):
            lines = [l.strip() for l in pasted.splitlines() if l.strip()]
            raw_messages = []
            for line in lines:
                if ":" in line:
                    author, body = line.split(":", 1)
                else:
                    author, body = "Unknown", line
                raw_messages.append({
                    "author": author.strip(),
                    "body": body.strip(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            if raw_messages:
                try:
                    with st.spinner(f"Analyzing {len(raw_messages)} message(s)..."):
                        analyzed = summarizer.analyze_chat_batch(client, raw_messages)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                    analyzed = []
                for m in analyzed:
                    msg_id = "manual-" + stable_id(m["author"], m["body"], m["created_at"])
                    storage.upsert_chat_message(
                        msg_id=msg_id, source="manual", author=m["author"],
                        created_at=m["created_at"], body=m["body"],
                        plain_english=m["plain_english"], is_position_change=m["is_position_change"],
                    )
                if analyzed:
                    st.success(f"Analyzed {len(analyzed)} message(s).")
            else:
                st.warning("Nothing to analyze -- paste some text first.")

    else:
        endpoint = get_secret("SUBSTACK_CHAT_ENDPOINT")
        st.caption(
            "Uses a chat API URL *you* capture from your own browser's Network tab, since "
            "Substack doesn't publish or document a Chat API. See README 'Finding your chat "
            "endpoint'. If this doesn't return usable data, fall back to Paste in above."
        )
        if not endpoint:
            st.warning("Set `SUBSTACK_CHAT_ENDPOINT` in your secrets to use this mode.")
        elif st.button("Fetch recent chat (experimental)"):
            try:
                raw = fetch_chat_raw(endpoint, COOKIE_HEADER)
                messages = extract_chat_messages(raw)
            except Exception as e:
                st.error(f"Fetch failed: {e}")
                messages = []
                raw = None

            if not messages and raw is not None:
                st.warning("Got a response but couldn't find messages in the expected shape. Raw response:")
                st.json(raw)
            elif messages:
                try:
                    with st.spinner(f"Analyzing {len(messages)} message(s)..."):
                        analyzed = summarizer.analyze_chat_batch(client, messages)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                    analyzed = []
                for m in analyzed:
                    msg_id = "auto-" + stable_id(m["author"], m["body"], m["created_at"])
                    if storage.chat_message_exists(msg_id):
                        continue
                    storage.upsert_chat_message(
                        msg_id=msg_id, source="auto", author=m["author"],
                        created_at=m["created_at"], body=m["body"],
                        plain_english=m["plain_english"], is_position_change=m["is_position_change"],
                    )
                if analyzed:
                    st.success(f"Analyzed {len(analyzed)} message(s).")

    st.divider()
    st.subheader("🚩 Key position / investment changes")
    changes = storage.get_position_changes()
    if not changes:
        st.info("None flagged yet.")
    for c in changes:
        st.markdown(f"**{c['created_at'][:16] if c['created_at'] else ''} — {c['author']}**")
        st.markdown(f"> {c['plain_english']}")
        with st.expander("Original message"):
            st.write(c["body"])

    st.divider()
    with st.expander("Full simplified chat log"):
        all_msgs = storage.get_all_chat_messages()
        if not all_msgs:
            st.write("Nothing analyzed yet.")
        for m in all_msgs:
            flag = "🚩 " if m["is_position_change"] else ""
            st.markdown(f"{flag}**{m['author']}**: {m['plain_english']}")

# ---------------------------------------------------------------- Setup tab
with tab_setup:
    st.subheader("Secret status")
    all_keys = REQUIRED_SECRETS + ["SUBSTACK_CHAT_ENDPOINT", "APP_ACCESS_PASSWORD"]
    for key in all_keys:
        present = bool(get_secret(key))
        st.write(f"{'✅' if present else '⬜'} `{key}`" + ("" if key in REQUIRED_SECRETS else " (optional)"))

    st.subheader("Export your data")
    st.caption("Streamlit Community Cloud's disk is wiped on redeploy -- export periodically if you care about history.")

    def _rows_to_csv(rows, columns) -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        for r in rows:
            writer.writerow([r[c] for c in columns])
        return buf.getvalue().encode("utf-8")

    posts_rows = storage.get_all_posts()
    if posts_rows:
        st.download_button(
            "Download posts.csv",
            _rows_to_csv(posts_rows, ["slug", "title", "post_date", "audience", "summary", "url"]),
            file_name="posts.csv",
        )
    chat_rows = storage.get_all_chat_messages()
    if chat_rows:
        st.download_button(
            "Download chat.csv",
            _rows_to_csv(chat_rows, ["created_at", "author", "body", "plain_english", "is_position_change", "source"]),
            file_name="chat.csv",
        )

    st.subheader("Full setup guide")
    st.caption("See README.md in this project's repo for step-by-step setup instructions.")
