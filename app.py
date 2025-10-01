import streamlit as st
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
import os

# ----------------------------
# Konfigurasi / Nama file
# ----------------------------
EXCEL_DATA_PATH = Path("ph_debit_data.xlsx") # <<< FILE TUNGGAL
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
# Utility Functions
# ----------------------------
def initialize_excel(path: Path, columns, sheets):
    # Membuat atau memastikan semua sheet data ada
    if not path.exists():
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet in sheets:
                pd.DataFrame(columns=columns).to_excel(writer, sheet_name=sheet, index=False)
    else:
        try:
            all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
            sheets_to_add = [sheet for sheet in sheets if sheet not in all_sheets]
            if sheets_to_add:
                with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                    for sheet in sheets_to_add:
                        pd.DataFrame(columns=columns).to_excel(writer, sheet_name=sheet, index=False)
        except Exception:
            path.unlink(missing_ok=True)
            initialize_excel(path, columns, sheets)

def read_all_sheets(path: Path):
    if not path.exists():
        return {}
    # Baca semua sheet kecuali 'Laporan Logbook' untuk menghindari error tipe data
    all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    if 'Laporan Logbook' in all_sheets:
        del all_sheets['Laporan Logbook']
    return all_sheets

def save_all_sheets(dfs: dict, path: Path, columns):
    # Gunakan mode 'a' dan 'overlay' saat menyimpan data input,
    # tetapi mode 'w' atau 'replace' akan digunakan di fungsi create_logbook_report
    # Kita hanya menyimpan sheet data di sini
    
    # Baca dulu sheet yang sudah ada (termasuk Laporan Logbook jika ada)
    try:
        existing_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    except Exception:
        existing_sheets = {}

    # Tambahkan sheet data yang diupdate
    existing_sheets.update(dfs)

    # Simpan semua sheet (data dan laporan) kembali ke file
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in existing_sheets.items():
            if sheet_name in SHEET_NAMES:
                df = df.reindex(columns=columns)
            df.to_excel(writer, sheet_name=sheet_name, index=False)

def reset_excel(path: Path, columns, sheets):
    # Membuat file baru dengan sheet data kosong
    wb = Workbook()
    for i, sheet in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = sheet
        ws.append(columns)
    wb.save(path)
    # Setelah reset data, file laporan lama hilang, jadi tidak perlu dihapus terpisah

def calculate_and_insert_average(df_loc: pd.DataFrame) -> pd.DataFrame:
    # Fungsi logika perhitungan rata-rata tetap sama
    df_data = df_loc[pd.to_datetime(df_loc["tanggal"], errors='coerce').notna()].copy()
    df_data['pH'] = pd.to_numeric(df_data['pH'], errors='coerce')
    df_data["tanggal"] = pd.to_datetime(df_data["tanggal"], errors="coerce")
    df_data["bulan"] = df_data["tanggal"].dt.month
    df_data["tahun"] = df_data["tanggal"].dt.year
    
    avg_df = (
        df_data.groupby(["tahun", "bulan"], as_index=False)["pH"]
        .mean()
        .round(3)
        .rename(columns={"pH": "ph_rata_rata_bulan"})
    )
    df_new_avg_rows = pd.DataFrame(columns=COLUMNS)
    for _, row in avg_df.iterrows():
        rata_row = {
            "tanggal": f"Rata-rata {row['bulan']}/{row['tahun']}",
            "pH": None,
            "debit": None,
            "ph_rata_rata_bulan": row["ph_rata_rata_bulan"]
        }
        df_new_avg_rows = pd.concat([df_new_avg_rows, pd.DataFrame([rata_row])], ignore_index=True)
        
    df_final = pd.concat([df_data[COLUMNS], df_new_avg_rows], ignore_index=True)
    return df_final.sort_values(by="tanggal", key=lambda x: pd.to_datetime(x, errors='coerce'), ascending=False).reset_index(drop=True)

