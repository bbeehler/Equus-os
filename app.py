import datetime
import io
import pandas as pd
from fpdf import FPDF
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
            "address": "Local Mobile",
        },
    )

  return barns, horses, barn_map


# ----------------------------------------------------
# 3. PDF Generator Classes
# ----------------------------------------------------
class PDFInvoice(FPDF):

  def header(self):
    self.set_font("helvetica", "B", 16)
    self.cell(0, 8, "EQUUS PERFORMANCE THERAPEUTICS", 0, 1, "L")
    self.set_font("helvetica", "", 10)
    self.cell(
        0,
        5,
        "Equine Cellular Regeneration & Pulmonary Recovery | Russell, ON",
        0,
        1,
        "L",
    )
    self.ln(5)
    self.set_draw_color(100, 100, 100)
    self.line(10, self.get_y(), 200, self.get_y())
    self.ln(5)

  def footer(self):
    self.set_y(-15)
    self.set_font("helvetica", "I", 8)
    self.cell(
        0,
        10,
        f"Page {self.page_no()} | Equus Performance Therapeutics - Official"
        " Record",
        0,
        0,
        "C",
    )


def create_pdf_invoice(barn_name, invoice_rows, total_billed):
  pdf = PDFInvoice()
  pdf.add_page()
  pdf.set_font("helvetica", "B", 14)
  pdf.cell(0, 8, f"STATEMENT OF ACCOUNT: {barn_name.upper()}", 0, 1, "L")

  pdf.set_font("helvetica", "", 10)
  pdf.cell(
      0, 6, f"Statement Date: {datetime.date.today().strftime('%B %d, %Y')}", 0, 1
  )
  pdf.cell(0, 6, "Payment Terms: Due upon receipt via e-Transfer", 0, 1)
  pdf.ln(5)

  pdf.set_font("helvetica", "B", 9)
  pdf.set_fill_color(240, 240, 240)
  pdf.cell(22, 7, "Date", 1, 0, "C", True)
  pdf.cell(38, 7, "Horse Name", 1, 0, "L", True)
  pdf.cell(32, 7, "Owner", 1, 0, "L", True)
  pdf.cell(38, 7, "Modality", 1, 0, "L", True)
  pdf.cell(15, 7, "Mins", 1, 0, "C", True)
  pdf.cell(22, 7, "Fee (CAD)", 1, 0, "R", True)
  pdf.cell(23, 7, "Notes", 1, 1, "L", True)

  pdf.set_font("helvetica", "", 8)
  for r in invoice_rows:
    pdf.cell(22, 6, str(r["Date"]), 1, 0, "C")
    pdf.cell(38, 6, str(r["Horse Name"][:20]), 1, 0, "L")
    pdf.cell(32, 6, str(r["Owner"][:18]), 1, 0, "L")
    pdf.cell(38, 6, str(r["Modality"][:20]), 1, 0, "L")
    pdf.cell(15, 6, str(r["Duration (Mins)"]), 1, 0, "C")
    pdf.cell(22, 6, str(r["Fee (CAD)"]), 1, 0, "R")
    pdf.cell(23, 6, str(r["Notes"][:15]), 1, 1, "L")

  pdf.ln(5)
  pdf.set_font("helvetica", "B", 12)
  pdf.cell(0, 8, f"Total Balance Due: ${total_billed:.2f} CAD", 0, 1, "R")

  return pdf.output()


