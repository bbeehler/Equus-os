import streamlit as st
from supabase import create_client, Client
import datetime

# ----------------------------------------------------
# 1. Configuration & Supabase Connection
# ----------------------------------------------------
st.set_page_config(page_title="EquusOS Hub", page_icon="🐎", layout="wide")

# Replace with your Supabase credentials (or set via .streamlit/secrets.toml)
SUPABASE_URL = "YOUR_SUPABASE_URL_HERE"
SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY_HERE"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# ----------------------------------------------------
# 2. Business Logic Helpers
# ----------------------------------------------------
def calculate_session_fee(duration_minutes: int, is_flagship: bool, is_marketing_tier: bool, previous_minutes: int):
    new_total = previous_minutes + duration_minutes

    if not is_flagship:
        fee = 60.0 if duration_minutes == 20 else duration_minutes * 2.0
        return fee, new_total, "Standard Mobile Rate ($2.00/min)"

    if is_marketing_tier:
        if new_total <= 200:
            return 0.0, new_total, "Promo Allowance (100% Free)"
        billable = duration_minutes if previous_minutes >= 200 else (new_total - 200)
        return float(billable * 1.0), new_total, "Marketing Tier Overage ($1.00/min)"

    if previous_minutes >= 200:
        return float(duration_minutes * 2.0), new_total, "Standard Tier Overage ($2.00/min)"
    if new_total <= 200:
        return float(duration_minutes * 1.0), new_total, "Standard Tier Baseline ($1.00/min)"

    base_mins = 200 - previous_minutes
    overage_mins = new_total - 200
    fee = (base_mins * 1.0) + (overage_mins * 2.0)
    return float(fee), new_total, "Standard Tier (Mixed Baseline & Overage Rate)"

def calculate_travel_fee(distance_km: float, same_day_horses: int):
    if same_day_horses >= 3:
        return 0.0, True, "Group Booking Incentive (3+ Horses: Fee Waived)"
    if distance_km <= 30:
        return 0.0, True, "Within Free 30km Base Radius"
    billable_km = distance_km - 30
    fee = round(billable_km * 0.73, 2)
    return fee, False, f"Standard Mileage ({billable_km:.1f} km @ $0.73/km)"

# ----------------------------------------------------
# 3. Sidebar Navigation
# ----------------------------------------------------
st.sidebar.title("🐎 EquusOS")
st.sidebar.caption("Equus Performance Therapeutics")
page = st.sidebar.radio(
    "Navigation",
    ["Operations & Treatment Feed", "Smart Route Booking", "Client Health Portal"]
)

# ----------------------------------------------------
# Page 1: Operations & Treatment Feed
# ----------------------------------------------------
if page == "Operations & Treatment Feed":
    st.title("Operations & Clinical Hub")
    st.markdown("Log sessions and manage horse profiles across regional facilities.")

    col1, col2 = st.columns(2)

    # Fetch Barns & Horses
    barns_res = supabase.table("barns").select("*").execute()
    barns = barns_res.data if barns_res.data else []
    horses_res = supabase.table("horses").select("*, barns(*)").execute()
    horses = horses_res.data if horses_res.data else []

    with col1:
        with st.expander("➕ Register New Horse Profile", expanded=True):
            with st.form("add_horse_form"):
                h_name = st.text_input("Horse Name")
                o_name = st.text_input("Owner Name")
                barn_opts = {b["name"]: b["id"] for b in barns}
                b_selected = st.selectbox("Select Barn / Facility", options=list(barn_opts.keys())) if barn_opts else None
                is_mktg = st.checkbox("Assign to Marketing Tier (First 200 Mins Free)")
                
                if st.form_submit_button("Save Horse Profile"):
                    if h_name and o_name and b_selected:
                        supabase.table("horses").insert({
                            "name": h_name,
                            "owner_name": o_name,
                            "barn_id": barn_opts[b_selected],
                            "is_marketing_tier": is_mktg,
                            "minutes_used_this_month": 0
                        }).execute()
                        st.success(f"Registered {h_name}!")
                        st.rerun()

    with col2:
        with st.expander("📝 Log Therapeutic Session", expanded=True):
            if horses:
                with st.form("log_treatment_form"):
                    horse_opts = {f"{h['name']} ({h['owner_name']})": h for h in horses}
                    selected_horse_label = st.selectbox("Select Horse", list(horse_opts.keys()))
                    h_obj = horse_opts[selected_horse_label]

                    modality = st.selectbox("Modality", ["Equitron-Pro (HECT)", "HaloEQ2 (Halotherapy)", "Peak Performance Combo"])
                    duration = st.number_input("Session Duration (Minutes)", min_value=5, max_value=120, value=20, step=5)
                    notes = st.text_area("Clinical Observations & Findings")

                    if st.form_submit_button("Record Session & Compute Fee"):
                        is_flagship = h_obj.get("barns", {}).get("is_flagship", False) if h_obj.get("barns") else False
                        fee, updated_mins, note = calculate_session_fee(
                            duration, is_flagship, h_obj.get("is_marketing_tier", False), h_obj.get("minutes_used_this_month", 0)
                        )
                        
                        # Insert treatment log
                        supabase.table("treatment_logs").insert({
                            "horse_id": h_obj["id"],
                            "modality": modality,
                            "duration_minutes": duration,
                            "calculated_fee": fee,
                            "session_notes": f"{notes} [Billing: {note}]"
                        }).execute()

                        # Update horse minutes
                        supabase.table("horses").update({"minutes_used_this_month": updated_mins}).eq("id", h_obj["id"]).execute()
                        st.success(f"Session Logged! Calculated Fee: ${fee:.2f} CAD ({note})")
                        st.rerun()
            else:
                st.info("Please register a horse first.")

    st.subheader("Live Clinical Treatment Feed")
    logs_res = supabase.table("treatment_logs").select("*, horses(*, barns(*))").order("created_at", desc=True).execute()
    if logs_res.data:
        for log in logs_res.data:
            with st.container():
                c1, c2 = st.columns([4, 1])
                with c1:
                    h_info = log.get("horses", {})
                    st.markdown(f"**{h_info.get('name', 'Unknown')}** *(Owner: {h_info.get('owner_name')})* — `{log['modality']}` ({log['duration_minutes']} mins)")
                    st.caption(f"{log['session_notes']}")
                with c2:
                    st.markdown(f"### ${float(log['calculated_fee']):.2f}")
                    st.caption(f"{log['created_at'][:10]}")
                st.divider()
    else:
        st.write("No treatments recorded yet.")

