import os
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# SUBSPHERE — Python-only subscription manager
# Local mode uses SQLite. Cloud mode can use Supabase Postgres.
# ============================================================

st.set_page_config(
    page_title="SubSphere | Subscription Manager",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CATEGORIES = [
    "Entertainment", "Education", "Software", "Music", "Gaming",
    "Cloud Storage", "News", "Shopping", "Fitness", "Other"
]
CURRENCIES = ["INR", "USD", "EUR", "GBP"]
STATUSES = ["Active", "Paused", "Cancelled"]
BILLING_CYCLES = ["Weekly", "Monthly", "Quarterly", "Yearly"]

# ---------- Appearance (CSS is embedded; no separate CSS/JS files) ----------
st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp {
  background:
    radial-gradient(ellipse at 85% 0%, rgba(112,74,230,.22), transparent 38%),
    radial-gradient(ellipse at 0% 45%, rgba(30,115,180,.12), transparent 35%),
    #080b16;
}
.block-container {max-width: 1450px; padding-top: 1.8rem; padding-bottom: 3rem;}
[data-testid="stMetric"] {
  background: linear-gradient(145deg, rgba(39,34,72,.96), rgba(17,21,39,.96));
  border: 1px solid rgba(167,139,250,.27);
  padding: 18px 20px; border-radius: 18px;
  box-shadow: 8px 10px 25px rgba(0,0,0,.28);
  transition: transform .2s ease, box-shadow .2s ease;
}
[data-testid="stMetric"]:hover {
  transform: translateY(-4px);
  box-shadow: 0 16px 35px rgba(112,74,230,.18);
}
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg,#11152a,#0b0e1b);
  border-right: 1px solid rgba(167,139,250,.18);
}
div.stButton > button, div.stDownloadButton > button {
  border-radius: 11px; border: 1px solid rgba(167,139,250,.35);
  background: linear-gradient(120deg,#7952e8,#4b35a8);
  color: white; font-weight: 650; transition: all .2s ease;
}
div.stButton > button:hover, div.stDownloadButton > button:hover {
  transform: translateY(-2px); border-color: #c4b5fd;
  box-shadow: 0 8px 22px rgba(121,82,232,.25); color: white;
}
div[data-testid="stForm"] {
  background: rgba(22,26,47,.72); border: 1px solid rgba(167,139,250,.2);
  border-radius: 16px; padding: 18px;
}
h1,h2,h3 { letter-spacing: -.035em; }
.small-muted {color:#9ca3bd; font-size:.88rem;}
.hero {
  padding: 22px 24px; border-radius: 22px;
  background: linear-gradient(120deg,rgba(93,65,177,.32),rgba(20,27,50,.78));
  border: 1px solid rgba(167,139,250,.25);
  box-shadow: 0 20px 45px rgba(0,0,0,.22);
}
</style>
""", unsafe_allow_html=True)

# ---------- Storage ----------
# Set Supabase secrets to enable cloud database:
# [supabase]
# url = "https://YOUR_PROJECT.supabase.co"
# key = "YOUR_SUPABASE_SERVICE_OR_SECRET_KEY"
# Never expose a service-role key in a public repository.
USE_SUPABASE = False
try:
    USE_SUPABASE = bool(st.secrets.get("supabase", {}).get("url")) and bool(
        st.secrets.get("supabase", {}).get("key")
    )
except Exception:
    USE_SUPABASE = False

def local_conn():
    db_path = os.environ.get("SUBSPHERE_DB", "subsphere.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            category TEXT NOT NULL,
            billing TEXT NOT NULL,
            next_payment TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active',
            website TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            paid_on TEXT NOT NULL,
            note TEXT DEFAULT ''
        )
    """)
    conn.commit()
    return conn

def supabase_client():
    from supabase import create_client
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["key"])

