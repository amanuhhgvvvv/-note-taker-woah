import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime
from io import BytesIO

# --- KONFIGURASI DAN INISIALISASI ---

EXCEL_PATH = 'ph_debit_data_logbook.xlsx'
# Daftar Lokasi (disesuaikan dengan template Anda)
SHEET_NAMES = [
    "POWER PLANT", "COOLING TOWER", "WTP TARJUN", "PLANT / DOMESTIK",
    "GARAGE", "COAL YARD", "Drainase A", "Drainase B", "Drainase C",
    "Mining Clay lat", "Mining Limestone", "Mining Silica"
]
# Kolom untuk Penyimpanan Data (Format Panjang - Lebih mudah untuk data entry)
COLUMNS_LONG = ['tanggal', 'lokasi', 'pH', 'debit']

# --- FUNGSI UTILITY DATA ---

def initialize_excel(path, sheet_names, columns):
    """Memastikan file Excel dan sheet yang diperlukan sudah ada."""
    if not os.path.exists(path):
        writer = pd.ExcelWriter(path, engine='openpyxl')
        for sheet in sheet_names:
            df_init = pd.DataFrame(columns=columns)
            df_init.to_excel(writer, sheet_name=sheet, index=False)
        writer.close()

@st.cache_data
def load_data(path, sheet_name):
    """Memuat data dari sheet spesifik."""
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except FileNotFoundError:
        st.error(f"File {path} tidak ditemukan.")
        return pd.DataFrame(columns=COLUMNS_LONG)
    except ValueError:
        # Jika sheet_name tidak ada, kembalikan DataFrame kosong
        return pd.DataFrame(columns=COLUMNS_LONG)

def save_data(path, location, new_data):
    """Menyimpan data baru ke sheet yang sesuai."""
    # Baca semua sheet yang ada
    all_dfs = pd.read_excel(path, sheet_name=None)

    # Dapatkan DataFrame untuk lokasi yang dipilih
    if location in all_dfs:
        df = all_dfs[location]
        # Pastikan kolom sesuai dengan COLUMNS_LONG sebelum concate
        df = df[COLUMNS_LONG]
    else:
        # Buat DataFrame baru jika lokasi tidak ada (seharusnya tidak terjadi jika initialize_excel benar)
        df = pd.DataFrame(columns=COLUMNS_LONG)

    # Tambahkan data baru
    new_data_df = pd.DataFrame([new_data], columns=COLUMNS_LONG)
    df_updated = pd.concat([df, new_data_df], ignore_index=True)

    # Hapus duplikat (untuk mencegah entri ganda pada tanggal dan lokasi yang sama)
    df_updated.drop_duplicates(subset=['tanggal'], keep='last', inplace=True)
    df_updated['tanggal'] = pd.to_datetime(df_updated['tanggal']).dt.date
    
    # Simpan kembali semua sheet
    writer = pd.ExcelWriter(path, engine='xlsxwriter')
    for sheet_name in SHEET_NAMES:
        if sheet_name == location:
            df_updated.to_excel(writer, sheet_name=location, index=False)
        elif sheet_name in all_dfs:
            # Pastikan sheet yang lain juga disalin kembali
            all_dfs[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)
        else:
            # Buat sheet kosong jika belum ada
             pd.DataFrame(columns=COLUMNS_LONG).to_excel(writer, sheet_name=sheet_name, index=False)

    writer.close()
    st.cache_data.clear() # Bersihkan cache data agar data terbaru dimuat

# --- FUNGSI GENERATOR LOGBOOK (WIDE FORMAT) BARU ---

