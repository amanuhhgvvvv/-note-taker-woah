import streamlit as st
import pandas as pd
import numpy as np
import datetime
import time 

# Mode simulasi sementara untuk testing
MODE_SIMULASI = True

st.set_page_config(page_title="Monitoring Air", layout="centered")
st.title("📊 Monitoring Air")

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

INTERNAL_COLUMNS = ["tanggal", "pH", "suhu", "debit", "ph_rata_rata_bulan", "suhu_rata_rata_bulan", "debit_rata_rata_bulan"]

if MODE_SIMULASI:
    st.warning("🔧 MODE SIMULASI - Data disimpan sementara di memori")
    
    # Simpan data di session state
    if 'simulasi_data' not in st.session_state:
        st.session_state.simulasi_data = {}
        for sheet_name in SHEET_NAMES:
            # Buat data kosong untuk semua lokasi
            today = datetime.date.today()
            df_kosong = pd.DataFrame({
                'tanggal': [f"{today.year}-{today.month:02d}-{day:02d}" for day in range(1, 32)],
                'pH': [None] * 31,
                'suhu': [None] * 31, 
                'debit': [None] * 31,
                'ph_rata_rata_bulan': [None],
                'suhu_rata_rata_bulan': [None],
                'debit_rata_rata_bulan': [None]
            })
            st.session_state.simulasi_data[sheet_name] = df_kosong

    def baca_data_simulasi():
        return st.session_state.simulasi_data

    def simpan_data_simulasi(lokasi, df):
        st.session_state.simulasi_data[lokasi] = df
        st.success(f"✅ Data simulasi berhasil disimpan untuk {lokasi}!")
        time.sleep(1)
        st.rerun()

