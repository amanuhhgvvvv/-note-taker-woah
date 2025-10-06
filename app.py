import streamlit as st
import pandas as pd
from pathlib import Path
import os 
import numpy as np 
import io 

# --- (Kode Konfigurasi dan Utility di sini tetap SAMA) ---
# ...

def create_pivot_data(df_raw, lokasi):
    """Memproses DataFrame mentah menjadi format pivot bulanan."""
    # ... (Fungsi ini tetap SAMA)
    # ...
    return pivot_sheets

def create_excel_with_pivot_sheets(all_raw_sheets):
    """Hanya membuat sheet pivot, menghilangkan sheet RAW dan menambahkan border."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        # 1. Dapatkan objek workbook dan definisikan format border
        workbook = writer.book
        # Definisi format border penuh (1)
        border_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'}) 
        
        # Format untuk header baris (kolom A), border + rata kiri
        header_format = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter', 'bold': True})
        
        # 2. Tulis sheet data pivot (format bulanan)
        for lokasi in SHEET_NAMES:
            df_raw = all_raw_sheets.get(lokasi)
            if df_raw is not None:
                pivot_data = create_pivot_data(df_raw, lokasi)
                
                if pivot_data: 
                    for sheet_name, df_pivot in pivot_data.items():
                         
                        # Dapatkan objek worksheet yang baru dibuat
                        worksheet = workbook.add_worksheet(sheet_name)
                        
                        # Tulis Header Utama (Start A1)
                        # Gunakan merge format agar judul terpusat
                        merge_format = workbook.add_format({
                            'bold': 1,
                            'align': 'center',
                            'valign': 'vcenter'
                        })
                        
                        # Tentukan rentang sel untuk merge, misalnya A1 sampai kolom terakhir
                        last_col_letter = pd.io.excel.xlwt._get_col_string(len(df_pivot.columns))
                        worksheet.merge_range(f'A1:{last_col_letter}1', f"Data Bulanan {lokasi}", merge_format)

                        # --- Tulis Header Kolom (Hari, Rata-rata, KETERANGAN) ---
                        # Dimulai dari sel B2 (kolom ke-2, baris ke-2)
                        col_headers = list(df_pivot.columns)
                        # Tulis header kolom dengan format border
                        worksheet.write_row('B2', col_headers, border_format) 

                        # --- Tulis Index Baris (pH, Debit (l/d)) ---
                        # Dimulai dari sel A3
                        row_headers = list(df_pivot.index)
                        # Tulis header baris (index) dengan format header_format (border + bold)
                        worksheet.write_column('A3', row_headers, header_format)

                        # --- Tulis Data dan Border ---
                        # Tulis DataFrame data mulai dari B3, menerapkan border_format ke setiap sel
                        
                        # Konversi DataFrame ke list of lists
                        data_to_write = df_pivot.values.tolist()
                        
                        start_row = 2 # Baris ke-3 (indeks 2)
                        start_col = 1 # Kolom ke-2 (indeks 1)

                        for row_num, row_data in enumerate(data_to_write):
                            # Tulis data di baris saat ini, terapkan format border
                            # Nilai 'None' akan ditulis sebagai string kosong
                            processed_data = ["" if pd.isna(item) else item for item in row_data]
                            worksheet.write_row(start_row + row_num, start_col, processed_data, border_format)
                            
                        # Atur lebar kolom A agar cukup menampung 'Debit (l/d)'
                        worksheet.set_column('A:A', 15) 
                        # Atur lebar kolom data (B sampai kolom terakhir)
                        worksheet.set_column('B:Z', 8) 
                        
    return output.getvalue()

# --- (Kode Form Input dan Preview di sini tetap SAMA) ---
# ...
