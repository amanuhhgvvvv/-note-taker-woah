import streamlit as st
import pandas as pd
from pathlib import Path
import os # Import os untuk operasi file jika pathlib.unlink() tidak berfungsi (meskipun pathlib lebih disukai)

# ----------------------------
# Konfigurasi / Nama file
# ----------------------------
EXCEL_PATH = Path("ph_debit_data.xlsx")
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
COLUMNS = ["tanggal", "pH", "debit", "ph_rata_rata_bulan"]

st.set_page_config(page_title="Pencatatan pH & Debit Air", layout="centered")
st.title("📊 Pencatatan pH dan Debit Air")

# ----------------------------
# Inisialisasi file Excel
# ----------------------------
def initialize_excel(path: Path):
    """Membuat atau memastikan file Excel ada dengan semua sheet yang diperlukan."""
    try:
        if not path.exists():
            # Jika file belum ada, buat semua sheet baru
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for sheet in SHEET_NAMES:
                    df = pd.DataFrame(columns=COLUMNS)
                    df.to_excel(writer, sheet_name=sheet, index=False)
        else:
            # Jika file sudah ada, pastikan sheet baru ikut ditambahkan (jika ada sheet baru)
            # Catatan: Mode 'a' tidak bisa diandalkan untuk 'openpyxl' dalam skenario ini.
            # Cara paling aman adalah membaca semua, lalu menulis ulang semua.
            all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
            
            # Tambahkan sheet yang hilang
            sheets_to_add = [sheet for sheet in SHEET_NAMES if sheet not in all_sheets]
            
            if sheets_to_add:
                with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                    for sheet in sheets_to_add:
                        df = pd.DataFrame(columns=COLUMNS)
                        df.to_excel(writer, sheet_name=sheet, index=False)
                        
    except Exception as e:
        st.error(f"Error saat inisialisasi file Excel: {e}")


initialize_excel(EXCEL_PATH)

# ----------------------------
# Utility: baca & simpan sheet
# ----------------------------
@st.cache_data
def read_all_sheets(path: Path):
    """Membaca semua sheet dari file Excel."""
    try:
        return pd.read_excel(path, sheet_name=None, engine="openpyxl")
    except Exception as e:
        st.error(f"Gagal membaca file Excel: {e}")
        return {}


def save_all_sheets(dfs: dict, path: Path):
    """Menyimpan semua DataFrame ke file Excel."""
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet, df in dfs.items():
                # Pastikan urutan kolom sesuai standar
                df = df.reindex(columns=COLUMNS)
                df.to_excel(writer, sheet_name=sheet, index=False)
    except Exception as e:
        st.error(f"Gagal menyimpan data ke file Excel: {e}")

# ----------------------------
# Form input
# ----------------------------
st.markdown("Isi data pengukuran di bawah ini:")

# Ambil data lokasi saat ini untuk preview
all_sheets_current = read_all_sheets(EXCEL_PATH)
lokasi_default = SHEET_NAMES[0]

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES, index=SHEET_NAMES.index(st.session_state.get('lokasi', lokasi_default)))

st.session_state['lokasi'] = lokasi # Simpan lokasi terpilih

