import streamlit as st
import pandas as pd
from pathlib import Path
import os 
import numpy as np 
import io # Diperlukan untuk menyimpan file Excel di memori

# ----------------------------
# Konfigurasi / Nama file
# ----------------------------
EXCEL_PATH = Path("ph_debit_data_pivot.xlsx") 
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
COLUMNS = ["tanggal", "pH", "debit", "ph_rata_rata_bulan", "debit_rata_rata_bulan"]

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air")

# ----------------------------
# Inisialisasi file Excel
# ----------------------------
def initialize_excel(path: Path):
    """Memastikan file Excel dan semua sheet yang dibutuhkan ada."""
    if not path.exists():
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet in SHEET_NAMES:
                df = pd.DataFrame(columns=COLUMNS)
                df.to_excel(writer, sheet_name=sheet, index=False)
    else:
        try:
            # Baca semua sheet untuk memastikan mana yang sudah ada
            all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={'tanggal': str})
        except Exception:
            all_sheets = {}

        # Simpan kembali dengan mode 'a' (append) untuk menambahkan sheet yang hilang
        with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
            for sheet in SHEET_NAMES:
                if sheet not in all_sheets:
                    df = pd.DataFrame(columns=COLUMNS)
                    df.to_excel(writer, sheet_name=sheet, index=False)

initialize_excel(EXCEL_PATH)

# ----------------------------
# Utility: baca & simpan sheet
# ----------------------------
@st.cache_data 
def read_all_sheets(path: Path):
    """Membaca semua sheet dari file Excel dengan 'tanggal' sebagai string."""
    return pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={'tanggal': str})

def save_all_sheets(dfs: dict, path: Path):
    """Menyimpan semua dataframe ke file Excel, memastikan urutan kolom."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df = df.reindex(columns=COLUMNS)
            df.to_excel(writer, sheet_name=sheet, index=False)

# ----------------------------
# FUNGSI BARU: MEMBUAT FILE EXCEL UNTUK DOWNLOAD DENGAN FORMAT PIVOT
# (PERBAIKAN UTAMA DI SINI)
# ----------------------------
def create_pivot_data(df_raw, lokasi):
    """Memproses DataFrame mentah menjadi format pivot bulanan."""
    
    # 1. Pisahkan Data Harian dan Rata-rata
    df_data_rows = df_raw[~df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    df_avg_rows = df_raw[df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()

    df_data_rows['tanggal_dt'] = pd.to_datetime(df_data_rows['tanggal'], errors='coerce')
    df_data_rows = df_data_rows.dropna(subset=['tanggal_dt'])

    if df_data_rows.empty:
        # PERBAIKAN: Hanya kembalikan None (bukan tuple) jika tidak ada data valid
        return None 
    
    df_data_rows['TahunBulan'] = df_data_rows['tanggal_dt'].dt.strftime('%Y-%m')
    df_data_rows['Hari'] = df_data_rows['tanggal_dt'].dt.day
    
    pivot_sheets = {}
    
    # Kelompokkan data berdasarkan Bulan/Tahun
    for (tahun_bulan, df_group) in df_data_rows.groupby('TahunBulan'):
        
        selected_month = df_group['tanggal_dt'].dt.month.iloc[0]
        selected_year = df_group['tanggal_dt'].dt.year.iloc[0]
        sheet_name = f"{lokasi} - {tahun_bulan}"

        # Lakukan Operasi Pivot
        df_pivot_data = df_group[['Hari', 'pH', 'debit']]
        
        df_pivot = pd.melt(
            df_pivot_data, 
            id_vars=['Hari'], 
            value_vars=['pH', 'debit'], 
            var_name='Parameter', 
            value_name='Nilai'
        )
        
        df_pivot = df_pivot.pivot(
            index='Parameter', 
            columns='Hari', 
            values='Nilai'
        )
        
        # Tambahkan Rata-rata Bulanan
        avg_row = df_avg_rows[
            df_avg_rows['tanggal'].astype(str).str.contains(f"{selected_month:02d}/{selected_year}", na=False)
        ]

        if not avg_row.empty:
            ph_avg = avg_row['ph_rata_rata_bulan'].iloc[0]
            debit_avg = avg_row['debit_rata_rata_bulan'].iloc[0]

            rata_rata_series = pd.Series(
                data=[ph_avg, debit_avg], 
                index=['pH', 'debit'], 
                name='Rata-rata'
            )
            df_pivot['Rata-rata'] = rata_rata_series 
        else:
             df_pivot['Rata-rata'] = np.nan
        
        # Finalisasi (Rename baris dan kolom)
        df_pivot = df_pivot.rename(index={'pH': 'pH', 'debit': 'Debit (l/d)'})
        df_pivot = df_pivot.reindex(['pH', 'Debit (l/d)'])
        
        # Ganti nama kolom index (Parameter) menjadi kosong
        df_pivot.index.name = None 
        
        # Sisipkan data pivot ke dalam dictionary
        pivot_sheets[sheet_name] = df_pivot
        
    return pivot_sheets

def create_excel_with_pivot_sheets(all_raw_sheets):
    """Membuat file Excel di memori dengan sheet mentah dan sheet pivot."""
    output = io.BytesIO()
    # Menggunakan xlsxwriter sebagai engine karena mendukung formatting yang lebih baik
    # Jika Anda hanya membutuhkan penulisan dasar, openpyxl juga bisa digunakan
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        # 1. Tulis sheet data mentah (raw data)
        for sheet_name, df_raw in all_raw_sheets.items():
             # Pastikan hanya kolom yang ditentukan yang disimpan dan urutannya benar
            df_raw.reindex(columns=COLUMNS).to_excel(writer, sheet_name=f"RAW - {sheet_name}", index=False)

        # 2. Tulis sheet data pivot (format bulanan)
        for lokasi in SHEET_NAMES:
            df_raw = all_raw_sheets.get(lokasi)
            if df_raw is not None:
                # Sekarang pivot_data akan menjadi dictionary atau None (jika data kosong)
                pivot_data = create_pivot_data(df_raw, lokasi)
                
                # Cek jika pivot_data bukan None (dan karena ini Streamlit, 
                # ini juga akan false jika dictionary kosong)
                if pivot_data: 
                    for sheet_name, df_pivot in pivot_data.items():
                         # Tambahkan baris header di atas tabel pivot
                        header_df = pd.DataFrame({sheet_name: [f"Data Bulanan {lokasi}"]}).T
                        # Menggunakan header=False dan index=True untuk menulis nama sheet sebagai header
                        header_df.to_excel(writer, sheet_name=sheet_name, index=True, header=False, startrow=0)
                        
                        # Tulis tabel pivot
                        df_pivot.to_excel(writer, sheet_name=sheet_name, startrow=2, index=True)
                        
    return output.getvalue()

# ----------------------------
# Form input (Sama seperti sebelumnya)
# ----------------------------
if 'lokasi' not in st.session_state:
    st.session_state['lokasi'] = SHEET_NAMES[0]

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES, index=SHEET_NAMES.index(st.session_state['lokasi']))
st.session_state['lokasi'] = lokasi

col_ph, col_debit = st.columns(2)
with col_ph:
    ph = st.number_input("pH (0.0 - 14.0)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
with col_debit:
    debit = st.number_input("Debit (L/detik)", min_value=0.0, value=0.0, format="%.3f")


if st.button("Simpan data"):
    read_all_sheets.clear() 
    all_sheets = read_
