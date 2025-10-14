import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials

# ----------------------------
# KONEKSI GOOGLE SHEETS MANUAL
# ----------------------------
@st.cache_resource
def init_gsheets_connection():
    try:
        # Ambil credentials dari secrets
        creds_dict = {
            "type": "service_account",
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"], 
            "private_key": st.secrets["private_key"].replace('\\n', '\n'),
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": st.secrets["client_x509_cert_url"]
        }
        
        scope = ['https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive']
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        return client
        
    except Exception as e:
        st.error(f"❌ Gagal inisialisasi koneksi Google Sheets: {e}")
        return None

# Inisialisasi koneksi
client = init_gsheets_connection()

if client is None:
    st.stop()

try:
    # Ambil spreadsheet ID dari secrets
    SHEET_ID = st.secrets["SHEET_ID"]
except Exception as e:
    st.error(f"❌ Gagal mengambil SHEET_ID dari secrets: {e}")
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

INTERNAL_COLUMNS = ["tanggal", "pH", "suhu", "debit", "ph_rata_rata_bulan", "suhu_rata_rata_bulan", "debit_rata_rata_bulan"]

# Mapping baris di Google Sheet
GSHEET_ROW_MAP = {
    'pH': 3,          
    'suhu': 4,        
    'debit': 5,        
}

GSHEET_AVG_COL_INDEX = 33 

st.set_page_config(page_title="Monitoring Air", layout="centered")
st.title("📊 Monitoring Air")

