import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter
import datetime
import time 
import gspread
from google.oauth2.service_account import Credentials

# ========== KONEKSI GOOGLE SHEETS ==========
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
        
        # Test koneksi
        spreadsheet = client.open_by_key(st.secrets["SHEET_ID"])
        st.success("✅ Koneksi Google Sheets berhasil!")
        return client
        
    except Exception as e:
        st.error(f"❌ Gagal inisialisasi koneksi Google Sheets: {str(e)}")
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

# Mapping baris di Google Sheet Anda (Baris 3, 4, 5)
GSHEET_ROW_MAP = {
    'pH': 3,          
    'suhu': 4,        
    'debit': 5,        
}

GSHEET_AVG_COL_INDEX = 33 

st.set_page_config(page_title="Monitoring Air", layout="centered")
st.title("📊 Monitoring Air")

# ----------------------------
# Utility: baca & simpan sheet 
# ----------------------------
@st.cache_data(ttl=10)
def read_all_sheets_gsheets():
    """
    Membaca semua sheet dari Google Sheets - VERSI SIMPLIFIED
    """
    all_dfs_raw = {}
    today = datetime.date.today()
    current_month = today.month
    current_year = today.year
    
    for sheet_name in SHEET_NAMES:
        try:
            # Buka spreadsheet
            spreadsheet = client.open_by_key(SHEET_ID)
            
            # Cek apakah worksheet ada
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                continue
            except gspread.exceptions.WorksheetNotFound:
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                continue
            
        except Exception as e:
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data ke Google Sheets - VERSI DIPERBAIKI DENGAN DEBUG
    """
    try:
        # Clear cache
        read_all_sheets_gsheets.clear()
        
        st.write("🔍 Debug: Memulai proses penyimpanan...")
        
        # 1. Filter Data Harian (tanpa baris rata-rata)
        df_harian = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
        st.write(f"🔍 Debug: Jumlah data harian: {len(df_harian)}")
        
        # 2. Siapkan data untuk ditulis
        data_harian = {
            'pH': [x if x is not None and not pd.isna(x) else '' for x in df_harian['pH']],
            'suhu': [x if x is not None and not pd.isna(x) else '' for x in df_harian['suhu']],
            'debit': [x if x is not None and not pd.isna(x) else '' for x in df_harian['debit']]
        }
        
        st.write(f"🔍 Debug: Data pH: {data_harian['pH']}")
        st.write(f"🔍 Debug: Data suhu: {data_harian['suhu']}")
        st.write(f"🔍 Debug: Data debit: {data_harian['debit']}")
        
        with st.spinner(f"Menyimpan data ke {lokasi}..."):
            try:
                # Buka spreadsheet
                st.write("🔍 Debug: Membuka spreadsheet...")
                spreadsheet = client.open_by_key(SHEET_ID)
                
                # Cek atau buat worksheet
                try:
                    st.write(f"🔍 Debug: Mencoba membuka worksheet {lokasi}...")
                    worksheet = spreadsheet.worksheet(lokasi)
                    st.write("🔍 Debug: Worksheet ditemukan")
                except gspread.exceptions.WorksheetNotFound:
                    st.write(f"🔍 Debug: Worksheet {lokasi} tidak ditemukan, membuat baru...")
                    worksheet = spreadsheet.add_worksheet(title=lokasi, rows="50", cols="35")
                    st.write("🔍 Debug: Worksheet baru dibuat")
                
                # Tulis data harian (kolom B sampai AF) - hanya 31 hari pertama
                data_to_write = data_harian['pH'][:31]  # Max 31 hari
                st.write(f"🔍 Debug: Menulis data pH: {data_to_write}")
                
                # Tulis pH (baris 3)
                if data_harian['pH']:
                    range_ph = "B3:AF3"
                    st.write(f"🔍 Debug: Range pH: {range_ph}")
                    worksheet.update(range_ph, [data_harian['pH'][:31]])
                    st.write("🔍 Debug: Data pH berhasil ditulis")
                
                # Tulis Suhu (baris 4)  
                if data_harian['suhu']:
                    range_suhu = "B4:AF4"
                    st.write(f"🔍 Debug: Range suhu: {range_suhu}")
                    worksheet.update(range_suhu, [data_harian['suhu'][:31]])
                    st.write("🔍 Debug: Data suhu berhasil ditulis")
                
                # Tulis Debit (baris 5)
                if data_harian['debit']:
                    range_debit = "B5:AF5"
                    st.write(f"🔍 Debug: Range debit: {range_debit}")
                    worksheet.update(range_debit, [data_harian['debit'][:31]])
                    st.write("🔍 Debug: Data debit berhasil ditulis")
                
                # Hitung dan tulis rata-rata
                st.write("🔍 Debug: Menghitung rata-rata...")
                ph_valid = [x for x in data_harian['pH'] if x != '']
                suhu_valid = [x for x in data_harian['suhu'] if x != '']
                debit_valid = [x for x in data_harian['debit'] if x != '']
                
                ph_rata = round(sum(ph_valid) / len(ph_valid), 2) if ph_valid else ''
                suhu_rata = round(sum(suhu_valid) / len(suhu_valid), 1) if suhu_valid else ''
                debit_rata = round(sum(debit_valid) / len(debit_valid), 2) if debit_valid else ''
                
                st.write(f"🔍 Debug: Rata-rata - pH: {ph_rata}, Suhu: {suhu_rata}, Debit: {debit_rata}")
                
                # Tulis rata-rata (kolom AG)
                if ph_rata != '':
                    worksheet.update_acell('AG3', ph_rata)
                if suhu_rata != '':
                    worksheet.update_acell('AG4', suhu_rata)  
                if debit_rata != '':
                    worksheet.update_acell('AG5', debit_rata)
                
                st.success(f"✅ Data berhasil disimpan di {lokasi}!")
                time.sleep(2)
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Gagal menyimpan ke Google Sheets: {str(e)}")
                st.write("🔍 Debug Info Tambahan:")
                st.write(f"- Error type: {type(e).__name__}")
                st.write(f"- Lokasi: {lokasi}")
                st.write(f"- Jumlah data: {len(df_harian)}")
    
    except Exception as e:
        st.error(f"❌ Error dalam proses penyimpanan: {str(e)}")
        st.write("🔍 Debug Error Detail:")
        st.write(f"- Error type: {type(e).__name__}")

# ==================== BAGIAN UTAMA APLIKASI ====================

# 1. SIDEBAR: Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_sheet = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=SHEET_NAMES,
    index=0 
)

# 2. Muat Semua Data
try:
    all_data = read_all_sheets_gsheets()
    current_df = all_data.get(selected_sheet, pd.DataFrame(columns=INTERNAL_COLUMNS))
except Exception as e:
    st.error(f"❌ Gagal memuat data: {e}")
    current_df = pd.DataFrame(columns=INTERNAL_COLUMNS)

# Tampilkan Status Lokasi
st.subheader(f"Data Harian untuk Lokasi: **{selected_sheet}**")

# 3. Input Data Baru (Gunakan Form)
st.markdown("---")
st.header("📝 Catat Data Baru")

# Dapatkan hari ini untuk input default
today_date = datetime.date.today()
today_day = today_date.day

# Cek apakah data untuk hari ini sudah ada
is_day_recorded = False
if not current_df.empty:
    try:
        existing_dates = [str(date) for date in current_df['tanggal'] if isinstance(date, str)]
        is_day_recorded = any(f"{today_date.year}-{today_date.month:02d}-{today_day:02d}" in date for date in existing_dates)
    except:
        is_day_recorded = False

if is_day_recorded:
    st.info(f"Data untuk tanggal **{today_day}** sudah ada.")
    st.markdown("Anda bisa menggunakan bagian di bawah untuk **mengubah** data yang sudah ada.")
    
with st.form("input_form"):
    
    # Pilih Hari
    day_options = [day for day in range(1, 32)]
    default_day_index = day_options.index(today_day) if today_day in day_options else 0
    
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=day_options,
        index=default_day_index,
        key='input_day'
    )
    
    st.write(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

    # Ambil nilai default jika hari yang dipilih sudah ada datanya
    default_ph = None
    default_suhu = None
    default_debit = None
    
    if not current_df.empty:
        try:
            target_date = f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            existing_data = current_df[current_df['tanggal'] == target_date]
            if not existing_data.empty:
                default_ph = existing_data['pH'].iloc[0] if pd.notna(existing_data['pH'].iloc[0]) else None
                default_suhu = existing_data['suhu'].iloc[0] if pd.notna(existing_data['suhu'].iloc[0]) else None
                default_debit = existing_data['debit'].iloc[0] if pd.notna(existing_data['debit'].iloc[0]) else None
        except:
            pass
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input(
            "Nilai pH", 
            min_value=0.0, max_value=14.0, 
            format="%.2f", step=0.01,
            key='input_ph',
            value=default_ph
        )
    with col2:
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0, 
            format="%.1f", step=0.1,
            key='input_suhu',
            value=default_suhu
        )
    with col3:
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0, 
            format="%.2f", step=0.01,
            key='input_debit',
            value=default_debit
        )
        
    submitted = st.form_submit_button("Simpan Data ke Google Sheets", type="primary")

    if submitted:
        if input_ph is None or input_suhu is None or input_debit is None:
            st.error("Mohon isi semua kolom (pH, Suhu, dan Debit) sebelum menyimpan.")
        else:
            target_date_str = f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            
            # Buat data baru
            new_data = {
                'tanggal': target_date_str,
                'pH': input_ph,
                'suhu': input_suhu,
                'debit': input_debit
            }
            
            # Update DataFrame
            if not current_df.empty:
                # Hapus data existing untuk hari yang sama
                current_df_clean = current_df[
                    current_df['tanggal'] != target_date_str
                ]
                # Tambah data baru
                new_row = pd.DataFrame([new_data])
                updated_df = pd.concat([current_df_clean, new_row], ignore_index=True)
            else:
                # DataFrame kosong, buat baru
                updated_df = pd.DataFrame([new_data])
            
            # Simpan ke Google Sheets
            save_sheet_to_gsheets(selected_sheet, updated_df)

# 4. Tampilkan Data
st.markdown("---")
st.subheader("Tinjauan Data Saat Ini (Dari Google Sheets)")

if not current_df.empty:
    display_df = current_df.copy()
    display_df.replace({np.nan: '', None: ''}, inplace=True)
    
    # Format tanggal untuk display
    def format_tanggal(x):
        if isinstance(x, str) and '-' in x:
            return x.split('-')[-1]
        return x
    
    display_df['Hari'] = display_df['tanggal'].apply(format_tanggal)
    
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

st.caption("Catatan: Data di atas adalah hasil konversi dari format pivot Google Sheets Anda.")
