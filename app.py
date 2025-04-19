import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import unicodedata
from datetime import datetime
from io import StringIO

# ---------- Updated Robust PDF Parser ----------
def extract_product_data_from_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    lines = []
    for page in doc:
        text = page.get_text("text")
        text = unicodedata.normalize("NFKD", text)
        lines.extend(text.splitlines())

    products = []
    i = 0
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    while i < len(lines):
        line = lines[i].strip()

        if re.match(r"[A-Z].*\d+[Xx]\d+", line):  # Likely a product name
            name = line.strip()
            i += 1

            while i < len(lines) and not lines[i].strip().startswith("2024 Q"):
                i += 1
            i += 1  # skip "2024 Q"

            q2024 = []
            while i < len(lines) and len(q2024) < 12:
                q2024 += list(map(int, re.findall(r"\d+", lines[i])))
                i += 1

            while i < len(lines) and not lines[i].strip().startswith("V"):
                i += 1
            i += 1  # skip "V"

            v2024 = []
            while i < len(lines) and len(v2024) < 12:
                v2024 += list(map(float, re.findall(r"\d+\.\d+", lines[i])))
                i += 1

            while i < len(lines) and not lines[i].strip().startswith("2025 Q"):
                i += 1
            i += 1  # skip "2025 Q"

            q2025 = []
            while i < len(lines) and len(q2025) < 12:
                q2025 += list(map(int, re.findall(r"\d+", lines[i])))
                i += 1

            while i < len(lines) and not lines[i].strip().startswith("V"):
                i += 1
            i += 1  # skip "V"

            v2025 = []
            while i < len(lines) and len(v2025) < 12:
                v2025 += list(map(float, re.findall(r"\d+\.\d+", lines[i])))
                i += 1

            batch_match = re.search(r"(\d+)[Xx](\d+(?:\.\d+)?)(KG|G|GR)?", name)
            if batch_match:
                units, size, unit = batch_match.groups()
                full_batch = f"{name} {size}{unit.upper() if unit else 'KG'}"
                weight_group = f"{size}{unit.upper() if unit else 'KG'}"
            else:
                single_match = re.search(r"(\d+(?:\.\d+)?)(KG|G|GR)", name)
                size = single_match.group(1) if single_match else "UNSPEC"
                unit = single_match.group(2) if single_match else "KG"
                full_batch = f"{name} {size}{unit.upper()}"
                weight_group = f"{size}{unit.upper()}"

            for j in range(12):
                products.append({
                    "Product": name,
                    "Batch": full_batch,
                    "Weight Group": weight_group,
                    "Month": months[j],
                    "Month_Num": j + 1,
                    "Year": 2024,
                    "Quantity": q2024[j] if j < len(q2024) else 0,
                    "Value": v2024[j] if j < len(v2024) else 0.0
                })
                products.append({
                    "Product": name,
                    "Batch": full_batch,
                    "Weight Group": weight_group,
                    "Month": months[j],
                    "Month_Num": j + 1,
                    "Year": 2025,
                    "Quantity": q2025[j] if j < len(q2025) else 0,
                    "Value": v2025[j] if j < len(v2025) else 0.0
                })
        else:
            i += 1

    return pd.DataFrame(products)

# ---------- Streamlit App ----------
st.set_page_config(page_title="Batch Sales - Monthly Filter", layout="wide")
st.title("📦 Sales Comparison by Month")

uploaded_file = st.file_uploader("Upload Product Sales PDF", type="pdf")