ph = st.number_input("pH (mis. 7.2)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
debit = st.number_input("Debit (mis. L/detik)", min_value=0.0, value=0.0, format="%.3f")

if st.button("Simpan data"):
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))

    # tambahkan data harian baru
    new_row = {
        "tanggal": tanggal,
        "pH": float(ph),
        "debit": float(debit),
        "ph_rata_rata_bulan": None
    }
    df_loc = pd.concat([df_loc, pd.DataFrame([new_row])], ignore_index=True)

    # pastikan tanggal datetime
    df_loc["tanggal"] = pd.to_datetime(df_loc["tanggal"], errors="coerce")

    # ---- Hitung rata-rata bulanan ----
    # Filter data harian (yang ph_rata_rata_bulan-nya adalah NaN)
    df_data = df_loc[pd.isna(df_loc["ph_rata_rata_bulan"])].copy() 
    
    # Hitung rata-rata hanya jika ada data harian
    if not df_data.empty:
        df_data["bulan"] = df_data["tanggal"].dt.month
        df_data["tahun"] = df_data["tanggal"].dt.year
        
        avg_df = (
            df_data.groupby(["tahun", "bulan"], as_index=False)["pH"]
            .mean()
            .round(3)
            .rename(columns={"pH": "ph_rata_rata_bulan"})
        )
        
        # Buang semua baris rata-rata lama (yang tidak punya tanggal datetime)
        # dan ambil kembali hanya data harian yang valid (punya tanggal datetime)
        df_loc = df_loc[df_loc["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].copy()
        
        # Hapus kolom bulan dan tahun sementara
        if 'bulan' in df_loc.columns:
            df_loc = df_loc.drop(columns=['bulan', 'tahun'], errors='ignore')
            
        # Tambahkan baris rata-rata tiap bulan
        for _, row in avg_df.iterrows():
            rata_row = {
                "tanggal": f"Rata-rata {row['bulan']:02d}/{row['tahun']}", # Format bulan jadi 2 digit
                "pH": None,
                "debit": None,
                "ph_rata_rata_bulan": row["ph_rata_rata_bulan"]
            }
            df_loc = pd.concat([df_loc, pd.DataFrame([rata_row])], ignore_index=True)
    else:
        # Jika tidak ada data harian, pastikan df_loc tetap hanya berisi baris non-rata-rata
        df_loc = df_loc[df_loc["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].copy()


    # simpan lagi ke dict & file
    all_sheets[lokasi] = df_loc
    save_all_sheets(all_sheets, EXCEL_PATH)

    st.success(f"✅ Data tersimpan di sheet '{lokasi}' — tanggal {tanggal.strftime('%Y-%m-%d')}")
    # Bersihkan cache agar preview data terupdate
    read_all_sheets.clear()
    st.experimental_rerun()


# ----------------------------
# Preview data
# ----------------------------
st.markdown("---")
st.subheader(f"Preview Data Lokasi: {lokasi}")
try:
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_preview = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))
    
    # Lakukan sorting berdasarkan kolom 'tanggal' (khusus baris yang punya format tanggal)
    df_data_rows = df_preview[df_preview["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].sort_values("tanggal", ascending=False)
    df_avg_rows = df_preview[~df_preview["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].copy()
    
    # Gabungkan kembali
    df_preview_sorted = pd.concat([df_data_rows.reset_index(drop=True), df_avg_rows.reset_index(drop=True)])

    if df_preview_sorted.empty:
        st.info("ℹ Belum ada data untuk lokasi ini.")
    else:
        # Tampilkan DataFrame, buang index pandas
        st.dataframe(df_preview_sorted.reset_index(drop=True), hide_index=True) 
        
except Exception as e:
    st.error(f"Gagal membaca/menampilkan file Excel: {e}")

# ----------------------------
# Tombol download file Excel gabungan (dengan fungsi hapus data setelah download)
# ----------------------------
st.markdown("---")
st.subheader("⬇ Download file Excel gabungan")

if EXCEL_PATH.exists():
    with open(EXCEL_PATH, "rb") as f:
        data_bytes = f.read()

    download_button = st.download_button(
        label="Download file Excel (semua lokasi)",
        data=data_bytes,
        file_name="ph_debit_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key='download_excel_button'
    )

    # 👇👇👇 LOGIKA HAPUS DATA SETELAH DOWNLOAD 👇👇👇
    if download_button:
        # Hapus file yang ada
        if EXCEL_PATH.exists():
            try:
                EXCEL_PATH.unlink() # Menghapus file yang sudah ada
                
                # Kemudian inisialisasi ulang, membuat file dengan sheet kosong
                initialize_excel(EXCEL_PATH) 
                
                # Bersihkan cache dan paksa refresh Streamlit untuk menampilkan tabel kosong
                read_all_sheets.clear()
                st.success("✅ File Excel telah diunduh. Semua data pencatatan telah *dihapus* dari aplikasi (file Excel di server telah direset).")
                st.experimental_rerun()
                
            except Exception as e:
                st.error(f"Gagal menghapus dan mereset file Excel: {e}")

else:
    st.warning("File Excel belum tersedia di server untuk diunduh.")

st.info("File disimpan di server sebagai ph_debit_data.xlsx. Setelah diunduh, file di server akan *dikosongkan*.")
