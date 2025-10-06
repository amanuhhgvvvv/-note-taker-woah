import streamlit as st
import pandas as pd
from pathlib import Path
import os 
import numpy as np 
import io 
import xlsxwriter # <--- TAMBAHAN: Diperlukan untuk utilitas kolom

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

    df_data_rows['