if uploaded_file:
    pdf_bytes = uploaded_file.read()
    with st.spinner("Extracting data from PDF..."):
        df = extract_product_data_from_pdf(pdf_bytes)

    if df.empty:
        st.error("No data extracted. Please check the PDF format.")
    else:
        group = df.groupby(["Batch", "Weight Group", "Month", "Month_Num", "Year"]).agg({
            "Quantity": "sum",
            "Value": "sum"
        }).reset_index()

        qty_pivot = group.pivot_table(index=["Batch", "Weight Group", "Month", "Month_Num"], columns="Year", values="Quantity", fill_value=0)
        val_pivot = group.pivot_table(index=["Batch", "Weight Group", "Month", "Month_Num"], columns="Year", values="Value", fill_value=0)

        qty_pivot.columns = [f"{col}_Qty" for col in qty_pivot.columns]
        val_pivot.columns = [f"{col}_Value" for col in val_pivot.columns]

        comparison_df = pd.merge(qty_pivot, val_pivot, on=["Batch", "Weight Group", "Month", "Month_Num"]).reset_index()

        comparison_df["Quantity Difference"] = comparison_df["2025_Qty"] - comparison_df["2024_Qty"]
        comparison_df["Value Difference"] = comparison_df["2025_Value"] - comparison_df["2024_Value"]

        comparison_df = comparison_df.rename(columns={
            "2024_Qty": "Quantity 2024",
            "2025_Qty": "Quantity 2025",
            "2024_Value": "Value 2024",
            "2025_Value": "Value 2025"
        })

        comparison_df = comparison_df.sort_values(by=["Weight Group", "Month_Num", "Batch"]).reset_index(drop=True)

        def is_loose_item(batch):
            return bool(re.match(r"(^|\s)1[Xx]\d+(?:\.\d+)?(KG|G|GR)", batch))

        def is_zero_quantity(row):
            return row["Quantity 2024"] == 0 and row["Quantity 2025"] == 0

        comparison_df["Loose_Flag"] = comparison_df["Batch"].apply(is_loose_item)
        comparison_df["Zero_Qty_Flag"] = comparison_df.apply(is_zero_quantity, axis=1)
        comparison_df["Basmati_Flag"] = comparison_df["Batch"].str.contains(r"\bBASMATI\b", case=False)

        month_list = comparison_df["Month"].unique().tolist()
        selected_month = st.selectbox("📅 Select Month to View", sorted(month_list, key=lambda x: datetime.strptime(x, "%B")))

        filtered_df = comparison_df[comparison_df["Month"] == selected_month]

        filtered_df = filtered_df.sort_values(
            by=["Weight Group", "Zero_Qty_Flag", "Loose_Flag", "Batch"],
            ascending=[True, True, False, True]
        ).reset_index(drop=True)

        # ---------- CSV Export ----------
        def export_grouped_csv(df):
            output = StringIO()

            basmati_df = df[df["Basmati_Flag"]]
            non_basmati_df = df[~df["Basmati_Flag"]]

            for group, group_df in non_basmati_df.groupby("Weight Group"):
                group_df = group_df.sort_values(by=["Zero_Qty_Flag", "Loose_Flag", "Batch"], ascending=[True, False, True])
                output.write(f"Weight Group: {group}\n\n")
                export_df = group_df[[
                    "Weight Group", "Batch", "Month",
                    "Quantity 2024", "Quantity 2025", "Quantity Difference",
                    "Value 2024", "Value 2025", "Value Difference"
                ]]
                export_df.to_csv(output, index=False)

                totals = export_df[[
                    "Quantity 2024", "Quantity 2025", "Quantity Difference",
                    "Value 2024", "Value 2025", "Value Difference"
                ]].sum().round(2)
                total_row = ["", "TOTAL", ""] + totals.tolist()
                output.write(",".join(map(str, total_row)) + "\n\n\n")

            if not basmati_df.empty:
                group_df = basmati_df.sort_values(by=["Weight Group", "Zero_Qty_Flag", "Loose_Flag", "Batch"])
                output.write(f"BASMATI GROUP\n\n")
                export_df = group_df[[
                    "Weight Group", "Batch", "Month",
                    "Quantity 2024", "Quantity 2025", "Quantity Difference",
                    "Value 2024", "Value 2025", "Value Difference"
                ]]
                export_df.to_csv(output, index=False)

                totals = export_df[[
                    "Quantity 2024", "Quantity 2025", "Quantity Difference",
                    "Value 2024", "Value 2025", "Value Difference"
                ]].sum().round(2)
                total_row = ["", "TOTAL", ""] + totals.tolist()
                output.write(",".join(map(str, total_row)) + "\n\n\n")

            return output.getvalue().encode("utf-8")

        csv_bytes = export_grouped_csv(filtered_df)

        filtered_df = filtered_df.drop(columns=["Loose_Flag", "Zero_Qty_Flag", "Basmati_Flag"])

        st.subheader(f"📊 Quantity & Value Comparison for {selected_month}")
        st.dataframe(filtered_df[[
            "Weight Group", "Batch", "Month",
            "Quantity 2024", "Quantity 2025", "Quantity Difference",
            "Value 2024", "Value 2025", "Value Difference"
        ]], use_container_width=True)

        st.download_button(
            f"📥 Download {selected_month} Grouped CSV",
            data=csv_bytes,
            file_name=f"{selected_month.lower()}_grouped_comparison.csv",
            mime="text/csv"
        )

else:
    st.info("Please upload a product sales PDF file.")
