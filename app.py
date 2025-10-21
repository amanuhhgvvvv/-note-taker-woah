import streamlit as st
import pandas as pd
import numpy as np
import datetime
import time
import gspread
import altair as alt 
from google.oauth2.service_account import Credentials
# import io # Tidak diperlukan lagi untuk CSV

# ----------------------------
# KONEKSI GOOGLE SHEETS
# (Tidak ada perubahan pada koneksi)
# ----------------------------
@st.cache_resource
def init_gsheets_connection():
    """Menginisialisasi koneksi gspread menggunakan st.secrets."""
    try:
        # Menggunakan private_key dari secrets.toml
        # Mengganti \n literal menjadi karakter newline yang sebenarnya
        private_key = st.secrets["private_key"].replace('\\n', '\n') 
        
        creds_dict = {
            "type": "service_account",
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"], 
            "private_key": private_key,
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": st.secrets["client_x509_cert_url"]
        }
        
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        return client
        
    except Exception as e:
        # Memberikan pesan error yang lebih informatif jika kredensial salah
        st.error(f"❌ Gagal inisialisasi koneksi Google Sheets. Pastikan 'secrets.toml' sudah benar dan Service Account sudah diberi akses Edit pada Google Sheet. Error: {e}")
        return None

# Inisialisasi koneksi
client = init_gsheets_connection()

# Hentikan eksekusi jika koneksi gagal
if client is None:
    # Memastikan tidak ada eksekusi lebih lanjut
    st.stop() 

# Ambil SHEET_ID
try:
    SHEET_ID = st.secrets["SHEET_ID"]
except Exception as e:
    st.error(f"❌ Gagal mengambil SHEET_ID dari secrets. Periksa 'secrets.toml'. Error: {e}")
    st.stop()

# Daftar nama sheet
SHEET_NAMES = [
    "Power Plant", "Plan Garage", "Drain A", "Drain B", "Drain C", 
    "WTP", "Coal Yard", "Domestik", "Limestone", "Clay Laterite", 
    "Silika", "Kondensor PLTU"
]

# Konfigurasi Halaman Streamlit
st.set_page_config(page_title="Monitoring Air", layout="centered")
st.title("📊 Monitoring Air")


# ----------------------------
# FUNGSI UTAMA 
# ----------------------------

@st.cache_data(show_spinner=False) 
def get_worksheet_name(lokasi):
    """Mengecek nama worksheet. Menambahkan penanganan spasi jika ada."""
    try:
        # Pengecekan spasi di akhir nama sheet hanya untuk kasus 'WTP '
        if lokasi == "WTP":
            ws_titles = [ws.title for ws in client.open_by_key(SHEET_ID).worksheets()]
            if "WTP " in ws_titles:
                return "WTP "  # Jika sheet asli memiliki spasi di akhir
        return lokasi
    except Exception:
        # Fallback jika gagal membuka spreadsheet
        return lokasi 