def load_subscriptions():
    if USE_SUPABASE:
        rows = supabase_client().table("subscriptions").select("*").order("next_payment").execute().data
        return pd.DataFrame(rows)
    with local_conn() as conn:
        return pd.read_sql_query("SELECT * FROM subscriptions ORDER BY next_payment", conn)

def load_payments():
    if USE_SUPABASE:
        rows = supabase_client().table("payments").select("*").order("paid_on", desc=True).execute().data
        return pd.DataFrame(rows)
    with local_conn() as conn:
        return pd.read_sql_query("SELECT * FROM payments ORDER BY paid_on DESC", conn)

def add_subscription(data):
    data["created_at"] = datetime.now().isoformat(timespec="seconds")
    if USE_SUPABASE:
        supabase_client().table("subscriptions").insert(data).execute()
    else:
        with local_conn() as conn:
            conn.execute("""
                INSERT INTO subscriptions
                (name,price,currency,category,billing,next_payment,status,website,notes,created_at)
                VALUES (:name,:price,:currency,:category,:billing,:next_payment,:status,:website,:notes,:created_at)
            """, data)

def update_subscription(sub_id, data):
    if USE_SUPABASE:
        supabase_client().table("subscriptions").update(data).eq("id", sub_id).execute()
    else:
        with local_conn() as conn:
            conn.execute("""
                UPDATE subscriptions SET name=:name,price=:price,currency=:currency,
                category=:category,billing=:billing,next_payment=:next_payment,
                status=:status,website=:website,notes=:notes WHERE id=:id
            """, {**data, "id": sub_id})

def delete_subscription(sub_id):
    if USE_SUPABASE:
        client = supabase_client()
        client.table("payments").delete().eq("subscription_id", sub_id).execute()
        client.table("subscriptions").delete().eq("id", sub_id).execute()
    else:
        with local_conn() as conn:
            conn.execute("DELETE FROM payments WHERE subscription_id=?", (sub_id,))
            conn.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,))

def add_payment(sub_id, name, amount, currency, paid_on, note):
    data = {
        "subscription_id": int(sub_id) if sub_id else None,
        "name": name, "amount": float(amount), "currency": currency,
        "paid_on": paid_on.isoformat(), "note": note
    }
    if USE_SUPABASE:
        supabase_client().table("payments").insert(data).execute()
    else:
        with local_conn() as conn:
            conn.execute("""
                INSERT INTO payments (subscription_id,name,amount,currency,paid_on,note)
                VALUES (:subscription_id,:name,:amount,:currency,:paid_on,:note)
            """, data)

def update_status(sub_id, status):
    if USE_SUPABASE:
        supabase_client().table("subscriptions").update({"status": status}).eq("id", sub_id).execute()
    else:
        with local_conn() as conn:
            conn.execute("UPDATE subscriptions SET status=? WHERE id=?", (status, sub_id))

# ---------- Helpers ----------
def money(value, currency="INR"):
    symbols = {"INR":"₹", "USD":"$", "EUR":"€", "GBP":"£"}
    return f"{symbols.get(currency, currency + ' ')}{value:,.2f}"

def monthly_equivalent(price, billing):
    factor = {"Weekly": 52/12, "Monthly": 1, "Quarterly": 1/3, "Yearly": 1/12}
    return float(price) * factor.get(billing, 1)

def normalized_df(df):
    if df.empty:
        return df
    out = df.copy()
    out["next_payment"] = pd.to_datetime(out["next_payment"], errors="coerce")
    out["monthly_equivalent"] = out.apply(
        lambda r: monthly_equivalent(r["price"], r["billing"]), axis=1
    )
    out["days_left"] = (out["next_payment"].dt.date - date.today()).apply(
        lambda x: x.days if pd.notna(x) else None
    )
    return out

