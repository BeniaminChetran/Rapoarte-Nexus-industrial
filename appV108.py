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
            pret_achizitie REAL,
            pret_intrare REAL DEFAULT 0,
            pret_iesire REAL DEFAULT 0,
            ad_com REAL DEFAULT 0,
            livrare REAL DEFAULT 0
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
    
    # 5.1. Tabel Devize de Calcul / Oferte
    c.execute('''
        CREATE TABLE IF NOT EXISTS devize (
            id SERIAL PRIMARY KEY,
            tip TEXT,
            firma TEXT,
            masina TEXT,
            piese_json TEXT,
            total_valoare REAL,
            tva_valoare REAL,
            total_cu_tva REAL,
            memo TEXT,
            data_creare TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 6. Tabel Setări Aplicație (inclusiv TVA, Pass și Curs BNR)
    c.execute('''
        CREATE TABLE IF NOT EXISTS setari (
            id SERIAL PRIMARY KEY,
            nume_firma_mea TEXT,
            cui_mea TEXT,
            reg_com_mea TEXT,
            adresa_mea TEXT,
            banca_mea TEXT,
            iban_mea TEXT,
            swep_mea TEXT,
            smtp_server TEXT,
            smtp_port INTEGER,
            smtp_user TEXT,
            smtp_pass TEXT,
            google_sheet_url TEXT,
            email_tehnician TEXT,
            tva REAL DEFAULT 21.0,
            pass TEXT DEFAULT 'nexus123',
            curs_bnr REAL DEFAULT 4.97
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM setari")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO setari (nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician, tva, pass, curs_bnr)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, ("Nexus Industrial SRL", "", "", "", "", "", "", "smtp.gmail.com", 587, "", "", "", "", 21.0, "nexus123", 4.97))
    
    conn.commit()
    conn.close()

init_db()

def get_setari():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician, tva, pass, curs_bnr FROM setari LIMIT 1")
    res = c.fetchone()
    conn.close()
    if res:
        return res
    return ("Nexus Industrial SRL", "", "", "", "", "", "", "smtp.gmail.com", 587, "", "", "", 21.0, "nexus123", 4.97)

# ------------------------------------------------------------------------------
# 3. Clasă Generare PDF Profesionist (Deviz, Oferta de pret, Raport)
# ------------------------------------------------------------------------------
class RaportPDF(FPDF):
    def __init__(self, document_title="RAPORT DE INTERVENTIE TEHNICA"):
        super().__init__()
        self.document_title = document_title

    def header(self):
        self.set_fill_color(30, 41, 59)
        self.rect(0, 0, 210, 25, 'F')
        
        self.set_font('Helvetica', 'B', 15)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 8)
        self.cell(0, 10, curata_text(self.document_title), 0, 0, 'L')
        
        self.set_font('Helvetica', '', 10)
        self.set_xy(140, 8)
        self.cell(60, 10, 'DOCUMENT OFICIAL', 0, 0, 'R')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, 'Pagina ' + str(self.page_no()) + ' | Generat automat - Nexus Industrial', 0, 0, 'C')

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

def genereaza_pdf(data, titlu_doc="RAPORT DE INTERVENTIE TEHNICA"):
    pdf = RaportPDF(document_title=titlu_doc)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    PRIMARY = (30, 41, 59)
    SECONDARY = (71, 85, 105)
    BG_LIGHT = (241, 245, 249)
    
    setari_pdf = get_setari()
    nume_emitent = setari_pdf[0]
    cui_emitent = setari_pdf[1]
    reg_emitent = setari_pdf[2]
    adresa_emitent = setari_pdf[3]
    banca_emitent = setari_pdf[4]
    iban_emitent = setari_pdf[5]
    swep_emitent = setari_pdf[6]
    curs_bnr_val = float(setari_pdf[15]) if len(setari_pdf) > 15 and setari_pdf[15] is not None else 4.97

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(0, 5, curata_text(f"{nume_emitent} | CUI: {cui_emitent} | Reg. Com.: {reg_emitent}"), 0, 1, 'L')
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(*SECONDARY)
    pdf.cell(0, 4, curata_text(f"Adresă: {adresa_emitent} | Bancă: {banca_emitent} | IBAN: {iban_emitent} | SWIFT: {swep_emitent}"), 0, 1, 'L')
    
    pdf.ln(6)

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*PRIMARY)
    doc_id = data.get('id', 'N/A')
    pdf.cell(100, 7, curata_text(f"Număr: #{doc_id}"), 0, 0)
    pdf.cell