@st.cache_data(ttl=60) 
def simpan_data_ke_sheet(lokasi, hari, pH, suhu, debit):
    """Menyimpan data ke worksheet (Baris 3, 4, 5)"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Menggunakan nama worksheet yang sesuai
        ws_name = get_worksheet_name(lokasi) 
        worksheet = spreadsheet.worksheet(ws_name)
        
        # MAPPING BARIS SESUAI STRUKTUR SPREADSHEET (Baris 3=pH, Baris 4=suhu, Baris 5=debit)
        mapping = {
            "pH": 3,      # Baris 3
            "suhu": 4,    # Baris 4
            "debit": 5    # Baris 5
        }
        
        # Kolom untuk hari tertentu (B=hari1, C=hari2, ..., AF=hari31)
        kolom = hari + 1  # Hari 1 → Kolom B (index 2), dst.
        
        # Update data dalam batch
        worksheet.update_cell(mapping["pH"], kolom, pH)
        worksheet.update_cell(mapping["suhu"], kolom, suhu)
        worksheet.update_cell(mapping["debit"], kolom, debit)
        
        return True
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan data ke Google Sheets. Pastikan 'SHEET_ID' benar dan nama sheet '{lokasi}' ada. Error: {str(e)}")
        return False

# FUNGSI BARU: Hapus SELURUH Data Bulanan di Google Sheet (Range B3:AF5)
def hapus_data_satu_bulan(lokasi):
    """Menghapus seluruh data bulanan (B3:AF5) di Google Sheet dengan string kosong."""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        ws_name = get_worksheet_name(lokasi) 
        worksheet = spreadsheet.worksheet(ws_name)
        
        # Kirim list of lists of empty strings (3 baris x 31 kolom)
        empty_data = [[''] * 31 for _ in range(3)] 
        
        # Update range B3:AF5
        worksheet.update('B3:AF5', empty_data)
        
        return True
    except Exception as e:
        # Jika penghapusan gagal
        st.error(f"❌ Gagal menghapus data dari Google Sheets. Error: {str(e)}")
        return False


@st.cache_data(ttl=60) 
def baca_data_dari_sheet(lokasi):
    """Membaca data dari worksheet (Range B3:AF5)"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Menggunakan nama worksheet yang sesuai
        ws_name = get_worksheet_name(lokasi)
        worksheet = spreadsheet.worksheet(ws_name)
        
        # RANGE: Baca dari baris 3-5 (Kolom B sampai AF)
        data_range = "B3:AF5"  
        data = worksheet.get(data_range)
        
        if not data:
            return pd.DataFrame()
        
        # Proses data
        today = datetime.date.today()
        current_month = today.month
        current_year = today.year
        
        # Buat DataFrame template untuk 31 hari
        df = pd.DataFrame()
        df['Hari'] = list(range(1, 32))
        df['Tanggal'] = [f"{current_year}-{current_month:02d}-{day:02d}" for day in range(1, 32)]
        
        # Inisialisasi kolom
        df['pH'] = [np.nan] * 31
        df['Suhu (°C)'] = [np.nan] * 31
        df['Debit (l/d)'] = [np.nan] * 31

        def safe_float_convert(val):
            """Mengkonversi nilai ke float, mengembalikan NaN jika gagal."""
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str) and val.strip() != '':
                try:
                    # Mengganti koma dengan titik jika ada, untuk konversi float
                    return float(val.replace(',', '.')) 
                except ValueError:
                    return np.nan
            return np.nan
            
        # Ambil data pH (index 0 di data/baris 3 di sheet)
        if len(data) >= 1:
            for i, val in enumerate(data[0][:31]):
                df.at[i, 'pH'] = safe_float_convert(val)
                
        # Ambil data Suhu (index 1 di data/baris 4 di sheet)
        if len(data) >= 2:
            for i, val in enumerate(data[1][:31]):
                df.at[i, 'Suhu (°C)'] = safe_float_convert(val)
                
        # Ambil data Debit (index 2 di data/baris 5 di sheet)
        if len(data) >= 3:
            for i, val in enumerate(data[2][:31]):
                df.at[i, 'Debit (l/d)'] = safe_float_convert(val)
        
        return df
        
    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"⚠ Worksheet '{lokasi}' tidak ditemukan di Spreadsheet Anda.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Gagal membaca data dari {lokasi}. Periksa Izin Berbagi Sheet. Error: {e}")
        return pd.DataFrame()

