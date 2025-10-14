import streamlit as st
import pandas as pd
import numpy as np
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials

# ----------------------------
# KONEKSI GOOGLE SHEETS
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

# KONFIGURASI YANG BENAR - SESUAI SHEET ANDA
SHEET_NAME = "Rata-rata"  # ✅ Nama worksheet yang benar
LOKASI_OPTIONS = [
    "Power Plant", "Plan Garage", "Drain A", "Drain B", "Drain C", 
    "WTP", "Coal Yard", "Domestik", "Limestone"
]

# MAPPING LOKASI - SESUAIKAN DENGAN STRUKTUR SHEET ANDA
LOKASI_ROW_MAP = {
    "Power Plant": {"pH": 3, "suhu": 4, "debit": 5},
    "Plan Garage": {"pH": 7, "suhu": 8, "debit": 9},
    "Drain A": {"pH": 11, "suhu": 12, "debit": 13},
    "Drain B": {"pH": 15, "suhu": 16, "debit": 17},
    "Drain C": {"pH": 19, "suhu": 20, "debit": 21},
    "WTP": {"pH": 23, "suhu": 24, "debit": 25},
    "Coal Yard": {"pH": 27, "suhu": 28, "debit": 29},
    "Domestik": {"pH": 31, "suhu": 32, "debit": 33},
    "Limestone": {"pH": 35, "suhu": 36, "debit": 37},
}

st.set_page_config(page_title="Monitoring Air", layout="centered")
st.title("📊 Monitoring Air - Rata-rata")

# ----------------------------
# FUNGSI UTAMA - UNTUK SHEET "Rata-rata"
# ----------------------------
def baca_data_dari_sheet():
    """Membaca data dari sheet 'Rata-rata'"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)  # ✅ Gunakan SHEET_NAME yang benar
        all_data = worksheet.get_all_values()
        
        data_dict = {}
        
        for lokasi, row_map in LOKASI_ROW_MAP.items():
            try:
                # Data untuk 31 hari
                pH_data = []
                suhu_data = []
                debit_data = []
                
                for hari in range(31):
                    col_index = hari + 1  # Kolom B=1, C=2, ..., AF=31
                    
                    # Baca data pH
                    if (row_map["pH"] - 1 < len(all_data) and 
                        col_index < len(all_data[row_map["pH"] - 1])):
                        val = all_data[row_map["pH"] - 1][col_index]
                        pH_data.append(float(val) if val and val.strip() else None)
                    else:
                        pH_data.append(None)
                    
                    # Baca data suhu
                    if (row_map["suhu"] - 1 < len(all_data) and 
                        col_index < len(all_data[row_map["suhu"] - 1])):
                        val = all_data[row_map["suhu"] - 1][col_index]
                        suhu_data.append(float(val) if val and val.strip() else None)
                    else:
                        suhu_data.append(None)
                    
                    # Baca data debit
                    if (row_map["debit"] - 1 < len(all_data) and 
                        col_index < len(all_data[row_map["debit"] - 1])):
                        val = all_data[row_map["debit"] - 1][col_index]
                        debit_data.append(float(val) if val and val.strip() else None)
                    else:
                        debit_data.append(None)
                
                # Buat DataFrame
                today = datetime.date.today()
                dates = [f"{today.year}-{today.month:02d}-{day:02d}" for day in range(1, 32)]
                
                df = pd.DataFrame({
                    'tanggal': dates,
                    'pH': pH_data,
                    'suhu': suhu_data,
                    'debit': debit_data
                })
                
                data_dict[lokasi] = df
                
            except Exception as e:
                st.warning(f"Gagal baca data untuk {lokasi}: {e}")
                # Buat dataframe kosong
                today = datetime.date.today()
                dates = [f"{today.year}-{today.month:02d}-{day:02d}" for day in range(1, 32)]
                data_dict[lokasi] = pd.DataFrame({
                    'tanggal': dates,
                    'pH': [None] * 31,
                    'suhu': [None] * 31,
                    'debit': [None] * 31
                })
        
        return data_dict
        
    except Exception as e:
        st.error(f"❌ Gagal membaca data dari sheet: {e}")
        return {}

def simpan_data_ke_sheet(lokasi, hari, pH, suhu, debit):
    """Menyimpan data ke sheet 'Rata-rata'"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)  # ✅ Gunakan SHEET_NAME yang benar
        
        row_map = LOKASI_ROW_MAP.get(lokasi)
        if not row_map:
            st.error(f"❌ Lokasi {lokasi} tidak ditemukan dalam mapping")
            return False
        
        # Kolom untuk hari tertentu (B=hari1, C=hari2, ..., AF=hari31)
        col_index = hari + 1  # +1 karena kolom A=1, B=2
        
        # Update data
        worksheet.update_cell(row_map["pH"], col_index, pH)
        worksheet.update_cell(row_map["suhu"], col_index, suhu)
        worksheet.update_cell(row_map["debit"], col_index, debit)
        
        st.success(f"✅ Data berhasil disimpan di {lokasi}, Hari {hari}")
        return True
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan data: {e}")
        return False

