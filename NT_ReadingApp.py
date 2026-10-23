import streamlit as st
import pandas as pd
import json
import os
import datetime
import urllib.request
import urllib.parse
import re
import bcrypt
import time
import threading
from streamlit_gsheets import GSheetsConnection

# --- CONFIG & SETUP ---
st.set_page_config(page_title="NT Reading Pro", layout="wide", initial_sidebar_state="collapsed")

BACKUP_DIR = r"E:\Bible_Reading_App\NewTestamentAPP\BibleFilesNT" if os.name == 'nt' else "My_Bible_Notes"
os.makedirs(BACKUP_DIR, exist_ok=True)
BIBLE_FILES_DIR = r"E:\Bible_Reading_App\NewTestamentAPP\BibleFilesNT" if os.name == 'nt' else "BibleFilesNT"

CHAPTER_COUNTS = {
    'Matthew': 28, 'Mark': 16, 'Luke': 24, 'John': 21, 'Acts': 28, 'Romans': 16, 
    '1 Corinthians': 16, '2 Corinthians': 13, 'Galatians': 6, 'Ephesians': 6, 
    'Philippians': 4, 'Colossians': 4, '1 Thessalonians': 5, '2 Thessalonians': 3, 
    '1 Timothy': 6, '2 Timothy': 4, 'Titus': 3, 'Philemon': 1, 'Hebrews': 13, 
    'James': 5, '1 Peter': 5, '2 Peter': 3, '1 John': 5, '2 John': 1, '3 John': 1, 
    'Jude': 1, 'Revelation': 22
}
BIBLE_BOOKS = list(CHAPTER_COUNTS.keys())

BOOK_COLORS = {
    'Matthew': '#FFD700', 'Mark': '#FF8C00', 'Luke': '#00CED1', 'John': '#1E90FF',
    'Acts': '#32CD32', 'Romans': '#FF69B4', '1 Corinthians': '#BA55D3', '2 Corinthians': '#9370DB',
    'Galatians': '#FF6347', 'Ephesians': '#20B2AA', 'Philippians': '#F08080', 'Colossians': '#8FBC8F',
    '1 Thessalonians': '#DDA0DD', '2 Thessalonians': '#EE82EE', '1 Timothy': '#87CEFA', '2 Timothy': '#B0C4DE',
    'Titus': '#F4A460', 'Philemon': '#CD853F', 'Hebrews': '#DAA520', 'James': '#BDB76B',
    '1 Peter': '#98FB98', '2 Peter': '#00FA9A', '1 John': '#7FFFD4', '2 John': '#AFEEEE',
    '3 John': '#E0FFFF', 'Jude': '#FFE4B5', 'Revelation': '#FF4500'
}

# --- GOOGLE SHEETS CONNECTION & SMART CACHING ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=600, show_spinner=False)
def get_sheet(sheet_name, default_cols):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        if df.empty or df.columns[0] == 0:  
            return pd.DataFrame(columns=default_cols)
        return df
    except Exception:
        return pd.DataFrame(columns=default_cols)

def update_sheet(sheet_name, df, retries=3):
    """Network-resilient synchronous update function (used for critical Admin/Login updates)."""
    for attempt in range(retries):
        try:
            conn.update(worksheet=sheet_name, data=df)
            get_sheet.clear()
            return True
        except Exception:
            if attempt < retries - 1: time.sleep(2)
            else:
                st.error("Network Timeout. Please check your internet connection.")
                return False

# --- AUTH & NAVIGATION STATE ---
for k in ["logged_in", "username", "role", "full_name"]:
    if k not in st.session_state: st.session_state[k] = None
