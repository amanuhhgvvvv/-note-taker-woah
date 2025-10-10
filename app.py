import streamlit as st
import pandas as pd
from pathlib import Path
import os 
import numpy as np 
import io 
import xlsxwriter 

# ----------------------------
# Konfigurasi / Nama file
# ----------------------------
EXCEL_PATH = Path("ph_debit_data_pivot.xlsx") 
SHEET_NAMES = [
    "Power Plant",
    "Plant Garage",
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
# Kolom pH, Suhu, dan Debit
COLUMNS = ["tanggal", "pH", "suhu", "debit", "ph_rata_rata_bulan", "suhu_rata_rata_bulan", "debit_rata_rata_bulan"] 

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air")

# ----------------------------
# Inisialisasi file Excel
# ----------------------------
def initialize_excel(path: Path):
    """Memastikan file Excel dan semua sheet yang dibutuhkan ada."""
    if not path.exists():
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet in SHEET_NAMES:
                df = pd.DataFrame(columns=COLUMNS)
                df.to_excel(writer, sheet_name=sheet, index=False)
    else:
        try:
            all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={'tanggal': str})
        except Exception:
            all_sheets = {}

        with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
            for sheet in SHEET_NAMES:
                if sheet not in all_sheets:
                    df = pd.DataFrame(columns=COLUMNS)
                    df.to_excel(writer, sheet_name=sheet, index=False)

initialize_excel(EXCEL_PATH)

# ----------------------------
# Utility: baca & simpan sheet
# ----------------------------
@st.cache_data 
def read_all_sheets(path: Path):
    """Membaca semua sheet, memastikan kolom 'suhu' ada, dan 'tanggal' sebagai string."""
    all_dfs = pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={'tanggal': str})
    
    # PERBAIKAN: Menambahkan kolom 'suhu' dan rata-rata suhu jika belum ada (dari file lama)
    for sheet_name, df in all_dfs.items():
        if 'suhu' not in df.columns:
            df['suhu'] = np.nan
        if 'suhu_rata_rata_bulan' not in df.columns:
            df['suhu_rata_rata_bulan'] = np.nan
        all_dfs[sheet_name] = df.reindex(columns=COLUMNS)
        
    return all_dfs

