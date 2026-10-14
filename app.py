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


# ------------------------------------------------------------------ look (palette and type inspired by sotoraglobal.com)
# deep teal, cream, warm off-white, orange accent; Open Sans throughout
PAPER, CREAM, TEAL, INK, MUTED, LINE = "#FFFFF2", "#FFF6D5", "#012626", "#012626", "#4D6464", "#E4DDC0"
ORANGE, ORANGE_DARK = "#FF8749", "#B4501C"   # bright orange on teal / large marks; darker orange for small text on light
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&display=swap');
html, body, .stApp, [data-testid="stAppViewContainer"] {{background:{PAPER}; color:{INK}; font-family:'Open Sans', sans-serif}}
.stApp p, .stApp label, .stApp input, .stApp button {{font-family:'Open Sans', sans-serif}}
header[data-testid="stHeader"] {{background:{TEAL}}}
header[data-testid="stHeader"] * {{color:{CREAM}}}
.block-container {{max-width:1040px; padding-top:0; padding-bottom:3rem}}
/* hero: full-width deep-teal band */
.hero {{background:{TEAL}; color:{CREAM}; margin:0 calc(50% - 50vw) 36px; padding:72px calc(50vw - 50%) 56px}}
.kicker {{font-size:13px; letter-spacing:.12em; text-transform:uppercase; color:{ORANGE}; font-weight:600}}
.stApp .hero h1 {{font-family:'Open Sans', sans-serif; font-weight:300; font-size:46px; line-height:1.15; margin:16px 0 18px; padding:0; color:{CREAM}}}
.stApp .hero p {{font-size:17px; font-weight:300; line-height:1.6; color:{CREAM}; max-width:660px; margin:0}}
.qlabel {{font-size:14px; font-weight:600; margin:0 0 6px; color:{INK}}}
/* question box */
.st-key-q input {{height:52px; font-size:17px; background:#fff; color:{INK}; border-radius:4px}}
.st-key-q div[data-baseweb="input"] {{height:52px; border:1px solid #C9C2A6; border-radius:4px; background:#fff}}
.st-key-q input {{min-height:50px}}
/* date field */
.st-key-dpick {{max-width:180px}}
.st-key-dpick [data-testid="stDateInputField"], .st-key-dpick div[data-baseweb="input"] {{background:#fff; border-color:#C9C2A6}}
.st-key-dpick [data-testid="stDateInputField"] *, .st-key-dpick input {{font-family:'Open Sans', sans-serif; font-size:17px; color:{INK}}}
.stApp .dlabel {{font-size:13px; font-weight:600; margin:0 0 10px; line-height:1.4; color:{INK}}}
.stApp .dlabel span {{font-weight:400; color:{MUTED}}}
/* Ask button: solid orange, teal text */
.st-key-ask button {{height:52px; width:100%; background:{ORANGE}; color:{TEAL}; border:1px solid {ORANGE}; border-radius:4px; font-weight:600; font-size:16px}}
.st-key-ask button:hover {{background:#FF9A66; border-color:#FF9A66; color:{TEAL}}}
/* example chips: outlined, like the site's buttons */
[class*="st-key-chip_"] button {{min-height:44px; background:transparent; border:1px solid {TEAL}; border-radius:4px; color:{TEAL}; font-size:14px; padding:0 16px}}
[class*="st-key-chip_"] button p {{white-space:nowrap}}
[class*="st-key-chip_"] button:hover {{border-color:{ORANGE_DARK}; color:{ORANGE_DARK}}}
.try {{font-size:14px; color:{MUTED}; padding-top:11px}}
/* answer card */
.card {{background:#fff; border:1px solid {LINE}; border-radius:6px; padding:36px 40px; margin:28px 0 8px}}
.meta {{font-size:14px; color:{MUTED}; display:flex; gap:12px; flex-wrap:wrap; align-items:baseline}}
.meta b {{color:{ORANGE_DARK}; font-weight:600}}
.meta.declined b {{color:#8A3A12}}
.stApp .answer {{font-family:'Open Sans', sans-serif; font-weight:300; font-size:25px; line-height:1.45; margin:18px 0 0; color:{INK}}}
.quote {{background:{CREAM}; border-radius:4px; margin-top:20px; padding:18px 22px}}
.stApp .quote p {{font-style:italic; font-weight:400; font-size:15.5px; line-height:1.65; color:#2A4242; margin:0}}
.quote .src {{font-size:13px; color:{MUTED}; margin-top:8px}}
.quote .src a, .card a {{color:{ORANGE_DARK}}}
.note {{font-size:15px; color:#2A4242; border-left:3px solid {ORANGE}; padding:4px 0 4px 12px; margin:20px 0 0}}
/* date box and timeline */
.st-key-datebox {{border:1px solid {LINE}; border-radius:6px; background:{CREAM}; padding:16px 18px 8px; margin-top:6px; gap:.6rem}}
.ruler {{position:relative; height:34px; margin:6px 0 0}}
.mk {{position:absolute; top:0; display:flex; flex-direction:column; gap:1px; font-size:11.5px; line-height:1.2; padding-left:6px; border-left:1px solid #B9B297; white-space:nowrap; color:{INK}}}
.mk span:first-child {{font-weight:600}} .mk span:last-child {{color:{MUTED}}}
.mk.right {{padding-left:0; padding-right:6px; border-left:none; border-right:1px solid #B9B297; text-align:right; transform:translateX(-100%)}}
.mk.on {{border-color:{ORANGE}; border-width:3px; color:{INK}}} .mk.on span:last-child {{color:{ORANGE_DARK}; font-weight:600}}
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBar"], [data-testid^="stSliderTickBar"] {{display:none}}
.inforce {{font-size:13px; color:{MUTED}; padding:0; margin:0; line-height:1.5}}
.inforce b {{color:{INK}}}
.inforce a {{color:{ORANGE_DARK}}}
[data-testid="stMarkdownContainer"]:has(> .inforce), [data-testid="stMarkdownContainer"]:has(> .ruler) {{margin-bottom:0 !important}}
.st-key-datebox [data-testid="stSlider"] {{margin-top:-10px}}
/* footer: teal band */
.foot {{background:{TEAL}; color:{CREAM}; font-size:13px; line-height:1.6; margin:40px calc(50% - 50vw) -3rem; padding:28px calc(50vw - 50%)}}
[data-testid="stExpander"] details {{background:transparent; border:1px solid {LINE}; border-radius:6px}}
@media (max-width: 640px) {{
  .stApp .hero h1 {{font-size:32px}} .hero {{padding-top:56px}} .card {{padding:24px 20px}} .stApp .answer {{font-size:21px}}
  .mk:not(.on) span {{visibility:hidden}} .mk {{font-size:12px}}
}}
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

chip_cols = st.columns([0.4, 1.7, 1.6, 1.7, 1.8, 0.8])
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
