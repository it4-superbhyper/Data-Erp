import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import unicodedata
from datetime import datetime
from io import StringIO, BytesIO

# PDF ReportLab Imports
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

# ---------- PDF Parser ----------
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
        if re.match(r"[A-Z].*\d+[Xx]\d+", line):
            name = line.strip()
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("2024 Q"):
                i += 1
            i += 1
            q2024 = []
            while i < len(lines) and len(q2024) < 12:
                q2024 += list(map(int, re.findall(r"\d+", lines[i])))
                i += 1
            while i < len(lines) and not lines[i].strip().startswith("V"):
                i += 1
            i += 1
            v2024 = []
            while i < len(lines) and len(v2024) < 12:
                v2024 += list(map(float, re.findall(r"\d+\.\d+", lines[i])))
                i += 1
            while i < len(lines) and not lines[i].strip().startswith("2025 Q"):
                i += 1
            i += 1
            q2025 = []
            while i < len(lines) and len(q2025) < 12:
                q2025 += list(map(int, re.findall(r"\d+", lines[i])))
                i += 1
            while i < len(lines) and not lines[i].strip().startswith("V"):
                i += 1
            i += 1
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

        def export_grouped_csv(df):
            output = StringIO()
            basmati_df = df[df["Basmati_Flag"]]
            non_basmati_df = df[~df["Basmati_Flag"]]

            for group, group_df in non_basmati_df.groupby("Weight Group"):
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
                output.write("BASMATI GROUP\n\n")
                export_df = basmati_df[[
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

        def export_grouped_pdf(df, selected_month):
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
            styles = getSampleStyleSheet()
            story = []

            basmati_df = df[df["Basmati_Flag"]]
            non_basmati_df = df[~df["Basmati_Flag"]]

            def add_group(title, group_df):
                story.append(Paragraph(title, styles['Heading2']))
                grouped = group_df.groupby("Weight Group")

                for group, gdf in grouped:
                    story.append(Spacer(1, 6))
                    story.append(Paragraph(f"Weight Group: {group}", styles['Heading3']))

                    table_data = [[
                        "Weight Group", "Batch", "Month",
                        "Qty 2024", "Qty 2025", "Diff",
                        "Val 2024", "Val 2025", "Diff"
                    ]]

                    for _, row in gdf.iterrows():
                        table_data.append([
                            row["Weight Group"], row["Batch"], row["Month"],
                            int(row["Quantity 2024"]), int(row["Quantity 2025"]), int(row["Quantity Difference"]),
                            f"{row['Value 2024']:.2f}", f"{row['Value 2025']:.2f}", f"{row['Value Difference']:.2f}"
                        ])

                    totals = gdf[[
                        "Quantity 2024", "Quantity 2025", "Quantity Difference",
                        "Value 2024", "Value 2025", "Value Difference"
                    ]].sum().round(2).tolist()
                    total_row = ["", "TOTAL", ""] + list(map(str, totals))
                    table_data.append(total_row)

                    col_widths = [35*mm, 60*mm, 25*mm, 20*mm, 20*mm, 20*mm, 25*mm, 25*mm, 25*mm]
                    table = Table(table_data, colWidths=col_widths, repeatRows=1)

                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 7),
                        ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                        ('TOPPADDING', (0, 1), (-1, -1), 2),
                    ]))

                    story.append(table)
                    story.append(Spacer(1, 18))

            add_group(f"📦 Sales Comparison - {selected_month}", non_basmati_df)
            if not basmati_df.empty:
                add_group("🍚 BASMATI GROUP", basmati_df)

            doc.build(story)
            return buffer.getvalue()

        csv_bytes = export_grouped_csv(filtered_df)
        pdf_bytes = export_grouped_pdf(filtered_df, selected_month)

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

        st.download_button(
            f"📄 Download {selected_month} Grouped PDF",
            data=pdf_bytes,
            file_name=f"{selected_month.lower()}_grouped_comparison.pdf",
            mime="application/pdf"
        )
else:
    st.info("Please upload a product sales PDF file.")