# ==================== BAGIAN UTAMA APLIKASI ====================

# 1. SIDEBAR: Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_lokasi = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=LOKASI_OPTIONS,
    index=0 
)

# Debug helper
if st.sidebar.button("🔧 Debug Connection"):
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        st.sidebar.success("✅ Terhubung ke Google Sheets!")
        st.sidebar.write(f"Worksheet: {SHEET_NAME}")
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")

# 2. Muat Data
with st.spinner("Memuat data dari Google Sheets..."):
    all_data = baca_data_dari_sheet()
current_df = all_data.get(selected_lokasi, pd.DataFrame())

# Tampilkan Status Lokasi
st.subheader(f"📍 Lokasi: {selected_lokasi}")

# 3. Input Data Baru
st.markdown("---")
st.header("📝 Catat Data Baru")

# Dapatkan hari ini untuk input default
today_date = datetime.date.today()
today_day = today_date.day

with st.form("input_form"):
    
    # Pilih Hari
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=list(range(1, 32)),
        index=today_day - 1
    )
    
    st.write(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

    # Ambil nilai existing jika ada
    existing_ph = existing_suhu = existing_debit = None
    if not current_df.empty and input_day <= len(current_df):
        existing_data = current_df.iloc[input_day - 1]
        existing_ph = existing_data['pH'] if pd.notna(existing_data['pH']) else None
        existing_suhu = existing_data['suhu'] if pd.notna(existing_data['suhu']) else None
        existing_debit = existing_data['debit'] if pd.notna(existing_data['debit']) else None

    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input(
            "Nilai pH", 
            min_value=0.0, max_value=14.0, 
            value=existing_ph if existing_ph is not None else 7.0,
            step=0.1,
            format="%.1f"
        )
    with col2:
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0, 
            value=existing_suhu if existing_suhu is not None else 25.0,
            step=0.1,
            format="%.1f"
        )
    with col3:
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0,
            value=existing_debit if existing_debit is not None else 0.0,
            step=0.1,
            format="%.1f"
        )
        
    submitted = st.form_submit_button("💾 Simpan Data ke Google Sheets", type="primary")

    if submitted:
        with st.spinner("Menyimpan data..."):
            success = simpan_data_ke_sheet(selected_lokasi, input_day, input_ph, input_suhu, input_debit)
            if success:
                time.sleep(2)
                st.rerun()

# 4. Tampilkan Data
st.markdown("---")
st.subheader("📋 Data Saat Ini (Dari Google Sheets)")

if not current_df.empty:
    display_df = current_df.copy()
    display_df['Hari'] = display_df['tanggal'].str.split('-').str[-1]
    
    # Format untuk display
    display_df = display_df[['Hari', 'pH', 'suhu', 'debit']]
    display_df = display_df.replace({np.nan: '', None: ''})
    
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        height=400
    )
else:
    st.info("Belum ada data untuk lokasi ini.")

st.caption("Aplikasi Monitoring Air - Worksheet: Rata-rata")