def next_due_text(days):
    if pd.isna(days): return "Date unavailable"
    if days < 0: return f"{abs(int(days))} days overdue"
    if days == 0: return "Due today"
    if days == 1: return "Due tomorrow"
    return f"In {int(days)} days"

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("# ◈ SubSphere")
    st.caption("SUBSCRIPTION CONTROL CENTER")
    page = st.radio(
        "NAVIGATION",
        ["Overview", "Subscriptions", "Calendar & Reminders", "Analytics",
         "Payment History", "Payment Centre (Sandbox)", "Settings & Backup"],
        label_visibility="visible"
    )
    st.divider()
    st.caption("STORAGE")
    st.success("Cloud database connected" if USE_SUPABASE else "Local SQLite database")
    st.caption("SubSphere • v3.1 SANDBOX")

# ---------- Data ----------
raw = load_subscriptions()
df = normalized_df(raw)
payments = load_payments()
active = df[df["status"] == "Active"] if not df.empty else df
monthly_total = active["monthly_equivalent"].sum() if not active.empty else 0.0
yearly_total = monthly_total * 12
currency = "INR"
budget_default = 3000.0
budget = st.session_state.get("monthly_budget", budget_default)
upcoming = active[
    (active["days_left"] >= 0) & (active["days_left"] <= 7)
] if not active.empty else active

# ---------- Overview ----------
if page == "Overview":
    st.markdown("""
    <div class="hero">
      <div style="color:#c4b5fd;font-size:11px;letter-spacing:2px;font-weight:700">
        YOUR MONEY. YOUR CONTROL.
      </div>
      <h1 style="margin:.35rem 0">Subscription Dashboard</h1>
      <div class="small-muted">See every recurring expense in one place.</div>
    </div>
    """, unsafe_allow_html=True)
    st.write("")
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Monthly equivalent", money(monthly_total))
    m2.metric("Yearly projection", money(yearly_total))
    m3.metric("Active subscriptions", int(len(active)))
    m4.metric("Due in next 7 days", int(len(upcoming)))
    st.write("")
    left,right = st.columns([1.5,1])
    with left:
        st.subheader("Recent subscriptions")
        if df.empty:
            st.info("Your dashboard is empty. Add your first subscription from the Subscriptions page.")
        else:
            view = df.sort_values("created_at", ascending=False).head(6)
            for _,r in view.iterrows():
                with st.container(border=True):
                    a,b,c = st.columns([2,1,1])
                    a.markdown(f"**{r['name']}**")
                    a.caption(f"{r['category']} · {r['billing']} · {r['status']}")
                    b.markdown(f"**{money(r['price'],r['currency'])}**")
                    c.caption(next_due_text(r["days_left"]))
    with right:
        st.subheader("Upcoming renewals")
        if upcoming.empty:
            st.success("No active renewals due in the next 7 days.")
        else:
            for _,r in upcoming.sort_values("next_payment").iterrows():
                st.warning(f"**{r['name']}** · {money(r['price'],r['currency'])}\n\n{next_due_text(r['days_left'])}")
        st.subheader("Budget check")
        st.caption(f"Monthly budget: {money(budget)}")
        st.progress(min(float(monthly_total / budget),1.0) if budget > 0 else 0.0)
        if budget > 0:
            st.caption(f"{monthly_total/budget*100:.1f}% of budget used")
            if monthly_total > budget:
                st.error(f"Over budget by {money(monthly_total-budget)}")
            else:
                st.success(f"Remaining: {money(budget-monthly_total)}")

