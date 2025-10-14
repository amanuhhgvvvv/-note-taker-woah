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
    SHEET_ID = st.secrets["SHEET_ID"]
except Exception as e:
    st.error(f"❌ Gagal mengambil SHEET_ID dari secrets: {e}")
    st.stop()

SHEET_NAMES = [
    "Power Plant", "Plan Garage", "Drain A", "Drain B", "Drain C", 
    "WTP", "Coal Yard", "Domestik", "Limestone", "Clay Laterite", 
    "Silika", "Kondensor PLTU"
]

st.set_page_config(page_title="Monitoring Air", layout="centered")
st.title("📊 Monitoring Air")

# ----------------------------
# FUNGSI UTAMA - SUDAH SESUAI STRUKTUR
# ----------------------------
def simpan_data_ke_sheet(lokasi, hari, pH, suhu, debit):
    """Menyimpan data ke worksheet - SUDAH SESUAI STRUKTUR ANDA"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(lokasi)
        
        # ✅ MAPPING YANG BENAR BERDASARKAN STRUKTUR ANDA:
        # Baris 3: pH, Baris 4: suhu, Baris 5: debit
        # Kolom B=hari1, C=hari2, ..., AF=hari31
        mapping = {
            "pH": 3,
            "suhu": 4, 
            "debit": 5
        }
        
        # Kolom untuk hari tertentu
        # Kolom A=1, B=2, C=3, ..., AF=32
        kolom = hari + 1  # Karena hari1 → kolom B (index 2)
        
        # Update data
        worksheet.update_cell(mapping["pH"], kolom, pH)
        worksheet.update_cell(mapping["suhu"], kolom, suhu)
        worksheet.update_cell(mapping["debit"], kolom, debit)
        
        st.success(f"✅ Data berhasil disimpan di {lokasi}!")
        st.info(f"📊 Posisi: Baris {mapping['pH']}-{mapping['debit']}, Kolom {kolom} (Hari {hari})")
        return True
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan: {str(e)}")
        return False

def baca_data_dari_sheet(lokasi):
    """Membaca data dari worksheet"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(lokasi)
        
        # Baca data hari 1-31 dari baris 3,4,5
        data_range = "B3:AF5"  # Kolom B sampai AF, baris 3-5
        data = worksheet.get(data_range)
        
        if not data:
            return pd.DataFrame()
        
        # Proses data
        today = datetime.date.today()
        current_month = today.month
        current_year = today.year
        
        # Buat DataFrame
        df = pd.DataFrame()
        df['Hari'] = list(range(1, 32))
        df['Tanggal'] = [f"{current_year}-{current_month:02d}-{day:02d}" for day in range(1, 32)]
        
        # Ambil data pH, suhu, debit
        if len(data) >= 1:
            df['pH'] = [float(x) if x != '' else None for x in data[0][:31]]
        else:
            df['pH'] = [None] * 31
            
        if len(data) >= 2:
            df['Suhu (°C)'] = [float(x) if x != '' else None for x in data[1][:31]]
        else:
            df['Suhu (°C)'] = [None] * 31
            
        if len(data) >= 3:
            df['Debit (l/d)'] = [float(x) if x != '' else None for x in data[2][:31]]
        else:
            df['Debit (l/d)'] = [None] * 31
        
        return df
        
    except Exception as e:
        st.error(f"❌ Gagal membaca data: {e}")
        return pd.DataFrame()

# ==================== APLIKASI UTAMA ====================

# Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_lokasi = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=SHEET_NAMES,
    index=0 
)

# Muat data existing
current_df = baca_data_dari_sheet(selected_lokasi)

# Tampilkan Status Lokasi
st.subheader(f"📍 Lokasi: {selected_lokasi}")

# Input Data Baru
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
    existing_data = None
    if not current_df.empty and input_day <= len(current_df):
        existing_data = current_df.iloc[input_day - 1]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input(
            "Nilai pH", 
            min_value=0.0, max_value=14.0, 
            value=existing_data['pH'] if existing_data is not None and pd.notna(existing_data['pH']) else 8.0,
            step=0.1,
            format="%.1f"
        )
    with col2:
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0, 
            value=existing_data['Suhu (°C)'] if existing_data is not None and pd.notna(existing_data['Suhu (°C)']) else 27.0,
            step=0.1,
            format="%.1f"
        )
    with col3:
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0,
            value=existing_data['Debit (l/d)'] if existing_data is not None and pd.notna(existing_data['Debit (l/d)']) else 65.0,
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

# Tampilkan Data Existing
st.markdown("---")
st.subheader("📋 Data Saat Ini")

if not current_df.empty:
    # Filter kolom untuk display
    display_columns = ['Hari', 'Tanggal', 'pH', 'Suhu (°C)', 'Debit (l/d)']
    display_df = current_df[display_columns].replace({np.nan: ''})
    
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        height=400
    )
else:
    st.info("Belum ada data untuk lokasi ini.")

st.caption("Aplikasi Monitoring Air")
