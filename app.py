import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter
import datetime
import time 
import gspread
from google.oauth2.service_account import Credentials

# ========== PERBAIKAN KONEKSI ==========
@st.cache_resource
def init_gsheets_connection():
    try:
        # Ambil credentials dari secrets
        creds_dict = {
            "type": "service_account",
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"], 
            "private_key": st.secrets["private_key"],
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
            except gspread.exceptions.WorksheetNotFound:
                # Jika worksheet tidak ada, buat dataframe kosong
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                continue
            
            # Baca data dengan approach yang lebih sederhana
            try:
                # Baca hanya data yang diperlukan (baris 3-5 untuk data, kolom B-AF untuk hari)
                data_range = "B3:AG5"  # pH, suhu, debit untuk 31 hari + rata-rata
                data = worksheet.get(data_range)
                
                if not data:
                    # Jika tidak ada data, buat dataframe kosong
                    df_empty = pd.DataFrame(columns=INTERNAL_COLUMNS)
                    all_dfs_raw[sheet_name] = df_empty
                    continue
                
                # Buat DataFrame dari data yang dibaca
                # Data format: [pH_data, suhu_data, debit_data]
                days_in_month = 31  # Default 31 hari
                
                # Pastikan data memiliki panjang yang cukup
                pH_data = data[0] if len(data) > 0 else [''] * days_in_month
                suhu_data = data[1] if len(data) > 1 else [''] * days_in_month  
                debit_data = data[2] if len(data) > 2 else [''] * days_in_month
                
                # Ambil rata-rata (kolom terakhir)
                pH_avg = pH_data[-1] if len(pH_data) > 30 else None
                suhu_avg = suhu_data[-1] if len(suhu_data) > 30 else None
                debit_avg = debit_data[-1] if len(debit_data) > 30 else None
                
                # Data harian (kolom 1-31)
                pH_harian = pH_data[:31]
                suhu_harian = suhu_data[:31]
                debit_harian = debit_data[:31]
                
                # Buat DataFrame
                df_raw = pd.DataFrame({
                    'tanggal': [f"{current_year}-{current_month:02d}-{day:02d}" for day in range(1, 32)],
                    'pH': [float(x) if x != '' and x != '#DIV/0!' else None for x in pH_harian],
                    'suhu': [float(x) if x != '' and x != '#DIV/0!' else None for x in suhu_harian],
                    'debit': [float(x) if x != '' and x != '#DIV/0!' else None for x in debit_harian],
                })
                
                # Hitung rata-rata dari data yang valid
                ph_valid = [x for x in df_raw['pH'] if x is not None]
                suhu_valid = [x for x in df_raw['suhu'] if x is not None]
                debit_valid = [x for x in df_raw['debit'] if x is not None]
                
                ph_rata = round(sum(ph_valid) / len(ph_valid), 2) if ph_valid else None
                suhu_rata = round(sum(suhu_valid) / len(suhu_valid), 1) if suhu_valid else None
                debit_rata = round(sum(debit_valid) / len(debit_valid), 2) if debit_valid else None
                
                # Tambahkan baris rata-rata
                avg_row = pd.DataFrame({
                    'tanggal': [f"Rata-rata {current_month:02d}/{current_year}"],
                    'pH': [None],
                    'suhu': [None], 
                    'debit': [None],
                    'ph_rata_rata_bulan': [ph_rata],
                    'suhu_rata_rata_bulan': [suhu_rata],
                    'debit_rata_rata_bulan': [debit_rata]
                })
                
                df_final = pd.concat([df_raw, avg_row], ignore_index=True)
                all_dfs_raw[sheet_name] = df_final
                
            except Exception as processing_error:
                st.warning(f"⚠️ Error processing {sheet_name}: {processing_error}")
                # Buat dataframe kosong jika error
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
        except Exception as e:
            st.warning(f"⚠️ Error reading {sheet_name}: {e}")
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data ke Google Sheets - VERSI SIMPLIFIED
    """
    try:
        # Clear cache
        read_all_sheets_gsheets.clear()
        
        # 1. Filter Data Harian (tanpa baris rata-rata)
        df_harian = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
        
        # 2. Hitung rata-rata dari data harian
        ph_valid = [x for x in df_harian['pH'] if x is not None and not pd.isna(x)]
        suhu_valid = [x for x in df_harian['suhu'] if x is not None and not pd.isna(x)]
        debit_valid = [x for x in df_harian['debit'] if x is not None and not pd.isna(x)]
        
        ph_rata = round(sum(ph_valid) / len(ph_valid), 2) if ph_valid else ''
        suhu_rata = round(sum(suhu_valid) / len(suhu_valid), 1) if suhu_valid else ''
        debit_rata = round(sum(debit_valid) / len(debit_valid), 2) if debit_valid else ''
        
        # 3. Siapkan data untuk ditulis
        data_harian = {
            'pH': [x if x is not None and not pd.isna(x) else '' for x in df_harian['pH']],
            'suhu': [x if x is not None and not pd.isna(x) else '' for x in df_harian['suhu']],
            'debit': [x if x is not None and not pd.isna(x) else '' for x in df_harian['debit']]
        }
        
        with st.spinner(f"Menyimpan data ke {lokasi}..."):
            try:
                # Buka spreadsheet
                spreadsheet = client.open_by_key(SHEET_ID)
                
                # Cek atau buat worksheet
                try:
                    worksheet = spreadsheet.worksheet(lokasi)
                except gspread.exceptions.WorksheetNotFound:
                    st.info(f"📝 Membuat worksheet baru: {lokasi}")
                    worksheet = spreadsheet.add_worksheet(title=lokasi, rows="50", cols="35")
                
                # Tulis data harian (kolom B sampai AF)
                # Baris 3: pH, Baris 4: Suhu, Baris 5: Debit
                
                # Tulis pH (baris 3)
                if data_harian['pH']:
                    range_ph = f"B3:AF3"
                    worksheet.update(range_ph, [data_harian['pH'][:31]])  # Max 31 hari
                
                # Tulis Suhu (baris 4)  
                if data_harian['suhu']:
                    range_suhu = f"B4:AF4"
                    worksheet.update(range_suhu, [data_harian['suhu'][:31]])
                
                # Tulis Debit (baris 5)
                if data_harian['debit']:
                    range_debit = f"B5:AF5"
                    worksheet.update(range_debit, [data_harian['debit'][:31]])
                
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
                st.info("💡 Pastikan Google Sheets sudah di-share ke service account dan tidak sedang dibuka oleh user lain.")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

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

# Tampilkan Status
st.subheader(f"📊 Data untuk: {selected_sheet}")

# 3. Input Data Baru
st.markdown("---")
st.header("📝 Input Data Baru")

today_date = datetime.date.today()
today_day = today_date.day

with st.form("input_form"):
    
    # Pilih Hari
    day_options = list(range(1, 32))
    default_day_index = day_options.index(today_day) if today_day in day_options else 0
    
    input_day = st.selectbox(
        "Pilih Hari:",
        options=day_options,
        index=default_day_index
    )
    
    st.write(f"**Tanggal:** {today_date.year}-{today_date.month:02d}-{input_day:02d}")

    # Cek data existing
    default_ph = None
    default_suhu = None  
    default_debit = None
    
    if not current_df.empty:
        try:
            existing_data = current_df[
                current_df['tanggal'] == f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            ]
            if not existing_data.empty:
                default_ph = existing_data['pH'].iloc[0]
                default_suhu = existing_data['suhu'].iloc[0]
                default_debit = existing_data['debit'].iloc[0]
        except:
            pass

    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input(
            "pH", 
            min_value=0.0, max_value=14.0, 
            value=default_ph, format="%.2f", step=0.01,
            placeholder="7.00"
        )
    with col2:
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0,
            value=default_suhu, format="%.1f", step=0.1,
            placeholder="25.0"
        )
    with col3:
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0,
            value=default_debit, format="%.2f", step=0.01, 
            placeholder="10.00"
        )
        
    submitted = st.form_submit_button("💾 Simpan Data", type="primary")

    if submitted:
        if input_ph is None or input_suhu is None or input_debit is None:
            st.error("❌ Harap isi semua field!")
        else:
            # Buat data baru
            new_data = {
                'tanggal': f"{today_date.year}-{today_date.month:02d}-{input_day:02d}",
                'pH': input_ph,
                'suhu': input_suhu,
                'debit': input_debit
            }
            
            # Update DataFrame
            if not current_df.empty:
                # Hapus data existing untuk hari yang sama
                current_df_clean = current_df[
                    current_df['tanggal'] != f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
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
st.subheader("📋 Data Saat Ini")

if not current_df.empty:
    display_df = current_df.copy()
    
    # Format untuk display
    display_df['Hari'] = display_df['tanggal'].apply(
        lambda x: x.split('-')[-1] if isinstance(x, str) and '-' in x else x
    )
    
    display_df = display_df[['Hari', 'pH', 'suhu', 'debit']]
    display_df = display_df.replace({np.nan: '', None: ''})
    
    st.dataframe(
        display_df,
        use_container_width=True,
        height=400
    )
else:
    st.info("📝 Belum ada data untuk lokasi ini.")

st.caption("💡 Data akan otomatis tersimpan ke Google Sheets")
