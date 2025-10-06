import streamlit as st
import pandas as pd
from pathlib import Path
import os 
import numpy as np # Diperlukan untuk perhitungan rata-rata

# ----------------------------
# Konfigurasi / Nama file
# ----------------------------
EXCEL_PATH = Path("ph_debit_suhu_data.xlsx") # Ganti nama file agar tidak bentrok dengan yang lama
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
    "Clay Laterite", # Pilihan yang sesuai dengan format tabel
    "Silika",
    "Kondensor PLTU"
]
# MENAMBAH KOLOM UNTUK SUHU
COLUMNS = ["tanggal", "pH", "suhu", "debit", "ph_rata_rata_bulan", "suhu_rata_rata_bulan", "debit_rata_rata_bulan"]

st.set_page_config(page_title="Pencatatan pH, Suhu & Debit Air", layout="centered")
st.title("📊 Pencatatan pH, Suhu, dan Debit Air")

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

# ----------------------------
# Form input
# ----------------------------
st.markdown("Isi data pengukuran di bawah ini:")

if 'lokasi' not in st.session_state:
    st.session_state['lokasi'] = SHEET_NAMES[0]

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES, index=SHEET_NAMES.index(st.session_state['lokasi']))
st.session_state['lokasi'] = lokasi

# MENAMBAH INPUT SUHU
col_ph, col_suhu, col_debit = st.columns(3)
with col_ph:
    ph = st.number_input("pH (0.0 - 14.0)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
with col_suhu:
    suhu = st.number_input("Suhu (°C)", min_value=0.0, value=30.0, format="%.2f")
with col_debit:
    debit = st.number_input("Debit (L/detik)", min_value=0.0, value=0.0, format="%.3f")


if st.button("Simpan data"):
    read_all_sheets.clear() 
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))

    # Hapus baris rata-rata lama sebelum menambahkan data baru
    df_loc_data_only = df_loc[~df_loc["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()

    # tambahkan data harian baru
    new_row = {
        "tanggal": tanggal.strftime('%Y-%m-%d %H:%M:%S'), 
        "pH": float(ph),
        "suhu": float(suhu), # Simpan suhu
        "debit": float(debit),
        "ph_rata_rata_bulan": None,
        "suhu_rata_rata_bulan": None,
        "debit_rata_rata_bulan": None
    }
    df_loc = pd.concat([df_loc_data_only, pd.DataFrame([new_row])], ignore_index=True)


    # ---- Hitung rata-rata bulanan ----
    df_data = df_loc[~df_loc["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    
    df_data["tanggal_dt"] = pd.to_datetime(df_data["tanggal"], errors="coerce")
    df_data = df_data.dropna(subset=['tanggal_dt']) 
    
    df_loc_new = df_data.drop(columns=['tanggal_dt'])[COLUMNS].copy()

    if not df_data.empty:
        df_data["bulan"] = df_data["tanggal_dt"].dt.month.astype(int)
        df_data["tahun"] = df_data["tanggal_dt"].dt.year.astype(int)
    
        # Hitung rata-rata untuk pH, Suhu, dan Debit
        avg_df = (
            df_data.groupby(["tahun", "bulan"], as_index=False)
            .agg(
                ph_rata_rata_bulan=('pH', 'mean'),
                suhu_rata_rata_bulan=('suhu', 'mean'), # Rata-rata suhu
                debit_rata_rata_bulan=('debit', 'mean') # Rata-rata debit
            )
            .round(3)
        )
            
        # Tambahkan baris rata-rata tiap bulan
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
            df_loc_new = pd.concat([df_loc_new, pd.DataFrame([rata_row])], ignore_index=True)
        
    df_loc = df_loc_new

    all_sheets[lokasi] = df_loc
    save_all_sheets(all_sheets, EXCEL_PATH)

    st.success(f"Data tersimpan di sheet '{lokasi}' — tanggal {tanggal.strftime('%Y-%m-%d')}")
    st.rerun() 

# ----------------------------
# Preview data dalam format Pivot Bulanan
# ----------------------------
st.markdown("---")
st.subheader("Preview Data Lokasi Aktif (Format Bulanan)")
st.info("Pilih bulan dan tahun di bawah untuk melihat data dalam format tabel harian.")

try:
    read_all_sheets.clear()
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_raw = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))
    
    # 1. Filter dan Siapkan Data Harian
    df_data_rows = df_raw[~df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()
    df_avg_rows = df_raw[df_raw["tanggal"].astype(str).str.startswith('Rata-rata', na=False)].copy()

    df_data_rows['tanggal_dt'] = pd.to_datetime(df_data_rows['tanggal'], errors='coerce')
    df_data_rows = df_data_rows.dropna(subset=['tanggal_dt'])
    
    if df_data_rows.empty:
        st.info(f"Belum ada data valid untuk lokasi '{lokasi}'.")
    else:
        # Tambahkan kolom Bulan, Tahun, dan Hari
        df_data_rows['Tahun'] = df_data_rows['tanggal_dt'].dt.year
        df_data_rows['Bulan'] = df_data_rows['tanggal_dt'].dt.month
        df_data_rows['Hari'] = df_data_rows['tanggal_dt'].dt.day
        
        # Ambil daftar unik Bulan dan Tahun untuk filter
        bulan_tahun = (
            df_data_rows[['Bulan', 'Tahun']]
            .drop_duplicates()
            .sort_values(by=['Tahun', 'Bulan'], ascending=False)
        )
        
        # Buat string format "Nama Bulan Tahun"
        bulan_tahun['Display'] = bulan_tahun.apply(
            lambda row: pd.to_datetime(f"{row['Tahun']}-{row['Bulan']}-01").strftime("%B %Y"), 
            axis=1
        )
        
        # --- Filter Bulan/Tahun ---
        bulan_options = bulan_tahun['Display'].tolist()
        selected_display = st.selectbox("Pilih Bulan dan Tahun:", options=bulan_options)
        
        selected_row = bulan_tahun[bulan_tahun['Display'] == selected_display].iloc[0]
        selected_month = selected_row['Bulan']
        selected_year = selected_row['Tahun']
        
        # Filter data berdasarkan pilihan
        df_filtered = df_data_rows[
            (df_data_rows['Bulan'] == selected_month) & 
            (df_data_rows['Tahun'] == selected_year)
        ]

        # 2. Lakukan Operasi Pivot (Transformasi Data)
        
        # Pilih kolom yang akan di-pivot
        df_pivot_data = df_filtered[['Hari', 'pH', 'suhu', 'debit']]
        
        # Susun ulang data: Hari sebagai Kolom, Parameter sebagai Index
        # Menggunakan 'Hari' sebagai kolom, 'pH', 'suhu', 'debit' sebagai values, dan membuat Index baru
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
        
        # 3. Tambahkan Rata-rata Bulanan (Kolom terakhir)
        
        # Ambil rata-rata untuk bulan/tahun yang dipilih
        avg_row = df_avg_rows[
            df_avg_rows['tanggal'].astype(str).str.contains(f"{selected_month:02d}/{selected_year}", na=False)
        ]

        if not avg_row.empty:
            ph_avg = avg_row['ph_rata_rata_bulan'].iloc[0]
            suhu_avg = avg_row['suhu_rata_rata_bulan'].iloc[0]
            debit_avg = avg_row['debit_rata_rata_bulan'].iloc[0]

            # Siapkan baris rata-rata untuk digabungkan
            rata_rata_series = pd.Series(
                data=[ph_avg, suhu_avg, debit_avg], 
                index=['pH', 'suhu', 'debit'], 
                name='Rata-rata'
            )
            
            # Gabungkan Kolom Rata-rata
            df_pivot['Rata-rata'] = rata_rata_series 
        else:
             df_pivot['Rata-rata'] = np.nan

        # 4. Finalisasi Tampilan
        
        # Tambahkan kolom 'Satuan'
        df_pivot.insert(0, 'Satuan', ['pH', '°C', 'l/d'])

        # Ganti nama Index (Parameter) menjadi 'SETTLING POND' (sesuai gambar)
        df_pivot.index.name = "CLAY & LATERITE"
        
        # Urutkan baris sesuai keinginan (pH, suhu, debit)
        df_pivot = df_pivot.reindex(['pH', 'suhu', 'debit'])

        st.dataframe(df_pivot, use_container_width=True)

except Exception as e:
    st.error(f"Gagal memproses data atau menampilkan format bulanan: {e}")

# ----------------------------
# Tombol download file Excel gabungan + LOGIKA HAPUS DATA (DIPISAHKAN)
# ----------------------------
st.markdown("---")
st.subheader("Pengelolaan File Excel")
st.info("File disimpan di server sebagai `ph_debit_suhu_data.xlsx`. Unduh data sebelum Anda mereset.")

if EXCEL_PATH.exists():
    with open(EXCEL_PATH, "rb") as f:
        data_bytes = f.read()
    
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="⬇️ Download File Excel (Semua Lokasi)",
            data=data_bytes,
            file_name="ph_debit_suhu_data.xlsx",
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