# -----------------------------------------------
# FUNGSI REPORTING: KE SHEET 'Laporan Logbook' DI FILE YANG SAMA
# -----------------------------------------------
def create_logbook_report(dfs: dict, data_path: Path):
    """Membuat laporan logbook visual di sheet 'Laporan Logbook' di file yang sama."""
    
    all_data_list = []
    for loc, df in dfs.items():
        df_clean = df[pd.to_datetime(df["tanggal"], errors='coerce').notna()].copy()
        if not df_clean.empty:
            df_clean["lokasi"] = loc
            df_clean["tanggal"] = pd.to_datetime(df_clean["tanggal"])
            df_clean["bulan_tahun"] = df_clean["tanggal"].dt.strftime('%Y-%m') 
            df_clean["bulan_display"] = df_clean["tanggal"].dt.strftime('%B %Y')
            df_clean["hari"] = df_clean["tanggal"].dt.day
            all_data_list.append(df_clean)
            
    if not all_data_list:
        return
        
    full_df = pd.concat(all_data_list, ignore_index=True)
    
    # Pivot Data pH dan Debit
    ph_pivot = full_df.pivot_table(index=["bulan_tahun", "bulan_display", "lokasi"], columns="hari", values="pH", aggfunc='mean')
    ph_pivot['Rata-Rata'] = ph_pivot.mean(axis=1).round(3)
    ph_pivot = ph_pivot.reset_index().rename(columns={'lokasi': 'Parameter/Lokasi'})
    ph_pivot['Param'] = 'pH'
    
    debit_pivot = full_df.pivot_table(index=["bulan_tahun", "bulan_display", "lokasi"], columns="hari", values="debit", aggfunc='mean')
    debit_pivot['Rata-Rata'] = debit_pivot.mean(axis=1).round(3)
    debit_pivot = debit_pivot.reset_index().rename(columns={'lokasi': 'Parameter/Lokasi'})
    debit_pivot['Param'] = 'Debit'

    report_df = pd.concat([ph_pivot, debit_pivot])
    report_df = report_df.sort_values(by=['bulan_tahun', 'Parameter/Lokasi', 'Param'])
    
    all_dates = list(range(1, 32))
    report_cols = ['bulan_display', 'Param', 'Parameter/Lokasi'] + all_dates + ['Rata-Rata']
    
    report_df = report_df.reindex(columns=report_cols).rename(columns={'bulan_display': 'Periode'})
    report_df.columns.name = None
    report_df = report_df.drop(columns=['bulan_tahun'], errors='ignore')

    # Tulis Laporan ke file Excel yang SAMA, di sheet 'Laporan Logbook'
    try:
        # Buka file Excel yang sudah ada
        wb = pd.ExcelWriter(data_path, engine='openpyxl', mode='a', if_sheet_exists='replace')
        
        # Tulis DataFrame laporan ke sheet baru (atau timpa yang lama)
        report_df.to_excel(wb, sheet_name='Laporan Logbook', index=False)
        
        wb.close()
            
    except Exception as e:
        st.error(f"Gagal menulis Laporan Logbook ke sheet baru: {e}")
        
# ----------------------------
# Inisialisasi
# ----------------------------
initialize_excel(EXCEL_DATA_PATH, COLUMNS, SHEET_NAMES)

# ----------------------------
# Form input
# ----------------------------
st.markdown("---")
st.markdown("Isi data pengukuran di bawah ini:")

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES)

ph = st.number_input("pH (mis. 7.2)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
debit = st.number_input("Debit (mis. L/detik)", min_value=0.0, value=0.0, format="%.3f")

if st.button("Simpan data & Perbarui Laporan"):
    all_sheets = read_all_sheets(EXCEL_DATA_PATH)
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))

    new_row = {
        "tanggal": tanggal,
        "pH": float(ph),
        "debit": float(debit),
        "ph_rata_rata_bulan": None
    }
    
    df_loc = pd.concat([df_loc, pd.DataFrame([new_row])], ignore_index=True)

    df_loc_updated = calculate_and_insert_average(df_loc)

    all_sheets[lokasi] = df_loc_updated
    save_all_sheets(all_sheets, EXCEL_DATA_PATH, COLUMNS) # Simpan data input

    # ✨ GENERATE LAPORAN VISUAL DI FILE YANG SAMA
    # Kita panggil create_logbook_report setelah data input disimpan.
    create_logbook_report(read_all_sheets(EXCEL_DATA_PATH), EXCEL_DATA_PATH) 

    st.success(f"Data tersimpan di '{lokasi}' dan *Laporan Logbook* sudah diperbarui di sheet yang sama! ✅")

# ----------------------------
# Download Section
# ----------------------------
st.markdown("---")
st.subheader("Download File Excel Gabungan")

# Tombol Download Data Mentah
try:
    with open(EXCEL_DATA_PATH, "rb") as f_data:
        data_bytes = f_data.read()
    if st.download_button(
        label="Download Semua Data & Laporan (ph_debit_data.xlsx)",
        data=data_bytes,
        file_name="ph_debit_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ):
        st.info("File berhasil diunduh.")
except FileNotFoundError:
    st.warning("File Excel belum ada. Silakan simpan data terlebih dahulu.")


# Tombol Reset
if st.button("Reset Semua Data"):
    reset_excel(EXCEL_DATA_PATH, COLUMNS, SHEET_NAMES)
    st.success("Semua data input dan file laporan telah direset!")
    st.rerun()