# ----------------------------
# UTILITY FUNCTIONS - VERSI SEDERHANA
# ----------------------------
@st.cache_data(ttl=10)
def read_all_sheets_gsheets():
    """
    Membaca semua sheet dari Google Sheets - VERSI SIMPLIFIED
    """
    all_dfs_raw = {}
    
    for sheet_name in SHEET_NAMES:
        try:
            # Buka spreadsheet
            spreadsheet = client.open_by_key(SHEET_ID)
            
            # Cek apakah worksheet ada
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                continue
            
            # Baca data sederhana - hanya data harian
            try:
                # Baca data dari kolom B sampai AF (hari 1-31) untuk baris 3,4,5
                data_range = "B3:AF5"
                data = worksheet.get(data_range)
                
                if not data:
                    all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                    continue
                
                # Proses data
                today = datetime.date.today()
                current_month = today.month
                current_year = today.year
                
                # Buat DataFrame sederhana
                df_raw = pd.DataFrame()
                df_raw['tanggal'] = [f"{current_year}-{current_month:02d}-{day:02d}" for day in range(1, 32)]
                
                # Ambil data pH, suhu, debit
                if len(data) >= 1:
                    df_raw['pH'] = [float(x) if x != '' else None for x in data[0][:31]]
                else:
                    df_raw['pH'] = [None] * 31
                    
                if len(data) >= 2:
                    df_raw['suhu'] = [float(x) if x != '' else None for x in data[1][:31]]
                else:
                    df_raw['suhu'] = [None] * 31
                    
                if len(data) >= 3:
                    df_raw['debit'] = [float(x) if x != '' else None for x in data[2][:31]]
                else:
                    df_raw['debit'] = [None] * 31
                
                # Hitung rata-rata
                ph_valid = [x for x in df_raw['pH'] if x is not None]
                suhu_valid = [x for x in df_raw['suhu'] if x is not None]
                debit_valid = [x for x in df_raw['debit'] if x is not None]
                
                ph_rata = round(sum(ph_valid) / len(ph_valid), 2) if ph_valid else None
                suhu_rata = round(sum(suhu_valid) / len(suhu_valid), 1) if suhu_valid else None
                debit_rata = round(sum(debit_valid) / len(debit_valid), 2) if debit_valid else None
                
                # Tambahkan baris rata-rata
                avg_row = {
                    "tanggal": f"Rata-rata {current_month:02d}/{current_year}",
                    "pH": None, "suhu": None, "debit": None,
                    "ph_rata_rata_bulan": ph_rata,
                    "suhu_rata_rata_bulan": suhu_rata,
                    "debit_rata_rata_bulan": debit_rata
                }
                df_raw = pd.concat([df_raw, pd.DataFrame([avg_row])], ignore_index=True)
                
                all_dfs_raw[sheet_name] = df_raw.reindex(columns=INTERNAL_COLUMNS)
                
            except Exception as e:
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
        except Exception as e:
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data ke Google Sheets - VERSI SEDERHANA
    """
    try:
        # Filter Data Harian
        df_harian = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
        
        # Siapkan data untuk ditulis
        data_harian = {
            'pH': [x if x is not None and not pd.isna(x) else '' for x in df_harian['pH']],
            'suhu': [x if x is not None and not pd.isna(x) else '' for x in df_harian['suhu']],
            'debit': [x if x is not None and not pd.isna(x) else '' for x in df_harian['debit']]
        }
        
        with st.spinner(f"Menyimpan data ke {lokasi}..."):
            # Buka spreadsheet
            spreadsheet = client.open_by_key(SHEET_ID)
            
            # Cek atau buat worksheet
            try:
                worksheet = spreadsheet.worksheet(lokasi)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=lokasi, rows="50", cols="35")
            
            # Tulis data harian
            # Baris 3: pH, Baris 4: Suhu, Baris 5: Debit
            if data_harian['pH']:
                worksheet.update('B3:AF3', [data_harian['pH'][:31]])
            
            if data_harian['suhu']:
                worksheet.update('B4:AF4', [data_harian['suhu'][:31]])
            
            if data_harian['debit']:
                worksheet.update('B5:AF5', [data_harian['debit'][:31]])
            
            # Tulis rata-rata
            rata_rata_rows = df_raw_data[df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)]
            if not rata_rata_rows.empty:
                rata_row = rata_rata_rows.iloc[0]
                
                if pd.notna(rata_row['ph_rata_rata_bulan']):
                    worksheet.update_acell('AG3', rata_row['ph_rata_rata_bulan'])
                
                if pd.notna(rata_row['suhu_rata_rata_bulan']):
                    worksheet.update_acell('AG4', rata_row['suhu_rata_rata_bulan'])
                
                if pd.notna(rata_row['debit_rata_rata_bulan']):
                    worksheet.update_acell('AG5', rata_row['debit_rata_rata_bulan'])
            
            st.success(f"✅ Data berhasil disimpan di {lokasi}!")
            time.sleep(2)
            st.rerun()
            
    except Exception as e:
        st.error(f"❌ Gagal menyimpan data: {e}")

# ==================== BAGIAN UTAMA APLIKASI ====================

# 1. SIDEBAR: Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_sheet = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=SHEET_NAMES,
    index=0 
)

# 2. Muat Semua Data
all_data = read_all_sheets_gsheets()
current_df = all_data.get(selected_sheet, pd.DataFrame(columns=INTERNAL_COLUMNS))

# Tampilkan Status Lokasi
st.subheader(f"Data Harian untuk Lokasi: **{selected_sheet}**")

# 3. Input Data Baru
st.markdown("---")
st.header("📝 Catat Data Baru")

# Dapatkan hari ini untuk input default
today_date = datetime.date.today()
today_day = today_date.day

with st.form("input_form"):
    
    # Pilih Hari
    day_options = [day for day in range(1, 32)]
    default_day_index = day_options.index(today_day) if today_day in day_options else 0
    
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=day_options,
        index=default_day_index
    )
    
    st.write(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

    # Ambil nilai default jika hari yang dipilih sudah ada datanya
    existing_row = current_df[current_df['tanggal'] == f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"]
    
    default_ph = existing_row['pH'].iloc[0] if not existing_row.empty and pd.notna(existing_row['pH'].iloc[0]) else None
    default_suhu = existing_row['suhu'].iloc[0] if not existing_row.empty and pd.notna(existing_row['suhu'].iloc[0]) else None
    default_debit = existing_row['debit'].iloc[0] if not existing_row.empty and pd.notna(existing_row['debit'].iloc[0]) else None
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input(
            "Nilai pH", 
            min_value=0.0, max_value=14.0, 
            format="%.2f", step=0.01,
            value=default_ph
        )
    with col2:
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0, 
            format="%.1f", step=0.1,
            value=default_suhu
        )
    with col3:
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0, 
            format="%.2f", step=0.01,
            value=default_debit
        )
        
    submitted = st.form_submit_button("Simpan Data ke Google Sheets", type="primary")

    if submitted:
        if input_ph is None or input_suhu is None or input_debit is None:
            st.error("Mohon isi semua kolom (pH, Suhu, dan Debit) sebelum menyimpan.")
        else:
            target_date_str = f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            
            # Update data
            if not current_df.empty:
                # Hapus data existing untuk hari yang sama
                current_df_clean = current_df[current_df['tanggal'] != target_date_str]
                # Tambah data baru
                new_data = {
                    'tanggal': target_date_str,
                    'pH': input_ph,
                    'suhu': input_suhu,
                    'debit': input_debit
                }
                new_row = pd.DataFrame([new_data])
                updated_df = pd.concat([current_df_clean, new_row], ignore_index=True)
            else:
                # Buat data baru
                new_data = {
                    'tanggal': target_date_str,
                    'pH': input_ph,
                    'suhu': input_suhu,
                    'debit': input_debit
                }
                updated_df = pd.DataFrame([new_data])
            
            # Simpan ke Google Sheets
            save_sheet_to_gsheets(selected_sheet, updated_df)

# 4. Tampilkan Data
st.markdown("---")
st.subheader("Tinjauan Data Saat Ini (Dari Google Sheets)")

if not current_df.empty:
    display_df = current_df.copy()
    display_df.replace({np.nan: '', None: ''}, inplace=True)
    display_df['Hari'] = display_df['tanggal'].apply(
        lambda x: x.split('-')[-1] if isinstance(x, str) and '-' in x else x
    )
    
    display_df.rename(columns={
        'pH': 'pH',
        'suhu': 'Suhu (°C)',
        'debit': 'Debit (l/d)'
    }, inplace=True)
    
    # Pilih kolom untuk display
    display_columns = ['Hari', 'pH', 'Suhu (°C)', 'Debit (l/d)']
    display_df = display_df[display_columns]

    st.dataframe(
        display_df,
        hide_index=True,
        width='stretch',
        height=400,
    )
else:
    st.info("Belum ada data untuk lokasi ini.")

st.caption("Aplikasi Monitoring Air - Data tersimpan di Google Sheets")