# FUNGSI UNTUK MENGUNDUH DATA MENTAH DENGAN STRUKTUR SPREADSHEET
def baca_data_raw_sheet_untuk_unduh(lokasi):
    """
    Membaca data MENTAH dari Google Sheet (Range A2:AF5) 
    untuk mempertahankan struktur Baris (Parameter) dan Kolom (Hari).
    """
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        ws_name = get_worksheet_name(lokasi)
        worksheet = spreadsheet.worksheet(ws_name)
        
        # Range A2:AF5 mencakup label hari (Baris 2) dan label parameter (Kolom A)
        data = worksheet.get("A2:AF5") 
        
        if not data or len(data) < 2:
            return pd.DataFrame() 

        # Baris pertama (data[0]) adalah header kolom: ['A2', 'B2', ..., 'AF2']
        cols = data[0].copy()
        
        # Jika sel A2 (index 0) kosong di Sheet, kita paksa beri nama 'Parameter'
        if not cols or not cols[0]:
            cols[0] = 'Parameter' 
        
        # Sisa baris adalah data: [['pH', 7.0, 7.1, ...], ['Suhu', 25, 26, ...], ...]
        raw_rows = data[1:] 
        
        # Buat DataFrame
        df_raw = pd.DataFrame(raw_rows, columns=cols)
        
        # Atur kolom pertama ('Parameter') sebagai index baris
        df_raw = df_raw.set_index(df_raw.columns[0])
        # df_raw.index.name = None # Hapus nama index (agar terlihat seperti di Sheet)
        
        return df_raw
        
    except Exception as e:
        # st.error(f"❌ Gagal membaca data mentah untuk unduhan. Error: {e}") # Tidak perlu ditampilkan
        return pd.DataFrame()

# FUNGSI BARU: Menggabungkan data dari semua lokasi ke dalam satu DataFrame
def baca_semua_data_untuk_unduh():
    """Mengambil dan menggabungkan data mentah dari semua lokasi ke dalam satu DataFrame."""
    all_data = []
    
    # Ambil tanggal hari ini untuk label arsip
    today_date = datetime.date.today()
    
    for lokasi in SHEET_NAMES:
        try:
            # Menggunakan fungsi pembaca data mentah
            df_lokasi = baca_data_raw_sheet_untuk_unduh(lokasi)
            
            if not df_lokasi.empty:
                # Tambahkan kolom identitas Lokasi di depan
                df_lokasi.insert(0, 'Lokasi', lokasi)
                df_lokasi.insert(1, 'Bulan/Tahun', today_date.strftime('%Y-%m'))
                
                all_data.append(df_lokasi)
        except Exception as e:
            # Lanjutkan ke sheet berikutnya jika ada error
            print(f"Gagal membaca data dari lokasi {lokasi}: {e}") 
            continue
            
    if all_data:
        # Menggabungkan semua DataFrame
        df_gabungan = pd.concat(all_data)
        
        # Ubah index menjadi kolom 'Parameter' sebelum unduh
        df_gabungan = df_gabungan.reset_index().rename(columns={'index': 'Parameter'})
        
        return df_gabungan
    else:
        return pd.DataFrame()


# ==================== APLIKASI UTAMA ====================

# Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_lokasi = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=SHEET_NAMES,
    index=0 
)

# Inisialisasi session state untuk konfirmasi hapus data
if 'confirm_clear_data_monthly' not in st.session_state:
    st.session_state['confirm_clear_data_monthly'] = False
if 'last_selected_lokasi' not in st.session_state:
    st.session_state['last_selected_lokasi'] = selected_lokasi

# Muat data existing (dengan cache)
current_df = baca_data_dari_sheet(selected_lokasi)

# Dapatkan hari ini untuk penamaan file download
today_date = datetime.date.today()
today_day = today_date.day

# Tampilkan Status Lokasi
st.subheader(f"📍 Lokasi: {selected_lokasi}")

# --- Bagian 1: Input Data Baru ---
st.markdown("---")
st.header("📝 Catat Data Baru")


