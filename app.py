import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Advanced MIS + CDR Analytics Tool", layout="wide")

st.title("📊 Advanced MIS + Multi-CDR Analytics Tool")
st.markdown("Upload MIS → Upload Multiple CDR Files → Use Presets or Manual Filter → Analyze")

st.info("🔒 Files are processed temporarily. Presets are saved locally. No lead data is stored.")

# =====================================================
# Preset System (Max 2 Presets)
# =====================================================

PRESET_FILE = "presets.json"

def load_presets():
    if os.path.exists(PRESET_FILE):
        with open(PRESET_FILE, "r") as f:
            return json.load(f)
    return {}

def save_presets(presets):
    with open(PRESET_FILE, "w") as f:
        json.dump(presets, f)

# =====================================================
# Utility Functions
# =====================================================

def read_file(file):
    if file.name.endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file)

def clean_phone(series):
    return (
        series.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
        .str[-10:]
    )

# =====================================================
# Sidebar Upload
# =====================================================

with st.sidebar:
    st.header("Upload Files")

    mis_file = st.file_uploader("Upload MIS File (xlsx/csv)", type=["xlsx", "csv"])
    cdr_files = st.file_uploader("Upload CDR Files", type=["xlsx", "csv"], accept_multiple_files=True)

# =====================================================
# Main Logic
# =====================================================

if mis_file and cdr_files:

    mis = read_file(mis_file)

    required_mis_cols = [
        "CorporateName","RequestDate","ContractName","PatientName",
        "ApplicationId","PolicyNo","Gender","RelationShip","EmailId",
        "ContactNo","NoOfReschedule","ProviderName","ProviderState"
    ]

    for col in required_mis_cols:
        if col not in mis.columns:
            st.error(f"Missing MIS column: {col}")
            st.stop()

    provider_list = sorted(mis["ProviderName"].dropna().unique())

    presets = load_presets()
    preset_names = list(presets.keys())

    st.subheader("Partner Filter")

    mode = st.radio("Selection Mode", ["Manual", "Preset"])

    if mode == "Preset" and preset_names:
        selected_preset = st.selectbox("Select Preset", preset_names)
        selected_providers = presets[selected_preset]
        st.write("Preset Providers:", selected_providers)
    else:
        selected_providers = st.multiselect("Select Provider(s)", provider_list)

    # ==============================
    # Preset Management
    # ==============================

    st.markdown("### Manage Presets (Max 2)")

    preset_name_input = st.text_input("Preset Name")
    preset_provider_input = st.multiselect("Preset Providers", provider_list, key="preset_select")

    colA, colB = st.columns(2)

    with colA:
        if st.button("Save / Update Preset"):
            if not preset_name_input:
                st.warning("Enter preset name.")
            elif len(presets) >= 2 and preset_name_input not in presets:
                st.warning("Maximum 2 presets allowed.")
            else:
                presets[preset_name_input] = preset_provider_input
                save_presets(presets)
                st.success("Preset saved.")
                st.rerun()

    with colB:
        if st.button("Delete Preset"):
            if preset_name_input in presets:
                del presets[preset_name_input]
                save_presets(presets)
                st.success("Preset deleted.")
                st.rerun()

    analyze = st.button("🔍 Analyze")

    # =====================================================
    # ANALYSIS SECTION
    # =====================================================

    if analyze:

        if not selected_providers:
            st.warning("Please select at least one provider.")
            st.stop()

        with st.spinner("Processing..."):

            mis_filtered = mis[mis["ProviderName"].isin(selected_providers)].copy()
            mis_filtered["phone"] = clean_phone(mis_filtered["ContactNo"])

            # Combine all CDR files
            cdr_list = [read_file(f) for f in cdr_files]
            cdr = pd.concat(cdr_list, ignore_index=True)

            required_cdr_cols = [
                "Customer Number",
                "Call Status",
                "Disposition Name",
                "Call Start Date",
                "Call Start Time"
            ]

            for col in required_cdr_cols:
                if col not in cdr.columns:
                    st.error(f"Missing CDR column: {col}")
                    st.stop()

            cdr = cdr[required_cdr_cols].copy()
            cdr["phone"] = clean_phone(cdr["Customer Number"])

            cdr["call_datetime"] = pd.to_datetime(
                cdr["Call Start Date"].astype(str) + " " +
                cdr["Call Start Time"].astype(str),
                errors="coerce"
            )

            cdr = cdr.dropna(subset=["phone", "call_datetime"])

            # =============================
            # Analytics Calculations
            # =============================

            attempt_count = cdr.groupby("phone").size().reset_index(name="Total_Attempts")

            connected = (
                cdr[cdr["Call Status"] == "Answered"]
                .groupby("phone")
                .size()
                .reset_index(name="Connected_Attempts")
            )

            first_call = cdr.groupby("phone")["call_datetime"].min().reset_index(name="First_Call_Date")
            last_call_date = cdr.groupby("phone")["call_datetime"].max().reset_index(name="Last_Call_Date")

            cdr_sorted = cdr.sort_values("call_datetime", ascending=False)
            last_disposition = cdr_sorted.drop_duplicates("phone")[["phone","Disposition Name","Call Status"]]

            # Merge everything
            final = mis_filtered.merge(attempt_count, on="phone", how="left")
            final = final.merge(connected, on="phone", how="left")
            final = final.merge(first_call, on="phone", how="left")
            final = final.merge(last_call_date, on="phone", how="left")
            final = final.merge(last_disposition, on="phone", how="left")

            final.fillna({
                "Total_Attempts":0,
                "Connected_Attempts":0
            }, inplace=True)

            final["NotConnected_Attempts"] = final["Total_Attempts"] - final["Connected_Attempts"]

        # =============================
        # Dashboard Metrics
        # =============================

        st.subheader("📈 Key Insights")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Total Leads", len(final))
        col2.metric("Total Calls", int(final["Total_Attempts"].sum()))
        col3.metric("Connected Calls", int(final["Connected_Attempts"].sum()))
        col4.metric("Connection Rate",
                    f"{(final['Connected_Attempts'].sum() / final['Total_Attempts'].sum() * 100):.1f}%"
                    if final["Total_Attempts"].sum() > 0 else "0%")

        # =============================
        # Disposition Breakdown
        # =============================

        st.subheader("📊 Disposition Breakdown")

        dispo_summary = final["Disposition Name"].value_counts().reset_index()
        dispo_summary.columns = ["Disposition", "Count"]

        st.dataframe(dispo_summary, use_container_width=True)

        # =============================
        # Detailed Table
        # =============================

        st.subheader("📋 Detailed Lead Report")
        st.dataframe(final, use_container_width=True)

        # =============================
        # Download
        # =============================

        csv = final.to_csv(index=False).encode("utf-8")

        st.download_button(
            "📥 Download Full Analytical Report",
            csv,
            "Analytical_Report.csv",
            "text/csv"
        )
