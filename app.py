import streamlit as st
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

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
# Inisialisasi & Utility (Disederhanakan)
# ----------------------------
# (Fungsi initialize_excel, read_all_sheets, save_all_sheets, reset_excel tetap sama seperti sebelumnya)

def initialize_excel(path: Path):
    if not path.exists():
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet in SHEET_NAMES:
                pd.DataFrame(columns=COLUMNS).to_excel(writer, sheet_name=sheet, index=False)
    else:
        try:
            all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
            sheets_to_add = [sheet for sheet in SHEET_NAMES if sheet not in all_sheets]
            if sheets_to_add:
                with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                    for sheet in sheets_to_add:
                        pd.DataFrame(columns=COLUMNS).to_excel(writer, sheet_name=sheet, index=False)
        except Exception:
            path.unlink(missing_ok=True)
            initialize_excel(path)

def read_all_sheets(path: Path):
    return pd.read_excel(path, sheet_name=None, engine="openpyxl")

def save_all_sheets(dfs: dict, path: Path):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df = df.reindex(columns=COLUMNS)
            df.to_excel(writer, sheet_name=sheet, index=False)

def reset_excel(path: Path):
    wb = Workbook()
    for i, sheet in enumerate(SHEET_NAMES):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = sheet
        ws.append(COLUMNS)
    wb.save(path)

def calculate_and_insert_average(df_loc: pd.DataFrame) -> pd.DataFrame:
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
# FUNGSI DIPERBAIKI: GENERATE LAPORAN LOGBOOK VISUAL (MULTI-BULAN)
# -----------------------------------------------
def create_logbook_report(dfs: dict, path: Path):
    """Membuat sheet baru dengan format logbook bulanan, diurutkan berdasarkan bulan."""
    
    all_data_list = []
    for loc, df in dfs.items():
        df_clean = df[pd.to_datetime(df["tanggal"], errors='coerce').notna()].copy()
        if not df_clean.empty:
            df_clean["lokasi"] = loc
            df_clean["tanggal"] = pd.to_datetime(df_clean["tanggal"])
            df_clean["bulan_tahun"] = df_clean["tanggal"].dt.strftime('%Y-%m') # Format untuk sorting
            df_clean["bulan_display"] = df_clean["tanggal"].dt.strftime('%B %Y') # Format untuk display
            df_clean["hari"] = df_clean["tanggal"].dt.day
            all_data_list.append(df_clean)
            
    if not all_data_list:
        return
        
    full_df = pd.concat(all_data_list, ignore_index=True)
    
    # 1. Pivot Data pH
    ph_pivot = full_df.pivot_table(
        index=["bulan_tahun", "bulan_display", "lokasi"], 
        columns="hari", 
        values="pH", 
        aggfunc='mean'
    )
    ph_pivot['Rata-Rata'] = ph_pivot.mean(axis=1).round(3)
    ph_pivot = ph_pivot.reset_index().rename(columns={'lokasi': 'Parameter/Lokasi'})
    ph_pivot['Param'] = 'pH'
    
    # 2. Pivot Data Debit
    debit_pivot = full_df.pivot_table(
        index=["bulan_tahun", "bulan_display", "lokasi"], 
        columns="hari", 
        values="debit", 
        aggfunc='mean'
    )
    debit_pivot['Rata-Rata'] = debit_pivot.mean(axis=1).round(3)
    debit_pivot = debit_pivot.reset_index().rename(columns={'lokasi': 'Parameter/Lokasi'})
    debit_pivot['Param'] = 'Debit'

    # 3. Gabungkan dan Atur Ulang Kolom
    report_df = pd.concat([ph_pivot, debit_pivot])
    
    # Sorting berdasarkan 'bulan_tahun' (Year-Month) untuk memastikan urutan Januari-Desember
    report_df = report_df.sort_values(by=['bulan_tahun', 'Parameter/Lokasi', 'Param'])
    
    # Kolom 1 sampai 31
    all_dates = list(range(1, 32))
    # Gunakan 'bulan_display' sebagai kolom periode akhir
    report_cols = ['bulan_display', 'Param', 'Parameter/Lokasi'] + all_dates + ['Rata-Rata']
    
    # Final Report
    report_df = report_df.reindex(columns=report_cols).rename(columns={'bulan_display': 'Periode'})
    report_df.columns.name = None

    # 4. Tulis Laporan ke file Excel
    try:
        # Hapus kolom sorting 'bulan_tahun' sebelum ditulis
        report_df = report_df.drop(columns=['bulan_tahun'], errors='ignore')
        
        wb = pd.ExcelWriter(path, engine='openpyxl', mode='a', if_sheet_exists='replace')
        report_df.to_excel(wb, sheet_name='Laporan Logbook', index=False)
        wb.close()
    except Exception as e:
        st.error(f"Gagal menulis Laporan Logbook: {e}")
        
# ----------------------------
# Form input
# ----------------------------
initialize_excel(EXCEL_PATH)
st.markdown("---")
st.markdown("Isi data pengukuran di bawah ini:")

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES)

ph = st.number_input("pH (mis. 7.2)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
debit = st.number_input("Debit (mis. L/detik)", min_value=0.0, value=0.0, format="%.3f")

if st.button("Simpan data & Perbarui Laporan"):
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))

    # Baris data baru
    new_row = {
        "tanggal": tanggal,
        "pH": float(ph),
        "debit": float(debit),
        "ph_rata_rata_bulan": None
    }
    
    df_loc = pd.concat([df_loc, pd.DataFrame([new_row])], ignore_index=True)

    # Hitung ulang dan sisipkan rata-rata (untuk data transaksional)
    df_loc_updated = calculate_and_insert_average(df_loc)

    all_sheets[lokasi] = df_loc_updated
    save_all_sheets(all_sheets, EXCEL_PATH)
    
    # ✨ GENERATE LAPORAN VISUAL MULTI-BULAN
    create_logbook_report(all_sheets, EXCEL_PATH)

    st.success(f"Data tersimpan di sheet '{lokasi}' dan Laporan Logbook sudah diperbarui! ✅")

# ----------------------------
# Preview data
# ----------------------------
st.markdown("---")
st.subheader("Preview data lokasi")
lokasi_preview = st.selectbox("Pilih lokasi untuk preview:", SHEET_NAMES, key="preview_select")

try:
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_preview = all_sheets.get(lokasi_preview, pd.DataFrame(columns=COLUMNS))
    df_preview_display = df_preview.astype(str)
    
    if df_preview.empty:
        st.info("Belum ada data untuk lokasi ini.")
    else:
        st.dataframe(df_preview_display.reset_index(drop=True))
except Exception as e:
    st.error(f"Gagal membaca file Excel: {e}")

# ----------------------------
# Tombol download file Excel gabungan + reset
# ----------------------------
st.markdown("---")
st.subheader("Download file Excel Gabungan (Termasuk Laporan Logbook Multi-Bulan)")
try:
    with open(EXCEL_PATH, "rb") as f:
        data_bytes = f.read()
    
    if st.download_button(
        label="Download file Excel",
        data=data_bytes,
        file_name="ph_debit_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ):
        reset_excel(EXCEL_PATH)
        st.success("Data berhasil diunduh dan aplikasi telah direset ✅")
except FileNotFoundError:
    st.warning("File Excel belum ada. Silakan simpan data terlebih dahulu.")