with st.form("input_form"):
    
    # Pilih Hari
    input_day = st.selectbox(
        "Pilih *Hari* untuk Pencatatan:",
        options=list(range(1, 32)),
        index=today_day - 1
    )
    
    st.caption(f"Tanggal lengkap yang akan dicatat: *{today_date.year}-{today_date.month:02d}-{input_day:02d}*")

    # Ambil nilai existing jika ada
    existing_data = None
    if not current_df.empty and input_day <= len(current_df):
        existing_data = current_df.iloc[input_day - 1]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Menangani nilai NaN agar number_input tidak error
        ph_value = existing_data['pH'] if existing_data is not None and pd.notna(existing_data['pH']) else 7.0
        input_ph = st.number_input(
            "Nilai pH", 
            min_value=0.0, max_value=14.0, 
            value=ph_value,
            step=0.1,
            format="%.1f"
        )
    with col2:
        suhu_value = existing_data['Suhu (°C)'] if existing_data is not None and pd.notna(existing_data['Suhu (°C)']) else 29.0
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0, 
            value=suhu_value,
            step=0.1,
            format="%.1f"
        )
    with col3:
        debit_value = existing_data['Debit (l/d)'] if existing_data is not None and pd.notna(existing_data['Debit (l/d)']) else 75.0
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0,
            value=debit_value,
            step=0.1,
            format="%.1f"
        )
        
    submitted = st.form_submit_button("💾 Simpan Data ke Google Sheets", type="primary")
    
    if submitted:
        # Periksa semua kolom apakah kosong (0.0 bisa jadi nilai valid)
        if input_ph is None or input_suhu is None or input_debit is None:
              st.warning("⚠ Harap isi semua kolom data.")
        else:
            with st.spinner("Menyimpan data..."):
                success_save = simpan_data_ke_sheet(selected_lokasi, input_day, input_ph, input_suhu, input_debit)
                
                # Hanya me-rerun jika berhasil disimpan
                if success_save:
                    st.cache_data.clear()
                    time.sleep(1.5)
                    st.rerun()

# --- Bagian 2: Tampilkan Data Existing ---
st.markdown("---")
st.subheader("📋 Data Saat Ini")

if not current_df.empty:
    # Filter kolom untuk display
    display_columns = ['Hari', 'Tanggal', 'pH', 'Suhu (°C)', 'Debit (l/d)']
    # Ganti nilai NaN dengan string kosong untuk tampilan bersih
    display_df = current_df[display_columns].replace({np.nan: ''})
    
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        height=400
    )
    
    # Tampilkan statistik sederhana
    valid_ph_entries = current_df['pH'].count()
    st.metric("Total Hari Tercatat (Bulan Ini)", f"{valid_ph_entries}/31 hari")
    
else:
    st.info("Belum ada data untuk lokasi ini.")

# --- Bagian 3: Visualisasi Data (Altair) ---
st.markdown("---")
st.header("📈 Tren Data Bulanan")

if not current_df.empty and current_df['pH'].notna().any():
    # Mengubah format data dari wide ke long untuk Altair
    df_melted = current_df.melt(
        id_vars=['Hari', 'Tanggal'],
        value_vars=['pH', 'Suhu (°C)', 'Debit (l/d)'],
        var_name='Parameter',
        value_name='Nilai'
    ).dropna(subset=['Nilai'])
    
    # Konversi Hari menjadi string kategori untuk sumbu X agar tidak ada gap di grafik
    df_melted['Hari_str'] = df_melted['Hari'].astype(str)
    
    # Buat Chart interaktif
    chart = alt.Chart(df_melted).mark_line(point=True).encode(
        # Sumbu X: Hari (sebagai string)
        x=alt.X('Hari_str', title='Hari ke-', sort=list(map(str, range(1, 32)))),
        # Sumbu Y: Nilai
        y=alt.Y('Nilai', title='Nilai Parameter'),
        # Warna: Berdasarkan Parameter
        color=alt.Color('Parameter', title='Parameter'),
        # Tooltip
        tooltip=['Tanggal', 'Parameter', 'Nilai']
    ).properties(
        #title=f"Tren pH, Suhu, dan Debit untuk {selected_lokasi}" # Judul dipindah ke atas
    ).interactive() # Zoom dan pan
    
    # Pisahkan chart per parameter (Faceted Chart)
    chart_faceted = chart.facet(
        column=alt.Column('Parameter', header=alt.Header(titleOrient="bottom", labelOrient="bottom")),
        columns=3 # Tampilkan 3 kolom
    ).resolve_scale(
        y='independent' # Skala Y yang independen untuk setiap parameter
    )
    
    st.altair_chart(chart_faceted, use_container_width=True)

