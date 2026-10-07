#-----------------------------------------------------------------------------------
# APLICATIE STREAMLIT OPTIMIZATĂ PENTRU SUPABASE (POSTGRESQL)
#-----------------------------------------------------------------------------------

import os
import json
import smtplib
import urllib.request
from datetime import datetime
from email.message import EmailMessage
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF
import psycopg2
import psycopg2.extras

# Încărcare variabile de mediu
load_dotenv()

# ------------------------------------------------------------------------------
# CONFIGURARE CONEXIUNE BAZĂ DE DATE SUPABASE (POSTGRESQL)
# ------------------------------------------------------------------------------
def get_db_connection():
    try:
        db_url = st.secrets["DATABASE_URL"]
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        st.error(f"Eroare critică de conectare la baza de date Supabase: {e}")
        st.stop()

# ------------------------------------------------------------------------------
# 1. Configurare Pagină & Stil UI (Optimizat și pentru Mobil)
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Nexus Industrial - Sistem Mentenanță",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------------------------------
# 2. Inițializare Tabele în Supabase (PostgreSQL)
# ------------------------------------------------------------------------------
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Tabel Firme / Clienti & Date Fiscale & Persoana Contact
    c.execute('''
        CREATE TABLE IF NOT EXISTS firme (
            id SERIAL PRIMARY KEY,
            nume_firma TEXT NOT NULL,
            cui TEXT,
            reg_com TEXT,
            adresa TEXT,
            banca TEXT,
            cont TEXT,
            nume_persoana TEXT NOT NULL,
            email TEXT NOT NULL,
            telefon TEXT
        )
    ''')
    
    # 2. Tabel Mașini / Echipamente & Detalii Complete
    c.execute('''
        CREATE TABLE IF NOT EXISTS masini (
            id SERIAL PRIMARY KEY,
            firma_id INTEGER,
            denumire TEXT NOT NULL,
            tip_masina TEXT,
            serie TEXT,
            an_fabricatie INTEGER,
            subansambluri TEXT,
            erori TEXT,
            defecte TEXT,
            remediu TEXT,
            piese_necesare TEXT,
            piese_inlocuite TEXT,
            tipuri_fluide TEXT,
            data_intretinere TEXT,
            tip_intretinere TEXT,
            FOREIGN KEY(firma_id) REFERENCES firme(id)
        )
    ''')
    
    # 3. Tabel Piese de Schimb
    c.execute('''
        CREATE TABLE IF NOT EXISTS piese (
            id SERIAL PRIMARY KEY,
            denumire TEXT NOT NULL,
            cod_producator TEXT,
            cod_comercial TEXT,
            masina_montaj TEXT,
            subansamblu TEXT,
            pret_achizitie REAL
        )
    ''')
    
    # 4. Tabel Optimizare Intervenție / Pași Remediu
    c.execute('''
        CREATE TABLE IF NOT EXISTS optimizari_interventie (
            id SERIAL PRIMARY KEY,
            masina TEXT,
            defect TEXT,
            pas_numar INTEGER,
            descriere_pas TEXT
        )
    ''')
    
    # 5. Tabel Activități Zilnice / Rapoarte Intervenție
    c.execute('''
        CREATE TABLE IF NOT EXISTS reparatii (
            id SERIAL PRIMARY KEY,
            firma TEXT,
            masina TEXT,
            subansamblu TEXT,
            defect TEXT,
            cod_eroare TEXT,
            piese_json TEXT,
            titlu TEXT,
            simptom TEXT,
            solutie TEXT,
            stare_finala TEXT,
            durata INTEGER,
            optimizari TEXT,
            tehnician TEXT,
            verificator TEXT,
            data_creare TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 6. Tabel Setări Aplicație & SMTP & Google Sheet URL
    c.execute('''
        CREATE TABLE IF NOT EXISTS setari (
            id SERIAL PRIMARY KEY,
            nume_firma_mea TEXT,
            cui_mea TEXT,
            adresa_mea TEXT,
            smtp_server TEXT,
            smtp_port INTEGER,
            smtp_user TEXT,
            smtp_pass TEXT,
            google_sheet_url TEXT
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM setari")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO setari (nume_firma_mea, cui_mea, adresa_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, ("Nexus Industrial SRL", "", "", "smtp.gmail.com", 587, "", "", ""))
    
    conn.commit()
    conn.close()

init_db()

def get_setari():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nume_firma_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url FROM setari LIMIT 1")
    res = c.fetchone()
    conn.close()
    if res:
        return res
    return ("Nexus Industrial SRL", "smtp.gmail.com", 587, "", "", "")

# ------------------------------------------------------------------------------
# 3. Clasă Generare PDF Profesionist
# ------------------------------------------------------------------------------
class RaportPDF(FPDF):
    def header(self):
        self.set_fill_color(30, 41, 59)
        self.rect(0, 0, 210, 25, 'F')
        
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 8)
        self.cell(0, 10, 'RAPORT DE INTERVENTIE TEHNICA', 0, 0, 'L')
        
        self.set_font('Helvetica', '', 10)
        self.set_xy(140, 8)
        self.cell(60, 10, 'DOCUMENT OFICIAL', 0, 0, 'R')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, 'Pagina ' + str(self.page_no()) + ' | Raport generat automat', 0, 0, 'C')

def curata_text(text):
    if not text:
        return ""
    inlocuiri = {
        'ă': 'a', 'Ă': 'A', 'â': 'a', 'Â': 'A',
        'î': 'i', 'Î': 'I', 'ș': 's', 'Ș': 'S',
        'ț': 't', 'Ț': 'T', 'ş': 's', 'Ş': 'S', 'ţ': 't', 'Ţ': 'T'
    }
    for k, v in inlocuiri.items():
        text = text.replace(k, v)
    return text

def genereaza_pdf(data):
    pdf = RaportPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    PRIMARY = (30, 41, 59)
    SECONDARY = (71, 85, 105)
    BG_LIGHT = (241, 245, 249)
    
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(100, 7, curata_text(f"Nr. Inregistrare: #{data['id']}"), 0, 0)
    pdf.cell(90, 7, curata_text(f"Data: {str(data['data'])[:10]}"), 0, 1, 'R')
    pdf.line(10, 35, 200, 35)
    pdf.ln(3)

    pdf.set_fill_color(*BG_LIGHT)
    pdf.rect(10, 38, 190, 32, 'F')
    
    pdf.set_xy(12, 40)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(90, 6, curata_text("DETALII CLIENT"), 0, 0)
    pdf.cell(90, 6, curata_text("DETALII ECHIPAMENT"), 0, 1)
    
    pdf.set_font('Helvetica', '', 9
