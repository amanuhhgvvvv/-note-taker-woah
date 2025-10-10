import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter
# BARIS 'import streamlit_gsheets_connection' SUDAH DIHAPUS
import datetime

# ----------------------------
# KONFIGURASI GOOGLE SHEETS
# ----------------------------
# Dapatkan ID Spreadsheet dari secrets.toml
try:
    SHEET_ID = st.secrets["gsheets"]["spreadsheet_id"]
    
    # PERBAIKAN: Menggunakan st.connection() dengan type="spreadsheet"
    conn = st.connection("gsheets", type="spreadsheet") 
    
except KeyError:
    st.error("Gagal membaca 'spreadsheet_id' dari secrets.toml. Pastikan kunci [gsheets] dan [connections.gsheets] sudah dikonfigurasi di Streamlit Secrets.")
    st.stop()
except Exception as e:
    # Error ini sering muncul jika format secrets.toml salah, terutama private_key
    st.error(f"Gagal inisialisasi koneksi Google Sheets. Pastikan Service Account Key sudah benar di Streamlit Secrets. Error: {e}")
    st.stop()
    

SHEET_NAMES = [
    "Power Plant",
    "Plan Garage",
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
# Kolom pH, Suhu, dan Debit untuk LOGIKA INTERNAL PYTHON
INTERNAL_COLUMNS = ["tanggal", "pH", "suhu", "debit", "ph_rata_rata_bulan", "suhu_rata_rata_bulan", "debit_rata_rata_bulan"]

# Mapping baris di Google Sheet Anda
GSHEET_ROW_MAP = {
    'pH': 3,         # Data pH ada di Baris 3
    'suhu': 4,       # Data Suhu ada di Baris 4
    'debit': 5,      # Data Debit ada di Baris 5
}
# Kolom rata-rata di Google Sheet Anda (Diasumsikan Kolom AG - Kolom 33 jika A=1)
GSHEET_AVG_COL_INDEX = 33 

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air (Data Permanen via Google Sheets)")


# ----------------------------
# Utility: baca & simpan sheet (SUDAH DIREVISI)
# ----------------------------
@st.cache_data(ttl=5)
def read_all_sheets_gsheets():
    """
    Membaaca semua sheet dari Google Sheets dengan format PIVOT Anda 
    dan mengkonversinya ke format RAW DATA (tanggal, pH, suhu, debit) untuk diproses.
    """
    all_dfs_raw = {}
    
    for sheet_name in SHEET_NAMES:
        try:
            # Baca data mentah, termasuk header baris 2 (Hari) dan kolom A (Parameter)
            # Rentang A2:AF5 mencakup Hari ke-1 sampai 31 dan Kolom Rata-rata (dianggap AF atau AG)
            df_pivot = conn.read(
                spreadsheet=SHEET_ID, 
                worksheet=sheet_name, 
                range="A2:AF5", # Rentang bacaan untuk hari 1-31 dan parameter
                header=1,       # Baris 2 (Hari) dijadikan header
                ttl=0
            )

            # 1. CLEANING & CONVERSION
            df_pivot.rename(columns={df_pivot.columns[0]: 'Parameter'}, inplace=True)
            df_pivot.set_index('Parameter', inplace=True)
            
            # 2. PENGAMBILAN RATA-RATA 
            # Karena Anda menggunakan rentang A2:AF5, kolom terakhir (indeks -1) adalah Rata-rata.
            avg_col_name = df_pivot.columns[-1] # Mengambil nama kolom terakhir
            
            # Ambil data rata-rata bulanan
            ph_avg = pd.to_numeric(df_pivot.loc['pH'].get(avg_col_name), errors='coerce')
            # PENTING: Pastikan penamaan indeks sesuai di GSheet Anda (suhu (°C), Debit (l/d))
            suhu_avg = pd.to_numeric(df_pivot.loc['suhu (°C)'].get(avg_col_name), errors='coerce') 
            debit_avg = pd.to_numeric(df_pivot.loc['Debit (l/d)'].get(avg_col_name), errors='coerce')

            # Hapus kolom rata-rata dari data harian untuk diproses
            df_pivot_harian = df_pivot.drop(columns=[avg_col_name])
            
            # 3. UN-PIVOT (Mengubah format pivot Anda menjadi format raw data)
            df_raw_data = df_pivot_harian.T # Transpose: Hari menjadi index

            # UNTUK KEMUDAHAN, kita asumsikan ini untuk BULAN DAN TAHUN SAAT INI
            today = datetime.date.today()
            current_month = today.month
            current_year = today.year
            
            # Membuat DataFrame Raw Data Harian
            df_raw = pd.DataFrame()
            df_raw['tanggal'] = [f"{current_year}-{current_month:02d}-{int(day):02d}" for day in df_raw_data.index]
            df_raw['pH'] = pd.to_numeric(df_raw_data['pH'], errors='coerce').values
            df_raw['suhu'] = pd.to_numeric(df_raw_data['suhu (°C)'], errors='coerce').values
            df_raw['debit'] = pd.to_numeric(df_raw_data['Debit (l/d)'], errors='coerce').values
            
            # Tambahkan baris rata-rata bulanan
            avg_row = {
                "tanggal": f"Rata-rata {current_month:02d}/{current_year}",
                "pH": None,
                "suhu": None,
                "debit": None,
                "ph_rata_rata_bulan": ph_avg,
                "suhu_rata_rata_bulan": suhu_avg,
                "debit_rata_rata_bulan": debit_avg
            }
            df_raw = pd.concat([df_raw, pd.DataFrame([avg_row])], ignore_index=True)
            
            all_dfs_raw[sheet_name] = df_raw.reindex(columns=INTERNAL_COLUMNS)
            
        except Exception as e:
            # PERBAIKAN SINTAKSIS PADA BARIS INI
            st.warning(f"Gagal membaca sheet '{sheet_name}'. Pastikan format header Anda benar dan data ada di rentang A2:AF5. Error: {e}")
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data RAW dari Python kembali ke format PIVOT di Google Sheets.
    Fungsi ini HANYA menulis nilai harian (pH, suhu, debit) dan nilai rata-rata.
    --- FUNGSI INI SUDAH DIPERBAIKI ---
    """
    read_all_sheets_gsheets.clear()
    
    # 1. Filter Data Harian dan Rata-rata
    df_data_only = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    # Periksa dan ambil data rata-rata (hanya satu baris yang mengandung
