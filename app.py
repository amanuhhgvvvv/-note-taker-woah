import streamlit as st
import pandas as pd
from pathlib import Path
from openpyxl import Workbook

# ----------------------------
# Konfigurasi / Nama file
# ----------------------------
EXCEL_PATH = Path("ph_debit_data.xlsx")
SHEET_NAMES = [
    "Power Plant",
    "Plant Garage",
    "Drain A",
    "Drain B",
    "Drain C",
    "WTP",
    "Coal Yard",
    "Domestik",
    "Limestone",
    "Clay Laterite",
    "Silika",
    "Kondensor PLTU"
]
COLUMNS = ["tanggal", "pH", "debit", "ph_rata_rata_bulan"]

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air")

# ----------------------------
# Inisialisasi file Excel
# ----------------------------
def initialize_excel(path: Path):
    if not path.exists():
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet in SHEET_NAMES:
                df = pd.DataFrame(columns=COLUMNS)
                df.to_excel(writer, sheet_name=sheet, index=False)
    else:
        all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
        with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
            for sheet in SHEET_NAMES:
                if sheet not in all_sheets:
                    df = pd.DataFrame(columns=COLUMNS)
                    df.to_excel(writer, sheet_name=sheet, index=False)

initialize_excel(EXCEL_PATH)

# ----------------------------
# Utility: baca & simpan sheet
# ----------------------------
def read_all_sheets(path: Path):
    return pd.read_excel(path, sheet_name=None, engine="openpyxl")

def save_all_sheets(dfs: dict, path: Path):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df = df.reindex(columns=COLUMNS)
            df.to_excel(writer, sheet_name=sheet, index=False)

# ----------------------------
# Reset Excel setelah download
# ----------------------------
def reset_excel(path: Path):
    wb = Workbook()
    for i, sheet in enumerate(SHEET_NAMES):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = sheet
        ws.append(COLUMNS)  # header
    wb.save(path)

# ----------------------------
# Form input
# ----------------------------
st.markdown("Isi data pengukuran di bawah ini:")

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES)

ph = st.number_input("pH (mis. 7.2)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
debit = st.number_input("Debit (mis. L/detik)", min_value=0.0, value=0.0, format="%.3f")

if st.button("Simpan data"):
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))

    new_row = {
        "tanggal": tanggal,
        "pH": float(ph),
        "debit": float(debit),
        "ph_rata_rata_bulan": None
    }
    df_loc = pd.concat([df_loc, pd.DataFrame([new_row])], ignore_index=True)

    # pastikan tanggal datetime
    df_loc["tanggal"] = pd.to_datetime(df_loc["tanggal"], errors="coerce")

    # ---- Hitung rata-rata bulanan ----
    df_data = df_loc[df_loc["ph_rata_rata_bulan"].isna()].copy()
    df_data["bulan"] = df_data["tanggal"].dt.month
    df_data["tahun"] = df_data["tanggal"].dt.year

    avg_df = (
        df_data.groupby(["tahun", "bulan"], as_index=False)["pH"]
        .mean()
        .round(3)
        .rename(columns={"pH": "ph_rata_rata_bulan"})
    )

    # buang baris rata-rata lama
    df_loc = df_data[COLUMNS].copy()

    # tambahkan baris rata-rata tiap bulan
    for _, row in avg_df.iterrows():
        rata_row = {
            "tanggal": f"Rata-rata {row['bulan']}/{row['tahun']}",
            "pH": None,
            "debit": None,
            "ph_rata_rata_bulan": row["ph_rata_rata_bulan"]
        }
        df_loc = pd.concat([df_loc, pd.DataFrame([rata_row])], ignore_index=True)

    all_sheets[lokasi] = df_loc
    save_all_sheets(all_sheets, EXCEL_PATH)

    st.success(f"Data tersimpan di sheet '{lokasi}' — tanggal {tanggal}")

# ----------------------------
# Preview data
# ----------------------------
st.markdown("---")
st.subheader("Preview data lokasi")
try:
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_preview = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))
    if df_preview.empty:
        st.info("Belum ada data untuk lokasi ini.")
    else:
        st.dataframe(df_preview.reset_index(drop=True))
except Exception as e:
    st.error(f"Gagal membaca file Excel: {e}")

# ----------------------------
# Tombol download file Excel gabungan + reset
# ----------------------------
st.markdown("---")
st.subheader("Download file Excel gabungan")
with open(EXCEL_PATH, "rb") as f:
    data_bytes = f.read()

if st.download_button(
    label="Download file Excel (semua lokasi)",
    data=data_bytes,
    file_name="ph_debit_data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
):
    reset_excel(EXCEL_PATH)  # 👉 otomatis reset setelah berhasil download
    st.success("Data berhasil diunduh dan aplikasi telah direset ✅")
