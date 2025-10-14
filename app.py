import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter
from streamlit_gsheets_connection import GSheetsConnection
import datetime

# ----------------------------
# KONFIGURASI GOOGLE SHEETS
# ----------------------------
# Dapatkan ID Spreadsheet dari secrets.toml
try:
    # Error: ModuleNotFoundError: No module named 'streamlit_gsheets_connection'
    # PENTING: Pastikan Anda menambahkan streamlit-gsheets-connection di file requirements.txt
    SHEET_ID = st.secrets["gsheets"]["spreadsheet_id"]
    conn = st.connection("gsheets", type=GSheetsConnection)
except KeyError:
    st.error("Gagal membaca 'spreadsheet_id' dari secrets.toml. Pastikan kunci [gsheets] sudah dikonfigurasi.")
    st.stop()
except Exception as e:
    # Error ini sering muncul jika format secrets.toml salah, terutama private_key
    st.error(f"Gagal inisialisasi koneksi Google Sheets: {e}")
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

# Mapping baris di Google Sheet Anda
GSHEET_ROW_MAP = {
    'pH': 3,         # Data pH ada di Baris 3
    'suhu': 4,       # Data Suhu ada di Baris 4
    'debit': 5,      # Data Debit ada di Baris 5
}
# Kolom rata-rata di Google Sheet Anda (Diasumsikan Kolom AG - Kolom 33 jika A=1)
GSHEET_AVG_COL_INDEX = 33 

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air (Data Permanen via Google Sheets)")


# ----------------------------
# Utility: baca & simpan sheet (SUDAH DIREVISI)
# ----------------------------
@st.cache_data(ttl=5)
def read_all_sheets_gsheets():
    """
    Membaca semua sheet dari Google Sheets dengan format PIVOT Anda 
    dan mengkonversinya ke format RAW DATA (tanggal, pH, suhu, debit) untuk diproses.
    """
    all_dfs_raw = {}
    
    for sheet_name in SHEET_NAMES:
        try:
            # Baca data mentah, termasuk header baris 2 (Hari) dan kolom A (Parameter)
            # Rentang A2:AF5 mencakup Hari ke-1 sampai 31 dan Kolom Rata-rata (dianggap AF atau AG)
            df_pivot = conn.read(
                spreadsheet=SHEET_ID, 
                worksheet=sheet_name, 
                range="A2:AF5", # Rentang bacaan untuk hari 1-31 dan parameter
                header=1,       # Baris 2 (Hari) dijadikan header
                ttl=0
            )

            # 1. CLEANING & CONVERSION
            df_pivot.rename(columns={df_pivot.columns[0]: 'Parameter'}, inplace=True)
            df_pivot.set_index('Parameter', inplace=True)
            
            # 2. PENGAMBILAN RATA-RATA 
            # Karena Anda menggunakan rentang A2:AF5, kolom terakhir (indeks -1) adalah Rata-rata.
            avg_col_name = df_pivot.columns[-1] # Mengambil nama kolom terakhir
            
            # Ambil data rata-rata bulanan
            ph_avg = pd.to_numeric(df_pivot.loc['pH'].get(avg_col_name), errors='coerce')
            # PENTING: Pastikan penamaan indeks sesuai di GSheet Anda (suhu (°C), Debit (l/d))
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
            df_raw['tanggal'] = [f"{current_year}-{current_month:02d}-{int(day):02d}" for day in df_raw_data.index]
            df_raw['pH'] = pd.to_numeric(df_raw_data['pH'], errors='coerce').values
            df_raw['suhu'] = pd.to_numeric(df_raw_data['suhu (°C)'], errors='coerce').values
            df_raw['debit'] = pd.to_numeric(df_raw_data['Debit (l/d)'], errors='coerce').values
            
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
            st.warning(f"Gagal membaca sheet '{sheet_name}'. Pastikan format header Anda benar dan data ada di rentang A2:AF5. Error: {e}")
            all_dfs_raw[sheet_name] = pd.DataFrame(columns=INTERNAL_COLUMNS)
            
    return all_dfs_raw

