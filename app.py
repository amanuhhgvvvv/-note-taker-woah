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
st.title("📊 Monitoring Air - Rata-rata")

# ----------------------------
# FUNGSI DEBUG - UNTUK MELIHAT STRUKTUR SHEET
# ----------------------------
def debug_sheet_structure():
    """Debug fungsi untuk melihat struktur sheet sebenarnya"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        all_data = worksheet.get_all_values()
        
        st.sidebar.subheader("🔍 Debug Sheet Structure")
        st.sidebar.write(f"Total baris: {len(all_data)}")
        
        # Tampilkan 20 baris pertama untuk analisis
        st.sidebar.write("**20 Baris Pertama:**")
        for i, row in enumerate(all_data[:20]):
            # Tampilkan hanya 10 kolom pertama agar tidak terlalu panjang
            st.sidebar.write(f"Baris {i+1}: {row[:10]}")
        
        return all_data
    except Exception as e:
        st.sidebar.error(f"Debug error: {e}")
        return None

# ----------------------------
# FUNGSI UTAMA - FLEKSIBEL
# ----------------------------
def cari_struktur_lokasi_otomatis(debug_data):
    """Mencari struktur lokasi secara otomatis dari data debug"""
    if debug_data is None:
        return {}
    
    lokasi_map = {}
    current_lokasi = None
    
    for i, row in enumerate(debug_data):
        baris_teks = ' '.join(str(cell) for cell in row[:5] if cell)  # Gabungkan 5 kolom pertama
        
        # Cari nama lokasi dalam baris
        for lokasi in LOKASI_OPTIONS:
            if lokasi.lower() in baris_teks.lower():
                current_lokasi = lokasi
                st.sidebar.info(f"📍 Ditemukan '{lokasi}' di baris {i+1}")
                # Asumsikan 3 baris berikutnya adalah pH, suhu, debit
                lokasi_map[lokasi] = {
                    "pH": i + 2,  # Baris setelah nama lokasi
                    "suhu": i + 3,
                    "debit": i + 4
                }
                break
    
    return lokasi_map

def baca_data_dari_sheet(lokasi_map):
    """Membaca data dari sheet berdasarkan mapping"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        all_data = worksheet.get_all_values()
        
        data_dict = {}
        
        for lokasi, row_map in lokasi_map.items():
            try:
                pH_data = []
                suhu_data = []
                debit_data = []
                
                # Baca data untuk 31 hari (kolom B sampai AF)
                for hari in range(31):
                    col_index = hari + 1  # Kolom B=1, C=2, ..., AF=31
                    
                    # Baca pH
                    pH_val = None
                    if (row_map["pH"] - 1 < len(all_data) and 
                        col_index < len(all_data[row_map["pH"] - 1])):
                        cell_val = all_data[row_map["pH"] - 1][col_index]
                        if cell_val and str(cell_val).strip() and str(cell_val).replace('.', '').isdigit():
                            try:
                                pH_val = float(cell_val)
                            except:
                                pH_val = None
                    pH_data.append(pH_val)
                    
                    # Baca suhu
                    suhu_val = None
                    if (row_map["suhu"] - 1 < len(all_data) and 
                        col_index < len(all_data[row_map["suhu"] - 1])):
                        cell_val = all_data[row_map["suhu"] - 1][col_index]
                        if cell_val and str(cell_val).strip() and str(cell_val).replace('.', '').isdigit():
                            try:
                                suhu_val = float(cell_val)
                            except:
                                suhu_val = None
                    suhu_data.append(suhu_val)
                    
                    # Baca debit
                    debit_val = None
                    if (row_map["debit"] - 1 < len(all_data) and 
                        col_index < len(all_data[row_map["debit"] - 1])):
                        cell_val = all_data[row_map["debit"] - 1][col_index]
                        if cell_val and str(cell_val).strip() and str(cell_val).replace('.', '').isdigit():
                            try:
                                debit_val = float(cell_val)
                            except:
                                debit_val = None
                    debit_data.append(debit_val)
                
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
        
        return data_dict
        
    except Exception as e:
        st.error(f"❌ Gagal membaca data dari sheet: {e}")
        return {}