else:
    # KODE GOOGLE SHEETS ASLI (jadi comment dulu)
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        @st.cache_resource
        def init_gsheets_connection():
            try:
                creds_dict = {
                    "type": "service_account",
                    "project_id": st.secrets["project_id"],
                    "private_key_id": st.secrets["private_key_id"], 
                    "private_key": st.secrets["private_key"].replace('\\n', '\n'),
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
                st.error(f"❌ Gagal inisialisasi koneksi Google Sheets: {e}")
                return None

        client = init_gsheets_connection()
        SHEET_ID = st.secrets["SHEET_ID"]
        
    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.stop()

# ==================== BAGIAN UTAMA APLIKASI ====================

# 1. SIDEBAR: Pilihan Lokasi
st.sidebar.title("Pilihan Lokasi")
selected_sheet = st.sidebar.selectbox(
    "Pilih Lokasi yang Ingin Dicatat:",
    options=SHEET_NAMES,
    index=0 
)

# 2. Muat Semua Data
if MODE_SIMULASI:
    all_data = baca_data_simulasi()
    current_df = all_data.get(selected_sheet, pd.DataFrame(columns=INTERNAL_COLUMNS))
else:
    # Untuk mode Google Sheets (akan diisi nanti)
    current_df = pd.DataFrame(columns=INTERNAL_COLUMNS)

# Tampilkan Status Lokasi
st.subheader(f"Data Harian untuk Lokasi: **{selected_sheet}**")

# 3. Input Data Baru (Gunakan Form)
st.markdown("---")
st.header("📝 Catat Data Baru")

# Dapatkan hari ini untuk input default
today_date = datetime.date.today()
today_day = today_date.day

# Cek apakah data untuk hari ini sudah ada
is_day_recorded = False
if not current_df.empty:
    try:
        existing_dates = [str(date) for date in current_df['tanggal'] if isinstance(date, str)]
        is_day_recorded = any(f"{today_date.year}-{today_date.month:02d}-{today_day:02d}" in date for date in existing_dates)
    except:
        is_day_recorded = False

if is_day_recorded:
    st.info(f"Data untuk tanggal **{today_day}** sudah ada.")
    st.markdown("Anda bisa menggunakan bagian di bawah untuk **mengubah** data yang sudah ada.")
    
with st.form("input_form"):
    
    # Pilih Hari
    day_options = [day for day in range(1, 32)]
    default_day_index = day_options.index(today_day) if today_day in day_options else 0
    
    input_day = st.selectbox(
        "Pilih **Hari** untuk Pencatatan:",
        options=day_options,
        index=default_day_index,
        key='input_day'
    )
    
    st.write(f"Tanggal lengkap yang akan dicatat: **{today_date.year}-{today_date.month:02d}-{input_day:02d}**")

    # Ambil nilai default jika hari yang dipilih sudah ada datanya
    default_ph = None
    default_suhu = None
    default_debit = None
    
    if not current_df.empty:
        try:
            target_date = f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            existing_data = current_df[current_df['tanggal'] == target_date]
            if not existing_data.empty:
                default_ph = existing_data['pH'].iloc[0] if pd.notna(existing_data['pH'].iloc[0]) else None
                default_suhu = existing_data['suhu'].iloc[0] if pd.notna(existing_data['suhu'].iloc[0]) else None
                default_debit = existing_data['debit'].iloc[0] if pd.notna(existing_data['debit'].iloc[0]) else None
        except:
            pass
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        input_ph = st.number_input(
            "Nilai pH", 
            min_value=0.0, max_value=14.0, 
            format="%.2f", step=0.01,
            key='input_ph',
            value=default_ph
        )
    with col2:
        input_suhu = st.number_input(
            "Suhu (°C)", 
            min_value=0.0, max_value=100.0, 
            format="%.1f", step=0.1,
            key='input_suhu',
            value=default_suhu
        )
    with col3:
        input_debit = st.number_input(
            "Debit (l/d)", 
            min_value=0.0, 
            format="%.2f", step=0.01,
            key='input_debit',
            value=default_debit
        )
        
    submitted = st.form_submit_button("Simpan Data", type="primary")

    if submitted:
        if input_ph is None or input_suhu is None or input_debit is None:
            st.error("Mohon isi semua kolom (pH, Suhu, dan Debit) sebelum menyimpan.")
        else:
            target_date_str = f"{today_date.year}-{today_date.month:02d}-{input_day:02d}"
            
            # Buat data baru
            new_data = {
                'tanggal': target_date_str,
                'pH': input_ph,
                'suhu': input_suhu,
                'debit': input_debit
            }
            
            # Update DataFrame
            if not current_df.empty:
                # Hapus data existing untuk hari yang sama
                current_df_clean = current_df[current_df['tanggal'] != target_date_str]
                # Tambah data baru
                new_row = pd.DataFrame([new_data])
                updated_df = pd.concat([current_df_clean, new_row], ignore_index=True)
            else:
                # DataFrame kosong, buat baru
                updated_df = pd.DataFrame([new_data])
            
            # Simpan data
            if MODE_SIMULASI:
                simpan_data_simulasi(selected_sheet, updated_df)
            else:
                # Untuk mode Google Sheets (akan diisi nanti)
                st.info("Fitur Google Sheets sedang dalam perbaikan...")

# 4. Tampilkan Data
st.markdown("---")
st.subheader("Tinjauan Data Saat Ini")

if not current_df.empty:
    display_df = current_df.copy()
    display_df.replace({np.nan: '', None: ''}, inplace=True)
    
    # Format tanggal untuk display
    def format_tanggal(x):
        if isinstance(x, str) and '-' in x:
            return x.split('-')[-1]
        return x
    
    display_df['Hari'] = display_df['tanggal'].apply(format_tanggal)
    
    display_df.rename(columns={
        'pH': 'pH',
        'suhu': 'Suhu (°C)',
        'debit': 'Debit (l/d)'
    }, inplace=True)
    
    # Pilih kolom untuk display
    display_columns = ['Hari', 'pH', 'Suhu (°C)', 'Debit (l/d)']
    display_df = display_df[display_columns]

    st.dataframe(
        display_df,
        hide_index=True,
        width='stretch',
        height=400,
    )
else:
    st.info("Belum ada data untuk lokasi ini.")

st.caption("Aplikasi Monitoring Air - Data tersimpan sementara di memori")

# Tombol untuk reset data simulasi
if MODE_SIMULASI and st.sidebar.button("🔄 Reset Data Simulasi"):
    for sheet_name in SHEET_NAMES:
        today = datetime.date.today()
        df_kosong = pd.DataFrame({
            'tanggal': [f"{today.year}-{today.month:02d}-{day:02d}" for day in range(1, 32)],
            'pH': [None] * 31,
            'suhu': [None] * 31, 
            'debit': [None] * 31,
            'ph_rata_rata_bulan': [None],
            'suhu_rata_rata_bulan': [None],
            'debit_rata_rata_bulan': [None]
        })
        st.session_state.simulasi_data[sheet_name] = df_kosong
    st.success("Data simulasi telah direset!")
    st.rerun()
