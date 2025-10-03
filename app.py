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
        # Menggunakan engine openpyxl karena kita menggunakan format .xlsx
        return pd.read_excel(path, sheet_name=sheet_name, engine='openpyxl')
    except FileNotFoundError:
        return pd.DataFrame(columns=COLUMNS_LONG)
    except ValueError:
        # Menangani ValueError jika sheet tidak ditemukan atau format tidak valid
        return pd.DataFrame(columns=COLUMNS_LONG)

def save_data(df, path, sheet_name):
    """Menyimpan data kembali ke sheet yang spesifik."""
    # Hapus duplikat berdasarkan tanggal, ambil baris terakhir (data terbaru)
    df = df.astype(str).drop_duplicates(subset=['tanggal'], keep='last')
    
    # Konversi tanggal kembali ke datetime
    df['tanggal'] = pd.to_datetime(df['tanggal'], errors='coerce')
    df = df.sort_values(by='tanggal')
    
    # Memastikan file ada sebelum menulis
    initialize_excel(path, SHEET_NAMES, COLUMNS_LONG)
    
    # Muat semua sheet (kecuali yang sedang diupdate)
    all_sheets = {sheet: load_data(path, sheet) for sheet in SHEET_NAMES if sheet != sheet_name}
    all_sheets[sheet_name] = df # Menambahkan sheet yang baru diupdate
    
    # Tulis ulang seluruh workbook dengan engine openpyxl
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        for sheet, data in all_sheets.items():
            data.to_excel(writer, sheet_name=sheet, index=False)


# --- FUNGSI UTILITY EXCEL DOWNLOAD (PERBAIKAN) ---

def to_excel(df):
    """Membuat file Excel dalam format BytesIO dengan data yang di-pivot sesuai format logbook."""
    output = BytesIO()
    # PERBAIKAN 1: Tambahkan engine='openpyxl' untuk penulisan ke BytesIO
    with pd.ExcelWriter(output, engine='openpyxl') as writer: 
        
        # Grup data berdasarkan lokasi (sheet)
        grouped_location = df.groupby('lokasi')
        
        # Loop melalui setiap lokasi
        for location, df_loc in grouped_location:
            sheet_name_safe = location.replace('/', ' ') # Membuat nama sheet aman
            start_row = 0
            
            # PERBAIKAN 2: Lelehkan data (Melt) untuk memisahkan pH dan debit ke kolom 'parameter'
            df_melted = df_loc.melt(
                id_vars=['tanggal', 'lokasi'],
                value_vars=['pH', 'debit'],
                var_name='parameter',
                value_name='nilai'
            ).dropna(subset=['nilai'])
            
            # Grup data berdasarkan tahun dan bulan (untuk setiap blok logbook)
            grouped_periode = df_melted.groupby([df_melted['tanggal'].dt.year, df_melted['tanggal'].dt.month])
            
            for (year, month), df_log in grouped_periode:
                
                # Dapatkan nama bulan
                try:
                    month_name = datetime(year, month, 1).strftime('%B')
                except ValueError:
                    continue

                # --- PERBAIKAN 3: Lakukan Pivoting untuk format Logbook Harian ---
                
                # Lakukan Pivot: index=Parameter, columns=Hari, values=Nilai
                df_pivot = df_log.pivot_table(
                    index='parameter',
                    columns=df_log['tanggal'].dt.day,
                    values='nilai',
                    aggfunc='first'
                ).reset_index()
                
                # Ganti nama kolom 'parameter' menjadi 'Parameter' dan hapus nama kolom index
                df_pivot.columns.name = None
                df_pivot = df_pivot.rename(columns={'parameter': 'Parameter'})
                
                # Tambahkan kolom 'No' (1, 2, ...)
                df_pivot.insert(0, 'No', range(1, 1 + len(df_pivot)))
                
                # Definisikan semua kolom yang diperlukan di output Excel
                day_cols = list(range(1, 32))
                fixed_cols = ['No', 'Parameter']
                # Nama kolom akhir sesuai template (gunakan float untuk hari agar sesuai dengan format template)
                final_cols_names = fixed_cols + [float(d) for d in day_cols] + ['Rata-Rata', 'Faktor Konversi', 'Debit (m3/H)', 'Debit (m3/M)']
                
                # Rename kolom hari di df_pivot (dari int ke float)
                column_mapping = {col: float(col) if isinstance(col, int) else col for col in df_pivot.columns if isinstance(col, int)}
                df_pivot = df_pivot.rename(columns=column_mapping)
                
                # Reindex ke final_cols_names
                df_pivot_final = df_pivot.reindex(columns=final_cols_names, fill_value='')
                
                # --- Tulis Header Awal (Baris 1-5) ---
                header_df = pd.DataFrame([
                    ['Logbook pengambilan pH dan Debit Harian'],
                    [f'Lokasi {location}'],
                    [''],
                    [''],
                    [f'Periode : Bulan {month_name} {year}']
                ])
                header_df.to_excel(writer, sheet_name=sheet_name_safe, startrow=start_row, index=False, header=False)
                
                # --- Tulis Baris Header Kolom 1 (Baris 6: Tanggal Pengukuran) ---
                header_row1_data = [['No', 'Parameter'] + ['Tanggal Pengukuran'] * 31 + ['Rata-Rata', 'Faktor Konversi', 'Debit (m3/H)', 'Debit (m3/M)']]
                pd.DataFrame(header_row1_data).to_excel(
                    writer, sheet_name=sheet_name_safe, startrow=start_row + 5, index=False, header=False
                )
                
                # --- Tulis Data Pivot (Mulai Baris 7: Header Hari, Baris 8: Data) ---
                # Tulis df_pivot_final. Header DataFrame (1.0, 2.0, ...) akan menjadi baris header kedua.
                df_pivot_final.to_excel(
                    writer, 
                    sheet_name=sheet_name_safe, 
                    startrow=start_row + 6, # Mulai dari baris 7 (indeks 6)
                    index=False, 
                    header=True # Gunakan nama kolom sebagai baris header ke-2
                )
                
                # Hitung jumlah baris yang ditulis
                rows_written = 5 + 1 + 1 + len(df_pivot_final) 
                
                # Pindah baris awal untuk periode berikutnya
                start_row += rows_written + 1 # Tambah 1 baris kosong

    writer.close()
    return output.getvalue()