def create_vet_report_pdf(horse_obj, vet_name, clinical_logs):
  pdf = PDFInvoice()
  pdf.add_page()

  pdf.set_font("helvetica", "B", 14)
  pdf.cell(0, 8, "CLINICAL THERAPY & REHABILITATION SUMMARY", 0, 1, "L")
  pdf.set_font("helvetica", "", 10)
  pdf.cell(
      0, 5, f"Report Date: {datetime.date.today().strftime('%B %d, %Y')}", 0, 1
  )
  pdf.cell(0, 5, "Attending Specialist: Paige Cummings (EquusOS Hub)", 0, 1)
  pdf.ln(3)

  pdf.set_fill_color(245, 245, 245)
  pdf.rect(10, pdf.get_y(), 190, 22, "F")
  pdf.set_xy(12, pdf.get_y() + 2)

  pdf.set_font("helvetica", "B", 10)
  pdf.cell(
      90,
      5,
      f"Patient: {horse_obj.get('name', 'N/A')} (Owner:"
      f" {horse_obj.get('owner_name', 'N/A')})",
      0,
      0,
  )
  pdf.cell(
      90,
      5,
      f"Facility: {horse_obj.get('barn_details', {}).get('name', 'N/A')}",
      0,
      1,
  )
  pdf.set_xy(12, pdf.get_y())
  pdf.set_font("helvetica", "", 9)
  pdf.cell(
      90, 5, f"Primary Veterinarian: {vet_name if vet_name else 'On File'}", 0, 0
  )
  total_mins = sum(int(l.get("duration_minutes", 0)) for l in clinical_logs)
  pdf.cell(90, 5, f"Cumulative Therapy Logged: {total_mins} Minutes", 0, 1)
  pdf.ln(8)

  pdf.set_font("helvetica", "B", 11)
  pdf.cell(0, 7, "Chronological Treatment History & Clinical Notes", 0, 1)

  for log in clinical_logs:
    pdf.set_draw_color(200, 200, 200)
    pdf.set_font("helvetica", "B", 9)
    date_str = str(log.get("created_at", ""))[:10]
    modality_str = str(log.get("modality", "Therapy"))
    mins_str = str(log.get("duration_minutes", "20"))
    pdf.cell(0, 6, f"[{date_str}] - {modality_str} ({mins_str} mins)", "B", 1)

    pdf.set_font("helvetica", "", 8)
    notes_clean = str(
        log.get("session_notes", "Routine complementary therapy administered.")
    )
    pdf.multi_cell(0, 5, f"Observations: {notes_clean}")
    pdf.ln(2)

  pdf.ln(4)
  pdf.set_font("helvetica", "I", 8)
  pdf.multi_cell(
      0,
      4,
      "Disclaimer: Equus Performance Therapeutics provides complementary"
      " non-invasive wellness, high-energy cellular bio-stimulation, and dry"
      " salt halotherapy. This summary is intended to support collaborative"
      " veterinary diagnosis and management.",
  )

  return pdf.output()