def save_sheet_to_gsheets(lokasi: str, df_raw_data: pd.DataFrame):
    """
    Menyimpan data RAW dari Python kembali ke format PIVOT di Google Sheets.
    Fungsi ini HANYA menulis nilai harian (pH, suhu, debit) dan nilai rata-rata.
    --- FUNGSI INI SUDAH DIPERBAIKI ---
    """
    read_all_sheets_gsheets.clear()
    
    # 1. Filter Data Harian dan Rata-rata
    df_data_only = df_raw_data[~df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    # Periksa dan ambil data rata-rata (hanya satu baris yang mengandung 'Rata-rata')
    df_avg_rows = df_raw_data[df_raw_data["tanggal"].astype(str).str.startswith('Rata-rata', na=False)]
    if df_avg_rows.empty:
        # Jika tidak ada baris rata-rata yang terhitung, buat baris kosong
        df_avg_row = pd.Series({'ph_rata_rata_bulan': np.nan, 'suhu_rata_rata_bulan': np.nan, 'debit_rata_rata_bulan': np.nan})
    else:
        df_avg_row = df_avg_rows.iloc[0]
    
    # 2. Siapkan Nilai untuk Ditulis
    data_to_write = []

    # Map data harian ke Hari (index 1-31)
    df_data_only['Hari'] = pd.to_datetime(df_data_only['tanggal']).dt.day

    # Tulis data harian (Baris 3, 4, 5)
    for parameter, row_num in GSHEET_ROW_MAP.items():
        # Buat dictionary Hari:Nilai untuk parameter ini
        param_dict = df_data_only[['Hari', parameter]].set_index('Hari')[parameter].to_dict()
        
        # Tulis data harian (Kolom B sampai AF, Hari 1 sampai 31)
        for day in range(1, 32):
            # xlsxwriter.utility.xl_col_to_name(day) mengembalikan B untuk day=1, C untuk day=2, dst.
            col_letter = xlsxwriter.utility.xl_col_to_name(day) 
            
            # Ambil nilai dari dictionary, jika tidak ada, gunakan "" (untuk menghapus sel kosong)
            val = param_dict.get(day, "")
            
            data_to_write.append({
                'range': f"{col_letter}{row_num}",
                'values': [[val if not pd.isna(val) else ""]]
            })

    # Tulis rata-rata (Asumsi Kolom AG - Kolom 33)
    avg_col_letter = 'AG'
    
    data_to_write.append({
        'range': f"{avg_col_letter}{GSHEET_ROW_MAP['pH']}",
        'values': [[df_avg_row['ph_rata_rata_bulan'] if not pd.isna(df_avg_row['ph_rata_rata_bulan']) else ""]]
    })
    data_to_write.append({
        'range': f"{avg_col_letter}{GSHEET_ROW_MAP['suhu']}",
        'values': [[df_avg_row['suhu_rata_rata_bulan'] if not pd.isna(df_avg_row['suhu_rata_rata_bulan']) else ""]]
    })
    data_to_write.append({
        'range': f"{avg_col_letter}{GSHEET_ROW_MAP['debit']}",
        'values': [[df_avg_row['debit_rata_rata_bulan'] if not pd.isna(df_avg_row['debit_rata_rata_bulan']) else ""]]
    })
    
    # Gunakan write_batch untuk mengirim semua data sekaligus (lebih cepat dan aman)
    conn.write_batch(
        spreadsheet=SHEET_ID,
        worksheet=lokasi,
        data=data_to_write
    )


# ----------------------------------------------------
# FUNGSI MEMBUAT FILE EXCEL UNTUK DOWNLOAD DENGAN FORMAT PIVOT (TETAP)
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
    """Membuat sheet pivot dengan border dan format yang diminta."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        workbook = writer.book
        border_bold_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'bold': True})
        border_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        header_bold_format = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter', 'bold': True})
        merge_format = workbook.add_format({
            'bold': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        for lokasi in SHEET_NAMES:
            df_raw = all_raw_sheets.get(lokasi)
            if df_raw is not None:
                pivot_data = create_pivot_data(df_raw, lokasi)
                
                if pivot_data:
                    for sheet_name, df_pivot in pivot_data.items():
                        
                        worksheet = workbook.add_worksheet(sheet_name)
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
                        col_headers = list(df_pivot.columns)
                        worksheet.write_row('B2', col_headers, border_bold_format)
                        worksheet.write('A2', 'TANGGAL', header_bold_format)
                        row_headers = list(df_pivot.index)
                        worksheet.write_column('A3', row_headers, header_bold_format)

                        data_to_write = df_pivot.values.tolist()
                        start_row = 2
                        start_col = 1

                        for row_num, row_data in enumerate(data_to_write):
                            processed_data = ["" if pd.isna(item) else item for item in row_data]
                            worksheet.write_row(start_row + row_num, start_col, processed_data, border_format)
                            
                        worksheet.set_column('A:A', 15)
                        worksheet.set_column('B:Z', 8)
                        
    return output.getvalue()


# ----------------------------
# Form input (TETAP SAMA)
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
    read_all_sheets_gsheets.clear()
    all_sheets = read_all_sheets_gsheets()
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=INTERNAL_COLUMNS))

    # --- Hapus entri lama dengan tanggal yang sama (harian) ---
    tanggal_input_str = tanggal.strftime('%Y-%m-%d')

    df_data_only = df_loc[~df_loc["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    df_data_only['tanggal_date'] = df_data_only["tanggal"].astype(str).str.split(' ').str[0]
    df_data_only = df_data_only[df_data_only['tanggal_date'] != tanggal_input_str].drop(columns=['tanggal_date']).copy()

    # Tambahkan data baru
    new_row = {
        "tanggal": tanggal.strftime('%Y-%m-%d %H:%M:%S'),
        "pH": float(ph),
        "suhu": float(suhu),
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

    df_final = df_final[~df_final["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()

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
    
    try:
        # Panggil fungsi save yang sudah diperbaiki
        save_sheet_to_gsheets(lokasi, df_loc)
        st.success(f"✅ Data TERSIMPAN PERMANEN di Google Sheets '{lokasi}' — tanggal {tanggal.strftime('%Y-%m-%d')}. Data rata-rata diperbarui.")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Gagal menyimpan ke Google Sheets. Pastikan Service Account diizinkan sebagai Editor dan format tabel Anda di Google Sheet benar. Error: {e}")


# ----------------------------
# Preview data (TETAP SAMA)
# ----------------------------
st.markdown("---")
st.subheader("Preview Data Lokasi Aktif (Format Bulanan)")
st.info("Pilih bulan dan tahun di bawah untuk melihat data dalam format tabel harian.")

try:
    read_all_sheets_gsheets.clear()
    all_sheets = read_all_sheets_gsheets()
    df_raw = all_sheets.get(lokasi, pd.DataFrame(columns=INTERNAL_COLUMNS))
    
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
# Tombol download file Excel gabungan (TETAP SAMA)
# ----------------------------
st.markdown("---")
st.subheader("Pengelolaan File Excel")
st.info("File yang diunduh hanya berisi sheet ringkasan bulanan berformat tabel dengan garis kotak (border).")

all_raw_sheets = read_all_sheets_gsheets()

if all_raw_sheets:
    
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
        st.warning("Tombol Reset Data telah dinonaktifkan. Data Anda sekarang tersimpan PERMANEN di Google Sheets.")
        
else:
    st.warning("Gagal memuat data dari Google Sheets.")
