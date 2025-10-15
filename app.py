import streamlit as st
import pandas as pd
import numpy as np
import datetime
import time
import gspread
import altair as alt
from google.oauth2.service_account import Credentials

# ----------------------------
# KONEKSI GOOGLE SHEETS
# ----------------------------
@st.cache_resource
def init_gsheets_connection():
    """Menginisialisasi koneksi gspread menggunakan st.secrets."""
    try:
        # REVISI PENTING: Menghapus .replace('\\n', '\n').strip() 
        # karena private_key di secrets.toml sekarang menggunakan tanda kutip tiga (""").
        private_key = st.secrets["private_key"] 
        
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
# FUNGSI UTAMA - DIBERSIHKAN & DIPERBAIKI
# ----------------------------

def get_worksheet_name(lokasi):
    """Mengecek nama worksheet. Menambahkan penanganan spasi jika ada."""
    # Mengatasi potensi perbedaan spasi pada nama sheet
    if lokasi == "WTP" and "WTP " in [ws.title for ws in client.open_by_key(SHEET_ID).worksheets()]:
        return "WTP "  # Jika sheet asli memiliki spasi di akhir
    return lokasi

@st.cache_data(ttl=60) # Cache data selama 60 detik untuk performa
def simpan_data_ke_sheet(lokasi, hari, pH, suhu, debit):
    """Menyimpan data ke worksheet - MAPPING BARIS DIPERBAIKI (Baris 3, 4, 5)"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Menggunakan nama worksheet yang sesuai
        ws_name = get_worksheet_name(lokasi) 
        worksheet = spreadsheet.worksheet(ws_name)
        
        # MAPPING BARIS SESUAI STRUKTUR SPREADSHEET (Baris 3=pH, Baris 4=suhu, Baris 5=debit)
        mapping = {
            "pH": 3,     # Baris 3
            "suhu": 4,    # Baris 4
            "debit": 5    # Baris 5
        }
        
        # Kolom untuk hari tertentu (B=hari1, C=hari2, ..., AF=hari31)
        kolom = hari + 1  # Hari 1 → Kolom B (index 2), dst.
        
        # Update data dalam batch
        worksheet.update_cell(mapping["pH"], kolom, pH)
        worksheet.update_cell(mapping["suhu"], kolom, suhu)
        worksheet.update_cell(mapping["debit"], kolom, debit)
        
        st.success(f"✅ Data berhasil disimpan/diperbarui di {lokasi} (Hari {hari})!")
        return True
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan data ke Google Sheets. Pastikan 'SHEET_ID' benar dan nama sheet '{lokasi}' ada. Error: {str(e)}")
        return False

@st.cache_data(ttl=60) # Cache data selama 60 detik
def baca_data_dari_sheet(lokasi):
    """Membaca data dari worksheet - MAPPING RANGE DIPERBAIKI (B3:AF5)"""
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Menggunakan nama worksheet yang sesuai
        ws_name = get_worksheet_name(lokasi)
        worksheet = spreadsheet.worksheet(ws_name)
        
        # RANGE DIPERBAIKI: Baca dari baris 3-5 (Kolom B sampai AF)
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
                    return float(val.replace(',', '.')) # Handle koma sebagai desimal
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
        st.warning(f"⚠️ Worksheet '{lokasi}' tidak ditemukan di Spreadsheet Anda.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Gagal membaca data dari {lokasi}. Periksa Izin Berbagi Sheet. Error: {e}")
        return pd.DataFrame()

# ==================== APLIKASI UTAMA ====================

# Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_lokasi = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=SHEET_NAMES,
    index=0 
)

# Muat data existing (dengan cache)
current_df = baca_data_dari_sheet(selected_lokasi)

# Tampilkan Status Lokasi
st.subheader(f"📍 Lokasi: {selected_lokasi}")

# --- Bagian 1: Input Data Baru ---
st.markdown("---")
st.header("📝 Catat Data Baru")

# Dapatkan hari ini untuk input default
today_date = datetime.date.today()
today_day = today_date.day

with st.form("input_form"):
    
    # Pilih Hari
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=list(range(1, 32)),
        index=today_day - 1
    )
    
    st.caption(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

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
              st.warning("⚠️ Harap isi semua kolom data.")
        else:
            with st.spinner("Menyimpan data..."):
                success = simpan_data_ke_sheet(selected_lokasi, input_day, input_ph, input_suhu, input_debit)
                if success:
                    # Clear cache dan rerun jika berhasil
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
    
    # --- Bagian 3: Visualisasi Data ---
    st.markdown("---")
    st.subheader("📈 Tren Data Bulanan")

    # Siapkan data untuk grafik
    chart_data = current_df.dropna(subset=['pH', 'Suhu (°C)', 'Debit (l/d)'])
    chart_data['Hari'] = chart_data['Hari'].astype(str)
    
    if not chart_data.empty:
        # Transformasi data untuk Altair (long format)
        melted_df = chart_data.melt(
            id_vars=['Hari'],
            value_vars=['pH', 'Suhu (°C)', 'Debit (l/d)'],
            var_name='Parameter',
            value_name='Nilai'
        )

        # 1. Grafik Gabungan (Multi-y axis - menggunakan layer Altair)
        # Note: Ini adalah grafik yang sulit divisualisasikan karena skala yang berbeda, tapi penting untuk tren
        st.caption("Grafik gabungan membantu melihat korelasi tren.")
        
        # Base Chart
        base = alt.Chart(melted_df).encode(
            x=alt.X('Hari', axis=alt.Axis(tickCount='exact', labelAngle=-45), title='Hari ke-'),
            tooltip=['Hari', 'Parameter', 'Nilai']
        ).properties(
            title=f'Tren pH, Suhu, & Debit di {selected_lokasi}'
        )

        # PH Chart (Skala Kiri)
        ph_chart = base.transform_filter(
            alt.datum.Parameter == 'pH'
        ).mark_line(point=True, color='#00aaff').encode(
            y=alt.Y('Nilai', axis=alt.Axis(title='pH', titleColor='#00aaff'))
        )
        
        # Suhu Chart (Skala Kiri, namun rentang berbeda)
        suhu_chart = base.transform_filter(
            alt.datum.Parameter == 'Suhu (°C)'
        ).mark_line(point=True, color='#ff6600').encode(
            y=alt.Y('Nilai', axis=alt.Axis(title='Suhu (°C)', titleColor='#ff6600'))
        )
        
        # Debit Chart (Skala Kanan) - Menggunakan skala berbeda.
        # Karena skala debit jauh lebih besar, ini dipecah menjadi chart terpisah di bawah.

        st.altair_chart(ph_chart + suhu_chart, use_container_width=True)

        
        # 2. Grafik Individu (Lebih Akurat untuk Analisis)
        st.subheader("Tren Detail per Parameter")

        # Membuat grafik untuk pH
        chart_ph = alt.Chart(chart_data).mark_line(point=True, color='#00aaff').encode(
            x=alt.X('Hari', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('pH', scale=alt.Scale(domain=[6, 9])), # Batasi domain pH agar sensitif
            tooltip=['Hari', 'Tanggal', 'pH']
        ).properties(
            title='Tren pH'
        )
        
        # Membuat grafik untuk Suhu
        chart_suhu = alt.Chart(chart_data).mark_line(point=True, color='#ff6600').encode(
            x=alt.X('Hari', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Suhu (°C)'),
            tooltip=['Hari', 'Tanggal', 'Suhu (°C)']
        ).properties(
            title='Tren Suhu (°C)'
        )

        # Membuat grafik untuk Debit
        chart_debit = alt.Chart(chart_data).mark_line(point=True, color='#00cc66').encode(
            x=alt.X('Hari', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Debit (l/d)'),
            tooltip=['Hari', 'Tanggal', 'Debit (l/d)']
        ).properties(
            title='Tren Debit (l/d)'
        )

        st.altair_chart(chart_ph, use_container_width=True)
        st.altair_chart(chart_suhu, use_container_width=True)
        st.altair_chart(chart_debit, use_container_width=True)

    else:
        st.info("Tidak ada data yang cukup untuk membuat visualisasi.")
else:
    st.info("Belum ada data untuk lokasi ini.")

st.caption("Aplikasi Monitoring Air | Pastikan akun layanan memiliki akses Edit.")
