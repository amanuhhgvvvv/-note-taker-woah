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

SHEET_NAME = "Rata-rata"
LOKASI_OPTIONS = ["Power Plant", "Plan Garage", "Drain A", "Drain B", "Drain C", "WTP", "Coal Yard", "Domestik", "Limestone"]

st.set_page_config(page_title="Monitoring Air", layout="centered")
st.title("📊 Monitoring Air")

# ----------------------------
# FUNGSI SEDERHANA - TEST DULU
# ----------------------------
def test_koneksi_dan_baca():
    """Fungsi sederhana untuk test koneksi dan baca data"""
    try:
        # Test koneksi
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        
        st.sidebar.success("✅ Terhubung ke Google Sheets!")
        
        # Baca data sederhana - hanya 10 baris pertama
        data = worksheet.get_values("A1:J10")
        
        st.sidebar.subheader("📊 Data Sample (A1:J10):")
        for i, row in enumerate(data):
            st.sidebar.write(f"Baris {i+1}: {row}")
        
        return True
        
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")
        return False

def simpan_data_sederhana(lokasi, hari, pH, suhu, debit):
    """Fungsi sederhana untuk menyimpan data"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        
        # TENTUKAN POSISI BERDASARKAN LOKASI
        # Ini adalah tebakan - kita perlu sesuaikan nanti
        baris_map = {
            "Power Plant": {"pH": 3, "suhu": 4, "debit": 5},
            "Plan Garage": {"pH": 6, "suhu": 7, "debit": 8},
            "Drain A": {"pH": 9, "suhu": 10, "debit": 11},
            "Drain B": {"pH": 12, "suhu": 13, "debit": 14},
            "Drain C": {"pH": 15, "suhu": 16, "debit": 17},
            "WTP": {"pH": 18, "suhu": 19, "debit": 20},
            "Coal Yard": {"pH": 21, "suhu": 22, "debit": 23},
            "Domestik": {"pH": 24, "suhu": 25, "debit": 26},
            "Limestone": {"pH": 27, "suhu": 28, "debit": 29},
        }
        
        mapping = baris_map.get(lokasi)
        if not mapping:
            st.error(f"❌ Mapping untuk {lokasi} tidak ditemukan")
            return False
        
        # Kolom: B=1, C=2, D=3, ..., AF=31
        kolom = hari + 1
        
        # Update cell
        worksheet.update_cell(mapping["pH"], kolom, pH)
        worksheet.update_cell(mapping["suhu"], kolom, suhu) 
        worksheet.update_cell(mapping["debit"], kolom, debit)
        
        st.success(f"✅ Data berhasil disimpan!")
        st.info(f"Lokasi: {lokasi}, Hari: {hari}")
        st.info(f"pH: {pH} → Baris {mapping['pH']}, Kolom {kolom}")
        st.info(f"Suhu: {suhu} → Baris {mapping['suhu']}, Kolom {kolom}")
        st.info(f"Debit: {debit} → Baris {mapping['debit']}, Kolom {kolom}")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan: {str(e)}")
        return False

# ==================== APLIKASI UTAMA ====================

# Test koneksi dulu
if st.sidebar.button("🔧 Test Koneksi"):
    test_koneksi_dan_baca()

# Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_lokasi = st.sidebar.selectbox(
    "Pilih Lokasi:",
    options=LOKASI_OPTIONS,
    index=0 
)

# Input Data
st.header("📝 Input Data Baru")

today_date = datetime.date.today()
today_day = today_date.day

with st.form("input_form"):
    input_day = st.selectbox(
        "Pilih Hari untuk Pencatatan:",
        options=list(range(1, 32)),
        index=today_day - 1
    )
    
    st.write(f"**Tanggal:** {today_date.year}-{today_date.month:02d}-{input_day:02d}")

    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input("Nilai pH", min_value=0.0, max_value=14.0, value=7.0, step=0.1, format="%.1f")
    with col2:
        input_suhu = st.number_input("Suhu (°C)", min_value=0.0, max_value=100.0, value=25.0, step=0.1, format="%.1f")
    with col3:
        input_debit = st.number_input("Debit (l/d)", min_value=0.0, value=0.0, step=0.1, format="%.1f")
    
    submitted = st.form_submit_button("💾 Simpan Data", type="primary")

    if submitted:
        with st.spinner("Menyimpan data..."):
            success = simpan_data_sederhana(selected_lokasi, input_day, input_ph, input_suhu, input_debit)
            if success:
                st.balloons()

# Informasi
st.markdown("---")
st.info("""
**Cara penggunaan:**
1. Pilih lokasi dan hari
2. Input data pH, suhu, debit  
3. Klik **Test Koneksi** di sidebar untuk debug
4. Simpan data
""")

st.caption("Aplikasi Monitoring Air")
