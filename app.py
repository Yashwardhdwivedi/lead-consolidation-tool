import streamlit as st
import pandas as pd

st.set_page_config(page_title="Lead Consolidation Tool", layout="wide")

st.title("📊 MIS + Acefone Consolidation Tool")
st.markdown("Upload files → Select Provider(s) → Click Analyze → Download Report")

st.info("🔒 Files are processed temporarily. No data is stored.")

# ==============================
# Sidebar Upload Section
# ==============================

with st.sidebar:
    st.header("Upload Files")

    mis_file = st.file_uploader(
        "Upload MIS File (xlsx/csv)",
        type=["xlsx", "csv"]
    )

    cdr_file = st.file_uploader(
        "Upload CDR File (xlsx/csv)",
        type=["xlsx", "csv"]
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
        .str.replace("+91", "", regex=False)
        .str.replace("91", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace("-", "", regex=False)
        .str[-10:]
    )

# ==============================
# Main Logic
# ==============================

if mis_file and cdr_file:

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

    # 🔹 Multi-select Provider Filter
    provider_list = sorted(mis["ProviderName"].dropna().unique())

    selected_providers = st.multiselect(
        "Select ProviderName(s)",
        provider_list
    )

    # 🔹 Analyze Button
    analyze = st.button("🔍 Analyze")

    if analyze and selected_providers:

        with st.spinner("Processing data..."):

            mis_filtered = mis[mis["ProviderName"].isin(selected_providers)].copy()
            mis_filtered["phone"] = clean_phone(mis_filtered["ContactNo"])

            cdr = read_file(cdr_file)

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

            # Get Last Call per phone
            cdr_sorted = cdr.sort_values("call_datetime", ascending=False)
            last_call = cdr_sorted.drop_duplicates("phone")

            final = mis_filtered.merge(last_call, on="phone", how="left")

            output_columns = required_mis_cols + [
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
        # UI Metrics
        # ==============================

        col1, col2, col3 = st.columns(3)

        col1.metric("Total Leads", len(final_output))
        col2.metric("Providers Selected", len(selected_providers))
        col3.metric("Unique Phones", final_output["ContactNo"].nunique())

        st.success("✅ Analysis Complete")

        st.dataframe(final_output, use_container_width=True)

        csv = final_output.to_csv(index=False).encode("utf-8")

        st.download_button(
            "📥 Download Consolidated Report",
            csv,
            "Consolidated_Report.csv",
            "text/csv"
        )

    elif analyze and not selected_providers:
        st.warning("Please select at least one ProviderName.")