# --- TAMPILAN STREAMLIT UTAMA ---

st.set_page_config(layout="wide", page_title="Logbook pH & Debit Harian")

# Inisialisasi file Excel
initialize_excel(EXCEL_PATH, SHEET_NAMES, COLUMNS_LONG)

st.title("Logbook pH & Debit Harian")

# Sidebar untuk Data Entry
st.sidebar.header("Input Data Harian")

with st.sidebar.form(key='data_form'):
    lokasi_input = st.selectbox("Lokasi", SHEET_NAMES)
    tanggal_input = st.date_input("Tanggal", datetime.now().date())
    ph_input = st.text_input("Nilai pH", "")
    debit_input = st.text_input("Nilai Debit (l/S)", "")
    
    submit_button = st.form_submit_button("Simpan Data")

    if submit_button:
        # Konversi input ke tipe data yang sesuai
        tanggal_dt = pd.to_datetime(tanggal_input)
        
        # Validasi dan konversi nilai pH dan Debit
        try:
            ph_value = float(ph_input) if ph_input and ph_input.strip() else np.nan
        except ValueError:
            st.error("Input pH harus berupa angka.")
            ph_value = np.nan

        try:
            debit_value = float(debit_input) if debit_input and debit_input.strip() else np.nan
        except ValueError:
            st.error("Input Debit harus berupa angka.")
            debit_value = np.nan
        
        # Hanya simpan jika ada setidaknya satu nilai yang valid
        if not pd.isna(ph_value) or not pd.isna(debit_value):
            new_data = pd.DataFrame([{
                'tanggal': tanggal_dt,
                'lokasi': lokasi_input,
                'pH': ph_value,
                'debit': debit_value
            }])
            
            # Muat data lama
            df_old = load_data(EXCEL_PATH, lokasi_input)
            
            # Gabungkan data baru dengan data lama
            df_combined = pd.concat([df_old, new_data], ignore_index=True)
            
            # Simpan data yang sudah digabungkan
            save_data(df_combined, EXCEL_PATH, lokasi_input)
            
            st.success(f"Data pH dan Debit untuk {lokasi_input} tanggal {tanggal_input} berhasil disimpan!")
            # Memaksa cache dimuat ulang
            load_data.clear()
        else:
            st.warning("Anda harus memasukkan setidaknya nilai pH atau Debit yang valid.")


# --- TAMPILAN DATA ---

st.header("Data Logbook Tersimpan")

# Tabs untuk setiap lokasi
tab_titles = SHEET_NAMES
tabs = st.tabs(tab_titles)

