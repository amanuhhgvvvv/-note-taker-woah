import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter
import datetime
import time 

try:
    # 1. Gunakan koneksi Streamlit standar (mengandalkan secrets.toml yang sudah benar)
    conn = st.connection("gsheets") 

    #
    # Karena secrets.toml sudah diperbaiki, ini seharusnya berfungsi.
    SHEET_ID = st.secrets["gsheets"]["spreadsheet_id"]
    
except Exception as e:
    # Tampilkan error jika gagal koneksi. Sekarang error ini akan lebih akurat.
    st.error("Gagal koneksi! Pastikan file `.streamlit/secrets.toml` Anda sudah memiliki kunci 'type = \"gsheets\"' dan kunci Service Account lainnya. (Detail: " + str(e) + ")")
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
# Kolom pH, Suhu, dan Debit untuk LOGIKA INTERNAL PYTHON
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
    Membaaca semua sheet dari Google Sheets dengan format PIVOT dan mengkonversinya 
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
            # Baca data mentah, header baris 2 (Hari), kolom A (Parameter)
            df_pivot = conn.read(
                spreadsheet=SHEET_ID, 
                worksheet=sheet_name, 
                range=GSHEET_RANGE, 
                header=1,
                ttl=0
            )

            # 1. CLEANING & CONVERSION
            df_pivot.rename(columns={df_pivot.columns[0]: 'Parameter'}, inplace=True)
            df_pivot.set_index('Parameter', inplace=True)
            
            # 2. PENGAMBILAN RATA-RATA 
            avg_col_name = df_pivot.columns[-1] 
            
            # Ambil data rata-rata bulanan. Perlu pengecekan nama indeks yang eksak
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
    Fungsi ini HANYA menulis nilai harian (pH, suhu, debit) dan nilai rata-rata.
    """
    # Hapus cache agar data terbaru dibaca setelah penulisan
    read_all_sheets_gsheets.clear()
    
    # 1. Filter Data Harian
    # Pisahkan data harian dari baris rata-rata
    df_data_only = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    # 2. Persiapan Nilai
    
    # Ambil baris rata-rata
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
    
    # 3. Menulis Data Harian (Kolom B sampai AF, Baris 3, 4, 5)
    
    # Kolom B adalah index 2
    start_col_index = 2 
    
    # Cek jumlah hari yang diinput (maksimal 31)
    num_days = len(df_data_only)
    
    with st.spinner(f"Menyimpan data ke sheet '{lokasi}'..."):
        try:
            # Tulis data harian (pH, Suhu, Debit)
            for param, row_index in GSHEET_ROW_MAP.items():
                
                # Menghitung kolom akhir (Misal: B + 31 hari = AF)
                end_col_index = start_col_index + num_days - 1 
                
                # Menggunakan chr(ord('A') + index - 1) untuk mendapatkan huruf kolom (A1 notation)
                start_col_letter = chr(ord('A') + start_col_index - 1) 
                end_col_letter = chr(ord('A') + end_col_index - 1) 
                
                # Rentang tulis untuk data harian (Misal: B3:AF3)
                range_to_write_harian = f"{start_col_letter}{row_index}:{end_col_letter}{row_index}"
                
                # Tulis data. Data harus berbentuk list of lists (1xN)
                data_list = [data_to_write[param]]
                
                conn.write(
                    spreadsheet=SHEET_ID,
                    worksheet=lokasi,
                    data=data_list,
                    range=range_to_write_harian,
                )

            # 4. Menulis Data Rata-rata (Hanya Kolom AG, Baris 3, 4, 5)
            # Kolom Rata-rata adalah AG (Kolom ke-33)
            avg_col_letter = chr(ord('A') + GSHEET_AVG_COL_INDEX - 1) # AG
            
            for param, row_index in GSHEET_ROW_MAP.items():
                
                # Ambil nilai rata-rata yang sesuai
                avg_value = data_avg.get(param)
                
                # Rentang tulis untuk rata-rata (Misal: AG3:AG3 untuk pH)
                range_to_write_avg = f"{avg_col_letter}{row_index}:{avg_col_letter}{row_index}"
                
                # Tulis data rata-rata. Data harus berbentuk list of lists (1x1)
                data_list_avg = [[avg_value]]
                
                conn.write(
                    spreadsheet=SHEET_ID,
                    worksheet=lokasi,
                    data=data_list_avg,
                    range=range_to_write_avg,
                )
            
            st.success(f"✅ Data berhasil disimpan dan diupdate di Google Sheet: **{lokasi}**!")
            time.sleep(1) # Beri jeda agar pesan sukses terlihat
            st.rerun() # Muat ulang aplikasi untuk menampilkan data terbaru

        except Exception as e:
            st.error(f"❌ Gagal menyimpan data ke Google Sheets! Pastikan Anda memiliki izin Tulis (Write Access) dan format sheet tidak berubah. Error: {e}")
            print(f"Error detail: {e}") 
            
# ----------------------------
# BAGIAN UTAMA APLIKASI STREAMLIT (ANTARMUKA PENGGUNA)
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
    
    # Set default ke hari ini
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
        # Pengecekan Input
        if input_ph is None or input_suhu is None or input_debit is None:
            st.error("Mohon isi semua kolom (pH, Suhu, dan Debit) sebelum menyimpan.")
        else:
            # 1. Siapkan Tanggal Target (Format YYYY-MM-DD)
            target_date_str = f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            
            # 2. Buat Row Baru
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
            
            # 3. Gabungkan/Replace Data
            # Pisahkan data harian dari baris rata-rata
            avg_row_df = current_df[current_df["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
            data_harian_lama = current_df[~current_df["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
            
            # Hapus baris lama yang sesuai dengan hari yang di-input
            # Menggunakan .str.endswith untuk filter hari yang lebih akurat
            data_harian_tanpa_hari_ini = data_harian_lama[
                data_harian_lama['tanggal'].str.endswith(f'-{input_day:02d}', na=False) == False
            ]
            
            # Gabungkan data lama yang sudah bersih dengan data baru
            updated_harian = pd.concat([
                data_harian_tanpa_hari_ini,
                new_row_df
            ]).sort_values(by='tanggal').reset_index(drop=True)

            # Gabungkan kembali dengan baris rata-rata
            final_df_to_save = pd.concat([updated_harian, avg_row_df]).reset_index(drop=True)
            
            # Pastikan semua kolom yang diperlukan ada
            final_df_to_save = final_df_to_save.reindex(columns=INTERNAL_COLUMNS)

            # 4. Simpan ke Google Sheets
            save_sheet_to_gsheets(selected_sheet, final_df_to_save)


# 4. Tampilkan Data (Hanya untuk Tampilan)
st.markdown("---")
st.subheader("Tinjauan Data Saat Ini (Dari Google Sheets)")

# Buat copy dataframe untuk tampilan
display_df = current_df.copy()

# Ganti nilai 'None' atau 'NaN' dengan string kosong untuk tampilan yang lebih bersih
display_df.replace({np.nan: '', None: ''}, inplace=True)

# Ubah kolom tanggal menjadi 'Hari' (hanya menampilkan angka hari)
display_df['tanggal'] = display_df['tanggal'].apply(lambda x: str(x).split('-')[-1] if isinstance(x, str) and x.count('-') == 2 else x)

# Ubah nama kolom untuk tampilan
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





