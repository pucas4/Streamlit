# 📈 Trader Joe Digest

A personal Streamlit app that turns your paid Substack subscription (posts + chat)
into plain-English summaries, and flags whenever a chat message looks like a real
position/investment change.

This is for **your own personal use** of content you already pay for. It logs in
as *you*, using *your* session cookie — it doesn't bypass any paywall, and it
doesn't republish anything publicly. Be aware that automated access like this
sits outside what most newsletter platforms officially support, so treat your
cookie like a password and don't share the deployed app link publicly.

## What you need to give it

| # | What | Where to get it |
|---|------|------------------|
| 1 | An Anthropic API key | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) — pay-as-you-go, summarizing a post costs well under a cent, chat analysis is similar |
| 2 | The Substack's URL | e.g. `https://example.substack.com` |
| 3 | Your logged-in session cookies | exported from your browser, see below |
| 4 | (Optional) A chat endpoint URL | only if you want automatic chat fetching instead of pasting — see below |
| 5 | A password for the app itself | anything you pick — stops randos from reading your paid content if they find the URL |

## Programs to install (one-time)

- **A free [GitHub](https://github.com) account** if you don't already have one (you're looking at this from one, so you're set).
- **A free [Streamlit Community Cloud](https://streamlit.io/cloud) account**, signed in with GitHub — this is what turns the code into a live web app you can open on your phone. No local installs needed for this path.
- *(Only if you want to run/test it on your own computer first)* [Python 3.11+](https://www.python.org/downloads/) and `pip`.
- A desktop browser (Chrome, Firefox, Edge, or Safari) to grab your session cookie — see below.

## Step-by-step setup

### 1. Get your Substack session cookies

Substack doesn't offer an official way to fetch your paid content programmatically,
so this app authenticates the same way your browser does: with your session cookie.

1. Log into Substack in a desktop browser, on the publication you're subscribed to.
2. Install the **Cookie Editor** extension (by Hot Cleaner; Chrome/Firefox/Edge).
3. With the Substack tab active, open the extension. It lists all cookies for
   substack.com. Expand `substack.sid` and `substack.lli` one at a time (click the
   arrow next to each) and use each one's **Copy** button — that copies a line like:
   ```
   substack.sid=abc123...;Domain=substack.com;Path=/;Expires=...;SameSite=None;Secure
   ```
4. Paste both copied lines together, one per line, as the `SUBSTACK_COOKIES` secret
   (see step 3 below) — you don't need to reformat them into JSON, just paste each
   line as-is.

These are session tokens for your account — treat them like a password. Don't paste
them anywhere except directly into Streamlit's Secrets panel or your local
`secrets.toml`.

Cookies expire — if the app starts saying paid content "came back nearly empty,"
repeat this to get a fresh cookie.

### 2. (Optional) Find your chat endpoint, for automatic chat fetching

Substack Chat has **no documented API**, official or unofficial — this app can't
ship a hardcoded chat endpoint because there genuinely isn't a stable, public one to
target. Automatic chat fetching is opt-in and experimental. The reliable default is
the **"Paste in"** tab: copy chat messages out of the Substack app and paste them in
for analysis — no reverse engineering required, and it never breaks.

If you want to try automatic fetching anyway:

1. Open the chat section of the Substack app in a desktop browser.
2. Open DevTools (right-click → Inspect) → **Network** tab → filter to `Fetch/XHR`.
3. Scroll the chat feed so it loads more messages, and watch for a request that
   returns a JSON list of messages.
4. Right-click that request → **Copy → Copy URL**. That's your `SUBSTACK_CHAT_ENDPOINT`.
5. This is inherently fragile — Substack can change it at any time with no notice.
   When it breaks, just go back to pasting chat in.

### 3. Configure secrets

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
SUBSTACK_PUBLICATION_URL = "https://example.substack.com"
SUBSTACK_COOKIES = '''
substack.sid=...;Domain=substack.com;Path=/;Expires=...;SameSite=None;Secure
substack.lli=...;Domain=substack.com;Path=/;Expires=...;SameSite=None;Secure
'''
SUBSTACK_CHAT_ENDPOINT = ""   # optional, see step 2
APP_ACCESS_PASSWORD = "pick-something"
```

**Never commit `.streamlit/secrets.toml`** — it's already in `.gitignore`.

### 4. Run it

**Locally**, to test:
```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

**On your phone**, via Streamlit Community Cloud:
1. Push this repo to GitHub (already done if you're reading this from your repo).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, click **New app**, point it at this repo and `streamlit_app.py`.
3. In the app's **Settings → Secrets**, paste the same contents as your `secrets.toml`.
4. Deploy. You'll get a URL like `https://your-app.streamlit.app`.
5. On your phone, open that URL in Safari/Chrome, then use **Share → Add to Home Screen**
   (iOS) or the browser menu's **Add to Home screen** (Android). It'll sit on your
   home screen and open full-screen like a normal app.

## Notes & limitations

- **Storage is ephemeral on Streamlit Community Cloud** — the SQLite database
  resets whenever the app redeploys or sleeps from inactivity for a long stretch.
  Use the **Setup tab's export buttons** to download `posts.csv`/`chat.csv` if you
  want to keep history.
- **Cost**: post summaries use Claude Sonnet (higher quality, still fractions of a
  cent each); chat analysis uses Claude Haiku (cheaper, for higher volume). You're
  billed by Anthropic directly based on your API key's usage.
- **This app is for you alone.** The password gate keeps casual visitors out, but
  don't share the deployed link — it's serving paid content you're not licensed to
  redistribute.