# ---------- Subscriptions ----------
elif page == "Subscriptions":
    st.title("Subscriptions")
    st.caption("Add, edit, pause, cancel, search and organize your recurring services.")
    with st.expander("＋ Add a subscription", expanded=df.empty):
        with st.form("add_subscription_form", clear_on_submit=True):
            c1,c2 = st.columns(2)
            name = c1.text_input("Service name *", placeholder="e.g. Music or video service")
            price = c2.number_input("Price *", min_value=0.0, step=10.0)
            c3,c4,c5 = st.columns(3)
            curr = c3.selectbox("Currency", CURRENCIES)
            category = c4.selectbox("Category", CATEGORIES)
            billing = c5.selectbox("Billing cycle", BILLING_CYCLES)
            c6,c7 = st.columns(2)
            next_payment = c6.date_input("Next payment date", value=date.today()+timedelta(days=30))
            status = c7.selectbox("Status", STATUSES)
            website = st.text_input("Website (optional)", placeholder="https://...")
            notes = st.text_area("Notes (optional)", placeholder="Plan details, cancellation notes, etc.", height=70)
            submitted = st.form_submit_button("Save subscription", use_container_width=True)
            if submitted:
                if not name.strip():
                    st.error("Please enter a service name.")
                else:
                    add_subscription({
                        "name":name.strip(),"price":float(price),"currency":curr,
                        "category":category,"billing":billing,
                        "next_payment":next_payment.isoformat(),"status":status,
                        "website":website.strip(),"notes":notes.strip()
                    })
                    st.success("Subscription saved.")
                    st.rerun()

    if not df.empty:
        f1,f2,f3 = st.columns([2,1,1])
        query = f1.text_input("Search subscriptions", placeholder="Search by name, category or notes")
        status_filter = f2.selectbox("Status filter", ["All"]+STATUSES)
        category_filter = f3.selectbox("Category filter", ["All"]+CATEGORIES)
        filtered = df.copy()
        if query:
            mask = filtered.astype(str).apply(lambda col: col.str.contains(query,case=False,na=False)).any(axis=1)
            filtered = filtered[mask]
        if status_filter != "All":
            filtered = filtered[filtered["status"] == status_filter]
        if category_filter != "All":
            filtered = filtered[filtered["category"] == category_filter]
        st.caption(f"{len(filtered)} result(s)")
        for _,r in filtered.iterrows():
            with st.expander(f"{r['name']}  ·  {money(r['price'],r['currency'])} / {r['billing']}  ·  {r['status']}"):
                st.write(f"**Category:** {r['category']}  |  **Next payment:** {r['next_payment'].date() if pd.notna(r['next_payment']) else 'Not set'}")
                st.write(f"**Monthly equivalent:** {money(r['monthly_equivalent'],r['currency'])}")
                if r["website"]:
                    st.write(f"**Website:** {r['website']}")
                if r["notes"]:
                    st.write(f"**Notes:** {r['notes']}")
                with st.form(f"edit_{int(r['id'])}"):
                    e1,e2 = st.columns(2)
                    ename = e1.text_input("Name", value=r["name"])
                    eprice = e2.number_input("Price", min_value=0.0, value=float(r["price"]), step=10.0)
                    e3,e4,e5 = st.columns(3)
                    ecurr = e3.selectbox("Currency", CURRENCIES, index=CURRENCIES.index(r["currency"]) if r["currency"] in CURRENCIES else 0)
                    ecat = e4.selectbox("Category", CATEGORIES, index=CATEGORIES.index(r["category"]) if r["category"] in CATEGORIES else 0)
                    ebill = e5.selectbox("Billing", BILLING_CYCLES, index=BILLING_CYCLES.index(r["billing"]) if r["billing"] in BILLING_CYCLES else 1)
                    edate = st.date_input("Next payment", value=r["next_payment"].date() if pd.notna(r["next_payment"]) else date.today())
                    estat = st.selectbox("Status", STATUSES, index=STATUSES.index(r["status"]) if r["status"] in STATUSES else 0)
                    ewebsite = st.text_input("Website", value=r["website"] or "")
                    enotes = st.text_area("Notes", value=r["notes"] or "")
                    save = st.form_submit_button("Save changes")
                    if save:
                        update_subscription(int(r["id"]),{
                            "name":ename.strip(),"price":float(eprice),"currency":ecurr,
                            "category":ecat,"billing":ebill,"next_payment":edate.isoformat(),
                            "status":estat,"website":ewebsite.strip(),"notes":enotes.strip()
                        })
                        st.success("Updated.")
                        st.rerun()
                ca,cb = st.columns(2)
                with ca:
                    if st.button("Record a payment", key=f"pay_{int(r['id'])}"):
                        st.session_state["record_for"] = int(r["id"])
                        st.session_state["record_name"] = r["name"]
                with cb:
                    if st.button("Delete subscription", key=f"del_{int(r['id'])}"):
                        st.session_state["confirm_delete"] = int(r["id"])
                if st.session_state.get("confirm_delete") == int(r["id"]):
                    st.error("Confirm deletion? Its payment history will also be deleted.")
                    x,y = st.columns(2)
                    if x.button("Yes, delete", key=f"yesdel_{int(r['id'])}"):
                        delete_subscription(int(r["id"]))
                        st.session_state.pop("confirm_delete",None)
                        st.rerun()
                    if y.button("Keep it", key=f"nodel_{int(r['id'])}"):
                        st.session_state.pop("confirm_delete",None)
                        st.rerun()

        if st.session_state.get("record_for"):
            st.divider()
            st.subheader(f"Record payment — {st.session_state.get('record_name','')}")
            with st.form("record_payment_form"):
                amt = st.number_input("Amount paid",min_value=0.0,step=10.0)
                paid_currency = st.selectbox("Currency",CURRENCIES)
                paid_on = st.date_input("Payment date",value=date.today())
                note = st.text_input("Payment note")
                p1,p2 = st.columns(2)
                record = p1.form_submit_button("Save payment")
                cancel = p2.form_submit_button("Cancel")
                if record:
                    add_payment(st.session_state["record_for"],st.session_state["record_name"],amt,paid_currency,paid_on,note)
                    st.session_state.pop("record_for",None)
                    st.success("Payment recorded.")
                    st.rerun()
                if cancel:
                    st.session_state.pop("record_for",None)
                    st.rerun()
    else:
        st.info("No subscriptions yet. Use the form above to add one.")