for i, sheet_name in enumerate(SHEET_NAMES):
    with tabs[i]:
        st.subheader(f"Lokasi: {sheet_name}")
        
        # Muat data yang sudah disimpan (akan menggunakan cache kecuali di-clear)
        df_log = load_data(EXCEL_PATH, sheet_name)
        
        # Konversi kembali 'tanggal' ke format datetime untuk manipulasi
        df_log['tanggal'] = pd.to_datetime(df_log['tanggal'], errors='coerce').dt.date
        df_log = df_log.dropna(subset=['tanggal'])
        
        # Pisahkan bulan dan tahun untuk dropdown
        df_log['tahun'] = pd.to_datetime(df_log['tanggal']).dt.year
        df_log['bulan'] = pd.to_datetime(df_log['tanggal']).dt.month

        # Filter data berdasarkan bulan dan tahun
        all_years = sorted(df_log['tahun'].unique(), reverse=True)
        # Tambahkan nilai default untuk mencegah error saat tidak ada data
        selected_year = st.selectbox(f"Pilih Tahun ({sheet_name})", [None] + all_years, key=f'year_select_{sheet_name}')

        if selected_year is not None:
            df_log_year = df_log[df_log['tahun'] == selected_year]
            
            all_months = sorted(df_log_year['bulan'].unique(), reverse=True)
            month_names = [datetime(selected_year, m, 1).strftime('%B') for m in all_months]
            
            # Buat mapping dari nama bulan ke angka bulan
            month_map = {name: month for name, month in zip(month_names, all_months)}
            
            selected_month_name = st.selectbox(f"Pilih Bulan ({sheet_name})", [None] + month_names, key=f'month_select_{sheet_name}')
            selected_month = month_map.get(selected_month_name)

            if selected_month is not None:
                df_log_final = df_log_year[df_log_year['bulan'] == selected_month]
                
                if not df_log_final.empty:
                    
                    # Siapkan data untuk ditampilkan dalam format logbook (pivot)
                    # Data harus di-melt dulu untuk kolom 'pH' dan 'debit'
                    df_display_melted = df_log_final.melt(
                        id_vars=['tanggal', 'lokasi'],
                        value_vars=['pH', 'debit'],
                        var_name='Parameter',
                        value_name='Nilai'
                    ).dropna(subset=['Nilai'])
                    
                    # Lakukan Pivot: index=Parameter, columns=Hari, values=Nilai
                    df_display_pivot = df_display_melted.pivot_table(
                        index='Parameter',
                        columns=df_display_melted['tanggal'].apply(lambda x: x.day),
                        values='Nilai',
                        aggfunc='first'
                    ).reset_index()
                    
                    df_display_pivot.columns.name = None
                    df_display_pivot.insert(0, 'No', range(1, 1 + len(df_display_pivot)))
                    
                    # Kolom yang akan ditampilkan (No, Parameter, Hari 1, 2, 3...)
                    display_cols_base = ['No', 'Parameter']
                    display_cols_final = display_cols_base + [c for c in df_display_pivot.columns if c not in display_cols_base]
                    
                    st.dataframe(df_display_pivot[display_cols_final].fillna(''))
                    
                    st.markdown("---")
                    st.caption("Data ditampilkan dalam format logbook (Hari sebagai kolom).")
                else:
                    st.info("Tidak ada data untuk bulan yang dipilih.")
                
# --- UNDUH DATA ---

st.sidebar.header("Unduh Data")

# Muat semua data dari semua sheet untuk didownload
all_data_for_download = pd.DataFrame(columns=COLUMNS_LONG)
for sheet in SHEET_NAMES:
    df_sheet = load_data(EXCEL_PATH, sheet)
    df_sheet['lokasi'] = sheet # Tambahkan kolom lokasi sebelum digabungkan
    all_data_for_download = pd.concat([all_data_for_download, df_sheet], ignore_index=True)
    
# Konversi kembali 'tanggal' ke format datetime yang benar
all_data_for_download['tanggal'] = pd.to_datetime(all_data_for_download['tanggal'], errors='coerce')
all_data_for_download = all_data_for_download.dropna(subset=['tanggal'])

# Tombol download
st.download_button(
    label="Unduh Logbook Excel (Semua Lokasi & Bulan)",
    data=to_excel(all_data_for_download),
    file_name=f'Logbook_pH_Debit_All_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

st.sidebar.markdown("---")
st.sidebar.markdown("Dibuat dengan Streamlit dan Pandas.")