def generate_logbook_view(df_long, year, month):
    """
    Mengubah data format panjang ke format Logbook Bulanan (lebar) sesuai permintaan.
    """
    if df_long.empty:
        return pd.DataFrame()

    # Pastikan kolom tanggal adalah datetime
    df_long['tanggal'] = pd.to_datetime(df_long['tanggal'])

    # Filter data berdasarkan Bulan dan Tahun yang dipilih
    df_filtered = df_long[
        (df_long['tanggal'].dt.year == year) & 
        (df_long['tanggal'].dt.month == month)
    ].copy()
    
    if df_filtered.empty:
        return pd.DataFrame()

    # Ekstrak hari dari tanggal dan ubah menjadi float (sesuai template Anda)
    df_filtered['Day'] = df_filtered['tanggal'].dt.day.astype(float)

    # Hitung Rata-Rata Bulanan
    # pH Rata-Rata Bulanan
    ph_monthly_avg = df_filtered['pH'].mean()
    
    # Debit Rata-Rata Bulanan (Debit harian/m3/H di template Anda)
    debit_daily_avg = df_filtered['debit'].mean() 
    
    # Asumsi: Debit (m3/M) adalah Debit Rata-Rata (m3/H) * 24 jam * jumlah hari dalam bulan
    num_days_in_month = pd.Period(f'{year}-{month:02d}-01', 'D').days_in_month
    debit_monthly_m3 = debit_daily_avg * 24 * num_days_in_month

    # Pivot data ke format lebar
    df_ph = df_filtered.pivot(index='lokasi', columns='Day', values='pH').T
    df_debit = df_filtered.pivot(index='lokasi', columns='Day', values='debit').T

    # Gabungkan pH dan Debit kembali ke format baris
    # Buat DataFrame target Logbook
    days = list(np.arange(1.0, 32.0))
    header_cols = ['No', 'Parameter'] + days + ['Rata-Rata', 'Faktor Konversi', 'Debit (m3/H)', 'Debit (m3/M)']
    
    logbook_df = pd.DataFrame(columns=header_cols)
    
    # Isi data pH
    ph_data = {'No': 1.0, 'Parameter': 'pH'}
    for day in days:
        # Gunakan 'Day' yang sudah diubah ke float sebagai kolom
        ph_data[day] = df_ph.get(day, np.nan).values[0] if not df_ph.empty and day in df_ph.columns else np.nan
    ph_data['Rata-Rata'] = ph_monthly_avg
    logbook_df = pd.concat([logbook_df, pd.DataFrame([ph_data])], ignore_index=True)

    # Isi data Debit
    debit_data = {'No': 2.0, 'Parameter': 'Debit'}
    for day in days:
        debit_data[day] = df_debit.get(day, np.nan).values[0] if not df_debit.empty and day in df_debit.columns else np.nan
    
    # Asumsi Debit Rata-Rata (m3/H) dan Faktor Konversi hanya berlaku untuk Debit
    debit_data['Rata-Rata'] = debit_daily_avg
    debit_data['Faktor Konversi'] = 3.6 # Nilai asumsi dari template Anda
    debit_data['Debit (m3/H)'] = debit_daily_avg * 3.6
    debit_data['Debit (m3/M)'] = debit_monthly_m3 # Debit Bulanan (m3/M)
    
    logbook_df = pd.concat([logbook_df, pd.DataFrame([debit_data])], ignore_index=True)
    
    # Formatting (Optional: clean up index and NaNs)
    logbook_df = logbook_df.fillna('')
    
    return logbook_df


# --- TAMPILAN STREAMLIT ---

st.title("Aplikasi Pencatatan pH dan Debit Air")
st.markdown("---")

# 1. Inisialisasi File Excel
initialize_excel(EXCEL_PATH, SHEET_NAMES, COLUMNS_LONG)