if "progress" not in st.session_state: st.session_state["progress"] = set()
if "active_tab" not in st.session_state: st.session_state["active_tab"] = "📊 READING PLAN"

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Malayalam:wght@400;700&display=swap');
        * { font-family: 'Noto Sans Malayalam', sans-serif; }
        .fire-title { background: linear-gradient(to right, #00BFFF, #00FF7F); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; }
        .stButton>button { border-radius: 8px; font-weight: bold; }
        button[kind="primary"] { background: linear-gradient(to right, #00BFFF, #00FF7F) !important; color: #000 !important; border: none !important; }
    </style>
""", unsafe_allow_html=True)

# --- LOGIN GATEWAY ---
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align:center;'>New Testament Reading Plan</h1>", unsafe_allow_html=True)
    tab_login, tab_register = st.tabs(["Login", "Create Account"])
    
    with tab_login:
        l_user = st.text_input("Username", key="l_user")
        l_pass = st.text_input("Password", type="password", key="l_pass")
        if st.button("Login", type="primary", use_container_width=True):
            users_df = get_sheet("Users", ["full_name", "mobile", "username", "password_hash", "status", "role"])
            if l_user in users_df["username"].values:
                user_row = users_df[users_df["username"] == l_user].iloc[0]
                if bcrypt.checkpw(l_pass.encode('utf-8'), user_row["password_hash"].encode('utf-8')):
                    if user_row["status"] == "Approved":
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = l_user
                        st.session_state["role"] = user_row["role"]
                        st.session_state["full_name"] = user_row["full_name"]
                        
                        if "data_synced" in st.session_state: del st.session_state["data_synced"]
                        
                        access_df = get_sheet("Access_Logs", ["timestamp", "username", "ip"])
                        ip = st.context.headers.get("X-Forwarded-For", "Local") if hasattr(st.context, 'headers') else "Local"
                        update_sheet("Access_Logs", pd.concat([access_df, pd.DataFrame([{"timestamp": str(datetime.datetime.now()), "username": l_user, "ip": ip}])], ignore_index=True))
                        st.rerun()
                    elif user_row["status"] == "Pending": st.warning("Awaiting Admin approval.")
                    else: st.error("Account blocked.")
                else: st.error("Incorrect password.")
            else: st.error("User not found.")
                
    with tab_register:
        r_name, r_mobile, r_user, r_pass = st.text_input("Full Name"), st.text_input("Mobile Number"), st.text_input("Desired Username"), st.text_input("Password", type="password")
        if st.button("Register Account", use_container_width=True):
            if all([r_name, r_mobile, r_user, r_pass]):
                users_df = get_sheet("Users", ["full_name", "mobile", "username", "password_hash", "status", "role"])
                if r_user in users_df["username"].values: st.error("Username taken.")
                else:
                    hashed = bcrypt.hashpw(r_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    role, status = ("Admin", "Approved") if users_df.empty else ("Member", "Pending")
                    new_user_df = pd.DataFrame([{"full_name": r_name, "mobile": r_mobile, "username": r_user, "password_hash": hashed, "status": status, "role": role}])
                    update_sheet("Users", pd.concat([users_df, new_user_df], ignore_index=True))
                    st.success("Account created! " + ("You are Admin. Log in." if role == "Admin" else "Wait for Admin approval."))
            else: st.error("Fill all fields.")
    st.stop()

# --- DATA PROCESSING LOGIC (Added New Time Columns) ---
logs_df_full = get_sheet("Reading_Logs", ["username", "chapter_id", "timestamp", "time_spent_seconds", "time_per_verse"])

if "data_synced" not in st.session_state:
    st.session_state["user_logs"] = logs_df_full[logs_df_full["username"] == st.session_state["username"]]
    st.session_state["progress"] = set(st.session_state["user_logs"]["chapter_id"].tolist())
    st.session_state["data_synced"] = True

@st.cache_data(show_spinner=False)
def load_bible_data(version):
    file_name = os.path.join(BIBLE_FILES_DIR, f'{version}.csv')
    try:
        with open(file_name, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
            
        sep = ','
        for line in lines[:10]:
            if '|' in line:
                sep = '|'
                break
                
        parsed_data = []
        for line in lines:
            line = line.strip()
            if not line: continue
            
            parts = line.split(sep, 3)
            if len(parts) == 4:
                b, c, v, t = [p.strip().strip('"') for p in parts]
                if c.isdigit() and v.isdigit():
                    parsed_data.append([b, int(c), int(v), t])
                    
        if not parsed_data:
            return pd.DataFrame()
            
        df = pd.DataFrame(parsed_data, columns=['b', 'c', 'v', 't'])
        df['t'] = df['t'].astype(str).apply(lambda x: re.sub(r'<[^>]+>', '', x))
        
        if df['b'].str.isdigit().mean() > 0.8:
            df['b'] = pd.to_numeric(df['b'], errors='coerce').fillna(-1).astype(int)
            unique_books = sorted(df[df['b'] >= 0]['b'].unique())
            
            if len(unique_books) >= 27:
                nt_ids = unique_books[-27:]
                mapping = dict(zip(nt_ids, BIBLE_BOOKS))
                df['b'] = df['b'].map(mapping)
                
        else:
            df.loc[df['b'].str.contains('Revelation', case=False, na=False), 'b'] = 'Revelation'
            book_fixes = {
                '1Corinthians': '1 Corinthians', 'ICorinthians': '1 Corinthians', 'I Corinthians': '1 Corinthians',
                '2Corinthians': '2 Corinthians', 'IICorinthians': '2 Corinthians', 'II Corinthians': '2 Corinthians',
                '1Thessalonians': '1 Thessalonians', 'IThessalonians': '1 Thessalonians', 'I Thessalonians': '1 Thessalonians',
                '2Thessalonians': '2 Thessalonians', 'IIThessalonians': '2 Thessalonians', 'II Thessalonians': '2 Thessalonians',
                '1Timothy': '1 Timothy', 'ITimothy': '1 Timothy', 'I Timothy': '1 Timothy',
                '2Timothy': '2 Timothy', 'IITimothy': '2 Timothy', 'II Timothy': '2 Timothy',
                '1Peter': '1 Peter', 'IPeter': '1 Peter', 'I Peter': '1 Peter',
                '2Peter': '2 Peter', 'IIPeter': '2 Peter', 'II Peter': '2 Peter',
                '1John': '1 John', 'IJohn': '1 John', 'I John': '1 John',
                '2John': '2 John', 'IIJohn': '2 John', 'II John': '2 John',
                '3John': '3 John', 'IIIJohn': '3 John', 'III John': '3 John'
            }
            df['b'] = df['b'].replace(book_fixes)
            df['b'] = df['b'].str.replace(r'^(\d)\s*([A-Za-z])', r'\1 \2', regex=True)
            
        df = df[df['b'].isin(BIBLE_BOOKS)]
        return df
        
    except Exception:
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def generate_56_day_plan(df):
    if df.empty: return [], {}, 0
    nt_df = df[df['b'].isin(BIBLE_BOOKS)]
    chapter_verses = nt_df.groupby(['b', 'c'])['v'].max().to_dict()
    
    all_chapters = []
    for bk in BIBLE_BOOKS:
        for ch in range(1, CHAPTER_COUNTS[bk] + 1):
            all_chapters.append((bk, ch, chapter_verses.get((bk, ch), 0)))
            
    plan, current_day, current_day_verses = [], [], 0
    
    for bk, ch, v in all_chapters:
        max_limit = 172 if (bk == 'Matthew' and ch == 26 and current_day_verses + v == 172) else 160
        
        if current_day_verses + v < 145:
            current_day.append(f"{bk}_{ch}")
            current_day_verses += v
        else:
            if current_day_verses + v <= max_limit:
                current_day.append(f"{bk}_{ch}")
                current_day_verses += v
                plan.append(current_day)
                current_day = []
                current_day_verses = 0
            else:
                if current_day:
                    plan.append(current_day)
                current_day = [f"{bk}_{ch}"]
                current_day_verses = v
                
    if current_day: plan.append(current_day)
    return plan, chapter_verses, sum(v for _, _, v in all_chapters)

master_df = load_bible_data("ASV")
day_plan, chapter_verses, TOTAL_VERSES = generate_56_day_plan(master_df)
TOTAL_DAYS = len(day_plan)

df = load_bible_data(st.session_state.get('nav_version', 'ASV'))

if 'nav_version' not in st.session_state: st.session_state['nav_version'] = "ASV"
if 'nav_book' not in st.session_state: st.session_state['nav_book'] = "Matthew"
if 'nav_chapter' not in st.session_state: st.session_state['nav_chapter'] = 1
if 'study_notes' not in st.session_state: st.session_state['study_notes'] = ""
if 'loaded_note_title' not in st.session_state: st.session_state['loaded_note_title'] = ""

c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 1, 1])

display_name = st.session_state.get('full_name') or st.session_state.get('username')
with c1: st.write(f"👤 **{display_name}** ({st.session_state['role']})")
with c2: st.selectbox("Version", ["ASV", "KJV", "YLT", "Malayalam"], key='nav_version')

with c3:
    curr_bk = st.session_state['nav_book']
    bk_idx = BIBLE_BOOKS.index(curr_bk) if curr_bk in BIBLE_BOOKS else 0
    sel_bk = st.selectbox("Book", BIBLE_BOOKS, index=bk_idx)

with c4:
    curr_ch = st.session_state['nav_chapter']
    ch_list = list(range(1, CHAPTER_COUNTS[sel_bk] + 1))
    ch_idx = ch_list.index(curr_ch) if curr_ch in ch_list else 0
    sel_ch = st.selectbox("Chapter", ch_list, index=ch_idx)

with c5: 
    if st.button("Logout"): 
        st.session_state.clear(); st.rerun()

if sel_bk != st.session_state['nav_book'] or sel_ch != st.session_state['nav_chapter']:
    st.session_state['nav_book'], st.session_state['nav_chapter'] = sel_bk, sel_ch
    st.rerun()

tabs = ["ℹ️ INSTRUCTIONS", "📊 READING PLAN", "📖 READ BIBLE", "📝 STUDY NOTES"]
if st.session_state["role"] == "Admin": tabs.append("🛡️ ADMIN PANEL")

tab_idx = tabs.index(st.session_state["active_tab"]) if st.session_state["active_tab"] in tabs else 0
selected_tab = st.radio("Navigation", tabs, horizontal=True, label_visibility="collapsed", index=tab_idx)

if selected_tab != st.session_state["active_tab"]:
    st.session_state["active_tab"] = selected_tab
    st.rerun()

st.markdown("---")
active_tab = st.session_state["active_tab"]

# ==========================================
# TAB 0: INSTRUCTIONS
# ==========================================
if active_tab == "ℹ️ INSTRUCTIONS":
    st.markdown("<h2 class='fire-title'>Welcome to the NT Reading Journey! 📖</h2>", unsafe_allow_html=True)
    
    st.info("👋 **Welcome!** This app is custom-built to guide our youth group through the entire New Testament in exactly 56 days. Here is how to get the most out of it:")
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("""
        ### 🔐 1. Accounts & Login
        *   **Logging In:** Always use your registered Username and Password.
        *   **New Users:** When you create an account, it goes into a "Pending" state. Please wait for the Admin to approve your account before you can log in.
        
        ### 📊 2. The 56-Day Roadmap
        *   The plan requires reading an average of **~145 verses per day**.
        *   Go to the **Reading Plan** tab to see your daily assignments.
        *   The **Green Bar** shows your overall progress.
        *   Click **▶️ Read Day** to instantly jump to your next unread chapter.
        """)
        
    with c2:
        st.markdown("""
        ### 📖 3. Guided Reading
        *   Use the drop-down at the top of the screen to switch between **English** and **Malayalam**.
        *   To help you pace yourself, the app loads **15 verses at a time**.
        *   Read the section, then click **"Load Next Verses 🔽"**.

        ### ⏱️ 4. Marking as Read & Notes
        *   **Take your time!** The **✅ MARK AS READ** button will only appear after you spend a realistic amount of time reading the chapter.
        *   Type your personal reflections in the **Study Notes** tab. (Use the Manglish-to-Malayalam button if needed!)
        *   Click **🖨️ EXPORT TO PDF** to save your notes.
        """)
    
    st.divider()
    st.markdown("<p style='text-align:center; color:#888;'><em>Select <strong>📊 READING PLAN</strong> from the menu above to begin!</em></p>", unsafe_allow_html=True)

# ==========================================
# TAB 1: READING PLAN
# ==========================================
if active_tab == "📊 READING PLAN":
    st.markdown(f"<h2 class='fire-title'>📖 Daily Reading Progress ({TOTAL_DAYS} Days)</h2>", unsafe_allow_html=True)
    
    actual_verses = sum(chapter_verses.get((ch.split('_')[0], int(ch.split('_')[1])), 0) for ch in st.session_state['progress'])
    first_read_date = pd.to_datetime(st.session_state['user_logs']['timestamp'].min()).date() if not st.session_state['user_logs'].empty else datetime.date.today()
    days_elapsed = (datetime.date.today() - first_read_date).days + 1
    
    target_verses = min(TOTAL_VERSES, int(days_elapsed * (TOTAL_VERSES / TOTAL_DAYS))) if TOTAL_DAYS > 0 else 0
    actual_pct = min(100, (actual_verses / TOTAL_VERSES) * 100) if TOTAL_VERSES > 0 else 0
    target_pct = min(100, (target_verses / TOTAL_VERSES) * 100) if TOTAL_VERSES > 0 else 0

    st.markdown(f"""
        <div style="background: #e0e0e0; height: 35px; border-radius: 10px; position: relative; width: 100%; border: 2px solid #555; overflow: hidden; margin-top: 10px;">
            <div style="background: #00FF7F; width: {max(1, actual_pct)}%; height: 100%; position: absolute; top:0; left:0; z-index: 3;"></div>
            <div style="background: #FF4444; width: 4px; height: 100%; position: absolute; left: {target_pct}%; top:0; z-index: 4;"></div>
        </div>
        <p style="font-weight: bold; font-size: 16px; margin-top: 8px;">
            🗓️ <span style="color: #00BFFF;">Days Active: {days_elapsed} / {TOTAL_DAYS}</span> &nbsp;|&nbsp; 
            🟢 <span style="color: #00FF7F;">Verses Read: {actual_verses} / {TOTAL_VERSES}</span> &nbsp;|&nbsp; 
            🔴 <span style="color: #FF4444;">Target Minimum: {target_verses}</span>
        </p>
    """, unsafe_allow_html=True)
    st.divider()

    st.markdown("<h3>Your Daily Roadmap</h3>", unsafe_allow_html=True)
    
    for row_idx in range(0, len(day_plan), 5):
        cols = st.columns(5)
        for col_idx in range(5):
            day_idx = row_idx + col_idx
            if day_idx < len(day_plan):
                day_chaps = day_plan[day_idx]
                read_count = sum(1 for ch in day_chaps if ch in st.session_state['progress'])
                pct = read_count / len(day_chaps) if len(day_chaps) > 0 else 0
                
                start_bk, start_ch = day_chaps[0].split('_')
                end_bk, end_ch = day_chaps[-1].split('_')
                
                c1_hex = BOOK_COLORS.get(start_bk, "#FFF")
                c2_hex = BOOK_COLORS.get(end_bk, "#FFF")
                if start_bk == end_bk:
                    label_html = f"<span style='color:{c1_hex}; font-weight:bold;'>{start_bk}</span> {start_ch}-{end_ch}"
                else:
                    label_html = f"<span style='color:{c1_hex}; font-weight:bold;'>{start_bk}</span> {start_ch} to <span style='color:{c2_hex}; font-weight:bold;'>{end_bk}</span> {end_ch}"
                
                with cols[col_idx]:
                    with st.container(border=True):
                        st.markdown(f"""
                            <div style="background: #FF4444; height: 6px; border-radius: 3px; margin-bottom: 8px; overflow: hidden;">
                                <div style="background: #00FF7F; width: {pct * 100}%; height: 100%;"></div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        if pct < 1.0:
                            next_ch_id = next(ch for ch in day_chaps if ch not in st.session_state['progress'])
                            n_bk, n_ch = next_ch_id.split('_')
                            if st.button(f"▶️ Read Day {day_idx+1}", key=f"btn_d{day_idx}", use_container_width=True):
                                st.session_state['nav_book'] = n_bk
                                st.session_state['nav_chapter'] = int(n_ch)
                                st.session_state['active_tab'] = "📖 READ BIBLE"
                                st.rerun()
                        else:
                            st.button(f"✅ Day {day_idx+1}", key=f"btn_d{day_idx}", disabled=True, use_container_width=True)
                        
                        st.markdown(f"<div style='text-align:center; font-size:14px; margin-top:5px;'>{label_html}</div>", unsafe_allow_html=True)

# ==========================================
# TAB 2: READ BIBLE
# ==========================================
elif active_tab == "📖 READ BIBLE":
    bk, ch = st.session_state['nav_book'], st.session_state['nav_chapter']
    chapter_id = f"{bk}_{ch}"
    
    bk_color = BOOK_COLORS.get(bk, "#00BFFF")
    st.markdown(f"<h1 style='text-align:center; color:{bk_color}; font-weight:800;'>{bk} {ch}</h1>", unsafe_allow_html=True)
    
    if not df.empty:
        verse_data = df[(df['b'] == bk) & (df['c'] == ch)]
        total_verses = len(verse_data)
        required_time_seconds = total_verses * 7
        
        if st.session_state.get('read_chapter_id') != chapter_id:
            st.session_state['read_chapter_id'] = chapter_id
            st.session_state['chunk_idx'] = 0
            st.session_state['chapter_start_time'] = time.time()
            st.session_state['read_stage'] = "chunking"
            st.session_state['q2_feedback'] = ""
            st.session_state['final_read_time'] = 0  # Initialize tracker
            
        max_verses_to_show = (st.session_state['chunk_idx'] + 1) * 15
        display_data = verse_data.iloc[:max_verses_to_show]
        
        text_block = "".join([f"<p style='font-size: 18px; line-height: 1.6;'><strong style='color:{bk_color};'>{row['v']}</strong> {row['t']}</p>" for _, row in display_data.iterrows()])
        st.markdown(text_block, unsafe_allow_html=True)
        st.write("")
        
        if chapter_id in st.session_state['progress']:
            st.warning("⚠️ Chapter Already Read - Choose Another from the Reading Plan.")
        else:
            st.markdown("---")
            
            if st.session_state['read_stage'] == "chunking":
                if max_verses_to_show < total_verses:
                    if st.button("Load Next Verses 🔽", use_container_width=True):
                        st.session_state['chunk_idx'] += 1
                        st.rerun()
                else:
                    if st.button("Next ⏭️", use_container_width=True):
                        elapsed = time.time() - st.session_state['chapter_start_time']
                        if elapsed >= required_time_seconds:
                            st.session_state['read_stage'] = "unlocked"
                            st.session_state['final_read_time'] = elapsed # Lock in time
                        else:
                            st.session_state['read_stage'] = "question_1"
                        st.rerun()
            
            elif st.session_state['read_stage'] == "question_1":
                st.markdown("### Have you read all the verses?")
                c_yes, c_no = st.columns(2)
                if c_yes.button("Yes", use_container_width=True):
                    elapsed_2 = time.time() - st.session_state['chapter_start_time']
                    if elapsed_2 >= required_time_seconds:
                        st.session_state['read_stage'] = "unlocked"
                        st.session_state['final_read_time'] = elapsed_2 # Lock in time
                    else:
                        st.session_state['read_stage'] = "question_2"
                    st.rerun()
                if c_no.button("No", use_container_width=True):
                    st.session_state['read_stage'] = "chunking"
                    st.rerun()
                    
            elif st.session_state['read_stage'] == "question_2":
                st.markdown("### How many verses have you read in the chapter?")
                with st.form("verse_count_form"):
                    user_ans = st.text_input("Enter number of verses:")
                    submitted = st.form_submit_button("Submit")
                    if submitted:
                        st.session_state['final_read_time'] = time.time() - st.session_state['chapter_start_time'] # Lock in bypass time
                        if user_ans.strip() != str(total_verses):
                            st.session_state['q2_feedback'] = f"There are {total_verses} verses in {bk} Chapter {ch}."
                        st.session_state['read_stage'] = "unlocked"
                        st.rerun()
                        
            elif st.session_state['read_stage'] == "unlocked":
                if st.session_state['q2_feedback']:
                    st.info(f"💡 {st.session_state['q2_feedback']}")
                    
                _, c_mark = st.columns([7, 2])
                with c_mark:
                    if st.button("✅ MARK AS READ", type="primary", use_container_width=True):
                        # Calculate Analytics
                        f_time = st.session_state.get('final_read_time', 0)
                        t_per_v = round(f_time / total_verses, 1) if total_verses > 0 else 0
                        
                        new_log = pd.DataFrame([{
                            "username": st.session_state["username"], 
                            "chapter_id": chapter_id, 
                            "timestamp": str(datetime.date.today()),
                            "time_spent_seconds": round(f_time, 1),
                            "time_per_verse": t_per_v
                        }])
                        
                        st.session_state["user_logs"] = pd.concat([st.session_state["user_logs"], new_log], ignore_index=True)
                        st.session_state['progress'].add(chapter_id)
                        
                        logs_full = get_sheet("Reading_Logs", ["username", "chapter_id", "timestamp", "time_spent_seconds", "time_per_verse"])
                        updated_full_logs = pd.concat([logs_full, new_log], ignore_index=True)
                        
                        def silent_push(data):
                            try:
                                conn.update(worksheet="Reading_Logs", data=data)
                                st.cache_data.clear() 
                            except: pass
                            
                        threading.Thread(target=silent_push, args=(updated_full_logs,)).start()
                        
                        st.session_state['read_chapter_id'] = None
                        
                        if ch >= CHAPTER_COUNTS[bk]:
                            bk_idx = BIBLE_BOOKS.index(bk)
                            if bk_idx + 1 < len(BIBLE_BOOKS):
                                st.session_state['nav_book'] = BIBLE_BOOKS[bk_idx + 1]
                                st.session_state['nav_chapter'] = 1
                        else: st.session_state['nav_chapter'] = ch + 1
                        st.rerun()
            
            today_str = str(datetime.date.today())
            today_verses_read = 0
            if not st.session_state["user_logs"].empty and 'chapter_id' in st.session_state["user_logs"].columns:
                today_logs = st.session_state["user_logs"][st.session_state["user_logs"]['timestamp'] == today_str]
                today_verses_read = sum(
                    chapter_verses.get((str(c).split('_')[0], int(str(c).split('_')[1])), 0) 
                    for c in today_logs['chapter_id'] 
                    if isinstance(c, str) and '_' in c
                )
            
            if 0 < today_verses_read < 145:
                st.info(f"📊 You have read **{today_verses_read}** verses today. The plan requires an average of **~145** verses daily!")

# ==========================================
# TAB 3: STUDY NOTES
# ==========================================
elif active_tab == "📝 STUDY NOTES":
    display_title = st.session_state['loaded_note_title'] if st.session_state['loaded_note_title'] else f"Notes_{st.session_state['nav_book']}_{st.session_state['nav_chapter']}"
    st.markdown(f"<h1 class='fire-title'>Study Notes: {display_title.replace('Notes_', '').replace('_', ' ')}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='font-weight:bold; color:#888;'>NOTES IN ENGLISH (IF IN MANGLISH CONVERT TO MALAYALAM)</p>", unsafe_allow_html=True)
    
    notes_val = st.text_area("Workspace", value=st.session_state['study_notes'], height=300, label_visibility="collapsed")
    st.session_state['study_notes'] = notes_val
    
    def transliterate_manglish(text):
        if not text.strip(): return ""
        try:
            url = f"https://inputtools.google.com/request?text={urllib.parse.quote(text)}&itc=ml-t-i0-und&num=1&cp=0&cs=1&ie=utf-8&oe=utf-8"
            with urllib.request.urlopen(urllib.request.Request(url)) as response:
                data = json.loads(response.read().decode())
                if data[0] == 'SUCCESS': return " ".join([item[1][0] for item in data[1]])
        except Exception: pass
        return text

    if st.button("🌐 Convert Manglish to Malayalam"):
        st.session_state['study_notes'] = transliterate_manglish(notes_val)
        st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    is_local = (os.name == 'nt' and os.path.exists(BACKUP_DIR))
    
    with c1:
        if is_local:
            if st.markdown('<button class="stButton btn-draft" style="width:100%;">💾 SAVE DRAFT</button>', unsafe_allow_html=True) and st.button("Confirm Draft", key="d_tmp"):
                with open(os.path.join(BACKUP_DIR, f"Draft_{display_title}.txt"), "w", encoding="utf-8") as f:
                    f.write(st.session_state['study_notes'])
                st.success("Draft saved to E:")
        else:
            st.download_button("💾 DOWNLOAD DRAFT", data=st.session_state['study_notes'], file_name=f"Draft_{display_title}.txt", use_container_width=True)
    
    with c2:
        if is_local:
            if st.markdown('<button class="stButton btn-backup" style="width:100%;">📂 BACKUP NOTES</button>', unsafe_allow_html=True) and st.button("Confirm Backup", key="b_tmp"):
                with open(os.path.join(BACKUP_DIR, f"{display_title}.txt"), "w", encoding="utf-8") as f:
                    f.write(st.session_state['study_notes'])
                st.success("Backed up to E:")
        else:
            st.download_button("📂 DOWNLOAD BACKUP", data=st.session_state['study_notes'], file_name=f"{display_title}.txt", use_container_width=True)

    with c3:
        if is_local:
            with st.popover("🔄 LOAD PREVIOUS", use_container_width=True):
                existing_files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.txt')]
                if existing_files:
                    selected_file = st.selectbox("Select file:", existing_files, label_visibility="collapsed")
                    if st.button("Load File"):
                        with open(os.path.join(BACKUP_DIR, selected_file), "r", encoding="utf-8") as f:
                            st.session_state['study_notes'] = f.read()
                        st.session_state['loaded_note_title'] = selected_file.replace('.txt', '')
                        st.rerun()
                else:
                    st.write("No saved notes found.")
        else:
            uploaded_file = st.file_uploader("Upload Note", type=["txt"], label_visibility="collapsed")
            if uploaded_file is not None:
                st.session_state['study_notes'] = uploaded_file.getvalue().decode("utf-8")
                st.session_state['loaded_note_title'] = uploaded_file.name.replace('.txt', '')
                st.success("Loaded successfully!")
                
    with c4:
        printable_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{display_title}</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Malayalam:wght@400;700&display=swap');
                @page {{ size: A4; margin: 20mm; }}
                body {{ font-family: 'Noto Sans Malayalam', sans-serif; font-size: 14pt; line-height: 1.6; color: #000; }}
                h1 {{ text-align: center; color: #333; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }}
                pre {{ white-space: pre-wrap; font-family: inherit; font-size: 14pt; }}
            </style>
        </head>
        <body onload="window.print()">
            <h1>{display_title.replace('Notes_', '').replace('_', ' ')}</h1>
            <pre>{st.session_state['study_notes']}</pre>
        </body>
        </html>
        """
        
        if is_local:
            if st.markdown('<button class="stButton btn-print" style="width:100%;">🖨️ EXPORT TO PDF</button>', unsafe_allow_html=True) and st.button("Generate File", key="p_tmp"):
                print_path = os.path.join(BACKUP_DIR, f"Print_{display_title}.html")
                with open(print_path, "w", encoding="utf-8") as f:
                    f.write(printable_html)
                st.success(f"File saved to E:! Open **{print_path}** in your browser, and it will instantly prompt you to Save as PDF.")
        else:
            st.download_button(
                label="🖨️ EXPORT TO PDF",
                data=printable_html,
                file_name=f"Print_{display_title}.html",
                mime="text/html",
                use_container_width=True
            )

# ==========================================
# TAB 4: ADMIN PANEL
# ==========================================
elif active_tab == "🛡️ ADMIN PANEL" and st.session_state["role"] == "Admin":
    st.markdown("<h2>User Management</h2>", unsafe_allow_html=True)
    users_df = get_sheet("Users", ["full_name", "mobile", "username", "password_hash", "status", "role"])
    
    if not users_df.empty:
        for i, row in users_df.iterrows():
            c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
            c1.write(f"**{row['full_name']}** ({row['username']})")
            c2.write(f"Status: {row['status']}")
            if row['status'] == "Pending":
                if c3.button("Approve", key=f"app_{i}"):
                    users_df.at[i, "status"] = "Approved"
                    update_sheet("Users", users_df)
                    st.rerun()
            elif row['status'] == "Approved" and row['role'] != "Admin":
                if c4.button("Block", key=f"blk_{i}"):
                    users_df.at[i, "status"] = "Blocked"
                    update_sheet("Users", users_df)
                    st.rerun()
    else:
        st.write("No users registered yet.")
    
    st.markdown("---")
    st.markdown("<h2>Access Logs</h2>", unsafe_allow_html=True)
    access_df = get_sheet("Access_Logs", ["timestamp", "username", "ip"])
    
    if not access_df.empty:
        col_filter, col_limit = st.columns(2)
        with col_filter:
            all_users = ["All Users"] + list(access_df["username"].unique())
            selected_user = st.selectbox("Filter by Username", all_users)
        with col_limit:
            row_limit = st.selectbox("Number of Rows to Show", [25, 50, 75, 100, "All Rows"])
            
        if selected_user != "All Users":
            display_df = access_df[access_df["username"] == selected_user]
        else:
            display_df = access_df
            
        display_df = display_df.sort_values(by="timestamp", ascending=False)
        if row_limit != "All Rows":
            display_df = display_df.head(row_limit)
            
        st.dataframe(display_df, use_container_width=True)
    else:
        st.write("No access logs recorded yet.")