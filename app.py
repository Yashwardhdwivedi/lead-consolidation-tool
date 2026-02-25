import streamlit as st
import pandas as pd

st.set_page_config(page_title="Lead Consolidation Tool", layout="wide")

st.title("📊 MIS + Multi-CDR Consolidation Tool")
st.markdown("Upload MIS → Upload Multiple CDR Files → Select Provider(s) → Analyze")

st.info("🔒 Files are processed temporarily. No data is stored.")

# ==============================
# Sidebar Upload
# ==============================

with st.sidebar:
    st.header("Upload Files")

    mis_file = st.file_uploader(
        "Upload MIS File (xlsx/csv)",
        type=["xlsx", "csv"]
    )

    cdr_files = st.file_uploader(
        "Upload One or More CDR Files",
        type=["xlsx", "csv"],
        accept_multiple_files=True
    )

# ==============================
# Utility Functions
# ==============================

def read_file(file):
    if file.name.endswith(".csv"):
        return pd.read_csv(file)
    else:
        return pd.read_excel(file)

def clean_phone(series):
    return (
        series.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
        .str[-10:]
    )

# ==============================
# Main Logic
# ==============================

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

    select_all = st.checkbox("Select All Providers")

    if select_all:
        selected_providers = provider_list
    else:
        selected_providers = st.multiselect(
            "Select ProviderName(s)",
            provider_list
        )

    analyze = st.button("🔍 Analyze")

    if analyze:

        if not selected_providers:
            st.warning("Please select at least one ProviderName.")
            st.stop()

        with st.spinner("Processing data..."):

            # ==============================
            # Filter MIS
            # ==============================

            mis_filtered = mis[
                mis["ProviderName"].isin(selected_providers)
            ].copy()

            mis_filtered["phone"] = clean_phone(mis_filtered["ContactNo"])

            # ==============================
            # Combine Multiple CDR Files
            # ==============================

            cdr_list = []
            for file in cdr_files:
                temp = read_file(file)
                cdr_list.append(temp)

            cdr = pd.concat(cdr_list, ignore_index=True)

            required_cdr_cols = [
                "Customer Number",
                "Call Type",
                "DID Number",
                "Connected to Agent",
                "Call Status",
                "Disposition Code",
                "Disposition Name",
                "Total Call Duration (HH:MM:SS)",
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

            # ==============================
            # Calculate Total Attempts
            # ==============================

            attempt_count = (
                cdr.groupby("phone")
                .size()
                .reset_index(name="Total_Call_Attempts")
            )

            # ==============================
            # Get True Last Call
            # ==============================

            cdr_sorted = cdr.sort_values("call_datetime", ascending=False)
            last_call = cdr_sorted.drop_duplicates("phone")

            # ==============================
            # Merge Everything
            # ==============================

            final = mis_filtered.merge(attempt_count, on="phone", how="left")
            final = final.merge(last_call, on="phone", how="left")

            final["Total_Call_Attempts"] = final["Total_Call_Attempts"].fillna(0)

            output_columns = required_mis_cols + [
                "Total_Call_Attempts",
                "Call Type",
                "DID Number",
                "Connected to Agent",
                "Call Status",
                "Disposition Code",
                "Disposition Name",
                "Total Call Duration (HH:MM:SS)"
            ]

            final_output = final[output_columns]

        # ==============================
        # Metrics
        # ==============================

        col1, col2, col3 = st.columns(3)

        col1.metric("Total Leads", len(final_output))
        col2.metric("Providers Selected", len(selected_providers))
        col3.metric("Total Calls Logged", final_output["Total_Call_Attempts"].sum())

        st.success("✅ Analysis Complete")

        st.dataframe(final_output, use_container_width=True)

        csv = final_output.to_csv(index=False).encode("utf-8")

        st.download_button(
            "📥 Download Consolidated Report",
            csv,
            "Consolidated_Report.csv",
            "text/csv"
        )
