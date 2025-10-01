import streamlit as st
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
import os

# ----------------------------
# Konfigurasi / Nama file
# ----------------------------
EXCEL_DATA_PATH = Path("ph_debit_data.xlsx")
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
AVERAGE_SHEET_NAME = "Rata-rata Bulanan" # <<< NAMA SHEET BARU

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
            # Baca semua sheet yang ada
            all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
            sheets_to_add = [sheet for sheet in sheets if sheet not in all_sheets]
            
            # Jika ada sheet baru, tambahkan
            if sheets_to_add:
                with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                    for sheet in sheets_to_add:
                        pd.DataFrame(columns=columns).to_excel(writer, sheet_name=sheet, index=False)

            # Hapus sheet 'Rata-rata Bulanan' jika ada
            if AVERAGE_SHEET_NAME in all_sheets:
                 # Hapus sheet 'Rata-rata Bulanan'
                 pass # Dibiarkan kosong, nanti akan ditimpa saat save
        except Exception:
            path.unlink(missing_ok=True)
            initialize_excel(path, columns, sheets)

def read_all_sheets(path: Path):
    if not path.exists():
        return {}
    # Baca semua sheet kecuali sheet laporan rata-rata
    all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    if AVERAGE_SHEET_NAME in all_sheets:
        del all_sheets[AVERAGE_SHEET_NAME]
    return all_sheets

def save_all_sheets(dfs: dict, path: Path, columns):
    # Baca dulu sheet yang sudah ada (termasuk Laporan Rata-rata jika ada)
    try:
        existing_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    except Exception:
        existing_sheets = {}

    # Update sheet data
    existing_sheets.update(dfs)

    # Simpan semua sheet (data dan laporan) kembali ke file
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in existing_sheets.items():
            if sheet_name in SHEET_NAMES:
                df = df.reindex(columns=columns)
            df.to_excel(writer, sheet_name=sheet_name, index=False)

def reset_excel(path: Path, columns, sheets):
    # Membuat file baru dengan sheet data kosong (otomatis menghapus sheet laporan lama)
    wb = Workbook()
    for i, sheet in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = sheet
        ws.append(columns)
    wb.save(path)

def calculate_and_insert_average(df_loc: pd.DataFrame) -> pd.DataFrame:
    # Fungsi ini tetap sama, hanya digunakan untuk memastikan rata-rata di kolom 'ph_rata_rata_bulan' tetap terisi (walaupun tidak digunakan di preview)
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
# FUNGSI BARU: LAPORAN RATA-RATA BULANAN TERPUSAT
# -----------------------------------------------
def create_monthly_average_report(dfs: dict, data_path: Path):
    """Mengumpulkan semua rata-rata bulanan pH dari semua lokasi ke dalam satu sheet."""
    
    final_report_list = []
    
    for loc, df in dfs.items():
        # Filter hanya baris rata-rata bulanan (yang kolom 'pH'-nya None dan 'ph_rata_rata_bulan' berisi nilai)
        df_avg = df[df['ph_rata_rata_bulan'].notna()].copy()
        
        if not df_avg.empty:
            df_avg['Lokasi'] = loc
            df_avg['Periode'] = df_avg['tanggal'].str.replace('Rata-rata ', '')
            df_avg = df_avg.rename(columns={'ph_rata_rata_bulan': 'pH Rata-Rata Bulanan'})
            
            final_report_list.append(df_avg[['Periode', 'Lokasi', 'pH Rata-Rata Bulanan']])

    if not final_report_list:
        return
        
    # Gabungkan semua lokasi
    report_df = pd.concat(final_report_list, ignore_index=True)
    
    # Konversi kolom 'Periode' ke datetime untuk sorting yang benar (Bulan/Tahun)
    def parse_period(p):
        try:
            # Mencoba mengurai Periode 'M/YYYY' menjadi datetime
            month, year = map(int, p.split('/'))
            return pd.to_datetime(f'{year}-{month}-01')
        except:
            return pd.NaT

    report_df['Sort_Key'] = report_df['Periode'].apply(parse_period)
    report_df = report_df.sort_values(by=['Sort_Key', 'Lokasi']).drop(columns=['Sort_Key'])
    
    # Tulis Laporan ke sheet 'Rata-rata Bulanan' di file Excel yang SAMA
    try:
        # Baca dulu semua sheet yang ada, agar tidak menimpa sheet lain
        existing_sheets = pd.read_excel(data_path, sheet_name=None, engine="openpyxl")
        
        # Tambahkan/timpa sheet rata-rata bulanan
        existing_sheets[AVERAGE_SHEET_NAME] = report_df
        
        # Simpan kembali semua sheet
        with pd.ExcelWriter(data_path, engine='openpyxl') as writer:
            for sheet_name, df in existing_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            
    except Exception as e:
        st.error(f"Gagal menulis Laporan Rata-rata Bulanan: {e}")
        
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

if st.button("Simpan data & Perbarui Laporan Rata-rata"):
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
    save_all_sheets(all_sheets, EXCEL_DATA_PATH, COLUMNS)

    # ✨ GENERATE LAPORAN RATA-RATA BULANAN TERPUSAT
    create_monthly_average_report(read_all_sheets(EXCEL_DATA_PATH), EXCEL_DATA_PATH) 

    st.success(f"Data tersimpan di '{lokasi}' dan *Laporan Rata-rata Bulanan* sudah diperbarui! ✅")

# ----------------------------
# Download Section
# ----------------------------
st.markdown("---")
st.subheader("Download File Excel Gabungan")

try:
    with open(EXCEL_DATA_PATH, "rb") as f_data:
        data_bytes = f_data.read()
    if st.download_button(
        label="Download Semua Data & Rata-rata (ph_debit_data.xlsx)",
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
    st.success("Semua data telah direset!")
    st.rerun()
