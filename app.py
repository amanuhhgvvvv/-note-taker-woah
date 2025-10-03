import streamlit as st
import pandas as pd
from pathlib import Path
import os # Diperlukan untuk beberapa operasi Path, meskipun Path.unlink() lebih disukai

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
    if not path.exists():
        # jika file belum ada, buat semua sheet baru
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet in SHEET_NAMES:
                df = pd.DataFrame(columns=COLUMNS)
                df.to_excel(writer, sheet_name=sheet, index=False)
    else:
        # jika file sudah ada, pastikan sheet baru ikut ditambahkan
        # Menggunakan st.cache_data untuk membaca (jika sudah ada)
        try:
            all_sheets = read_all_sheets.clear()
            all_sheets = read_all_sheets(path)
        except:
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
@st.cache_data # Menggunakan cache untuk kecepatan baca
def read_all_sheets(path: Path):
    return pd.read_excel(path, sheet_name=None, engine="openpyxl")

def save_all_sheets(dfs: dict, path: Path):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df = df.reindex(columns=COLUMNS)
            df.to_excel(writer, sheet_name=sheet, index=False)

# ----------------------------
# Form input
# ----------------------------
st.markdown("Isi data pengukuran di bawah ini:")

# Menggunakan session_state untuk mempertahankan lokasi yang dipilih
if 'lokasi' not in st.session_state:
    st.session_state['lokasi'] = SHEET_NAMES[0]
    
tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES, index=SHEET_NAMES.index(st.session_state['lokasi']))
st.session_state['lokasi'] = lokasi # Update state

ph = st.number_input("pH (mis. 7.2)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
debit = st.number_input("Debit (mis. L/detik)", min_value=0.0, value=0.0, format="%.3f")

if st.button("Simpan data"):
    # Clear cache sebelum membaca data untuk memastikan data terbaru
    read_all_sheets.clear() 
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
    df_data = df_loc[pd.isna(df_loc["ph_rata_rata_bulan"])].copy()  # hanya data harian
    
    if not df_data.empty:
        df_data["bulan"] = df_data["tanggal"].dt.month
        df_data["tahun"] = df_data["tanggal"].dt.year
    
        avg_df = (
            df_data.groupby(["tahun", "bulan"], as_index=False)["pH"]
            .mean()
            .round(3)
            .rename(columns={"pH": "ph_rata_rata_bulan"})
        )
    
        # Ambil kembali hanya baris data harian yang valid (punya tanggal datetime)
        df_loc = df_loc[df_loc["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].copy()
    
        # Tambahkan baris rata-rata tiap bulan
        for _, row in avg_df.iterrows():
            rata_row = {
                "tanggal": f"Rata-rata {row['bulan']:02d}/{row['tahun']}",
                "pH": None,
                "debit": None,
                "ph_rata_rata_bulan": row["ph_rata_rata_bulan"]
            }
            df_loc = pd.concat([df_loc, pd.DataFrame([rata_row])], ignore_index=True)
    else:
        # Jika tidak ada data harian, pastikan df_loc hanya berisi data harian
        df_loc = df_loc[df_loc["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].copy()

    # simpan lagi ke dict & file
    all_sheets[lokasi] = df_loc
    save_all_sheets(all_sheets, EXCEL_PATH)

    st.success(f"Data tersimpan di sheet '{lokasi}' — tanggal {tanggal.strftime('%Y-%m-%d')}")
    # Force rerun agar preview langsung terupdate
    st.rerun()


# ----------------------------
# Preview data
# ----------------------------
st.markdown("---")
st.subheader("Preview data lokasi")
try:
    # Clear cache sebelum preview
    read_all_sheets.clear() 
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_preview = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))
    
    # Sortir data harian
    df_data_rows = df_preview[df_preview["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].sort_values("tanggal", ascending=False)
    # Pisahkan baris rata-rata
    df_avg_rows = df_preview[~df_preview["tanggal"].apply(lambda x: isinstance(x, pd.Timestamp))].copy()
    # Gabungkan kembali
    df_preview_sorted = pd.concat([df_data_rows.reset_index(drop=True), df_avg_rows.reset_index(drop=True)])

    if df_preview_sorted.empty:
        st.info("Belum ada data untuk lokasi ini.")
    else:
        st.dataframe(df_preview_sorted.reset_index(drop=True), hide_index=True)
        
except Exception as e:
    st.error(f"Gagal membaca file Excel: {e}")

# ----------------------------
# Tombol download file Excel gabungan
# ----------------------------
st.markdown("---")
st.subheader("Download file Excel gabungan")

if EXCEL_PATH.exists():
    with open(EXCEL_PATH, "rb") as f:
        data_bytes = f.read()

    download_button_clicked = st.download_button(
        label="Download file Excel (semua lokasi)",
        data=data_bytes,
        file_name="ph_debit_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key='download_excel_button'
    )

    # 👇👇👇 KODE BARU UNTUK MENGHAPUS DATA SETELAH DI-DOWNLOAD 👇👇👇
    if 'download_status' not in st.session_state:
        st.session_state['download_status'] = False

    # Logika ini akan berjalan pada rerun setelah tombol ditekan
    if download_button_clicked:
        # Pengecekan status untuk menghindari eksekusi berulang yang tidak perlu
        if not st.session_state['download_status']:
            st.session_state['download_status'] = True
            
            # 1. Hapus file yang ada
            if EXCEL_PATH.exists():
                try:
                    EXCEL_PATH.unlink() # Menghapus file
                    
                    # 2. Inisialisasi ulang, membuat file dengan sheet kosong
                    initialize_excel(EXCEL_PATH) 
                    
                    # 3. Bersihkan cache dan tampilkan pesan sukses
                    read_all_sheets.clear()
                    st.success("✅ File Excel telah diunduh. Semua data pencatatan di aplikasi (file di server) telah *dihapus*.")
                    
                    # Reset status dan paksa muat ulang (rerun)
                    st.session_state['download_status'] = False
                    st.rerun() 
                    
                except Exception as e:
                    st.error(f"Gagal menghapus dan mereset file Excel: {e}")

else:
    st.warning("File Excel belum tersedia di server untuk diunduh.")

st.info("File disimpan di server sebagai ph_debit_data.xlsx. Data akan dikosongkan setelah Anda menekan tombol Download.")