def save_all_sheets(dfs: dict, path: Path):
    """Menyimpan semua dataframe ke file Excel, memastikan urutan kolom."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df = df.reindex(columns=COLUMNS)
            df.to_excel(writer, sheet_name=sheet, index=False)

# ----------------------------------------------------
# FUNGSI MEMBUAT FILE EXCEL UNTUK DOWNLOAD DENGAN FORMAT PIVOT
# ----------------------------------------------------
def create_pivot_data(df_raw, lokasi):
    """Memproses DataFrame mentah menjadi format pivot bulanan."""
    
    df_data_rows = df_raw[~df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    df_avg_rows = df_raw[df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()

    df_data_rows['tanggal_dt'] = pd.to_datetime(df_data_rows['tanggal'], errors='coerce')
    df_data_rows = df_data_rows.dropna(subset=['tanggal_dt'])

    if df_data_rows.empty:
        return None 
    
    df_data_rows['TahunBulan'] = df_data_rows['tanggal_dt'].dt.strftime('%Y-%m')
    df_data_rows['Hari'] = df_data_rows['tanggal_dt'].dt.day
    
    pivot_sheets = {}
    
    for (tahun_bulan, df_group) in df_data_rows.groupby('TahunBulan'):
        
        selected_month = df_group['tanggal_dt'].dt.month.iloc[0]
        selected_year = df_group['tanggal_dt'].dt.year.iloc[0]
        sheet_name = f"{lokasi} - {tahun_bulan}"

        df_pivot_data = df_group[['Hari', 'pH', 'suhu', 'debit']] 
        
        df_pivot = pd.melt(
            df_pivot_data, 
            id_vars=['Hari'], 
            value_vars=['pH', 'suhu', 'debit'], 
            var_name='Parameter', 
            value_name='Nilai'
        )
        
        df_pivot = df_pivot.pivot(
            index='Parameter', 
            columns='Hari', 
            values='Nilai'
        )
        
        avg_row = df_avg_rows[
            df_avg_rows['tanggal'].astype(str).str.contains(f"{selected_month:02d}/{selected_year}", na=False)
        ]

        if not avg_row.empty:
            ph_avg = avg_row['ph_rata_rata_bulan'].iloc[0]
            suhu_avg = avg_row['suhu_rata_rata_bulan'].iloc[0]
            debit_avg = avg_row['debit_rata_rata_bulan'].iloc[0]

            rata_rata_series = pd.Series(
                data=[ph_avg, suhu_avg, debit_avg], 
                index=['pH', 'suhu', 'debit'], 
                name='Rata-rata'
            )
            df_pivot['Rata-rata'] = rata_rata_series 
        else:
             df_pivot['Rata-rata'] = np.nan
        
        df_pivot = df_pivot.rename(index={'pH': 'pH', 'suhu': 'Suhu (°C)', 'debit': 'Debit (l/d)'})
        df_pivot = df_pivot.reindex(['pH', 'Suhu (°C)', 'Debit (l/d)']) 
        
        df_pivot.index.name = None 
        
        pivot_sheets[sheet_name] = df_pivot
        
    return pivot_sheets

def create_excel_with_pivot_sheets(all_raw_sheets):
    """Membuat sheet pivot dengan border dan format yang diminta (KETERANGAN dihapus, header kolom TANGGAL/Hari ditebalkan)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        # 1. Dapatkan objek workbook dan definisikan format border
        workbook = writer.book
        
        # PERUBAHAN FORMAT: Format baru untuk menebalkan Hari/Rata-rata dan TANGGAL/Parameter
        border_bold_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'bold': True})
        border_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'}) 
        header_bold_format = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter', 'bold': True})
        
        # Format untuk judul yang digabungkan
        merge_format = workbook.add_format({
            'bold': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        # 2. Tulis sheet data pivot (format bulanan)
        for lokasi in SHEET_NAMES:
            df_raw = all_raw_sheets.get(lokasi)
            if df_raw is not None:
                pivot_data = create_pivot_data(df_raw, lokasi)
                
                if pivot_data: 
                    for sheet_name, df_pivot in pivot_data.items():
                         
                        # Dapatkan objek worksheet yang baru dibuat
                        worksheet = workbook.add_worksheet(sheet_name)
                        
                        # --- Tulis Header Utama (Start A1 - Judul Dinamis) ---
                        last_col_letter = xlsxwriter.utility.xl_col_to_name(len(df_pivot.columns)) 
                        
                        sheet_info = sheet_name.split(' - ')
                        if len(sheet_info) > 1:
                            lokasi_nama = sheet_info[0]
                            tahun_bulan_str = sheet_info[1]
                            display_date = pd.to_datetime(tahun_bulan_str, format='%Y-%m').strftime('%B %Y')
                            title = f"Data {lokasi_nama} Bulan {display_date}"
                        else:
                            title = f"Data {lokasi}"
                            
                        worksheet.merge_range(f'A1:{last_col_letter}1', title, merge_format)

                        # --- Tulis Header Kolom (Hari, Rata-rata) ---
                        col_headers = list(df_pivot.columns)
                        # MENEBALKAN teks Hari/Rata-rata
                        worksheet.write_row('B2', col_headers, border_bold_format) 

                        # TULIS LABEL "TANGGAL" di A2. MENEBALKAN teks TANGGAL.
                        worksheet.write('A2', 'TANGGAL', header_bold_format)
                        
                        # --- Tulis Index Baris (pH, Suhu, Debit (l/d)) ---
                        row_headers = list(df_pivot.index)
                        # MENEBALKAN teks di kolom TANGGAL (Parameter)
                        worksheet.write_column('A3', row_headers, header_bold_format)

                        # --- Tulis Data dan Border ---
                        data_to_write = df_pivot.values.tolist()
                        
                        start_row = 2 
                        start_col = 1 

                        for row_num, row_data in enumerate(data_to_write):
                            processed_data = ["" if pd.isna(item) else item for item in row_data]
                            # Data nilai tetap menggunakan format biasa (tidak tebal)
                            worksheet.write_row(start_row + row_num, start_col, processed_data, border_format)
                            
                        # Atur lebar kolom agar terlihat rapi
                        worksheet.set_column('A:A', 15) 
                        worksheet.set_column('B:Z', 8) 
                        
    return output.getvalue()

# ----------------------------
# Form input 
# ----------------------------
if 'lokasi' not in st.session_state:
    st.session_state['lokasi'] = SHEET_NAMES[0]

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES, index=SHEET_NAMES.index(st.session_state['lokasi']))
st.session_state['lokasi'] = lokasi

col_ph, col_suhu, col_debit = st.columns(3) 
with col_ph:
    ph = st.number_input("pH (0.0 - 14.0)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
with col_suhu:
    suhu = st.number_input("Suhu (°C)", min_value=0.0, max_value=100.0, value=25.0, format="%.3f")
with col_debit:
    debit = st.number_input("Debit (L/detik)", min_value=0.0, value=0.0, format="%.3f")


if st.button("Simpan data"):
    read_all_sheets.clear() 
    all_sheets = read_all_sheets(EXCEL_PATH) 
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))

    # --- Hapus entri lama dengan tanggal yang sama (harian) ---
    tanggal_input_str = tanggal.strftime('%Y-%m-%d')

    df_data_only = df_loc[~df_loc["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    df_data_only['tanggal_date'] = df_data_only["tanggal"].astype(str).str.split(' ').str[0]
    df_data_only = df_data_only[df_data_only['tanggal_date'] != tanggal_input_str].drop(columns=['tanggal_date']).copy()

    # BAGIAN INI SUDAH DIKOREKSI UNTUK MEMASTIKAN KURUNG TUTUP ADA
    new_row = {
        "tanggal": tanggal.strftime('%Y-%m-%d %H:%M:%S'), 
        "pH": float(ph),
        "suhu": float(suhu), # <--- Tanda kurung tutup float() sudah ada di sini
        "debit": float(debit),
        "ph_rata_rata_bulan": None,
        "suhu_rata_rata_bulan": None, 
        "debit_rata_rata_bulan": None
    }
    
    df_loc_with_new_data = pd.concat([df_data_only, pd.DataFrame([new_row])], ignore_index=True)


    # ---- Hitung dan Tambahkan Rata-rata Bulanan ----
    
    df_hitung_rata = df_loc_with_new_data.copy()
    df_hitung_rata["tanggal_dt"] = pd.to_datetime(df_hitung_rata["tanggal"], errors="coerce")
    df_hitung_rata = df_hitung_rata.dropna(subset=['tanggal_dt']) 
    
    df_final = df_loc_with_new_data.copy()

    if not df_hitung_rata.empty:
        df_hitung_rata["bulan"] = df_hitung_rata["tanggal_dt"].dt.month.astype(int)
        df_hitung_rata["tahun"] = df_hitung_rata["tanggal_dt"].dt.year.astype(int)
    
        avg_df = (
            df_hitung_rata.groupby(["tahun", "bulan"], as_index=False)
            .agg(
                ph_rata_rata_bulan=('pH', 'mean'),
                suhu_rata_rata_bulan=('suhu', 'mean'), 
                debit_rata_rata_bulan=('debit', 'mean')
            )
            .round(3)
        )
            
        for _, row in avg_df.iterrows():
            bulan_int = int(row['bulan'])
            tahun_int = int(row['tahun'])
            
            rata_row = {
                "tanggal": f"Rata-rata {bulan_int:02d}/{tahun_int}", 
                "pH": None,
                "suhu": None, 
                "debit": None,
                "ph_rata_rata_bulan": row["ph_rata_rata_bulan"],
                "suhu_rata_rata_bulan": row["suhu_rata_rata_bulan"], 
                "debit_rata_rata_bulan": row["debit_rata_rata_bulan"]
            }
            df_final = pd.concat([df_final, pd.DataFrame([rata_row])], ignore_index=True)
        
    df_loc = df_final 
    all_sheets[lokasi] = df_loc
    save_all_sheets(all_sheets, EXCEL_PATH)

    st.success(f"Data tersimpan di sheet '{lokasi}' — tanggal {tanggal.strftime('%Y-%m-%d')}. Data rata-rata diperbarui.")
    st.rerun() 

# ----------------------------
# Preview data
# ----------------------------
st.markdown("---")
st.subheader("Preview Data Lokasi Aktif (Format Bulanan)")
st.info("Pilih bulan dan tahun di bawah untuk melihat data dalam format tabel harian.")

try:
    read_all_sheets.clear()
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_raw = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))
    
    df_data_rows = df_raw[~df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    df_avg_rows = df_raw[df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()

    df_data_rows['tanggal_dt'] = pd.to_datetime(df_data_rows['tanggal'], errors='coerce')
    df_data_rows = df_data_rows.dropna(subset=['tanggal_dt'])
    
    if df_data_rows.empty:
        st.info(f"Belum ada data valid untuk lokasi '{lokasi}'.")
    else:
        df_data_rows['Tahun'] = df_data_rows['tanggal_dt'].dt.year
        df_data_rows['Bulan'] = df_data_rows['tanggal_dt'].dt.month
        df_data_rows['Hari'] = df_data_rows['tanggal_dt'].dt.day
        
        bulan_tahun = (
            df_data_rows[['Bulan', 'Tahun']]
            .drop_duplicates()
            .sort_values(by=['Tahun', 'Bulan'], ascending=False)
        )
        
        bulan_tahun['Display'] = bulan_tahun.apply(
            lambda row: pd.to_datetime(f"{row['Tahun']}-{row['Bulan']}-01").strftime("%B %Y"), 
            axis=1
        )
        
        bulan_options = bulan_tahun['Display'].tolist()
        
        if not bulan_options:
            st.info(f"Tidak ada data harian yang tersedia untuk membuat preview bulanan.")
        else:
            selected_display = st.selectbox("Pilih Bulan dan Tahun:", options=bulan_options)
            
            selected_row = bulan_tahun[bulan_tahun['Display'] == selected_display].iloc[0]
            selected_month = selected_row['Bulan']
            selected_year = selected_row['Tahun']
            
            df_filtered = df_data_rows[
                (df_data_rows['Bulan'] == selected_month) & 
                (df_data_rows['Tahun'] == selected_year)
            ]

            df_pivot_data = df_filtered[['Hari', 'pH', 'suhu', 'debit']] 
            
            df_pivot = pd.melt(
                df_pivot_data, 
                id_vars=['Hari'], 
                value_vars=['pH', 'suhu', 'debit'],
                var_name='Parameter', 
                value_name='Nilai'
            )
            
            df_pivot = df_pivot.pivot(
                index='Parameter', 
                columns='Hari', 
                values='Nilai'
            )
            
            avg_row = df_avg_rows[
                df_avg_rows['tanggal'].astype(str).str.contains(f"{selected_month:02d}/{selected_year}", na=False)
            ]

            if not avg_row.empty:
                ph_avg = avg_row['ph_rata_rata_bulan'].iloc[0]
                suhu_avg = avg_row['suhu_rata_rata_bulan'].iloc[0]
                debit_avg = avg_row['debit_rata_rata_bulan'].iloc[0]

                rata_rata_series = pd.Series(
                    data=[ph_avg, suhu_avg, debit_avg], 
                    index=['pH', 'suhu', 'debit'], 
                    name='Rata-rata'
                )
                df_pivot['Rata-rata'] = rata_rata_series 
            else:
                 df_pivot['Rata-rata'] = np.nan
            
            df_pivot.index.name = lokasi 
            
            df_pivot = df_pivot.rename(index={'pH': 'pH', 'suhu': 'Suhu (°C)', 'debit': 'Debit (l/d)'})
            df_pivot = df_pivot.reindex(['pH', 'Suhu (°C)', 'Debit (l/d)']) 
            
            # Penyesuaian tampilan untuk Streamlit
            df_pivot_display = df_pivot.reset_index()
            df_pivot_display.columns.values[0] = ""
            df_pivot_display = df_pivot_display.set_index("")

            st.dataframe(df_pivot_display, use_container_width=True)

except Exception as e:
    if "cannot reshape" in str(e):
        st.error(f"Gagal memproses data: Ada duplikasi data harian pada bulan yang dipilih. Silakan periksa entri data.")
    else:
        st.error(f"Gagal memproses data atau menampilkan format bulanan: {e}")

# ----------------------------
# Tombol download file Excel gabungan
# ----------------------------
st.markdown("---")
st.subheader("Pengelolaan File Excel")
st.info("File yang diunduh hanya berisi sheet ringkasan bulanan berformat tabel dengan garis kotak (border).")

all_raw_sheets = read_all_sheets(EXCEL_PATH)

if EXCEL_PATH.exists() and all_raw_sheets:
    
    excel_data_for_download = create_excel_with_pivot_sheets(all_raw_sheets)
    
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="⬇ Download File Excel (Ringkasan Format Tabel)",
            data=excel_data_for_download, 
            file_name="ph_debit_ringkasan_bulanan_bordered.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col2:
        if st.button("🗑 Reset Data di Server", help="Menghapus file Excel di server dan membuat ulang file kosong."):
            try:
                EXCEL_PATH.unlink() 
                initialize_excel(EXCEL_PATH) 

                read_all_sheets.clear() 
                st.success("✅ File Excel telah *dihapus* dari server dan direset menjadi file kosong.")
                
                st.rerun() 
                
            except Exception as e:
                st.error(f"Gagal menghapus dan mereset file Excel: {e}")

else:
    st.warning("File Excel belum tersedia di server untuk diunduh (mungkin sudah di-reset).")
