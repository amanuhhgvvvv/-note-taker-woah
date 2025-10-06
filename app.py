import streamlit as st
import pandas as pd
from pathlib import Path
import os 
import numpy as np 
import io 

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
# Kolom HANYA pH dan Debit
COLUMNS = ["tanggal", "pH", "debit", "ph_rata_rata_bulan", "debit_rata_rata_bulan"] 

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
    """Membaca semua sheet dari file Excel dengan 'tanggal' sebagai string."""
    return pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={'tanggal': str})

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

        df_pivot_data = df_group[['Hari', 'pH', 'debit']] 
        
        df_pivot = pd.melt(
            df_pivot_data, 
            id_vars=['Hari'], 
            value_vars=['pH', 'debit'], 
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
            debit_avg = avg_row['debit_rata_rata_bulan'].iloc[0]

            rata_rata_series = pd.Series(
                data=[ph_avg, debit_avg], 
                index=['pH', 'debit'], 
                name='Rata-rata'
            )
            df_pivot['Rata-rata'] = rata_rata_series 
        else:
             df_pivot['Rata-rata'] = np.nan
        
        df_pivot = df_pivot.rename(index={'pH': 'pH', 'debit': 'Debit (l/d)'})
        df_pivot = df_pivot.reindex(['pH', 'Debit (l/d)']) 
        
        # Tambahkan kolom KETERANGAN di bagian paling kanan
        df_pivot['KETERANGAN'] = '' 
        
        df_pivot.index.name = None 
        
        pivot_sheets[sheet_name] = df_pivot
        
    return pivot_sheets

def create_excel_with_pivot_sheets(all_raw_sheets):
    """Hanya membuat sheet pivot, menghilangkan sheet RAW."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        # HILANGKAN BAGIAN INI:
        # for sheet_name, df_raw in all_raw_sheets.items():
        #     df_raw.reindex(columns=COLUMNS).to_excel(writer, sheet_name=f"RAW - {sheet_name}", index=False)

        # 2. Tulis sheet data pivot (format bulanan)
        for lokasi in SHEET_NAMES:
            df_raw = all_raw_sheets.get(lokasi)
            if df_raw is not None:
                pivot_data = create_pivot_data(df_raw, lokasi)
                
                if pivot_data: 
                    for sheet_name, df_pivot in pivot_data.items():
                         # Tambahkan baris header 
                        header_df = pd.DataFrame({sheet_name: [f"Data Bulanan {lokasi}"]}).T
                        header_df.to_excel(writer, sheet_name=sheet_name, index=True, header=False, startrow=0)
                        
                        # Tulis tabel pivot
                        df_pivot.to_excel(writer, sheet_name=sheet_name, startrow=2, index=True)
                        
    return output.getvalue()

# ----------------------------
# Form input 
# ----------------------------
if 'lokasi' not in st.session_state:
    st.session_state['lokasi'] = SHEET_NAMES[0]

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES, index=SHEET_NAMES.index(st.session_state['lokasi']))
st.session_state['lokasi'] = lokasi

col_ph, col_debit = st.columns(2) 
with col_ph:
    ph = st.number_input("pH (0.0 - 14.0)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
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

    new_row = {
        "tanggal": tanggal.strftime('%Y-%m-%d %H:%M:%S'), 
        "pH": float(ph),
        "debit": float(debit),
        "ph_rata_rata_bulan": None,
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
                "debit": None,
                "ph_rata_rata_bulan": row["ph_rata_rata_bulan"],
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

            df_pivot_data = df_filtered[['Hari', 'pH', 'debit']] 
            
            df_pivot = pd.melt(
                df_pivot_data, 
                id_vars=['Hari'], 
                value_vars=['pH', 'debit'],
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
                debit_avg = avg_row['debit_rata_rata_bulan'].iloc[0]

                rata_rata_series = pd.Series(
                    data=[ph_avg, debit_avg], 
                    index=['pH', 'debit'], 
                    name='Rata-rata'
                )
                df_pivot['Rata-rata'] = rata_rata_series 
            else:
                 df_pivot['Rata-rata'] = np.nan
            
            df_pivot.index.name = lokasi 
            
            df_pivot = df_pivot.rename(index={'pH': 'pH', 'debit': 'Debit (l/d)'})
            df_pivot = df_pivot.reindex(['pH', 'Debit (l/d)']) 
            
            # Tambahkan kolom KETERANGAN untuk preview 
            df_pivot['KETERANGAN'] = '' 
            
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
st.info("File yang diunduh hanya berisi sheet ringkasan bulanan berformat tabel.")

all_raw_sheets = read_all_sheets(EXCEL_PATH)

if EXCEL_PATH.exists() and all_raw_sheets:
    
    excel_data_for_download = create_excel_with_pivot_sheets(all_raw_sheets)
    
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="⬇️ Download File Excel (Ringkasan Format Tabel)",
            data=excel_data_for_download, 
            file_name="ph_debit_ringkasan_bulanan.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col2:
        if st.button("🗑️ Reset Data di Server", help="Menghapus file Excel di server dan membuat ulang file kosong."):
            try:
                EXCEL_PATH.unlink() 
                initialize_excel(EXCEL_PATH) 

                read_all_sheets.clear() 
                st.success("✅ File Excel telah **dihapus** dari server dan direset menjadi file kosong.")
                
                st.rerun() 
                
            except Exception as e:
                st.error(f"Gagal menghapus dan mereset file Excel: {e}")

else:
    st.warning("File Excel belum tersedia di server untuk diunduh (mungkin sudah di-reset).")
