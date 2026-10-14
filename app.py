"""Live demo: ask a question about the VCMI Claims Code of Practice, pick a date on the timeline,
and get the answer from the version that was in force on that date.

Run locally:   streamlit run app.py      (set GROQ_API_KEY first; without it, the app shows retrieval only)
"""
import hashlib, json, os, re, sys
from datetime import date
from html import escape
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "rag"))
import asof  # noqa: E402

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
SESSION_LIMIT = 25      # new (uncached) model calls per visitor session
DAILY_LIMIT = 800       # new model calls per day for the whole app (Groq free tier: 1,000 requests/day)
EXAMPLES = {  # button label: question
    "CCP-label deadline": "What is the deadline after which only CCP-labelled credits may be used?",
    "Silver threshold": "What is the threshold for the Silver claim?",
    "Are claims issued?": "Can companies obtain a VCMI claim?",
    "Tier names history": "How did the claim tier names change?",
}

st.set_page_config(page_title="VCMI Code Timeline", page_icon="🕰️", layout="centered")


# ------------------------------------------------------------------ data and model
@st.cache_resource
def data(today):
    return asof.load(today)


def api_key():
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:  # no secrets file
        pass
    return os.environ.get("GROQ_API_KEY")


@st.cache_resource
def usage():
    """Shared across all visitors: new model calls per day."""
    return {"day": date.today(), "calls": 0}


def parse(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("The model did not return JSON.")
    obj = json.loads(m.group(0))
    if isinstance(obj.get("declined"), str):
        obj["declined"] = obj["declined"].strip().lower() == "true"
    return obj


def json_instruction():
    props = asof.R.ANSWER_TOOL["input_schema"]["properties"]
    return "\n\nRespond with ONLY a JSON object with exactly these keys:\n" + "\n".join(
        f'  "{k}": {v["type"]}' + (f' (one of {v["enum"]})' if "enum" in v else "") + f' - {v.get("description", "")}'
        for k, v in props.items())


@st.cache_resource
def answers():
    """Answers shared by all visitors, keyed by the exact prompt. The prompt depends on the version, not the
    exact date, so moving the slider within one version's period reuses the answer and uses no API quota."""
    return {}


def ask_model(system, user, model):
    import openai
    client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key(), max_retries=2)
    resp = client.chat.completions.create(
        model=model, temperature=0, max_tokens=2000,
        messages=[{"role": "system", "content": system + json_instruction()}, {"role": "user", "content": user}])
    return parse(resp.choices[0].message.content)