# --- FORMULIR INPUT DATA BARU ---
st.header("1. Input Data Pengukuran Harian")
with st.form("input_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        input_date = st.date_input("Tanggal Pengukuran", datetime.now().date())
    
    with col2:
        lokasi_terpilih = st.selectbox("Lokasi Pengukuran", SHEET_NAMES)

    col3, col4 = st.columns(2)
    with col3:
        input_ph = st.number_input("Nilai pH", min_value=0.0, max_value=14.0, format="%.2f", step=0.01)

    with col4:
        # Asumsi debit dalam m3/H agar mudah dikonversi
        input_debit = st.number_input("Nilai Debit (m³/H)", min_value=0.0, format="%.3f", step=0.01)

    submitted = st.form_submit_button("Simpan Data")

    if submitted:
        new_data = {
            'tanggal': input_date, 
            'lokasi': lokasi_terpilih, 
            'pH': input_ph, 
            'debit': input_debit
        }
        try:
            save_data(EXCEL_PATH, lokasi_terpilih, new_data)
            st.success(f"Data pH: {input_ph} dan Debit: {input_debit} untuk lokasi **{lokasi_terpilih}** pada tanggal **{input_date}** berhasil disimpan.")
        except Exception as e:
            st.error(f"Gagal menyimpan data: {e}")

# --- TAMPILAN LOGBOOK DAN UNDUH DATA ---
st.markdown("---")
st.header("2. Pratinjau dan Unduh Logbook (Format Bulanan)")

# Kontrol pemilihan untuk tampilan Logbook
col_view_1, col_view_2, col_view_3 = st.columns(3)
with col_view_1:
    view_location = st.selectbox("Pilih Lokasi Logbook", SHEET_NAMES, key='view_location')

with col_view_2:
    current_year = datetime.now().year
    view_year = st.selectbox("Pilih Tahun", range(current_year - 2, current_year + 2), index=2, key='view_year')

with col_view_3:
    current_month = datetime.now().month
    view_month_name = st.selectbox("Pilih Bulan", 
        list(pd.to_datetime(np.arange(1, 13), format='%m').strftime('%B')), 
        index=current_month - 1, key='view_month')
    view_month = pd.to_datetime(view_month_name, format='%B').month

# Muat data yang tersimpan (format panjang)
df_saved_long = load_data(EXCEL_PATH, view_location)

# Konversi ke format Logbook (lebar)
logbook_df = generate_logbook_view(df_saved_long, view_year, view_month)

# Tampilkan Logbook
if logbook_df.empty:
    st.info(f"Tidak ada data untuk lokasi **{view_location}** pada bulan **{view_month_name} {view_year}**.")
else:
    st.subheader(f"Logbook pH dan Debit: {view_location} - {view_month_name} {view_year}")
    st.dataframe(logbook_df)

    # Tombol Download dalam format Excel yang benar
    st.markdown("### Unduh Logbook")
    
    # Membuat File Excel Logbook untuk Download (Semua Lokasi)
    def to_excel(df_long_all):
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        
        # Iterasi melalui semua lokasi untuk membuat sheet Logbook
        for location in SHEET_NAMES:
            df_loc = df_long_all[df_long_all['lokasi'] == location].copy()
            
            # Mendapatkan semua bulan dan tahun unik dari data ini
            df_loc['Year'] = df_loc['tanggal'].dt.year
            df_loc['Month'] = df_loc['tanggal'].dt.month
            unique_periods = df_loc[['Year', 'Month']].drop_duplicates().sort_values(['Year', 'Month'])
            
            # Buat sheet untuk Logbook, yang berisi logbook per bulan
            start_row = 0
            for index, row in unique_periods.iterrows():
                year = row['Year']
                month = row['Month']
                month_name = pd.to_datetime(month, format='%m').strftime('%B')
                
                # Filter data untuk bulan ini
                df_month = df_loc[(df_loc['Year'] == year) & (df_loc['Month'] == month)]
                
                # Buat Logbook format lebar
                df_log = generate_logbook_view(df_month, year, month)
                
                if not df_log.empty:
                    # Tulis judul dan periode
                    sheet_name_safe = location[:31] # Batas nama sheet
                    
                    # Tambahkan header Logbook di awal setiap periode
                    # Ini adalah trik untuk membuat tampilan logbook yang lebih mendekati format template Anda
                    header_df = pd.DataFrame([
                        ['Logbook pengambilan pH dan Debit Harian'],
                        [f'Lokasi {location}'],
                        [''],
                        [''],
                        [f'Periode : Bulan {month_name} {year}']
                    ])
                    header_df.to_excel(writer, sheet_name=sheet_name_safe, startrow=start_row, index=False, header=False)
                    
                    # Tulis DataFrame Logbook di bawah header
                    df_log.to_excel(writer, sheet_name=sheet_name_safe, startrow=start_row + 5, index=False)
                    
                    # Pindah baris awal untuk periode berikutnya
                    start_row += len(df_log) + 7
                    
        writer.close()
        return output.getvalue()

    # Muat semua data dari semua sheet untuk didownload
    all_data_for_download = pd.DataFrame(columns=COLUMNS_LONG)
    for sheet in SHEET_NAMES:
        df_sheet = load_data(EXCEL_PATH, sheet)
        df_sheet['lokasi'] = sheet
        all_data_for_download = pd.concat([all_data_for_download, df_sheet], ignore_index=True)
    
    st.download_button(
        label="Unduh Logbook Excel (Semua Lokasi & Bulan)",
        data=to_excel(all_data_for_download),
        file_name='Logbook_pH_Debit_Output.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

