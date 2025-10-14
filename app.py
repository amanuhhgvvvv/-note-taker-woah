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
# FUNGSI UTAMA DENGAN DEBUG DETAIL
# ----------------------------
def debug_detailed_sheet_structure():
    """Debug detail struktur sheet"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Cek semua worksheet yang ada
        worksheets = spreadsheet.worksheets()
        st.sidebar.subheader("📋 Worksheets Tersedia:")
        for ws in worksheets:
            st.sidebar.write(f"- {ws.title}")
        
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        
        # Baca range yang lebih besar untuk analisis
        st.sidebar.subheader("🔍 Struktur Detail (A1:Z50):")
        all_data = worksheet.get_values("A1:Z50")
        
        for i, row in enumerate(all_data):
            # Hanya tampilkan baris yang tidak kosong
            if any(cell.strip() for cell in row if cell):
                st.sidebar.write(f"Baris {i+1}: {row}")
        
        return worksheet, all_data
        
    except Exception as e:
        st.sidebar.error(f"❌ Debug error: {str(e)}")
        return None, None

def cari_posisi_lokasi_manual(worksheet, all_data):
    """Cari posisi lokasi secara manual dari data"""
    lokasi_positions = {}
    
    # Cari setiap lokasi dalam data
    for i, row in enumerate(all_data):
        for j, cell in enumerate(row):
            cell_text = str(cell).strip().lower()
            
            # Cek setiap lokasi option
            for lokasi in LOKASI_OPTIONS:
                if lokasi.lower() in cell_text:
                    st.sidebar.info(f"📍 Ditemukan '{lokasi}' di Baris {i+1}, Kolom {j+1}")
                    
                    # Asumsikan struktur: lokasi, kemudian pH, suhu, debit di baris berikutnya
                    lokasi_positions[lokasi] = {
                        "pH": i + 2,  # Baris setelah nama lokasi
                        "suhu": i + 3,
                        "debit": i + 4,
                        "found_at": f"Baris {i+1}, Kolom {j+1}"
                    }
    
    return lokasi_positions

def simpan_data_dengan_debug(lokasi, hari, pH, suhu, debit, lokasi_map):
    """Simpan data dengan debugging detail"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        
        mapping = lokasi_map.get(lokasi)
        if not mapping:
            st.error(f"❌ Tidak ada mapping untuk: {lokasi}")
            st.info(f"Lokasi yang tersedia: {list(lokasi_map.keys())}")
            return False
        
        # Kolom: A=1, B=2, C=3, ..., AF=32
        kolom = hari + 1  # Karena kolom A=1 (judul), B=2 (hari1), C=3 (hari2), dst
        
        st.write("🔧 **Debug Info:**")
        st.write(f"- Lokasi: {lokasi}")
        st.write(f"- Mapping: pH baris {mapping['pH']}, suhu baris {mapping['suhu']}, debit baris {mapping['debit']}")
        st.write(f"- Hari: {hari} → Kolom: {kolom} ({(chr(64+kolom))})")
        st.write(f"- Data: pH={pH}, suhu={suhu}, debit={debit}")
        
        # Test baca data existing dulu
        try:
            existing_ph = worksheet.cell(mapping["pH"], kolom).value
            existing_suhu = worksheet.cell(mapping["suhu"], kolom).value
            existing_debit = worksheet.cell(mapping["debit"], kolom).value
            
            st.write(f"📊 Data existing: pH={existing_ph}, suhu={existing_suhu}, debit={existing_debit}")
        except Exception as e:
            st.write(f"ℹ️ Tidak bisa baca data existing: {e}")
        
        # Update data
        worksheet.update_cell(mapping["pH"], kolom, pH)
        worksheet.update_cell(mapping["suhu"], kolom, suhu)
        worksheet.update_cell(mapping["debit"], kolom, debit)
        
        st.success("✅ Data berhasil disimpan!")
        return True
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan: {str(e)}")
        # Tampilkan error detail
        import traceback
        st.code(traceback.format_exc())
        return False

# ==================== APLIKASI UTAMA ====================

# Debug struktur sheet
worksheet, debug_data = debug_detailed_sheet_structure()

# Cari posisi lokasi
if debug_data:
    lokasi_map = cari_posisi_lokasi_manual(worksheet, debug_data)
else:
    lokasi_map = {}
    st.error("❌ Tidak bisa membaca struktur sheet")

# Jika tidak ditemukan, gunakan mapping default yang berbeda
if not lokasi_map:
    st.warning("⚠️ Lokasi tidak terdeteksi, menggunakan mapping alternatif")
    lokasi_map = {
        "Power Plant": {"pH": 2, "suhu": 3, "debit": 4},
        "Plan Garage": {"pH": 5, "suhu": 6, "debit": 7},
        "Drain A": {"pH": 8, "suhu": 9, "debit": 10},
    }

# Tampilkan mapping
st.sidebar.subheader("🗺️ Mapping Lokasi")
for lokasi, map_info in lokasi_map.items():
    st.sidebar.write(f"**{lokasi}**")
    st.sidebar.write(f"  - pH: baris {map_info['pH']}")
    st.sidebar.write(f"  - suhu: baris {map_info['suhu']}")
    st.sidebar.write(f"  - debit: baris {map_info['debit']}")

# Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
available_lokasi = list(lokasi_map.keys())
if not available_lokasi:
    available_lokasi = LOKASI_OPTIONS

selected_lokasi = st.sidebar.selectbox(
    "Pilih Lokasi:",
    options=available_lokasi,
    index=0 if available_lokasi else None
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
        input_debit = st.number_input("Debit (l/d)", min_value=0.0, value=10.0, step=0.1, format="%.1f")
    
    submitted = st.form_submit_button("💾 Simpan Data ke Google Sheets", type="primary")

    if submitted:
        with st.spinner("Menyimpan data..."):
            success = simpan_data_dengan_debug(selected_lokasi, input_day, input_ph, input_suhu, input_debit, lokasi_map)
            if success:
                time.sleep(2)
                st.rerun()

st.caption("Aplikasi Monitoring Air")