# ------------------------------------------------------------------ look ("Archive" design)
PAPER, INK, MUTED, LINE, ACCENT = "#F6F4EE", "#1C1B19", "#5E5A52", "#D9D4C7", "#1F5C46"
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Work+Sans:wght@400;500;600&display=swap');
html, body, .stApp, [data-testid="stAppViewContainer"] {{background:{PAPER}; color:{INK}; font-family:'Work Sans', sans-serif}}
.stApp p, .stApp label, .stApp input, .stApp button {{font-family:'Work Sans', sans-serif}}
header[data-testid="stHeader"] {{background:transparent}}
.block-container {{max-width:1040px; padding-top:3.5rem; padding-bottom:3rem}}
.serif {{font-family:'Newsreader', serif}}
.kicker {{font-size:13px; letter-spacing:.12em; text-transform:uppercase; color:{MUTED}}}
.hero h1 {{font-family:'Newsreader', serif; font-weight:500; font-size:52px; line-height:1.05; letter-spacing:-.01em; margin:14px 0 14px; padding:0; color:{INK}}}
.stApp .hero p {{font-size:17px; line-height:1.55; color:#46423B; max-width:640px; margin:0}}
.hero {{border-bottom:1px solid {LINE}; padding-bottom:28px; margin-bottom:28px}}
.qlabel {{font-size:14px; font-weight:600; margin:0 0 6px}}
/* question box */
.st-key-q input {{height:52px; font-size:17px; background:#fff; color:{INK}; border-radius:4px}}
.st-key-q div[data-baseweb="input"] {{height:52px; border:1px solid #BDB6A6; border-radius:4px; background:#fff}}
/* date field: compact, serif (works for both the older and the newer Streamlit date widget) */
.st-key-dpick {{max-width:180px}}
.st-key-dpick [data-testid="stDateInputField"], .st-key-dpick div[data-baseweb="input"] {{background:#fff; border-color:#BDB6A6}}
.st-key-dpick [data-testid="stDateInputField"] *, .st-key-dpick input {{font-family:'Newsreader', serif; font-size:18px; color:{INK}}}
.stApp .dlabel {{font-size:13px; font-weight:600; margin:0 0 8px}}
.stApp .dlabel span {{font-weight:400; color:{MUTED}}}
/* Ask button */
.st-key-ask button {{height:52px; width:100%; background:{ACCENT}; color:#fff; border:none; border-radius:4px; font-weight:600; font-size:16px}}
.st-key-ask button:hover {{background:#174A38; color:#fff}}
/* example chips */
[class*="st-key-chip_"] button {{min-height:44px; background:transparent; border:1px solid #BDB6A6; border-radius:999px; color:{INK}; font-size:14px; padding:0 16px}}
[class*="st-key-chip_"] button:hover {{border-color:{ACCENT}; color:{ACCENT}}}
.try {{font-size:14px; color:{MUTED}; padding-top:11px}}
/* answer card */
.card {{background:#fff; border:1px solid {LINE}; border-radius:6px; padding:36px 40px; margin:28px 0 8px}}
.meta {{font-size:14px; color:{MUTED}; display:flex; gap:12px; flex-wrap:wrap; align-items:baseline}}
.meta b {{color:{ACCENT}; font-weight:600}}
.meta.declined b {{color:#8A4B12}}
.stApp .answer {{font-family:'Newsreader', serif; font-size:26px; line-height:1.38; margin:20px 0 0; color:{INK}}}
.quote {{border-top:1px solid #E6E1D5; margin-top:22px; padding-top:18px}}
.stApp .quote p {{font-family:'Newsreader', serif; font-style:italic; font-size:17px; line-height:1.6; color:#46423B; margin:0}}
.quote .src {{font-size:13px; color:{MUTED}; margin-top:8px}}
.quote .src a, .card a {{color:{ACCENT}}}
.note {{font-size:15px; color:#46423B; border-left:2px solid {ACCENT}; padding:4px 0 4px 12px; margin:20px 0 0}}
/* timeline */
.ruler {{position:relative; height:36px; margin:10px 10px 0}}
.mk {{position:absolute; top:0; display:flex; flex-direction:column; gap:1px; font-size:11.5px; line-height:1.2; padding-left:6px; border-left:1px solid #BDB6A6; white-space:nowrap}}
.mk span:first-child {{font-weight:600}} .mk span:last-child {{color:{MUTED}}}
.mk.right {{padding-left:0; padding-right:6px; border-left:none; border-right:1px solid #BDB6A6; text-align:right; transform:translateX(-100%)}}
.mk.on {{border-color:{ACCENT}; border-width:2px; color:{ACCENT}}} .mk.on span:last-child {{color:{ACCENT}}}
.years {{position:relative; height:16px; font-size:11px; color:{MUTED}; margin:0 10px}}
.years span {{position:absolute}}
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{display:none}}
.inforce {{font-size:13px; color:{MUTED}; padding-top:10px; line-height:1.5}}
.inforce a {{color:{ACCENT}}}
.st-key-datebox {{border:1px solid {LINE}; border-radius:6px; background:rgba(255,255,255,.55); padding:14px 18px 8px; margin-top:6px; gap:.35rem}}
.foot {{font-size:13px; line-height:1.6; color:{MUTED}; border-top:1px solid {LINE}; padding-top:20px; margin-top:32px}}
@media (max-width: 640px) {{
  .stApp .hero h1 {{font-size:38px}} .card {{padding:24px 20px}} .stApp .answer {{font-size:22px}}
  .mk:not(.on) span {{visibility:hidden}} .mk {{font-size:12px}}
}}
.st-key-q input {{min-height:50px}}
[data-testid="stExpander"] details {{background:transparent; border:1px solid {LINE}; border-radius:6px}}
</style>"""


def pct(x, start, span):
    return 100 * (x - start).days / span


def ruler_html(versions, start, end, selected):
    span = (end - start).days or 1
    active = asof.in_force(selected, versions)
    out = []
    for v in versions:
        left = pct(v["published"], start, span)
        cls = "mk" + (" on" if active and v["version"] == active["version"] else "") + (" right" if left > 90 else "")
        style = f"left:{left:.2f}%" + (";border-left:none;padding-left:0" if left == 0 and "on" not in cls else "")
        out.append(f'<div class="{cls}" style="{style}"><span>v{escape(v["version"])}</span>'
                   f'<span>{v["published"]:%b %Y}</span></div>')
    years = "".join(f'<span style="left:{pct(date(y, 1, 1), start, span):.2f}%">{y}</span>'
                    for y in range(start.year + 1, end.year + 1))
    return (f'<div class="ruler">{"".join(out)}</div>', f'<div class="years">{years}<span style="right:0">Today</span></div>')


def on_date_picked():
    """Date field (calendar or typed DD/MM/YYYY) -> slider."""
    if st.session_state.dpick:
        st.session_state.d = st.session_state.dpick


def on_slider():
    """Slider -> date field."""
    st.session_state.dpick = st.session_state.d


def answer_html(result, cmap, p, versions):
    vmap = {v["version"]: v for v in versions}
    ver = str(result.get("version_relied_on", "none")).lstrip("v")
    declined = bool(result.get("declined"))
    if declined or ver not in vmap:
        meta = '<div class="meta declined"><b>Not found in the documents</b></div>' if declined else \
               '<div class="meta"><b>Answer</b></div>'
    else:
        v = vmap[ver]
        span = (f"in force {v['published']:%d %B %Y} to {v['superseded_on']:%d %B %Y}" if v.get("superseded_on")
                else f"in force since {v['published']:%d %B %Y}, current version")
        meta = f'<div class="meta"><b>Version {escape(ver)}</b><span>{span}</span></div>'
    quotes = []
    for cid in result.get("citations", []):
        c = cmap.get(cid)
        if not c:
            continue
        text = c["text"][:360].rsplit(" ", 1)[0] + ("…" if len(c["text"]) > 360 else "")
        src = vmap.get(c["version"], {}).get("source")
        link = f' · <a href="{escape(src)}" target="_blank">open source</a>' if src else ""
        quotes.append(f'<div class="quote"><p>“{escape(text)}”</p>'
                      f'<div class="src">Claims Code v{escape(c["version"])}, page {c["page"]}{link}</div></div>')
    note = f'<div class="note">{escape(p["reason"])}</div>' if p["override"] else ""
    return f'<div class="card">{meta}<p class="answer">{escape(result.get("answer", ""))}</p>{note}{"".join(quotes)}</div>'


# ------------------------------------------------------------------ page
today = date.today()
chunks, versions, bm25 = data(today)
start = versions[0]["published"]
if "d" not in st.session_state:
    st.session_state.d = today
    st.session_state.dpick = today
if "calls" not in st.session_state:
    st.session_state.calls = 0

st.markdown(CSS, unsafe_allow_html=True)
st.markdown(f"""<div class="hero"><div class="kicker">VCMI Claims Code of Practice · {len(versions)} versions, {start:%B %Y} to today</div>
<h1>Ask the Code as it stood on any date.</h1>
<p>Type a question and pick a date: type it, or drag the slider. The answer is drawn only from the version in force on that day,
with the page it came from.</p></div>""", unsafe_allow_html=True)

st.markdown('<div class="qlabel">Your question</div>', unsafe_allow_html=True)
c1, c2 = st.columns([6, 1], vertical_alignment="center")
question = c1.text_input("Your question", key="q", label_visibility="collapsed",
                         placeholder="e.g. What is the threshold for the Gold claim?")
c2.button("Ask", key="ask")

chip_cols = st.columns([0.5, 1.6, 1.4, 1.5, 1.5, 2])
chip_cols[0].markdown('<div class="try">Try</div>', unsafe_allow_html=True)
for i, (c, (label, ex)) in enumerate(zip(chip_cols[1:], EXAMPLES.items())):
    c.button(label, key=f"chip_{i}", help=ex, on_click=st.session_state.__setitem__, args=("q", ex))

# date: type it or drag the slider (directly under the question)
d = st.session_state.d
active = asof.in_force(d, versions)
with st.container(key="datebox"):
    st.markdown('<p class="dlabel">Date <span>· pick or type one (DD/MM/YYYY), or drag the slider</span></p>',
                unsafe_allow_html=True)
    dc1, dc2 = st.columns([1, 4], vertical_alignment="center")
    dc1.date_input("Date", key="dpick", min_value=start, max_value=today, format="DD/MM/YYYY",
                   on_change=on_date_picked, label_visibility="collapsed")
    if active:
        until = f"until {active['superseded_on']:%d %b %Y}" if active.get("superseded_on") else "still current"
        dc2.markdown(f'<div class="inforce">Version in force: <b>v{escape(active["version"])}</b> '
                     f'(published {active["published"]:%d %b %Y}, {until}) · '
                     f'<a href="{escape(active["source"] or "#")}" target="_blank">source</a></div>', unsafe_allow_html=True)
    ruler, years = ruler_html(versions, start, today, d)
    st.markdown(ruler, unsafe_allow_html=True)
    st.slider("Date slider", min_value=start, max_value=today, key="d", format="D MMM YYYY",
              label_visibility="collapsed", on_change=on_slider)
    st.markdown(years, unsafe_allow_html=True)

p = asof.plan(question, d, versions) if question.strip() else None
answer_box = st.container()

# answer
with answer_box:
    if p:
        passages = asof.retrieve(question, p, chunks, bm25)
        system = asof.system_prompt(today)
        user = asof.user_prompt(question, passages, asof.notes(d, p, versions))
        result, error = None, None
        if p["mode"] == "missing":
            result = {"answer": p["reason"] + " I can't answer it from the documents.", "citations": [],
                      "version_relied_on": "none", "declined": True}
        elif not api_key():
            error = "Demo mode: no API key is set, so only the retrieved passages are shown."
        else:
            k = hashlib.sha256(json.dumps([system, user, MODEL]).encode()).hexdigest()
            cache, u = answers(), usage()
            if u["day"] != today:
                u.update(day=today, calls=0)
            if k in cache:
                result = cache[k]
            elif st.session_state.calls >= SESSION_LIMIT or u["calls"] >= DAILY_LIMIT:
                error = "The free API quota for this demo is used up for now. Please try again later."
            else:
                with st.spinner(f"Reading {len(passages)} passages…"):
                    try:
                        result = cache[k] = ask_model(system, user, MODEL)
                    except Exception as e:  # rate limit, network, bad JSON
                        msg = str(e)
                        error = ("The free API limit was reached; wait a minute and try again."
                                 if "429" in msg or "rate" in msg.lower() else f"The model call failed: {msg[:200]}")
                    st.session_state.calls += 1
                    u["calls"] += 1

        cmap = {c["chunk_id"]: c for c in passages}
        if result:
            st.markdown(answer_html(result, cmap, p, versions), unsafe_allow_html=True)
        if error:
            st.warning(error)
        if passages:
            with st.expander(f"All {len(passages)} passages the model was given"):
                st.caption(p["reason"])
                for c in passages:
                    st.markdown(f"**v{c['version']} · page {c['page']}** · `{c['chunk_id']}`")
                    st.write(c["text"])

st.markdown('<div class="foot">Independent demo, not affiliated with VCMI. Answers can be wrong: check the cited page. '
            f'Model: {escape(MODEL)} via Groq; retrieval: BM25 with date-based version routing. '
            'On 66 test questions: 73% correct, against 42% for plain RAG and 12% with no documents.</div>',
            unsafe_allow_html=True)