# ---------- Calendar & reminders ----------
elif page == "Calendar & Reminders":
    st.title("Calendar & Reminders")
    st.caption("A date-based view of your next subscription renewals.")
    days = st.slider("Show payments due within how many days?",7,90,30)
    if active.empty:
        st.info("Add active subscriptions to see your renewal calendar.")
    else:
        due = active[(active["days_left"] >= 0)&(active["days_left"] <= days)].sort_values("next_payment")
        if due.empty:
            st.success(f"No active renewals due in the next {days} days.")
        else:
            for _,r in due.iterrows():
                with st.container(border=True):
                    a,b,c = st.columns([2,1,1])
                    a.markdown(f"**{r['name']}**")
                    a.caption(f"{r['category']} · {r['billing']}")
                    b.markdown(f"**{money(r['price'],r['currency'])}**")
                    c.warning(next_due_text(r["days_left"]))
        st.subheader("All upcoming dates")
        cal = active[active["days_left"] >= 0][["name","category","next_payment","price","currency","days_left"]].copy()
        if not cal.empty:
            cal["next_payment"] = cal["next_payment"].dt.strftime("%d %b %Y")
            cal["When"] = cal["days_left"].apply(next_due_text)
            st.dataframe(cal[["next_payment","name","category","price","currency","When"]],use_container_width=True,hide_index=True)