# ----------------------------------------------------
# 4. Sidebar Navigation
# ----------------------------------------------------
st.sidebar.title("🐎 EquusOS")
st.sidebar.caption("Equus Performance Therapeutics")
page = st.sidebar.radio(
    "Navigation",
    [
        "Operations & Treatment Feed",
        "Smart Route Booking",
        "Corridor Calendar & Run-Sheet",
        "Client Intake & Waiver",
        "Client Health Portal",
        "Monthly Invoicing & Exports",
        "Payments & Accounts Receivable",
        "Veterinary Clinical Reports",
        "Corridor Travel & Expense Tracker",
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

  with st.expander(
      "⚙️ Equitron-Pro Service Odometer & Maintenance Tracker", expanded=False
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
          f" `${float(a.get('travel_fee', 0)):.2f}` CAD | Status:"
          f" `{a.get('status', 'Confirmed')}`"
      )
  else:
    st.write("No appointments scheduled.")

# ----------------------------------------------------
# Page 3: Corridor Calendar & Daily Run-Sheet (NEW MODULE)
# ----------------------------------------------------
elif page == "Corridor Calendar & Run-Sheet":
  st.title("📅 Corridor Schedule & Daily Dispatch Run-Sheet")
  st.markdown(
      "Organize weekly corridor runs, track stop order, and generate daily"
      " mobile dispatch sheets."
  )

  try:
    appts_res = (
        supabase.table("appointments")
        .select("*")
        .order("appointment_date")
        .execute()
    )
    all_appts = appts_res.data if appts_res.data else []
  except Exception:
    all_appts = []

  horse_map = {h["id"]: h for h in horses}

  col_d1, col_d2 = st.columns([1, 2])

  with col_d1:
    st.subheader("Select Run-Sheet Date")
    selected_run_date = st.date_input(
        "Dispatch Date", datetime.date.today(), key="run_date_picker"
    )

    day_of_week = selected_run_date.strftime("%A")
    corridor_match = {
        "Monday": "Ottawa Metro & Russell Home Corridor",
        "Tuesday": "Kingston Corridor (South - Hwy 416/401)",
        "Wednesday": "Pembroke & Upper Valley Corridor (North - Hwy 17)",
        "Thursday": "Montreal Corridor (East - Hwy 417)",
        "Friday": "Flagship Barn Dedicated Intensive",
    }.get(day_of_week, "Custom / Weekend Route")

    st.info(f"📍 **Scheduled Corridor:** {corridor_match}")

  with col_d2:
    daily_appts = [
        a for a in all_appts if a.get("appointment_date") == str(selected_run_date)
    ]

    st.subheader(
        f"Daily Stop Itinerary: {selected_run_date.strftime('%b %d, %Y')} ({len(daily_appts)} Stops)"
    )

    if daily_appts:
      for idx, appt in enumerate(daily_appts, start=1):
        h_info = horse_map.get(appt.get("horse_id"), {})
        b_info = h_info.get("barn_details", {})
        with st.container():
          c_s1, c_s2 = st.columns([3, 1])
          with c_s1:
            st.markdown(
                f"**Stop {idx}: {h_info.get('name', 'Horse')}** (Owner:"
                f" {h_info.get('owner_name', 'N/A')})"
            )
            st.caption(
                f"📍 Facility: **{b_info.get('name', 'Barn')}** | Distance:"
                f" {appt.get('distance_from_base_km', 0)} km | Fee:"
                f" ${float(appt.get('travel_fee', 0)):.2f}"
            )
          with c_s2:
            new_status = st.selectbox(
                "Status",
                ["Confirmed", "En Route", "Completed", "Rescheduled"],
                index=["Confirmed", "En Route", "Completed", "Rescheduled"].index(
                    appt.get("status", "Confirmed")
                ),
                key=f"status_select_{appt['id']}",
            )
            if new_status != appt.get("status"):
              supabase.table("appointments").update(
                  {"status": new_status}
              ).eq("id", appt["id"]).execute()
              st.rerun()
          st.divider()

      run_sheet_df = pd.DataFrame([
          {
              "Stop": i + 1,
              "Horse": horse_map.get(a.get("horse_id"), {}).get("name", ""),
              "Owner": horse_map.get(a.get("horse_id"), {}).get("owner_name", ""),
              "Barn / Facility": horse_map.get(a.get("horse_id"), {})
              .get("barn_details", {})
              .get("name", ""),
              "Distance (km)": a.get("distance_from_base_km", 0),
              "Travel Fee": f"${float(a.get('travel_fee', 0)):.2f}",
              "Status": a.get("status", "Confirmed"),
          }
          for i, a in enumerate(daily_appts)
      ])

      csv_sheet = run_sheet_df.to_csv(index=False).encode("utf-8")
      st.download_button(
          label="📥 Export Daily Dispatch Run-Sheet (CSV)",
          data=csv_sheet,
          file_name=f"EquusOS_RunSheet_{selected_run_date}.csv",
          mime="text/csv",
      )
    else:
      st.info(f"No appointments booked for {selected_run_date.strftime('%A, %B %d, %Y')}.")

  st.subheader("Upcoming 14-Day Dispatch Outlook")
  if all_appts:
    outlook_rows = []
    for a in all_appts:
      h_obj = horse_map.get(a.get("horse_id"), {})
      outlook_rows.append({
          "Date": a.get("appointment_date"),
          "Horse": h_obj.get("name", "N/A"),
          "Owner": h_obj.get("owner_name", "N/A"),
          "Barn": h_obj.get("barn_details", {}).get("name", "N/A"),
          "Travel Fee": f"${float(a.get('travel_fee', 0)):.2f}",
          "Status": a.get("status", "Confirmed"),
      })
    st.dataframe(pd.DataFrame(outlook_rows), use_container_width=True)

# ----------------------------------------------------
# Page 4: Client Intake & Waiver
# ----------------------------------------------------
elif page == "Client Intake & Waiver":
  st.title("Client Onboarding & Legal Liability Waiver")
  st.markdown(
      "New clients must complete this intake form and execute the liability"
      " acknowledgment prior to receiving treatment."
  )

  with st.form("client_waiver_form"):
    st.subheader("1. Owner & Horse Details")
    col_w1, col_w2 = st.columns(2)
    with col_w1:
      owner_name = st.text_input("Owner Full Name")
      client_email = st.text_input("Email Address")
      horse_name = st.text_input("Horse Competition Name")
    with col_w2:
      primary_vet = st.text_input("Primary Veterinarian Name")
      vet_phone = st.text_input("Veterinarian Contact Number")

    st.subheader("2. Modality Consent Selection")
    consent_hect = st.checkbox(
        "Consent for High-Energy Cell Treatment (Equitron-Pro / HECT)"
    )
    consent_halo = st.checkbox(
        "Consent for Clinical Dry Salt Halotherapy (HaloEQ2)"
    )

    st.subheader("3. Terms & Liability Acknowledgment")
    st.markdown("""
        > **Scope of Practice & Release of Liability:**  
        > Equus Performance Therapeutics provides non-invasive complementary equine wellness, cellular regeneration, and respiratory recovery support. These services do not replace formal veterinary diagnosis, medicine, or surgery. The undersigned owner confirms that the animal is free of acute, contagious infectious diseases, and releases Paige Cummings and Equus Performance Therapeutics from liability arising from complementary therapy applications.
        """)

    waiver_agreed = st.checkbox(
        "I have read, understood, and agree to the terms of service and"
        " liability waiver."
    )
    signature_name = st.text_input(
        "Electronic Signature (Type Full Legal Name)"
    )

    if st.form_submit_button("Submit Intake & Signed Waiver"):
      if owner_name and client_email and horse_name and signature_name:
        if not waiver_agreed:
          st.error(
              "You must check the waiver agreement box to complete onboarding."
          )
        else:
          try:
            modalities_chosen = []
            if consent_hect:
              modalities_chosen.append("Equitron-Pro (HECT)")
            if consent_halo:
              modalities_chosen.append("HaloEQ2 (Halotherapy)")

            supabase.table("client_waivers").insert({
                "owner_name": owner_name,
                "client_email": client_email,
                "horse_name": horse_name,
                "primary_veterinarian": primary_vet,
                "vet_phone": vet_phone,
                "modality_consent": modalities_chosen,
                "waiver_agreed": waiver_agreed,
                "signature_name": signature_name,
            }).execute()

            st.success(
                f"Waiver successfully executed and archived for {horse_name}"
                f" (Owner: {owner_name})!"
            )
          except Exception as e:
            st.error(f"Error saving waiver: {e}")
      else:
        st.warning(
            "Please fill in all required contact fields and provide your"
            " electronic signature."
        )

  st.subheader("Archived Client Waivers & Onboarding Records")
  try:
    waivers_res = (
        supabase.table("client_waivers")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    saved_waivers = waivers_res.data if waivers_res.data else []
  except Exception:
    saved_waivers = []

  if saved_waivers:
    for w in saved_waivers:
      st.info(f"""
            **Owner:** {w.get('owner_name')} ({w.get('client_email')}) | **Horse:** {w.get('horse_name')}  
            **Veterinarian:** {w.get('primary_veterinarian', 'N/A')} ({w.get('vet_phone', 'N/A')})  
            **Modalities Authorized:** {', '.join(w.get('modality_consent', []))}  
            **Signed By:** {w.get('signature_name')} on {w.get('created_at', '')[:10]}
            """)
  else:
    st.write("No waivers on record yet.")

# ----------------------------------------------------
# Page 5: Client Health Portal
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
# Page 6: Monthly Invoicing & Exports
# ----------------------------------------------------
elif page == "Monthly Invoicing & Exports":
  st.title("Monthly Invoicing & Billing Summary")
  st.markdown(
      "Generate monthly billing breakdowns and export professional PDF"
      " statements for barns and owners."
  )

  if barns:
    barn_opts = {b["name"]: b["id"] for b in barns}
    chosen_barn_name = st.selectbox(
        "Select Barn / Facility", list(barn_opts.keys())
    )
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

      pdf_output = create_pdf_invoice(
          chosen_barn_name, invoice_rows, total_billed
      )

      st.download_button(
          label="📄 Download Professional PDF Invoice",
          data=bytes(pdf_output),
          file_name=f"EquusOS_Invoice_{chosen_barn_name.replace(' ', '_')}_{datetime.date.today()}.pdf",
          mime="application/pdf",
      )
    else:
      st.info(f"No treatment sessions on record for {chosen_barn_name}.")
  else:
    st.info("No barns registered in the database.")

# ----------------------------------------------------
# Page 7: Payments & Accounts Receivable
# ----------------------------------------------------
elif page == "Payments & Accounts Receivable":
  st.title("💳 Accounts Receivable & Payment Tracking")
  st.markdown(
      "Record received payments from horse owners and monitor outstanding"
      " account balances."
  )

  try:
    all_logs_res = supabase.table("treatment_logs").select("*").execute()
    all_logs_data = all_logs_res.data if all_logs_res.data else []
  except Exception:
    all_logs_data = []

  try:
    all_pmts_res = (
        supabase.table("client_payments")
        .select("*")
        .order("payment_date", desc=True)
        .execute()
    )
    all_pmts_data = all_pmts_res.data if all_pmts_res.data else []
  except Exception:
    all_pmts_data = []

  horse_id_to_owner = {
      h["id"]: h.get("owner_name", "Unknown") for h in horses
  }
  all_owners = sorted(
      list(
          set(
              [h.get("owner_name") for h in horses if h.get("owner_name")]
              + [p.get("owner_name") for p in all_pmts_data]
          )
      )
  )

  total_revenue_billed = sum(
      float(l.get("calculated_fee", 0)) for l in all_logs_data
  )
  total_revenue_received = sum(
      float(p.get("amount_paid", 0)) for p in all_pmts_data
  )
  total_outstanding_ar = total_revenue_billed - total_revenue_received

  m1, m2, m3 = st.columns(3)
  m1.metric("Total Billed to Date", f"${total_revenue_billed:,.2f} CAD")
  m2.metric("Total Payments Collected", f"${total_revenue_received:,.2f} CAD")
  m3.metric(
      "Outstanding A/R Balance",
      f"${total_outstanding_ar:,.2f} CAD",
      delta=f"-${total_outstanding_ar:,.2f}"
      if total_outstanding_ar > 0
      else "Paid in Full",
      delta_color="inverse",
  )

  col_pay1, col_pay2 = st.columns(2)

  with col_pay1:
    with st.expander("💵 Record Client Payment", expanded=True):
      with st.form("record_payment_form"):
        p_owner = st.selectbox(
            "Select Owner / Client",
            all_owners
            if all_owners
            else ["Please register a horse/owner first"],
        )
        p_date = st.date_input("Payment Date", datetime.date.today())
        p_amount = st.number_input(
            "Amount Paid (CAD)", min_value=0.0, step=10.0, value=60.0
        )
        p_method = st.selectbox(
            "Payment Method", ["e-Transfer", "Cheque", "Credit Card", "Cash"]
        )
        p_ref = st.text_input("Reference / Confirmation # (Optional)")
        p_notes = st.text_area("Notes / Invoice Applied To")

        if st.form_submit_button("Save Payment Record"):
          if p_owner and p_amount > 0:
            try:
              supabase.table("client_payments").insert({
                  "payment_date": str(p_date),
                  "owner_name": p_owner,
                  "amount_paid": float(p_amount),
                  "payment_method": p_method,
                  "reference_number": p_ref,
                  "notes": p_notes,
              }).execute()
              st.success(f"Recorded ${p_amount:.2f} payment from {p_owner}!")
              st.rerun()
            except Exception as e:
              st.error(f"Error saving payment: {e}")
          else:
            st.warning("Please enter a valid amount and select an owner.")

  with col_pay2:
    with st.expander("📊 Owner Balance Breakdown", expanded=True):
      if all_owners:
        owner_balances = []
        for o in all_owners:
          o_billed = sum(
              float(l.get("calculated_fee", 0))
              for l in all_logs_data
              if horse_id_to_owner.get(l.get("horse_id")) == o
          )
          o_paid = sum(
              float(p.get("amount_paid", 0))
              for p in all_pmts_data
              if p.get("owner_name") == o
          )
          o_balance = o_billed - o_paid
          owner_balances.append({
              "Owner Name": o,
              "Total Billed": f"${o_billed:,.2f}",
              "Total Paid": f"${o_paid:,.2f}",
              "Balance Due": f"${o_balance:,.2f}",
              "Status": "✅ Paid" if o_balance <= 0 else "⚠️ Outstanding",
          })

        st.dataframe(pd.DataFrame(owner_balances), use_container_width=True)
      else:
        st.write("No owner accounts active.")

  st.subheader("Recent Payment History")
  if all_pmts_data:
    for p in all_pmts_data:
      with st.container():
        c_p1, c_p2 = st.columns([4, 1])
        with c_p1:
          st.markdown(
              f"**{p.get('owner_name')}** — `${float(p.get('amount_paid', 0)):.2f}`"
              f" CAD via `{p.get('payment_method')}`"
          )
          ref_txt = (
              f"Ref: {p.get('reference_number')} | "
              if p.get("reference_number")
              else ""
          )
          st.caption(f"{ref_txt}{p.get('notes', '')}")
        with c_p2:
          st.markdown(f"📅 **{p.get('payment_date')}**")
        st.divider()
  else:
    st.write("No payments recorded yet.")

# ----------------------------------------------------
# Page 8: Veterinary Clinical Reports
# ----------------------------------------------------
elif page == "Veterinary Clinical Reports":
  st.title("🩺 Veterinary Clinical Summary Reports")
  st.markdown(
      "Generate concise, professional clinical treatment summaries for"
      " veterinarians and training teams."
  )

  if horses:
    col_v1, col_v2 = st.columns([1, 2])

    with col_v1:
      horse_lookup = {
          f"{h['name']} ({h['owner_name']} | {h['barn_details']['name']})": h
          for h in horses
      }
      sel_label = st.selectbox(
          "Select Horse for Clinical Report", list(horse_lookup.keys())
      )
      chosen_horse_obj = horse_lookup[sel_label]

      try:
        w_res = (
            supabase.table("client_waivers")
            .select("primary_veterinarian, vet_phone")
            .eq("horse_name", chosen_horse_obj.get("name"))
            .execute()
        )
        vet_info = w_res.data[0] if w_res.data else {}
      except Exception:
        vet_info = {}

      default_vet = vet_info.get("primary_veterinarian", "")
      vet_contact_input = st.text_input(
          "Primary Veterinarian",
          value=default_vet if default_vet else "Attending Equine DVM",
      )

      try:
        h_logs_res = (
            supabase.table("treatment_logs")
            .select("*")
            .eq("horse_id", str(chosen_horse_obj["id"]))
            .order("created_at", desc=True)
            .execute()
        )
        horse_logs = h_logs_res.data if h_logs_res.data else []
      except Exception:
        horse_logs = []

    with col_v2:
      st.subheader(f"Clinical Summary: {chosen_horse_obj['name']}")
      st.markdown(
          f"**Owner:** {chosen_horse_obj['owner_name']} | **Facility:**"
          f" {chosen_horse_obj['barn_details']['name']}"
      )

      if horse_logs:
        st.write(f"Total Recorded Sessions: **{len(horse_logs)}**")

        for l in horse_logs[:3]:
          st.caption(
              f"• **{l.get('created_at', '')[:10]}** —"
              f" `{l.get('modality')}` ({l.get('duration_minutes')} mins):"
              f" {l.get('session_notes')}"
          )

        vet_pdf_bytes = create_vet_report_pdf(
            chosen_horse_obj, vet_contact_input, horse_logs
        )

        st.download_button(
            label="📄 Export Veterinary Clinical Report (PDF)",
            data=bytes(vet_pdf_bytes),
            file_name=f"EquusOS_Clinical_Report_{chosen_horse_obj['name'].replace(' ', '_')}_{datetime.date.today()}.pdf",
            mime="application/pdf",
        )
      else:
        st.info("No clinical sessions recorded for this horse yet.")
  else:
    st.info("Please register a horse profile first.")

# ----------------------------------------------------
# Page 9: Corridor Travel & Expense Tracker
# ----------------------------------------------------
elif page == "Corridor Travel & Expense Tracker":
  st.title("🚗 Corridor Travel & Operational Expense Tracker")
  st.markdown(
      "Log travel expenses, track fuel and maintenance costs, and analyze net"
      " profitability across regional corridors."
  )

  try:
    exp_res = (
        supabase.table("corridor_expenses")
        .select("*")
        .order("expense_date", desc=True)
        .execute()
    )
    all_expenses = exp_res.data if exp_res.data else []
  except Exception:
    all_expenses = []

  try:
    appts_res = supabase.table("appointments").select("travel_fee").execute()
    all_appts = appts_res.data if appts_res.data else []
    total_travel_collected = sum(
        float(a.get("travel_fee", 0)) for a in all_appts
    )
  except Exception:
    total_travel_collected = 0.0

  total_expenses_logged = sum(
      float(e.get("amount", 0)) for e in all_expenses
  )
  fuel_total = sum(
      float(e.get("amount", 0))
      for e in all_expenses
      if e.get("category") == "Fuel"
  )
  net_travel_margin = total_travel_collected - total_expenses_logged

  m1, m2, m3, m4 = st.columns(4)
  m1.metric(
      "Total Expenses Logged", f"${total_expenses_logged:,.2f} CAD"
  )
  m2.metric("Fuel Costs Total", f"${fuel_total:,.2f} CAD")
  m3.metric(
      "Mileage Fees Collected", f"${total_travel_collected:,.2f} CAD"
  )
  m4.metric(
      "Net Travel Margin",
      f"${net_travel_margin:,.2f} CAD",
      delta=f"${net_travel_margin:,.2f}",
      delta_color="normal" if net_travel_margin >= 0 else "inverse",
  )

  col_e1, col_e2 = st.columns(2)

  with col_e1:
    with st.expander("⛽ Log Travel Expense", expanded=True):
      with st.form("log_expense_form"):
        e_date = st.date_input("Expense Date", datetime.date.today())
        e_corridor = st.selectbox(
            "Regional Corridor",
            [
                "Monday: Ottawa Metro & Russell",
                "Tuesday: Kingston Corridor (South)",
                "Wednesday: Pembroke / Valley (North)",
                "Thursday: Montreal Corridor (East)",
                "Friday: Flagship Dedicated",
                "General / Fleet Operations",
            ],
        )
        e_category = st.selectbox(
            "Expense Category",
            [
                "Fuel",
                "Vehicle Maintenance / Tires",
                "Parking & Tolls",
                "Equipment Consumables / Salt",
                "Other Operational",
            ],
        )
        e_amount = st.number_input(
            "Amount (CAD)", min_value=0.0, step=5.0, value=75.0
        )
        e_odo = st.number_input(
            "Odometer Reading (km) - Optional",
            min_value=0,
            step=100,
            value=0,
        )
        e_receipt = st.text_input("Receipt Ref / Vendor Name (Optional)")
        e_notes = st.text_area("Expense Notes")

        if st.form_submit_button("Record Operational Expense"):
          if e_amount > 0:
            try:
              payload = {
                  "expense_date": str(e_date),
                  "corridor": e_corridor,
                  "category": e_category,
                  "amount": float(e_amount),
                  "odometer_reading": int(e_odo) if e_odo > 0 else None,
                  "receipt_ref": e_receipt,
                  "notes": e_notes,
              }
              supabase.table("corridor_expenses").insert(payload).execute()
              st.success(
                  f"Recorded ${e_amount:.2f} CAD for {e_category} on"
                  f" {e_corridor}!"
              )
              st.rerun()
            except Exception as ex:
              st.error(f"Error saving expense: {ex}")
          else:
            st.warning("Please enter a valid amount.")

  with col_e2:
    with st.expander("📈 Expense Category Breakdown", expanded=True):
      if all_expenses:
        cat_breakdown = {}
        for e in all_expenses:
          c = e.get("category", "Other")
          cat_breakdown[c] = cat_breakdown.get(c, 0.0) + float(
              e.get("amount", 0)
          )

        cat_rows = [
            {"Category": k, "Total Spent": f"${v:,.2f} CAD"}
            for k, v in cat_breakdown.items()
        ]
        st.dataframe(pd.DataFrame(cat_rows), use_container_width=True)
      else:
        st.write("No expenses logged yet.")

  st.subheader("Expense Log History")
  if all_expenses:
    exp_table_rows = []
    for e in all_expenses:
      exp_table_rows.append({
          "Date": e.get("expense_date"),
          "Corridor": e.get("corridor"),
          "Category": e.get("category"),
          "Amount (CAD)": f"${float(e.get('amount', 0)):.2f}",
          "Vendor / Ref": e.get("receipt_ref", ""),
          "Notes": e.get("notes", ""),
      })
    st.dataframe(pd.DataFrame(exp_table_rows), use_container_width=True)
  else:
    st.write("No travel expenses recorded.")
