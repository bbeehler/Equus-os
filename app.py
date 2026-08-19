import datetime
import pandas as pd
import streamlit as st
from supabase import Client, create_client

# ----------------------------------------------------
# 1. Configuration & Supabase Connection
# ----------------------------------------------------
st.set_page_config(page_title="EquusOS Hub", page_icon="🐎", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]


@st.cache_resource
def init_supabase() -> Client:
  return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = init_supabase()


# ----------------------------------------------------
# 2. Business Logic Helpers
# ----------------------------------------------------
def calculate_session_fee(
    duration_minutes: int,
    is_flagship: bool,
    is_marketing_tier: bool,
    previous_minutes: int,
):
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
    return (
        float(duration_minutes * 2.0),
        new_total,
        "Standard Tier Overage ($2.00/min)",
    )
  if new_total <= 200:
    return (
        float(duration_minutes * 1.0),
        new_total,
        "Standard Tier Baseline ($1.00/min)",
    )

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


def get_data_maps():
  try:
    barns_res = supabase.table("barns").select("*").execute()
    barns = barns_res.data if barns_res.data else []
  except Exception:
    barns = []
  barn_map = {b["id"]: b for b in barns}

  try:
    horses_res = supabase.table("horses").select("*").execute()
    horses = horses_res.data if horses_res.data else []
  except Exception:
    horses = []

  for h in horses:
    h["barn_details"] = barn_map.get(
        h.get("barn_id"),
        {
            "name": "No Barn",
            "is_flagship": False,
            "rate_per_minute": 2.0,
            "address": "",
        },
    )

  return barns, horses, barn_map


# ----------------------------------------------------
# 3. Sidebar Navigation
# ----------------------------------------------------
st.sidebar.title("🐎 EquusOS")
st.sidebar.caption("Equus Performance Therapeutics")
page = st.sidebar.radio(
    "Navigation",
    [
        "Operations & Treatment Feed",
        "Smart Route Booking",
        "Client Health Portal",
        "Monthly Invoicing & Exports",
    ],
)

barns, horses, barn_map = get_data_maps()