# ---------- Analytics ----------
elif page == "Analytics":
    st.title("Analytics & Insights")
    if df.empty:
        st.info("Add subscriptions to unlock analytics.")
    else:
        active_analytics = df[df["status"]=="Active"].copy()
        a,b,c = st.columns(3)
        a.metric("Monthly equivalent",money(active_analytics["monthly_equivalent"].sum()))
        a2 = active_analytics["monthly_equivalent"].sum()
        b.metric("Annual projection",money(a2*12))
        c.metric("Average per active service",money(a2/len(active_analytics)) if len(active_analytics) else money(0))
        if not active_analytics.empty:
            by_cat = active_analytics.groupby("category",as_index=False)["monthly_equivalent"].sum()
            fig = px.pie(by_cat,names="category",values="monthly_equivalent",hole=.62,
                         title="Monthly cost by category",
                         color_discrete_sequence=px.colors.sequential.Purples)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="white")
            st.plotly_chart(fig,use_container_width=True)
            fig2 = px.bar(active_analytics,x="name",y="monthly_equivalent",color="category",
                          title="Monthly equivalent by subscription")
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="white")
            st.plotly_chart(fig2,use_container_width=True)
            st.subheader("Most expensive subscriptions")
            st.dataframe(active_analytics.sort_values("monthly_equivalent",ascending=False)[
                ["name","category","billing","price","currency","monthly_equivalent"]
            ],use_container_width=True,hide_index=True)
        st.caption("Different currencies are displayed separately in records; totals assume all entries use the same currency. Convert currencies manually before combining mixed-currency spending.")

# ---------- Payment history ----------
elif page == "Payment History":
    st.title("Payment History")
    st.caption("Record real payments manually and keep a searchable history.")
    if payments.empty:
        st.info("No payments recorded yet. Open a subscription and choose Record a payment.")
    else:
        p = payments.copy()
        p["paid_on"] = pd.to_datetime(p["paid_on"],errors="coerce")
        st.metric("Payments recorded",len(p))
        st.dataframe(p[["paid_on","name","amount","currency","note"]],use_container_width=True,hide_index=True)
        st.download_button("Download payment history CSV",p.to_csv(index=False).encode("utf-8"),
                           "subsphere_payment_history.csv","text/csv")