# ----------------------------------------------------
# Page 2: Smart Route Booking
# ----------------------------------------------------
elif page == "Smart Route Booking":
    st.title("Smart Route Corridor Dispatcher")
    st.markdown("Optimize travel routes and automatically calculate mileage fees outside the 30km radius.")

    horses_res = supabase.table("horses").select("*, barns(*)").execute()
    horses = horses_res.data if horses_res.data else []

    col1, col2 = st.columns(2)
    with col1:
        with st.form("booking_form"):
            st.subheader("Book Route Appointment")
            if horses:
                horse_opts = {f"{h['name']} ({h['barns']['name'] if h.get('barns') else 'No Barn'})": h for h in horses}
                h_choice = st.selectbox("Select Horse", list(horse_opts.keys()))
                chosen_horse = horse_opts[h_choice]

                app_date = st.date_input("Appointment Date", datetime.date.today())
                distance = st.number_input("Estimated Distance from Base (km)", min_value=0.0, value=35.0, step=1.0)

                if st.form_submit_button("Confirm Booking"):
                    # Check same day count
                    appts_res = supabase.table("appointments").select("*").eq("appointment_date", str(app_date)).eq("barn_id", chosen_horse.get("barn_id")).execute()
                    same_day_count = (len(appts_res.data) if appts_res.data else 0) + 1

                    travel_fee, is_waived, reason = calculate_travel_fee(distance, same_day_count)

                    supabase.table("appointments").insert({
                        "appointment_date": str(app_date),
                        "horse_id": chosen_horse["id"],
                        "barn_id": chosen_horse.get("barn_id"),
                        "distance_from_base_km": distance,
                        "travel_fee": travel_fee,
                        "status": "Confirmed"
                    }).execute()

                    st.success(f"Appointment Confirmed! Travel Fee: ${travel_fee:.2f} CAD ({reason})")
                    st.rerun()

    with col2:
        st.subheader("Designated Corridor Days")
        st.info("""
        * **Monday:** Ottawa Metro & Russell Home Base
        * **Tuesday:** Kingston Corridor (South)
        * **Wednesday:** Pembroke / Valley Corridor (North)
        * **Thursday:** Montreal Corridor (East)
        * **Friday:** Flagship Barn Dedicated Intensive
        """)

    st.subheader("Scheduled Route Dispatches")
    appts = supabase.table("appointments").select("*, horses(*, barns(*))").order("appointment_date").execute()
    if appts.data:
        for a in appts.data:
            st.write(f"📅 **{a['appointment_date']}** | **{a.get('horses', {}).get('name')}** @ {a.get('horses', {}).get('barns', {}).get('name')} | Travel Fee: `${float(a['travel_fee']):.2f}` CAD")

# ----------------------------------------------------
# Page 3: Client Health Portal
# ----------------------------------------------------
elif page == "Client Health Portal":
    st.title("Client Health & Progress Portal")
    st.markdown("Transparent access for horse owners to review clinical notes and session logs[cite: 7].")

    horses_res = supabase.table("horses").select("*, barns(*)").execute()
    horses = horses_res.data if horses_res.data else []

    if horses:
        owners = sorted(list(set(h["owner_name"] for h in horses if h.get("owner_name"))))
        selected_owner = st.selectbox("Select Registered Owner", owners)

        owner_horses = [h for h in horses if h.get("owner_name") == selected_owner]
        selected_horse_name = st.selectbox("Select Your Horse", [h["name"] for h in owner_horses])
        active_horse = next(h for h in owner_horses if h["name"] == selected_horse_name)

        # Overview Stats
        st.metric(label="Monthly Usage Logged", value=f"{active_horse.get('minutes_used_this_month', 0)} Mins")

        # Display Treatment History
        st.subheader(f"Treatment History: {active_horse['name']}")
        logs = supabase.table("treatment_logs").select("*").eq("horse_id", active_horse["id"]).order("created_at", desc=True).execute()

        if logs.data:
            for log in logs.data:
                st.info(f"""
                **Date:** {log['created_at'][:10]} | **Modality:** {log['modality']} ({log['duration_minutes']} mins)  
                **Observations:** {log['session_notes']}  
                **Amount:** ${float(log['calculated_fee']):.2f} CAD
                """)
        else:
            st.write("No session records found for this horse.")