def simpan_data_ke_sheet(lokasi, hari, pH, suhu, debit, lokasi_map):
    """Menyimpan data ke sheet"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)
        
        row_map = lokasi_map.get(lokasi)
        if not row_map:
            st.error(f"❌ Lokasi {lokasi} tidak ditemukan dalam mapping")
            return False
        
        # Kolom untuk hari tertentu (B=hari1, C=hari2, ..., AF=hari31)
        col_index = hari + 1  # +1 karena kolom A=1, B=2
        
        # Update data
        worksheet.update_cell(row_map["pH"], col_index, pH)
        worksheet.update_cell(row_map["suhu"], col_index, suhu)
        worksheet.update_cell(row_map["debit"], col_index, debit)
        
        st.success(f"✅ Data berhasil disimpan!")
        return True
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan data: {e}")
        return False

# ==================== BAGIAN UTAMA APLIKASI ====================

# 1. DEBUG STRUCTURE
debug_data = debug_sheet_structure()

# 2. CARI STRUKTUR OTOMATIS
lokasi_map = cari_struktur_lokasi_otomatis(debug_data)

# Jika tidak ditemukan otomatis, gunakan mapping default
if not lokasi_map:
    st.warning("⚠️ Struktur tidak terdeteksi otomatis, menggunakan mapping default")
    lokasi_map = {
        "Power Plant": {"pH": 3, "suhu": 4, "debit": 5},
        "Plan Garage": {"pH": 7, "suhu": 8, "debit": 9},
        "Drain A": {"pH": 11, "suhu": 12, "debit": 13},
    }

# Tampilkan mapping yang digunakan
st.sidebar.subheader("🗺️ Mapping yang Digunakan")
for lokasi, mapping in lokasi_map.items():
    st.sidebar.write(f"{lokasi}: pH={mapping['pH']}, suhu={mapping['suhu']}, debit={mapping['debit']}")

# 3. SIDEBAR: Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
available_lokasi = [lok for lok in LOKASI_OPTIONS if lok in lokasi_map]
if not available_lokasi:
    available_lokasi = LOKASI_OPTIONS

selected_lokasi = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=available_lokasi,
    index=0 
)

# 4. MUAT DATA
with st.spinner("Memuat data dari Google Sheets..."):
    all_data = baca_data_dari_sheet(lokasi_map)
current_df = all_data.get(selected_lokasi, pd.DataFrame())

# Tampilkan Status Lokasi
st.subheader(f"📍 Lokasi: {selected_lokasi}")

# 5. INPUT DATA BARU
st.markdown("---")
st.header("📝 Catat Data Baru")

today_date = datetime.date.today()
today_day = today_date.day

with st.form("input_form"):
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=list(range(1, 32)),
        index=today_day - 1
    )
    
    st.write(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input("Nilai pH", min_value=0.0, max_value=14.0, value=7.0, step=0.1, format="%.1f")
    with col2:
        input_suhu = st.number_input("Suhu (°C)", min_value=0.0, max_value=100.0, value=25.0, step=0.1, format="%.1f")
    with col3:
        input_debit = st.number_input("Debit (l/d)", min_value=0.0, value=0.0, step=0.1, format="%.1f")
        
    submitted = st.form_submit_button("💾 Simpan Data ke Google Sheets", type="primary")

    if submitted:
        with st.spinner("Menyimpan data..."):
            success = simpan_data_ke_sheet(selected_lokasi, input_day, input_ph, input_suhu, input_debit, lokasi_map)
            if success:
                time.sleep(2)
                st.rerun()

# 6. TAMPILKAN DATA
st.markdown("---")
st.subheader("📋 Data Saat Ini")

if not current_df.empty:
    display_df = current_df.copy()
    display_df['Hari'] = display_df['tanggal'].str.split('-').str[-1]
    display_df = display_df[['Hari', 'pH', 'suhu', 'debit']].replace({np.nan: ''})
    st.dataframe(display_df, hide_index=True, use_container_width=True, height=400)
else:
    st.info("Belum ada data untuk lokasi ini atau terjadi error loading data.")

st.caption("Aplikasi Monitoring Air")