else:
    st.info("Tidak cukup data (pH, Suhu, atau Debit) untuk menampilkan tren bulan ini.")


# --- Bagian 4: Arsipkan & Hapus Data Bulan Ini ---
st.markdown("---")
st.header("📦 Arsipkan & Kosongkan Data Bulanan")
st.info("Setelah data bulanan Anda **diarsip dan diunduh** menggunakan tombol di bawah, gunakan tombol HAPUS untuk mengosongkan data dari Spreadsheet, siap untuk bulan berikutnya.")

# Kontainer untuk tombol Download & Hapus
col_download, col_clear = st.columns([1, 1.5])

# Tombol Unduh Global (Semua Lokasi)
with col_download:
    # Ambil data dari semua lokasi dan gabungkan
    df_all_data = baca_semua_data_untuk_unduh()
    
    if not df_all_data.empty:
        # Konversi DataFrame gabungan ke CSV. Index=False karena index sudah diubah jadi kolom 'Parameter'.
        # Diberi separator (sep=';') untuk kompatibilitas yang lebih baik dengan Excel di region Indonesia.
        csv_data_all = df_all_data.to_csv(index=False, sep=';').encode('utf-8')

        st.download_button(
            label="⬇️ Unduh Semua Lokasi (CSV)", 
            data=csv_data_all,
            file_name=f"MonitoringAir_SEMUA_LOKASI_{today_date.strftime('%Y%m')}.csv", 
            mime="text/csv", 
            type="primary",
            use_container_width=True
        )
        st.caption("Mengunduh data mentah dari semua sheet sekaligus.")
    else:
        st.warning("Tidak ada data dari semua lokasi untuk diunduh.")


# Logika tombol hapus dengan konfirmasi 2 langkah (Hanya untuk lokasi yang dipilih)
with col_clear:
    if not current_df.empty:
        # Cek apakah konfirmasi sedang aktif
        is_confirming = st.session_state.get('confirm_clear_data_monthly', False)

        if st.button(
            f"🗑️ KOSONGKAN DATA {selected_lokasi}",
            # Ganti warna tombol saat mode konfirmasi
            type="secondary" if not is_confirming else "primary",
            key="clear_monthly_data_btn",
            use_container_width=True # Membuat tombol penuh lebar
        ):
            if is_confirming:
                # LANGKAH 2: Konfirmasi penghapusan
                with st.spinner(f"Menghapus seluruh data bulan ini dari {selected_lokasi}..."):
                    clear_success = hapus_data_satu_bulan(selected_lokasi)
                    
                    if clear_success:
                        st.session_state['confirm_clear_data_monthly'] = False # Reset confirmation
                        st.success(f"✅ Seluruh data {selected_lokasi} untuk bulan ini berhasil dikosongkan dari Google Sheets.")
                        st.cache_data.clear()
                        time.sleep(1.5)
                        st.rerun()
                        
            else:
                # LANGKAH 1: Meminta konfirmasi
                st.session_state['confirm_clear_data_monthly'] = True
                st.warning(f"❗ Anda yakin ingin menghapus **SEMUA** data bulanan **{selected_lokasi}**? Pastikan Anda **sudah mengarsipkannya**. Klik tombol **sekali lagi** untuk konfirmasi penghapusan.")
                st.rerun()
                
        # Tampilkan pesan konfirmasi jika aktif
        if is_confirming:
            st.warning("Menunggu konfirmasi klik kedua untuk menghapus...")
            
        # Reset konfirmasi jika pengguna mengganti lokasi saat konfirmasi aktif
        if selected_lokasi != st.session_state.get('last_selected_lokasi'):
            st.session_state['confirm_clear_data_monthly'] = False
        st.session_state['last_selected_lokasi'] = selected_lokasi

    else:
        st.info("Tidak ada data untuk dihapus di lokasi ini.")


st.caption("Aplikasi Monitoring Air | Pastikan akun layanan memiliki akses Edit.")