# ----------------------------------------------------
# Page 1: Operations & Treatment Feed
# ----------------------------------------------------
if page == "Operations & Treatment Feed":
  st.title("Operations & Clinical Hub")
  st.markdown(
      "Log sessions and manage horse profiles across regional facilities."
  )

  # --- EQUIPMENT MAINTENANCE ODOMETER WIDGET ---
  with st.expander(
      "⚙️ Equitron-Pro Service Odometer & Maintenance Tracker", expanded=True
  ):
    try:
      logs_res = (
          supabase.table("treatment_logs")
          .select("duration_minutes, modality")
          .execute()
      )
      all_logs = logs_res.data if logs_res.data else []
    except Exception:
      all_logs = []

    # Sum minutes for Equitron and Combo sessions
    total_equitron_mins = sum(
        l.get("duration_minutes", 0)
        for l in all_logs
        if l.get("modality")
        in ["Equitron-Pro (HECT)", "Peak Performance Combo"]
    )

    SERVICE_INTERVAL = 22000
    progress_val = min(total_equitron_mins / SERVICE_INTERVAL, 1.0)
    remaining_mins = max(0, SERVICE_INTERVAL - total_equitron_mins)
    sinking_fund_reserve = total_equitron_mins * 0.12

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric(
        "Lifetime Operating Minutes", f"{total_equitron_mins:,} Mins"
    )
    col_m2.metric(
        "Minutes Until 22k Recertification", f"{remaining_mins:,} Mins"
    )
    col_m3.metric(
        "Sinking Fund Reserve ($0.12/min)", f"${sinking_fund_reserve:,.2f} CAD"
    )

    st.progress(
        progress_val,
        text=f"Equipment Wear Progress: {total_equitron_mins:,} / {SERVICE_INTERVAL:,} Minutes",
    )

    if total_equitron_mins >= 20000:
      st.error(
          "⚠️ **MAINTENANCE WARNING:** Equitron-Pro is approaching or has"
          " exceeded the 22,000-minute service threshold. Schedule"
          " manufacturer overhaul ($2,000 + freight) and 1-week downtime."
      )
    elif total_equitron_mins >= 18000:
      st.warning(
          "🔔 **Notice:** Equipment is within 4,000 minutes of required"
          " service. Plan upcoming shoulder-season halotherapy focus week."
      )
    else:
      st.success(
          "✅ **System Healthy:** Operating well within manufacturer service"
          " parameters."
      )

  col1, col2 = st.columns(2)

  with col1:
    with st.expander("➕ Register New Horse Profile", expanded=True):
      with st.form("add_horse_form"):
        h_name = st.text_input("Horse Name")
        o_name = st.text_input("Owner Name")
        barn_opts = {b["name"]: b["id"] for b in barns}
        b_selected = (
            st.selectbox("Select Barn / Facility", options=list(barn_opts.keys()))
            if barn_opts
            else None
        )
        is_mktg = st.checkbox(
            "Assign to Marketing Tier (First 200 Mins Free / Month)"
        )

        if st.form_submit_button("Save Horse Profile"):
          if h_name and o_name and b_selected:
            try:
              supabase.table("horses").insert({
                  "name": h_name,
                  "owner_name": o_name,
                  "barn_id": barn_opts[b_selected],
                  "is_marketing_tier": is_mktg,
                  "minutes_used_this_month": 0,
              }).execute()
              st.success(f"Registered {h_name}!")
              st.rerun()
            except Exception as e:
              st.error(f"Error registering horse: {e}")

  with col2:
    with st.expander("📝 Log Therapeutic Session", expanded=True):
      if horses:
        with st.form("log_treatment_form"):
          horse_opts = {f"{h['name']} ({h['owner_name']})": h for h in horses}
          selected_horse_label = st.selectbox(
              "Select Horse", list(horse_opts.keys())
          )
          h_obj = horse_opts[selected_horse_label]

          modality = st.selectbox(
              "Modality",
              [
                  "Equitron-Pro (HECT)",
                  "HaloEQ2 (Halotherapy)",
                  "Peak Performance Combo",
              ],
          )
          duration = st.number_input(
              "Session Duration (Minutes)",
              min_value=5,
              max_value=120,
              value=20,
              step=5,
          )
          notes = st.text_area("Clinical Observations & Findings")

          if st.form_submit_button("Record Session & Compute Fee"):
            try:
              is_flagship = h_obj.get("barn_details", {}).get(
                  "is_flagship", False
              )
              fee, updated_mins, note = calculate_session_fee(
                  int(duration),
                  is_flagship,
                  h_obj.get("is_marketing_tier", False),
                  h_obj.get("minutes_used_this_month", 0),
              )

              supabase.table("treatment_logs").insert({
                  "horse_id": str(h_obj["id"]),
                  "modality": str(modality),
                  "therapies_used": [str(modality)],
                  "duration_minutes": int(duration),
                  "calculated_fee": float(fee),
                  "session_notes": f"{notes} [Billing: {note}]",
              }).execute()

              supabase.table("horses").update(
                  {"minutes_used_this_month": int(updated_mins)}
              ).eq("id", str(h_obj["id"])).execute()

              st.success(
                  f"Session Logged! Calculated Fee: ${fee:.2f} CAD ({note})"
              )
              st.rerun()
            except Exception as e:
              st.error(f"Error logging session: {e}")
      else:
        st.info("Please register a horse first.")

  st.subheader("Live Clinical Treatment Feed")
  try:
    logs_res = (
        supabase.table("treatment_logs")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    logs = logs_res.data if logs_res.data else []
  except Exception:
    logs = []

  horse_map = {h["id"]: h for h in horses}

  if logs:
    for log in logs:
      with st.container():
        c1, c2 = st.columns([4, 1])
        h_info = horse_map.get(log.get("horse_id"), {})
        b_info = h_info.get("barn_details", {})
        with c1:
          st.markdown(
              f"**{h_info.get('name', 'Unknown')}** *(Owner:"
              f" {h_info.get('owner_name', 'N/A')} |"
              f" {b_info.get('name', 'No Barn')})* —"
              f" `{log.get('modality', 'Therapy')}`"
              f" ({log.get('duration_minutes', 20)} mins)"
          )
          st.caption(f"{log.get('session_notes', '')}")
        with c2:
          st.markdown(f"### ${float(log.get('calculated_fee', 0)):.2f}")
          st.caption(f"{log.get('created_at', '')[:10]}")
        st.divider()
  else:
    st.write("No treatments recorded yet.")

# ----------------------------------------------------
# Page 2: Smart Route Booking
# ----------------------------------------------------
elif page == "Smart Route Booking":
  st.title("Smart Route Corridor Dispatcher")
  st.markdown(
      "Optimize travel routes and automatically calculate mileage fees outside"
      " the 30km radius."
  )

  col1, col2 = st.columns(2)
  with col1:
    with st.form("booking_form"):
      st.subheader("Book Route Appointment")
      if horses:
        horse_opts = {
            f"{h['name']} ({h['barn_details']['name']})": h for h in horses
        }
        h_choice = st.selectbox("Select Horse", list(horse_opts.keys()))
        chosen_horse = horse_opts[h_choice]

        app_date = st.date_input("Appointment Date", datetime.date.today())
        distance = st.number_input(
            "Estimated Distance from Base (km)",
            min_value=0.0,
            value=35.0,
            step=1.0,
        )

        if st.form_submit_button("Confirm Booking"):
          try:
            barn_id_val = chosen_horse.get("barn_id")

            query = (
                supabase.table("appointments")
                .select("id")
                .eq("appointment_date", str(app_date))
            )
            if barn_id_val:
              query = query.eq("barn_id", str(barn_id_val))

            appts_res = query.execute()
            same_day_count = (len(appts_res.data) if appts_res.data else 0) + 1

            travel_fee, is_waived, reason = calculate_travel_fee(
                float(distance), same_day_count
            )

            payload = {
                "appointment_date": str(app_date),
                "horse_id": str(chosen_horse["id"]),
                "distance_from_base_km": float(distance),
                "travel_fee": float(travel_fee),
                "status": "Confirmed",
            }
            if barn_id_val:
              payload["barn_id"] = str(barn_id_val)

            supabase.table("appointments").insert(payload).execute()

            st.success(
                f"Appointment Confirmed! Travel Fee: ${travel_fee:.2f} CAD"
                f" ({reason})"
            )
            st.rerun()
          except Exception as err:
            st.error(f"Booking Error: {err}")

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
  try:
    appts_res = (
        supabase.table("appointments")
        .select("*")
        .order("appointment_date")
        .execute()
    )
    appts = appts_res.data if appts_res.data else []
  except Exception:
    appts = []

  horse_map = {h["id"]: h for h in horses}

  if appts:
    for a in appts:
      h_obj = horse_map.get(a.get("horse_id"), {})
      b_name = h_obj.get("barn_details", {}).get("name", "Barn")
      st.write(
          f"📅 **{a.get('appointment_date')}** |"
          f" **{h_obj.get('name', 'Horse')}** @ {b_name} | Travel Fee:"
          f" `${float(a.get('travel_fee', 0)):.2f}` CAD"
      )
  else:
    st.write("No appointments scheduled.")

# ----------------------------------------------------
# Page 3: Client Health Portal
# ----------------------------------------------------
elif page == "Client Health Portal":
  st.title("Client Health & Progress Portal")
  st.markdown(
      "Transparent access for horse owners to review clinical notes and session"
      " logs."
  )

  if horses:
    owners = sorted(
        list(set(h["owner_name"] for h in horses if h.get("owner_name")))
    )
    selected_owner = st.selectbox("Select Registered Owner", owners)

    owner_horses = [h for h in horses if h.get("owner_name") == selected_owner]
    selected_horse_name = st.selectbox(
        "Select Your Horse", [h["name"] for h in owner_horses]
    )
    active_horse = next(
        h for h in owner_horses if h["name"] == selected_horse_name
    )

    st.metric(
        label="Monthly Usage Logged",
        value=f"{active_horse.get('minutes_used_this_month', 0)} Mins",
    )

    st.subheader(f"Treatment History: {active_horse['name']}")
    try:
      logs_res = (
          supabase.table("treatment_logs")
          .select("*")
          .eq("horse_id", str(active_horse["id"]))
          .order("created_at", desc=True)
          .execute()
      )
      logs = logs_res.data if logs_res.data else []
    except Exception:
      logs = []

    if logs:
      for log in logs:
        st.info(f"""
                **Date:** {log.get('created_at', '')[:10]} | **Modality:** {log.get('modality', 'Therapy')} ({log.get('duration_minutes', 20)} mins)  
                **Observations:** {log.get('session_notes', '')}  
                **Amount:** ${float(log.get('calculated_fee', 0)):.2f} CAD
                """)
    else:
      st.write("No session records found for this horse.")
  else:
    st.info("No horses registered in the database yet.")

# ----------------------------------------------------
# Page 4: Monthly Invoicing & Exports
# ----------------------------------------------------
elif page == "Monthly Invoicing & Exports":
  st.title("Monthly Invoicing & Billing Summary")
  st.markdown(
      "Generate monthly billing breakdowns and export itemized CSV statements"
      " for barns and owners."
  )

  if barns:
    barn_opts = {b["name"]: b["id"] for b in barns}
    chosen_barn_name = st.selectbox("Select Barn / Facility", list(barn_opts.keys()))
    chosen_barn_id = barn_opts[chosen_barn_name]

    facility_horses = [h for h in horses if h.get("barn_id") == chosen_barn_id]
    facility_horse_ids = [h["id"] for h in facility_horses]

    try:
      logs_res = (
          supabase.table("treatment_logs")
          .select("*")
          .order("created_at", desc=True)
          .execute()
      )
      all_logs = logs_res.data if logs_res.data else []
    except Exception:
      all_logs = []

    facility_logs = [
        l for l in all_logs if l.get("horse_id") in facility_horse_ids
    ]
    horse_dict = {h["id"]: h for h in facility_horses}

    if facility_logs:
      invoice_rows = []
      total_billed = 0.0

      for l in facility_logs:
        h = horse_dict.get(l.get("horse_id"), {})
        fee = float(l.get("calculated_fee", 0))
        total_billed += fee
        invoice_rows.append({
            "Date": l.get("created_at", "")[:10],
            "Horse Name": h.get("name", "Unknown"),
            "Owner": h.get("owner_name", "Unknown"),
            "Modality": l.get("modality", ""),
            "Duration (Mins)": l.get("duration_minutes", 0),
            "Fee (CAD)": f"${fee:.2f}",
            "Notes": l.get("session_notes", ""),
        })

      df_invoice = pd.DataFrame(invoice_rows)

      c1, c2, c3 = st.columns(3)
      c1.metric(
          "Total Horses Active",
          len(set([r["Horse Name"] for r in invoice_rows])),
      )
      c2.metric("Total Sessions", len(invoice_rows))
      c3.metric("Facility Total Billed", f"${total_billed:.2f} CAD")

      st.dataframe(df_invoice, use_container_width=True)

      csv_data = df_invoice.to_csv(index=False).encode("utf-8")
      st.download_button(
          label="📥 Download Itemized Billing Statement (CSV)",
          data=csv_data,
          file_name=f"EquusOS_Invoice_{chosen_barn_name.replace(' ', '_')}_{datetime.date.today()}.csv",
          mime="text/csv",
      )
    else:
      st.info(f"No treatment sessions on record for {chosen_barn_name}.")
  else:
    st.info("No barns registered in the database.")