# ---------- Payment centre: safe sandbox only ----------
elif page == "Payment Centre (Sandbox)":
    from payment_security import init_payment_db, add_demo_method, list_demo_methods, create_demo_mandate, list_demo_mandates, sign_test_webhook, verify_webhook, record_webhook_once
    init_payment_db()
    st.title("Payment Centre · v3.1")
    st.caption("India + Global · provider comparison · sandbox simulation only")
    st.warning("DEMO MODE ONLY — no real money moves, no real bank/card/UPI linking, and no automatic debit is enabled. Never enter a real card number, CVV, UPI PIN, OTP, password, or bank account number here.")
    t1,t2,t3,t4 = st.tabs(["Payment methods", "Recurring mandates", "Webhook lab", "Provider comparison"])
    with t1:
        st.subheader("Secure payment-method linking (simulated)")
        st.write("A real gateway should collect payment details on its hosted checkout and return a provider token. SubSphere should store only that token reference and safe display metadata.")
        with st.form("demo_method_form"):
            method_type=st.selectbox("Demo method type",["Card token","UPI mandate token","Bank e-mandate token"])
            label=st.text_input("Display label", value="Demo card •••• 4242" if method_type=="Card token" else ("Demo UPI handle" if method_type=="UPI mandate token" else "Demo bank mandate"))
            provider=st.selectbox("Provider label",["Razorpay (test adapter)","Cashfree (test adapter)","Local simulator"])
            token_ref=st.text_input("Fake provider token reference",value="tok_demo_"+str(abs(hash((method_type,label)))%1000000))
            consent=st.checkbox("I understand this is a fake sandbox record, not a real payment method.")
            add=st.form_submit_button("Link demo method")
            if add:
                if not consent: st.error("Confirm the sandbox notice first.")
                elif not label.strip() or not token_ref.strip(): st.error("Enter a label and fake token reference.")
                else:
                    add_demo_method(method_type,label.strip(),provider,token_ref.strip())
                    st.success("Demo token reference saved. No payment details were collected.")
        methods=list_demo_methods()
        st.subheader("Linked demo methods")
        if methods: st.dataframe(methods,use_container_width=True,hide_index=True)
        else: st.info("No demo methods linked yet.")
        st.caption("The sample database stores only a fake token reference, provider label, method type and display label. It never stores PAN, CVV, UPI PIN, OTP, or bank credentials.")
    with t2:
        st.subheader("Recurring mandate lifecycle simulator")
        st.write("A mandate is not created merely by saving a card or UPI ID. The customer must review the amount/frequency and approve the mandate in the provider/bank/UPI flow.")
        if methods:
            labels=[f"{m['id']} · {m['method_type']} · {m['display_label']}" for m in methods]
            chosen=st.selectbox("Choose demo method",labels)
            amount=st.number_input("Test renewal amount",min_value=1.0,value=199.0,step=1.0)
            currency=st.selectbox("Currency",["INR","USD","EUR","GBP"])
            frequency=st.selectbox("Frequency",["Monthly","Weekly","Quarterly","Yearly"])
            consent2=st.checkbox("Simulate customer consent to this test mandate")
            if st.button("Create simulated mandate"):
                if not consent2: st.error("Customer consent is required, even in this simulation.")
                else:
                    mid=int(chosen.split(" · ",1)[0])
                    create_demo_mandate(mid,amount,currency,frequency)
                    st.success("Simulated mandate created with status: AUTHORIZED (demo only). No debit was attempted.")
        else: st.info("Link a demo method first.")
        mandates=list_demo_mandates()
        if mandates: st.dataframe(mandates,use_container_width=True,hide_index=True)
        st.info("Production mandates require merchant approval, provider activation, customer authentication, mandate limits/notifications and cancellation/pause handling. This project does not send real recurring charges.")
    with t3:
        st.subheader("Signed webhook verification lab")
        st.write("The verifier checks HMAC-SHA256 against the exact raw request body. Production secrets belong only in server-side environment secrets, never in source code or a public repository.")
        test_secret=st.text_input("Temporary test webhook secret",value="subsphere_local_test_secret_change_me",type="password")
        payload=st.text_area("Webhook JSON payload",value='{"id":"evt_demo_001","type":"subscription.activated","data":{"subscription_id":"sub_demo_001","status":"active"}}',height=120)
        if st.button("Sign + verify test event"):
            try:
                raw_body=payload.encode("utf-8")
                sig=sign_test_webhook(raw_body,test_secret.encode("utf-8"))
                valid=verify_webhook(raw_body,sig,test_secret.encode("utf-8"))
                obj=json.loads(payload)
                if valid and record_webhook_once(obj.get("id",""),obj.get("type","unknown")):
                    st.success("Signature valid. Event accepted once and marked processed (local demo).")
                elif valid: st.info("Signature valid, but this event ID was already processed (idempotency check).")
                else: st.error("Invalid signature.")
                st.code("X-Demo-Signature: "+sig)
            except Exception as exc: st.error(f"Webhook test failed: {exc}")
        st.caption("In a real endpoint: read raw bytes before JSON parsing; verify the provider signature using that provider's exact scheme; reject invalid signatures; persist event IDs uniquely; acknowledge quickly; process asynchronously; and fetch payment status server-to-server before marking a renewal paid.")
    with t4:
        st.subheader("Provider comparison · India + Global")
        st.markdown("**Razorpay** — strong fit for India-first subscriptions: cards, UPI recurring (availability/activation and limits apply), e-mandates; supports international card subscription use cases subject to merchant eligibility and activation.")
        st.markdown("**Cashfree** — broad India recurring stack: UPI AutoPay, card standing instructions and eNACH; also advertises global recurring subscriptions/international card support. Exact features depend on merchant approval and product configuration.")
        st.markdown("| Requirement | Razorpay | Cashfree |\n|---|---|---|\n| India one-time cards / UPI | Yes | Yes |\n| UPI AutoPay / recurring | Yes; activation and method limits | Yes; activation and mandate limits |\n| Card recurring | Yes; tokenisation / mandate rules | Yes; standing instructions |\n| Bank e-mandate | Available with restrictions | eNACH offered |\n| International payments | Supported products/currencies vary | Global collections and international subscriptions advertised |\n| Sandbox | Test mode and webhook testing | Sandbox / DevStudio testing |\n| Best initial path | India-first subscription API | Compare if UPI AutoPay + eNACH/global mix is central |")
        st.caption("This is a capability-level comparison, not a guarantee of account eligibility, pricing, or current enablement. Confirm current product docs, supported countries/currencies, RBI/NPCI rules, fees and contract terms before any adult-managed production deployment.")
        st.markdown("Official documentation: [Razorpay Subscriptions](https://razorpay.com/docs/payments/subscriptions/) · [Razorpay recurring webhook signatures](https://razorpay.com/docs/webhooks/validate-test/) · [Cashfree Subscriptions](https://www.cashfree.com/docs/payments/subscription/) · [Cashfree UPI AutoPay](https://www.cashfree.com/upi-autopay/)")
        st.warning("Live payment onboarding and merchant-account ownership must be handled by an eligible adult/business. This downloadable build intentionally contains no live charge endpoint or production API-key form.")

