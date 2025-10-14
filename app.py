import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Koneksi (sama seperti di atas)
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
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=[
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ])
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"❌ Gagal koneksi: {e}")
        return None

client = init_gsheets_connection()
if not client:
    st.stop()

SHEET_ID = st.secrets["SHEET_ID"]

st.title("🆕 Buat Worksheet Baru")

# Buat worksheet baru yang sederhana
worksheet_name = st.text_input("Nama Worksheet:", "Monitoring-Air")
if st.button("Buat Worksheet Baru", type="primary"):
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=10)
        
        # Header sederhana
        worksheet.update('A1', [['Timestamp', 'Lokasi', 'Hari', 'pH', 'Suhu', 'Debit']])
        
        st.success(f"✅ Worksheet '{worksheet_name}' berhasil dibuat!")
        st.balloons()
        
    except Exception as e:
        st.error(f"❌ Error: {e}")
