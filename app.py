import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime
from io import BytesIO

# --- KONFIGURASI DAN INISIALISASI ---

# Nama file Excel yang akan digunakan untuk menyimpan data
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
        # Menggunakan openpyxl untuk inisialisasi file agar dapat diakses oleh Streamlit
        writer = pd.ExcelWriter(path, engine='openpyxl')
        for sheet in sheet_names:
            df_init = pd.DataFrame(columns=columns)
            df_init.to_excel(writer, sheet_name=sheet, index=False)
        writer.close()

@st.cache_data
def load_data(path, sheet_name):
    """Memuat data dari sheet spesifik."""
    try:
        # Menggunakan openpyxl karena default engine 'xlrd' tidak mendukung .xlsx
        df = pd.read_excel(path, sheet_name=sheet_name, engine='openpyxl')
        # Konversi kolom 'tanggal' ke datetime dan isi NaN dengan hari ini
        df['tanggal'] = pd.to_datetime(df['tanggal'], errors='coerce').fillna(datetime.now().date())
        # Konversi kolom numerik
        for col in ['pH', 'debit']:
             df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['tanggal', 'pH', 'debit']) # Hapus baris yang semua data pentingnya NaN
    except Exception as e:
        st.error(f"Gagal memuat data dari sheet {sheet_name}: {e}")
        return pd.DataFrame(columns=COLUMNS_LONG)

def save_data(df, path, sheet_name):
    """Menyimpan DataFrame kembali ke sheet spesifik."""
    try:
        # Muat semua sheet yang ada ke dalam memory
        all_sheets = pd.read_excel(path, sheet_name=None, engine='openpyxl')
        
        # Ganti sheet yang spesifik dengan data baru
        all_sheets[sheet_name] = df
        
        # Tulis semua kembali ke file
        writer = pd.ExcelWriter(path, engine='openpyxl')
        for sheet_name_i, df_i in all_sheets.items():
            df_i.to_excel(writer, sheet_name=sheet_name_i, index=False)
        writer.close()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan data: {e}")
        return False

@st.cache_data
def to_excel(df_all):
    """Mengonversi DataFrame menjadi format Excel dalam memori (BytesIO) dengan format logbook per bulan per lokasi."""
    output = BytesIO()
    
    # Pastikan 'tanggal' adalah tipe datetime sebelum grouping
    df_all['tanggal'] = pd.to_datetime(df_all['tanggal'])
    
    # Kelompokkan data berdasarkan 'lokasi' dan kemudian 'bulan'
    # 'M' adalah Month End frequency
    grouped = df_all.groupby(['lokasi', pd.Grouper(key='tanggal', freq='ME')])
    
    # KOREKSI PENTING: Tambahkan engine='xlsxwriter' untuk mengatasi error
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer: 
        
        # 1. Buat sheet untuk ringkasan/data mentah
        df_all.to_excel(writer, sheet_name='Data Mentah', index=False)
        
        # 2. Iterasi untuk membuat sheet logbook per bulan per lokasi
        for (location, month_period), df_log in grouped:
            
            # Dapatkan nama bulan dan tahun (diterjemahkan ke Bahasa Indonesia)
            month_name = month_period.strftime('%B %Y').replace('January', 'Januari').replace('February', 'Februari').replace('March', 'Maret').replace('April', 'April').replace('May', 'Mei').replace('June', 'Juni').replace('July', 'Juli').replace('August', 'Agustus').replace('September', 'September').replace('October', 'Oktober').replace('November', 'November').replace('December', 'Desember').replace(' ', ' ')
            year = month_period.year
            
            # Batasi kolom dan format tanggal untuk tampilan logbook
            df_log = df_log[['tanggal', 'pH', 'debit']]
            df_log['tanggal'] = df_log['tanggal'].dt.day
            df_log.rename(columns={'tanggal': 'Tanggal Pengukuran'}, inplace=True)
            
            # Amankan nama sheet (maksimal 31 karakter)
            sheet_name_safe = f"{location[:15]} - {month_period.strftime('%b %y')}"
            
            start_row = 0
            
            # Pisahkan logbook ke dalam per bulan agar mendekati format template Anda
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
            
        # writer.close() tidak diperlukan karena menggunakan 'with'
        return output.getvalue()


# --- INTERFACE STREAMLIT ---

# Pastikan file Excel sudah terinisialisasi
initialize_excel(EXCEL_PATH, SHEET_NAMES, COLUMNS_LONG)

st.title("Aplikasi Logbook pH & Debit Harian")
st.subheader("Input Data")

# --- Form Input ---

with st.form("input_form"):
    
    col1, col2 = st.columns(2)
    
    with col1:
        lokasi_input = st.selectbox("Pilih Lokasi", options=SHEET_NAMES, key="lokasi_input")
        tanggal_input = st.date_input("Tanggal Pengukuran", datetime.now().date(), key="tanggal_input")
    
    with col2:
        ph_input = st.number_input("Input pH", min_value=0.0, max_value=14.0, step=0.01, key="ph_input", format="%.2f")
        debit_input = st.number_input("Input Debit (l/S)", min_value=0.0, step=0.01, key="debit_input", format="%.2f")

    submitted = st.form_submit_button("Simpan Data")

    if submitted:
        # Muat data lama dari sheet yang dipilih
        df_old = load_data(EXCEL_PATH, lokasi_input)
        
        # Siapkan data baru
        new_data = pd.DataFrame([{
            'tanggal': pd.to_datetime(tanggal_input),
            'lokasi': lokasi_input,
            'pH': ph_input,
            'debit': debit_input
        }])
        
        # Gabungkan data lama dan baru
        df_new = pd.concat([df_old, new_data], ignore_index=True)
        
        # Hapus duplikat (jika ada data yang diinput dua kali untuk tanggal yang sama)
        df_new.drop_duplicates(subset=['tanggal', 'lokasi'], keep='last', inplace=True)
        
        # Simpan kembali data ke file Excel
        if save_data(df_new, EXCEL_PATH, lokasi_input):
            st.success(f"Data pH: {ph_input} dan Debit: {debit_input} berhasil disimpan untuk lokasi **{lokasi_input}** pada tanggal **{tanggal_input.strftime('%d %B %Y')}**!")
            st.cache_data.clear() # Hapus cache data setelah penyimpanan
        else:
            st.error("Gagal menyimpan data.")

# --- Tampilan Data & Download ---

st.divider()
st.subheader("Data Tersimpan")

# Pilih lokasi untuk melihat data
lokasi_view = st.selectbox("Lihat Data Lokasi:", options=SHEET_NAMES, key="lokasi_view")
df_current = load_data(EXCEL_PATH, lokasi_view)

if not df_current.empty:
    st.dataframe(df_current.sort_values(by='tanggal', ascending=False), use_container_width=True)
else:
    st.info(f"Belum ada data tersimpan untuk lokasi **{lokasi_view}**.")


# Muat semua data dari semua sheet untuk didownload
all_data_for_download = pd.DataFrame(columns=COLUMNS_LONG)
for sheet in SHEET_NAMES:
    df_sheet = load_data(EXCEL_PATH, sheet)
    df_sheet['lokasi'] = sheet
    all_data_for_download = pd.concat([all_data_for_download, df_sheet], ignore_index=True)

if not all_data_for_download.empty:
    st.download_button(
        label="Unduh Logbook Excel (Semua Lokasi & Bulan)",
        data=to_excel(all_data_for_download),
        file_name='Logbook_pH_Debit_Harian.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
