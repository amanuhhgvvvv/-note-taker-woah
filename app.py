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
    Membaca semua sheet dari Google Sheets
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
                # Buat dataframe kosong jika sheet tidak ada
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                continue
            
            # Baca data dengan range yang aman
            try:
                data = worksheet.get("A1:AG10")
            except:
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                continue
            
            if not data or len(data) < 4:
                # Sheet ada tapi kosong
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
                continue
            
            # Proses data
            try:
                df_pivot = pd.DataFrame(data[1:], columns=data[0])
                
                # Handle nama kolom pertama
                first_col = df_pivot.columns[0]
                df_pivot.rename(columns={first_col: 'Parameter'}, inplace=True)
                df_pivot.set_index('Parameter', inplace=True)
                
                # Cari parameter yang ada
                available_params = [str(param).lower() for param in df_pivot.index]
                
                # Cari parameter pH
                ph_param = None
                if 'ph' in available_params:
                    ph_param = df_pivot.index[available_params.index('ph')]
                
                # Cari parameter suhu
                suhu_param = None
                for pattern in ['suhu (oc)', 'suhu (°c)', 'suhu']:
                    if any(pattern.lower() in param for param in available_params):
                        suhu_param = df_pivot.index[[pattern.lower() in param for param in available_params].index(True)]
                        break
                
                # Cari parameter debit
                debit_param = None
                for pattern in ['debit (l/d)', 'debit']:
                    if any(pattern.lower() in param for param in available_params):
                        debit_param = df_pivot.index[[pattern.lower() in param for param in available_params].index(True)]
                        break
                
                # Hapus kolom rata-rata untuk data harian
                df_pivot_harian = df_pivot.iloc[:, :-1] if len(df_pivot.columns) > 1 else df_pivot
                
                # UN-PIVOT data
                df_raw_data = df_pivot_harian.T
                
                # Buat DataFrame Raw Data Harian
                df_raw = pd.DataFrame()
                
                # Ambil hari yang valid (1-31)
                valid_days = [day for day in range(1, 32)]
                df_raw['tanggal'] = [f"{current_year}-{current_month:02d}-{day:02d}" for day in valid_days]
                
                # Fungsi untuk ambil data dengan handle error
                def safe_get_data(param, days):
                    if param and param in df_raw_data.columns:
                        values = []
                        for day in days:
                            try:
                                raw_value = df_raw_data.loc[day, param]
                                if raw_value in ['', '#DIV/0!', '#ERROR!', '#N/A', '#VALUE!', None]:
                                    values.append(None)
                                else:
                                    values.append(float(raw_value))
                            except:
                                values.append(None)
                        return values
                    else:
                        return [None] * len(days)
                
                # Ambil data harian
                df_raw['pH'] = safe_get_data(ph_param, valid_days)
                df_raw['suhu'] = safe_get_data(suhu_param, valid_days)
                df_raw['debit'] = safe_get_data(debit_param, valid_days)
                
                # HITUNG RATA-RATA DARI DATA HARIAN
                ph_data_valid = [x for x in df_raw['pH'] if x is not None and not pd.isna(x)]
                suhu_data_valid = [x for x in df_raw['suhu'] if x is not None and not pd.isna(x)]
                debit_data_valid = [x for x in df_raw['debit'] if x is not None and not pd.isna(x)]
                
                ph_rata_rata = sum(ph_data_valid) / len(ph_data_valid) if ph_data_valid else None
                suhu_rata_rata = sum(suhu_data_valid) / len(suhu_data_valid) if suhu_data_valid else None
                debit_rata_rata = sum(debit_data_valid) / len(debit_data_valid) if debit_data_valid else None
                
                # Format rata-rata
                if ph_rata_rata is not None:
                    ph_rata_rata = round(ph_rata_rata, 2)
                if suhu_rata_rata is not None:
                    suhu_rata_rata = round(suhu_rata_rata, 1)
                if debit_rata_rata is not None:
                    debit_rata_rata = round(debit_rata_rata, 2)
                
                # Tambahkan baris rata-rata dengan nilai yang dihitung
                avg_row = {
                    "tanggal": f"Rata-rata {current_month:02d}/{current_year}",
                    "pH": None, "suhu": None, "debit": None,
                    "ph_rata_rata_bulan": ph_rata_rata,
                    "suhu_rata_rata_bulan": suhu_rata_rata,
                    "debit_rata_rata_bulan": debit_rata_rata
                }
                df_raw = pd.concat([df_raw, pd.DataFrame([avg_row])], ignore_index=True)
                
                all_dfs_raw[sheet_name] = df_raw.reindex(columns=INTERNAL_COLUMNS)
                
            except Exception as processing_error:
                all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
        except Exception as e:
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data RAW dari Python kembali ke format PIVOT di Google Sheets.
    """
    read_all_sheets_gsheets.clear()
    
    try:
        # 1. Filter Data Harian
        df_data_only = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
        
        # 2. HITUNG RATA-RATA OTOMATIS dari data harian
        ph_data_valid = [x for x in df_data_only['pH'] if x is not None and not pd.isna(x)]
        suhu_data_valid = [x for x in df_data_only['suhu'] if x is not None and not pd.isna(x)]
        debit_data_valid = [x for x in df_data_only['debit'] if x is not None and not pd.isna(x)]
        
        ph_rata_rata = sum(ph_data_valid) / len(ph_data_valid) if ph_data_valid else None
        suhu_rata_rata = sum(suhu_data_valid) / len(suhu_data_valid) if suhu_data_valid else None
        debit_rata_rata = sum(debit_data_valid) / len(debit_data_valid) if debit_data_valid else None
        
        # Format rata-rata
        if ph_rata_rata is not None:
            ph_rata_rata = round(ph_rata_rata, 2)
        if suhu_rata_rata is not None:
            suhu_rata_rata = round(suhu_rata_rata, 1)
        if debit_rata_rata is not None:
            debit_rata_rata = round(debit_rata_rata, 2)
        
        # Data harian dalam format list
        data_to_write = {
            'pH': df_data_only['pH'].fillna('').tolist(),
            'suhu': df_data_only['suhu'].fillna('').tolist(),
            'debit': df_data_only['debit'].fillna('').tolist(),
        }
        
        # Data Rata-rata
        data_avg = {
            'pH': ph_rata_rata,
            'suhu': suhu_rata_rata,
            'debit': debit_rata_rata,
        }
        
        # 3. Menulis Data ke Google Sheets
        start_col_index = 2  # Kolom B adalah index 2
        num_days = len(df_data_only)
        
        with st.spinner(f"Menyimpan data ke sheet '{lokasi}'..."):
            try:
                # Buka spreadsheet
                spreadsheet = client.open_by_key(SHEET_ID)
                
                # Cek apakah worksheet ada, jika tidak buat baru
                try:
                    worksheet = spreadsheet.worksheet(lokasi)
                except gspread.exceptions.WorksheetNotFound:
                    worksheet = spreadsheet.add_worksheet(title=lokasi, rows="100", cols="50")
                
                # Tulis data harian (pH, Suhu, Debit)
                for param, row_index in GSHEET_ROW_MAP.items():
                    # Hitung range kolom
                    end_col_index = start_col_index + num_days - 1 
                    
                    # Konversi index ke huruf kolom
                    start_col_letter = chr(ord('A') + start_col_index - 1) 
                    end_col_letter = chr(ord('A') + end_col_index - 1) 
                    
                    # Range untuk data harian
                    range_to_write_harian = f"{start_col_letter}{row_index}:{end_col_letter}{row_index}"
                    
                    # Tulis data
                    values = data_to_write[param]
                    cell_range = worksheet.range(range_to_write_harian)
                    for i, cell in enumerate(cell_range):
                        if i < len(values):
                            cell.value = values[i] if pd.notna(values[i]) and values[i] != '' else ""
                    worksheet.update_cells(cell_range)

                # 4. Menulis Data Rata-rata
                avg_col_letter = chr(ord('A') + GSHEET_AVG_COL_INDEX - 1) # AG
                
                for param, row_index in GSHEET_ROW_MAP.items():
                    avg_value = data_avg.get(param)
                    if pd.notna(avg_value) and avg_value is not None:
                        range_to_write_avg = f"{avg_col_letter}{row_index}"
                        worksheet.update_acell(range_to_write_avg, avg_value)
                    else:
                        # Kosongkan sel jika tidak ada nilai
                        range_to_write_avg = f"{avg_col_letter}{row_index}"
                        worksheet.update_acell(range_to_write_avg, "")
                
                st.success(f"✅ Data berhasil disimpan dan diupdate di Google Sheet: **{lokasi}**!")
                time.sleep(1)
                st.rerun()

            except Exception as e:
                st.error(f"❌ Gagal menyimpan data ke Google Sheets! Error: {e}")
    
    except Exception as e:
        st.error(f"❌ Error dalam proses penyimpanan: {e}")

# ==================== BAGIAN UTAMA APLIKASI ====================

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
is_day_recorded = False
if not current_df.empty:
    try:
        dates = pd.to_datetime(current_df['tanggal'], errors='coerce')
        is_day_recorded = today_day in dates.dt.day.values
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
    existing_row = current_df[current_df['tanggal'].str.contains(f'-{input_day:02d}', na=False)]
    
    default_ph = existing_row['pH'].iloc[0] if not existing_row.empty and pd.notna(existing_row['pH'].iloc[0]) else None
    default_suhu = existing_row['suhu'].iloc[0] if not existing_row.empty and pd.notna(existing_row['suhu'].iloc[0]) else None
    default_debit = existing_row['debit'].iloc[0] if not existing_row.empty and pd.notna(existing_row['debit'].iloc[0]) else None
    
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
