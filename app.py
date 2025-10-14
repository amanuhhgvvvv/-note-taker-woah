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
        # Ambil credentials dari secrets - FORMAT BARU
        creds_dict = {
            "type": "service_account",
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"], 
            "private_key": st.secrets["private_key"].replace("\\n", "\n"),
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
    SHEET_ID = st.secrets["SHEET_ID"]  # Pastikan ada di secrets
    
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

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air (Data Permanen via Google Sheets)")

# ----------------------------
# Utility: baca & simpan sheet 
# ----------------------------
@st.cache_data(ttl=5)
def read_all_sheets_gsheets():
    """
    Membaca semua sheet dari Google Sheets dengan format PIVOT dan mengkonversinya 
    ke format RAW DATA (tanggal, pH, suhu, debit) untuk diproses.
    """
    all_dfs_raw = {}
    today = datetime.date.today()
    current_month = today.month
    current_year = today.year
    
    # Ambil hari ini untuk menentukan rentang hari yang valid
    days_in_month = (datetime.date(current_year, current_month % 12 + 1, 1) - datetime.timedelta(days=1)).day if current_month < 12 else 31
    
    # Rentang A2 sampai kolom rata-rata (AG) dan baris 5.
    GSHEET_RANGE = "A2:AG5" 
    
    for sheet_name in SHEET_NAMES:
        try:
            # BUKA SPREADSHEET DENGAN GSPREAD
            spreadsheet = client.open_by_key(SHEET_ID)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            # Baca data mentah
            data = worksheet.get(GSHEET_RANGE)
            df_pivot = pd.DataFrame(data[1:], columns=data[0])  # Baris pertama sebagai header

            # 1. CLEANING & CONVERSION
            df_pivot.rename(columns={df_pivot.columns[0]: 'Parameter'}, inplace=True)
            df_pivot.set_index('Parameter', inplace=True)
            
            # 2. PENGAMBILAN RATA-RATA 
            avg_col_name = df_pivot.columns[-1] 
            
            # Ambil data rata-rata bulanan
            ph_avg = pd.to_numeric(df_pivot.loc['pH'].get(avg_col_name), errors='coerce')
            suhu_avg = pd.to_numeric(df_pivot.loc['suhu (°C)'].get(avg_col_name), errors='coerce') 
            debit_avg = pd.to_numeric(df_pivot.loc['Debit (l/d)'].get(avg_col_name), errors='coerce')

            # Hapus kolom rata-rata dari data harian untuk diproses
            df_pivot_harian = df_pivot.drop(columns=[avg_col_name])
            
            # 3. UN-PIVOT (Mengubah format pivot menjadi format raw data)
            df_raw_data = df_pivot_harian.T # Transpose: Hari menjadi index

            # Membuat DataFrame Raw Data Harian
            df_raw = pd.DataFrame()
            
            # Hanya mengambil index yang berupa angka (Hari 1-31)
            numeric_days = [
                int(day) for day in df_raw_data.index 
                if isinstance(day, (int, np.integer)) 
                or (isinstance(day, str) and day.isdigit())
            ]
            
            # Filter hanya hari yang valid untuk bulan ini
            valid_days = [day for day in numeric_days if day <= days_in_month]

            df_raw['tanggal'] = [f"{current_year}-{current_month:02d}-{day:02d}" for day in valid_days]
            
            # Pastikan hanya mengambil kolom yang relevan dari data pivot (pH, suhu (°C), Debit (l/d))
            df_raw['pH'] = pd.to_numeric(df_raw_data.loc[valid_days, 'pH'], errors='coerce').values
            df_raw['suhu'] = pd.to_numeric(df_raw_data.loc[valid_days, 'suhu (°C)'], errors='coerce').values
            df_raw['debit'] = pd.to_numeric(df_raw_data.loc[valid_days, 'Debit (l/d)'], errors='coerce').values
            
            # Tambahkan baris rata-rata bulanan di akhir
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
            st.warning(f"Gagal membaca sheet '{sheet_name}'. Pastikan format header Anda benar ('pH', 'suhu (°C)', 'Debit (l/d)') dan rentang data A2:AG5. Error: {e}")
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data RAW dari Python kembali ke format PIVOT di Google Sheets.
    """
    read_all_sheets_gsheets.clear()
    
    # 1. Filter Data Harian
    df_data_only = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    # 2. Persiapan Nilai
    rata_rata_row = df_raw_data[df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].iloc[0]
    
    # Data harian dalam format list
    data_to_write = {
        'pH': df_data_only['pH'].tolist(),
        'suhu': df_data_only['suhu'].tolist(),
        'debit': df_data_only['debit'].tolist(),
    }
    
    # Data Rata-rata Bulanan
    data_avg = {
        'pH': rata_rata_row['ph_rata_rata_bulan'],
        'suhu': rata_rata_row['suhu_rata_rata_bulan'],
        'debit': rata_rata_row['debit_rata_rata_bulan'],
    }
    
    # 3. Menulis Data ke Google Sheets dengan GSPREAD
    start_col_index = 2  # Kolom B adalah index 2
    num_days = len(df_data_only)
    
    with st.spinner(f"Menyimpan data ke sheet '{lokasi}'..."):
        try:
            # Buka worksheet
            spreadsheet = client.open_by_key(SHEET_ID)
            worksheet = spreadsheet.worksheet(lokasi)
            
            # Tulis data harian (pH, Suhu, Debit)
            for param, row_index in GSHEET_ROW_MAP.items():
                # Hitung range kolom
                end_col_index = start_col_index + num_days - 1 
                
                # Konversi index ke huruf kolom
                start_col_letter = chr(ord('A') + start_col_index - 1) 
                end_col_letter = chr(ord('A') + end_col_index - 1) 
                
                # Range untuk data harian
                range_to_write_harian = f"{start_col_letter}{row_index}:{end_col_letter}{row_index}"
                
                # Tulis data menggunakan gspread
                cell_list = worksheet.range(range_to_write_harian)
                for i, cell in enumerate(cell_list):
                    if i < len(data_to_write[param]):
                        cell.value = data_to_write[param][i]
                worksheet.update_cells(cell_list)

            # 4. Menulis Data Rata-rata
            avg_col_letter = chr(ord('A') + GSHEET_AVG_COL_INDEX - 1) # AG
            
            for param, row_index in GSHEET_ROW_MAP.items():
                avg_value = data_avg.get(param)
                range_to_write_avg = f"{avg_col_letter}{row_index}"
                
                # Tulis nilai rata-rata
                worksheet.update_acell(range_to_write_avg, avg_value)
            
            st.success(f"✅ Data berhasil disimpan dan diupdate di Google Sheet: **{lokasi}**!")
            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Gagal menyimpan data ke Google Sheets! Error: {e}")

# ----------------------------
# BAGIAN UTAMA APLIKASI STREAMLIT (SAMA PERSIS)
# ----------------------------

# 1. SIDEBAR: Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_sheet = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=SHEET_NAMES,
    index=0 
)

# 2. Muat Semua Data (dari Cache)
all_data = read_all_sheets_gsheets()
current_df = all_data.get(selected_sheet, pd.DataFrame(columns=INTERNAL_COLUMNS))

# Tampilkan Status Lokasi
st.subheader(f"Data Harian untuk Lokasi: **{selected_sheet}**")

# 3. Input Data Baru (Gunakan Form)
st.markdown("---")
st.header("📝 Catat Data Baru")

# Dapatkan hari ini untuk input default
today_date = datetime.date.today()
today_day = today_date.day

# Cek apakah data untuk hari ini sudah ada
is_day_recorded = today_day in pd.to_datetime(current_df['tanggal'], errors='coerce').dt.day.values

if is_day_recorded:
    st.info(f"Data untuk tanggal **{today_day}** sudah ada.")
    st.markdown("Anda bisa menggunakan bagian di bawah untuk **mengubah** data yang sudah ada.")
    
with st.form("input_form"):
    
    # Pilih Hari
    day_options = [day for day in range(1, 32)]
    default_day_index = day_options.index(today_day)
    
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=day_options,
        index=default_day_index,
        key='input_day'
    )
    
    st.write(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

    # Ambil nilai default jika hari yang dipilih sudah ada datanya
    existing_row = current_df[current_df['tanggal'].str.contains(f'-{input_day:02d}', na=False)]
    
    default_ph = existing_row['pH'].iloc[0] if not existing_row.empty and existing_row['pH'].iloc[0] else None
    default_suhu = existing_row['suhu'].iloc[0] if not existing_row.empty and existing_row['suhu'].iloc[0] else None
    default_debit = existing_row['debit'].iloc[0] if not existing_row.empty and existing_row['debit'].iloc[0] else None
    
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
            
            new_data_row = {
                'tanggal': target_date_str, 
                'pH': input_ph, 
                'suhu': input_suhu, 
                'debit': input_debit, 
                'ph_rata_rata_bulan': None,
                'suhu_rata_rata_bulan': None,
                'debit_rata_rata_bulan': None
            }
            new_row_df = pd.DataFrame([new_data_row], columns=INTERNAL_COLUMNS)
            
            # Gabungkan/Replace Data
            avg_row_df = current_df[current_df["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
            data_harian_lama = current_df[~current_df["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
            
            data_harian_tanpa_hari_ini = data_harian_lama[
                data_harian_lama['tanggal'].str.endswith(f'-{input_day:02d}', na=False) == False
            ]
            
            updated_harian = pd.concat([
                data_harian_tanpa_hari_ini,
                new_row_df
            ]).sort_values(by='tanggal').reset_index(drop=True)

            final_df_to_save = pd.concat([updated_harian, avg_row_df]).reset_index(drop=True)
            final_df_to_save = final_df_to_save.reindex(columns=INTERNAL_COLUMNS)

            # Simpan ke Google Sheets
            save_sheet_to_gsheets(selected_sheet, final_df_to_save)

# 4. Tampilkan Data
st.markdown("---")
st.subheader("Tinjauan Data Saat Ini (Dari Google Sheets)")

display_df = current_df.copy()
display_df.replace({np.nan: '', None: ''}, inplace=True)
display_df['tanggal'] = display_df['tanggal'].apply(lambda x: str(x).split('-')[-1] if isinstance(x, str) and x.count('-') == 2 else x)

display_df.rename(columns={
    'tanggal': 'Hari',
    'pH': 'pH',
    'suhu': 'Suhu (°C)',
    'debit': 'Debit (l/d)',
    'ph_rata_rata_bulan': 'Rata-rata pH',
    'suhu_rata_rata_bulan': 'Rata-rata Suhu',
    'debit_rata_rata_bulan': 'Rata-rata Debit'
}, inplace=True)

st.dataframe(
    display_df,
    hide_index=True,
    use_container_width=True,
    height=400,
)

st.caption("Catatan: Data di atas adalah hasil konversi dari format pivot Google Sheets Anda.")
