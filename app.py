import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter
import datetime
import time # Tambahkan untuk kebutuhan sleep/jeda

# ----------------------------
# KONFIGURASI GOOGLE SHEETS
# ----------------------------
# Dapatkan ID Spreadsheet dari secrets.toml
try:
    SHEET_ID = st.secrets["gsheets"]["spreadsheet_id"]
    
    # PERBAIKAN: Menggunakan st.connection() dengan type="spreadsheet"
    conn = st.connection("gsheets", type="spreadsheet") 
    
except KeyError:
    st.error("Gagal membaca 'spreadsheet_id' dari secrets.toml. Pastikan kunci [gsheets] dan [connections.gsheets] sudah dikonfigurasi di Streamlit Secrets.")
    st.stop()
except Exception as e:
    # Error ini sering muncul jika format secrets.toml salah, terutama private_key
    st.error(f"Gagal inisialisasi koneksi Google Sheets. Pastikan Service Account Key sudah benar di Streamlit Secrets. Error: {e}")
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
# Kolom rata-rata di Google Sheet Anda (Kolom AG - Kolom 33 jika A=1)
GSHEET_AVG_COL_INDEX = 33 

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air (Data Permanen via Google Sheets)")


# ----------------------------
# Utility: baca & simpan sheet 
# ----------------------------
@st.cache_data(ttl=5)
def read_all_sheets_gsheets():
    """
    Membaaca semua sheet dari Google Sheets dengan format PIVOT Anda 
    dan mengkonversinya ke format RAW DATA (tanggal, pH, suhu, debit) untuk diproses.
    """
    all_dfs_raw = {}
    
    for sheet_name in SHEET_NAMES:
        try:
            # Baca data mentah, termasuk header baris 2 (Hari) dan kolom A (Parameter)
            # Rentang A2:AG5 mencakup Hari ke-1 sampai 31 dan Kolom Rata-rata (dianggap AF atau AG)
            df_pivot = conn.read(
                spreadsheet=SHEET_ID, 
                worksheet=sheet_name, 
                range="A2:AG5", # DIUBAH ke AG5, karena AG adalah Kolom 33 (Rata-rata)
                header=1,       # Baris 2 (Hari) dijadikan header
                ttl=0
            )

            # 1. CLEANING & CONVERSION
            df_pivot.rename(columns={df_pivot.columns[0]: 'Parameter'}, inplace=True)
            df_pivot.set_index('Parameter', inplace=True)
            
            # 2. PENGAMBILAN RATA-RATA 
            # Kolom rata-rata adalah kolom terakhir (indeks -1)
            avg_col_name = df_pivot.columns[-1] 
            
            # Ambil data rata-rata bulanan
            # PENTING: Pastikan penamaan indeks sesuai di GSheet Anda ('pH', 'suhu (°C)', 'Debit (l/d)')
            ph_avg = pd.to_numeric(df_pivot.loc['pH'].get(avg_col_name), errors='coerce')
            suhu_avg = pd.to_numeric(df_pivot.loc['suhu (°C)'].get(avg_col_name), errors='coerce') 
            debit_avg = pd.to_numeric(df_pivot.loc['Debit (l/d)'].get(avg_col_name), errors='coerce')

            # Hapus kolom rata-rata dari data harian untuk diproses
            df_pivot_harian = df_pivot.drop(columns=[avg_col_name])
            
            # 3. UN-PIVOT (Mengubah format pivot Anda menjadi format raw data)
            df_raw_data = df_pivot_harian.T # Transpose: Hari menjadi index

            # UNTUK KEMUDAHAN, kita asumsikan ini untuk BULAN DAN TAHUN SAAT INI
            today = datetime.date.today()
            current_month = today.month
            current_year = today.year
            
            # Membuat DataFrame Raw Data Harian
            df_raw = pd.DataFrame()
            # Hanya mengambil index yang berupa angka (hari 1-31)
            numeric_days = [day for day in df_raw_data.index if isinstance(day, (int, np.integer)) or (isinstance(day, str) and day.isdigit())]

            df_raw['tanggal'] = [f"{current_year}-{current_month:02d}-{int(day):02d}" for day in numeric_days]
            df_raw['pH'] = pd.to_numeric(df_raw_data.loc[numeric_days, 'pH'], errors='coerce').values
            df_raw['suhu'] = pd.to_numeric(df_raw_data.loc[numeric_days, 'suhu (°C)'], errors='coerce').values
            df_raw['debit'] = pd.to_numeric(df_raw_data.loc[numeric_days, 'Debit (l/d)'], errors='coerce').values
            
            # Tambahkan baris rata-rata bulanan
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
            st.warning(f"Gagal membaca sheet '{sheet_name}'. Pastikan format header Anda benar, nama parameter di kolom A adalah 'pH', 'suhu (°C)', dan 'Debit (l/d)', serta rentang data A2:AG5. Error: {e}")
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data RAW dari Python kembali ke format PIVOT di Google Sheets.
    Fungsi ini HANYA menulis nilai harian (pH, suhu, debit) dan nilai rata-rata.
    """
    # Hapus cache agar data terbaru dibaca setelah penulisan
    read_all_sheets_gsheets.clear()
    
    # 1. Filter Data Harian dan Rata-rata
    df_data_only = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    # Periksa dan ambil data rata-rata
    rata_rata_row = df_raw_data[df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].iloc[0]
    
    # 2. Persiapan Data untuk Ditulis ke Google Sheets
    data_to_write = {
        'pH': df_data_only['pH'].tolist(),
        'suhu': df_data_only['suhu'].tolist(),
        'debit': df_data_only['debit'].tolist(),
    }
    
    # Data Rata-rata Bulanan (Hanya untuk referensi internal, nilai ini tidak digunakan di sini)
    data_avg = {
        'pH': rata_rata_row['ph_rata_rata_bulan'],
        'suhu': rata_rata_row['suhu_rata_rata_bulan'],
        'debit': rata_rata_row['debit_rata_rata_bulan'],
    }
    
    # 3. Menulis Data Harian (Kolom B sampai AF, Baris 3, 4, 5)
    
    # Kolom untuk hari (Kolom B hingga AF adalah kolom 2-32, total 31 hari)
    # Data dimulai dari kolom B (index 2)
    start_col_index = 2 # Kolom B
    
    # Cek jumlah hari yang diinput (maksimal 31)
    num_days = len(df_data_only)
    
    with st.spinner(f"Menyimpan data ke sheet '{lokasi}'..."):
        try:
            # Tulis data harian (pH, Suhu, Debit)
            for param, row_index in GSHEET_ROW_MAP.items():
                
                # Tentukan rentang penulisan (misal: B3:AF3 untuk pH)
                # Google Sheets API menggunakan notasi A1 (A=1, B=2, dst)
                start_col_letter = chr(ord('A') + start_col_index - 1) 
                end_col_letter = chr(ord('A') + start_col_index - 1 + num_days -1) # Hanya menulis sebanyak hari yang ada
                
                # Rentang tulis untuk data harian
                range_to_write_harian = f"{start_col_letter}{row_index}:{end_col_letter}{row_index}"
                
                # Data harus berbentuk list of lists (1xN)
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
                
                # Tentukan nilai rata-rata yang sesuai
                if param == 'pH':
                    avg_value = rata_rata_row['ph_rata_rata_bulan']
                elif param == 'suhu':
                    avg_value = rata_rata_row['suhu_rata_rata_bulan']
                elif param == 'debit':
                    avg_value = rata_rata_row['debit_rata_rata_bulan']
                
                # Rentang tulis untuk rata-rata (misal: AG3:AG3 untuk pH)
                range_to_write_avg = f"{avg_col_letter}{row_index}:{avg_col_letter}{row_index}"
                
                # Data harus berbentuk list of lists (1x1)
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
            st.error(f"❌ Gagal menyimpan data ke Google Sheets! Pastikan Anda memiliki izin Tulis (Write Access). Error: {e}")
            print(f"Error detail: {e}") # Untuk debugging internal
            
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
is_day_recorded = any(pd.to_datetime(current_df['tanggal'], errors='coerce').dt.day == today_day)

if is_day_recorded:
    st.info(f"Data untuk tanggal **{today_day}** sudah ada.")
    st.markdown("Anda bisa menggunakan bagian di bawah untuk **mengubah** data yang sudah ada.")
    
with st.form("input_form"):
    
    # Pilih Hari
    # Filter hari yang sudah ada untuk memudahkan penggantian/update
    day_options = [day for day in range(1, 32)]
    
    # Set default ke hari ini jika data belum dicatat
    default_day_index = day_options.index(today_day)
    
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=day_options,
        index=default_day_index,
        key='input_day'
    )
    
    st.write(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input(
            "Nilai pH", 
            min_value=0.0, max_value=14.0, 
            format="%.2f", step=0.01,
            key='input_ph',
            value=None
        )
    with col2:
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0, 
            format="%.1f", step=0.1,
            key='input_suhu',
            value=None
        )
    with col3:
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0, 
            format="%.2f", step=0.01,
            key='input_debit',
            value=None
        )
        
    submitted = st.form_submit_button("Simpan Data ke Google Sheets", type="primary")

    if submitted:
        # Pengecekan Input
        if input_ph is None or input_suhu is None or input_debit is None:
            st.error("Mohon isi semua kolom (pH, Suhu, dan Debit) sebelum menyimpan.")
        else:
            # 1. Siapkan Tanggal Target
            target_date_str = f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            
            # 2. Buat Row Baru
            new_data_row = {
                'tanggal': target_date_str, 
                'pH': input_ph, 
                'suhu': input_suhu, 
                'debit': input_debit, 
                # Set rata-rata bulanan ke None saat update harian
                'ph_rata_rata_bulan': None,
                'suhu_rata_rata_bulan': None,
                'debit_rata_rata_bulan': None
            }
            new_row_df = pd.DataFrame([new_data_row], columns=INTERNAL_COLUMNS)
            
            # 3. Gabungkan/Replace Data
            # Logika Update/Tambah:
            # Temukan baris rata-rata, simpan
            avg_row_df = current_df[current_df["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
            # Hapus baris rata-rata dari data harian
            data_harian_lama = current_df[~current_df["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
            
            # Update atau tambahkan data baru ke data harian lama
            
            # Gantikan baris yang sesuai dengan hari yang di-input
            # Kita menggunakan string.contains untuk menghindari masalah tipe data
            date_filter = data_harian_lama['tanggal'].str.contains(f'-{input_day:02d}') == False
            
            updated_harian = pd.concat([
                data_harian_lama[date_filter],
                new_row_df
            ]).sort_values(by='tanggal').reset_index(drop=True)

            # Gabungkan kembali dengan baris rata-rata
            final_df_to_save = pd.concat([updated_harian, avg_row_df]).reset_index(drop=True)

            # 4. Simpan ke Google Sheets
            save_sheet_to_gsheets(selected_sheet, final_df_to_save)


# 4. Tampilkan Data (Hanya untuk Tampilan)
st.markdown("---")
st.subheader("Tinjauan Data Saat Ini (Dari Google Sheets)")

# Buat copy dataframe untuk tampilan
display_df = current_df.copy()
# Ganti nilai 'None' atau 'NaN' dengan string kosong untuk tampilan yang lebih bersih
display_df.fillna('', inplace=True)
display_df['tanggal'] = display_df['tanggal'].apply(lambda x: x.split('-')[-1] if x.count('-') == 2 else x)

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
