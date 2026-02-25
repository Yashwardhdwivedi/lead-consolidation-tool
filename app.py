import streamlit as st
import pandas as pd

st.set_page_config(page_title="Lead Consolidation Tool", layout="wide")

st.title("📊 MIS + Acefone Lead Consolidation Tool")
st.markdown(
    "Upload MIS & Acefone CDR files (CSV or Excel) → Select Provider → Download consolidated report"
)

st.info("🔒 No data is stored. Files are processed temporarily and cleared after session ends.")

# ===============================
# File Upload Section
# ===============================

mis_file = st.file_uploader(
    "Upload MIS File (xlsx or csv)",
    type=["xlsx", "csv"]
)

cdr_file = st.file_uploader(
    "Upload Acefone CDR File (xlsx or csv)",
    type=["xlsx", "csv"]
)

# ===============================
# Utility Functions
# ===============================

def read_file(file):
    """Automatically detect CSV or Excel"""
    if file.name.endswith(".csv"):
        return pd.read_csv(file)
    else:
        return pd.read_excel(file)

def clean_phone(series):
    """Vectorized phone cleaning"""
    return (
        series.astype(str)
        .str.replace("+91", "", regex=False)
        .str.replace("91", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace("-", "", regex=False)
        .str[-10:]
    )

# ===============================
# Main Processing
# ===============================

if mis_file and cdr_file:

    try:
        with st.spinner("Reading MIS file..."):
            mis = read_file(mis_file)

        # Validate MIS columns
        required_mis_cols = ["ContactNo", "ProviderName"]
        for col in required_mis_cols:
            if col not in mis.columns:
                st.error(f"❌ Missing column in MIS file: {col}")
                st.stop()

        # Provider Dropdown
        provider_list = sorted(mis["ProviderName"].dropna().unique())

        if not provider_list:
            st.error("No ProviderName values found in MIS file.")
            st.stop()

        selected_provider = st.selectbox("Select ProviderName", provider_list)

        if selected_provider:

            with st.spinner("Processing data..."):

                # Filter MIS by provider
                mis_filtered = mis[mis["ProviderName"] == selected_provider].copy()

                # Clean MIS phone numbers
                mis_filtered["phone"] = clean_phone(mis_filtered["ContactNo"])

                # Load CDR (only required columns for performance)
                required_cdr_cols = [
                    "Customer Number",
                    "Call Status",
                    "Disposition Name",
                    "Call Start Date",
                    "Call Start Time"
                ]

                cdr = read_file(cdr_file)

                # Validate CDR columns
                for col in required_cdr_cols:
                    if col not in cdr.columns:
                        st.error(f"❌ Missing column in CDR file: {col}")
                        st.stop()

                cdr = cdr[required_cdr_cols]

                # Clean CDR phone numbers
                cdr["phone"] = clean_phone(cdr["Customer Number"])

                # Create datetime
                cdr["call_datetime"] = pd.to_datetime(
                    cdr["Call Start Date"].astype(str) + " " +
                    cdr["Call Start Time"].astype(str),
                    errors="coerce"
                )

                # Drop invalid rows
                cdr = cdr.dropna(subset=["phone", "call_datetime"])

                # ===============================
                # Aggregation Logic
                # ===============================

                agg = (
                    cdr.sort_values("call_datetime")
                    .groupby("phone")
                    .agg(
                        Total_Attempts=("phone", "size"),
                        First_Call_Date=("call_datetime", "min"),
                        Last_Call_Date=("call_datetime", "max"),
                        Last_Disposition=("Disposition Name", "last"),
                        Last_Call_Status=("Call Status", "last"),
                    )
                    .reset_index()
                )

                # Connected Attempts
                connected = (
                    cdr[cdr["Call Status"] == "Answered"]
                    .groupby("phone")
                    .size()
                    .reset_index(name="Connected_Attempts")
                )

                agg = agg.merge(connected, on="phone", how="left")
                agg["Connected_Attempts"] = agg["Connected_Attempts"].fillna(0)

                # Not Connected
                agg["NotConnected_Attempts"] = (
                    agg["Total_Attempts"] - agg["Connected_Attempts"]
                )

                # Merge with MIS
                final = mis_filtered.merge(agg, on="phone", how="left")

                # Fill missing values
                final.fillna({
                    "Total_Attempts": 0,
                    "Connected_Attempts": 0,
                    "NotConnected_Attempts": 0,
                    "Last_Disposition": "No Call",
                    "Last_Call_Status": "No Call"
                }, inplace=True)

            st.success(f"✅ Report Ready for Provider: {selected_provider}")

            st.write("Preview (Top 50 rows)")
            st.dataframe(final.head(50))

            # Download
            csv = final.to_csv(index=False).encode("utf-8")

            st.download_button(
                "📥 Download Consolidated Report",
                csv,
                f"{selected_provider}_Consolidated_Report.csv",
                "text/csv"
            )

    except Exception as e:
        st.error(f"⚠️ Error processing files: {str(e)}")