# ---------- Settings and backup ----------
elif page == "Settings & Backup":
    st.title("Settings & Backup")
    st.subheader("Monthly budget")
    current_budget = st.number_input("Set your monthly subscription budget (₹)",min_value=0.0,
                                     value=float(st.session_state.get("monthly_budget",3000.0)),step=100.0)
    if st.button("Save budget"):
        st.session_state["monthly_budget"] = current_budget
        st.success("Budget saved for this session. For permanent preferences, a settings table can be added to the cloud database.")
        st.rerun()

    st.divider()
    st.subheader("Export your data")
    if not raw.empty:
        st.download_button("Download subscriptions CSV",raw.to_csv(index=False).encode("utf-8"),
                           "subsphere_subscriptions.csv","text/csv")
        backup = {"subscriptions":raw.fillna("").to_dict(orient="records"),
                  "payments":payments.fillna("").to_dict(orient="records")}
        st.download_button("Download complete JSON backup",json.dumps(backup,indent=2,default=str).encode("utf-8"),
                           "subsphere_backup.json","application/json")
    else:
        st.info("Add data before exporting a backup.")

    st.divider()
    st.subheader("Import subscriptions from CSV")
    st.caption("CSV columns must match: name, price, currency, category, billing, next_payment. Optional: status, website, notes.")
    uploaded = st.file_uploader("Choose a SubSphere-compatible CSV",type=["csv"])
    if uploaded is not None and st.button("Import CSV"):
        try:
            incoming = pd.read_csv(uploaded)
            required = {"name","price","currency","category","billing","next_payment"}
            if not required.issubset(incoming.columns):
                st.error("CSV is missing required columns.")
            else:
                count = 0
                for _,r in incoming.iterrows():
                    add_subscription({
                        "name":str(r["name"]),"price":float(r["price"]),
                        "currency":str(r["currency"]),"category":str(r["category"]),
                        "billing":str(r["billing"]),"next_payment":str(r["next_payment"])[:10],
                        "status":str(r.get("status","Active")),
                        "website":str(r.get("website","")),
                        "notes":str(r.get("notes",""))
                    })
                    count += 1
                st.success(f"Imported {count} subscription(s).")
                st.rerun()
        except Exception as exc:
            st.error(f"Could not import CSV: {exc}")

    st.divider()
    st.subheader("Database mode")
    if USE_SUPABASE:
        st.success("Supabase database is configured.")
    else:
        st.warning("Local SQLite mode is active. On hosted deployments, local files may not be durable. Configure Supabase before relying on cloud storage.")
    st.caption("Security: this starter app has no user login. Do not put sensitive personal or payment-card information into it.")

st.divider()
st.caption("◈ SUBSPHERE 3.1  ·  Built with Python and Streamlit  ·  Subscription records are entered manually.")
