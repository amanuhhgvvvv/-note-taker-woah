import streamlit as st
import pandas as pd
from pathlib import Path
import os 

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
        # jika file sudah ada, pastikan sheet baru ikut ditambahkan (tanpa menggunakan cache)
        try:
            all_sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={'tanggal': str})
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
@st.cache_data # Menggunakan cache untuk performa
def read_all_sheets(path: Path):
    # Memaksa kolom 'tanggal' dibaca sebagai string untuk menghindari error konversi dengan baris 'Rata-rata'
    return pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={'tanggal': str})

def save_all_sheets(dfs: dict, path: Path):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df = df.reindex(columns=COLUMNS)
            df.to_excel(writer, sheet_name=sheet, index=False)

# ----------------------------
# Form input
# ----------------------------
st.markdown("Isi data pengukuran di bawah ini:")

# Menggunakan session_state untuk lokasi
if 'lokasi' not in st.session_state:
    st.session_state['lokasi'] = SHEET_NAMES[0]

tanggal = st.date_input("Tanggal pengukuran:", pd.Timestamp.now())
lokasi = st.selectbox("Lokasi pengukuran:", SHEET_NAMES, index=SHEET_NAMES.index(st.session_state['lokasi']))
st.session_state['lokasi'] = lokasi

ph = st.number_input("pH (mis. 7.2)", min_value=0.0, max_value=14.0, value=7.0, format="%.3f")
debit = st.number_input("Debit (mis. L/detik)", min_value=0.0, value=0.0, format="%.3f")

if st.button("Simpan data"):
    # Clear cache sebelum membaca data
    read_all_sheets.clear() 
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_loc = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))

    # tambahkan data harian baru
    new_row = {
        "tanggal": tanggal.strftime('%Y-%m-%d %H:%M:%S'), # Simpan tanggal sebagai string terformat
        "pH": float(ph),
        "debit": float(debit),
        "ph_rata_rata_bulan": None
    }
    df_loc = pd.concat([df_loc, pd.DataFrame([new_row])], ignore_index=True)

    # ---- Hitung rata-rata bulanan ----
    # Data yang akan dihitung rata-rata adalah yang BUKAN string "Rata-rata"
    df_data = df_loc[~df_loc["tanggal"].astype(str).str.contains('Rata-rata', na=False)].copy()
    
    # Konversi tanggal ke datetime hanya untuk perhitungan
    df_data["tanggal_dt"] = pd.to_datetime(df_data["tanggal"], errors="coerce")
    df_data = df_data.dropna(subset=['tanggal_dt']) # Hapus baris yang gagal konversi
    
    if not df_data.empty:
        df_data["bulan"] = df_data["tanggal_dt"].dt.month
        df_data["tahun"] = df_data["tanggal_dt"].dt.year
    
        avg_df = (
            df_data.groupby(["tahun", "bulan"], as_index=False)["pH"]
            .mean()
            .round(3)
            .rename(columns={"pH": "ph_rata_rata_bulan"})
        )
    
        # Ambil kembali data harian (yang sudah jadi string)
        df_loc_new = df_data[COLUMNS].copy()
    
        # Tambahkan baris rata-rata tiap bulan
        for _, row in avg_df.iterrows():
            rata_row = {
                "tanggal": f"Rata-rata {row['bulan']:02d}/{row['tahun']}",
                "pH": None,
                "debit": None,
                "ph_rata_rata_bulan": row["ph_rata_rata_bulan"]
            }
            df_loc_new = pd.concat([df_loc_new, pd.DataFrame([rata_row])], ignore_index=True)
        
        df_loc = df_loc_new
    else:
         df_loc = df_data[COLUMNS].copy()

    # simpan lagi ke dict & file
    all_sheets[lokasi] = df_loc
    save_all_sheets(all_sheets, EXCEL_PATH)

    st.success(f"Data tersimpan di sheet '{lokasi}' — tanggal {tanggal.strftime('%Y-%m-%d')}")
    st.rerun() # Paksa rerun untuk update preview

# ----------------------------
# Preview data
# ----------------------------
st.markdown("---")
st.subheader("Preview data lokasi")
try:
    read_all_sheets.clear()
    all_sheets = read_all_sheets(EXCEL_PATH)
    df_preview = all_sheets.get(lokasi, pd.DataFrame(columns=COLUMNS))
    
    # Pisahkan baris data harian dan rata-rata untuk sorting
    df_data_rows = df_preview[~df_preview["tanggal"].astype(str).str.contains('Rata-rata', na=False)].copy()
    df_avg_rows = df_preview[df_preview["tanggal"].astype(str).str.contains('Rata-rata', na=False)].copy()
    
    # Sortir data harian
    df_data_rows['tanggal_sort'] = pd.to_datetime(df_data_rows['tanggal'], errors='coerce')
    df_data_rows = df_data_rows.sort_values('tanggal_sort', ascending=False).drop(columns=['tanggal_sort'])
    
    df_preview_sorted = pd.concat([df_data_rows.reset_index(drop=True), df_avg_rows.reset_index(drop=True)])

    if df_preview_sorted.empty:
        st.info("Belum ada data untuk lokasi ini.")
    else:
        st.dataframe(df_preview_sorted.reset_index(drop=True), hide_index=True)
        
except Exception as e:
    st.error(f"Gagal membaca/menampilkan file Excel: {e}")

# ----------------------------
# Tombol download file Excel gabungan + LOGIKA HAPUS DATA
# ----------------------------
st.markdown("---")
st.subheader("Download file Excel gabungan")

if EXCEL_PATH.exists():
    with open(EXCEL_PATH, "rb") as f:
        data_bytes = f.read()
    
    # Gunakan session state untuk melacak apakah tombol download baru saja ditekan
    if 'download_clicked' not in st.session_state:
        st.session_state['download_clicked'] = False

    download_button = st.download_button(
        label="Download file Excel (semua lokasi)",
        data=data_bytes,
        file_name="ph_debit_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        on_click=lambda: st.session_state.update(download_clicked=True)
    )

    # 👇👇👇 LOGIKA HAPUS DATA SETELAH DOWNLOAD BERHASIL 👇👇👇
    if st.session_state['download_clicked']:
        # Reset flag agar tidak loop
        st.session_state['download_clicked'] = False 

        if EXCEL_PATH.exists():
            try:
                EXCEL_PATH.unlink() # Menghapus file yang sudah diunduh
                initialize_excel(EXCEL_PATH) # Membuat ulang file kosong

                read_all_sheets.clear() # Membersihkan cache data
                st.success("✅ File Excel telah diunduh, dan semua data pencatatan telah *dihapus* dari aplikasi (file di server direset).")
                
                # Paksa Streamlit me-muat ulang untuk menampilkan tabel kosong
                st.rerun() 
                
            except Exception as e:
                st.error(f"Gagal menghapus dan mereset file Excel: {e}")

else:
    st.warning("File Excel belum tersedia di server untuk diunduh.")

st.info("File disimpan di server sebagai ph_debit_data.xlsx. Data akan *dikosongkan* setelah Anda menekan tombol Download.")
