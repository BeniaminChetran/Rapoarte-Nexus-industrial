#-----------------------------------------------------------------------------------
# APLICATIE NexInd CMMS Enterprise Dashboard & Predictive v10.4.7
#-----------------------------------------------------------------------------------

import os
import json
import smtplib
import urllib.request
import threading
from datetime import datetime, date
from email.message import EmailMessage
from contextlib import contextmanager
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
import pandas as pd
import plotly.express as px

load_dotenv()

# ------------------------------------------------------------------------------
# 1. CONFIGURARE CONNECTION POOL & CACHE RESOURCE
# ------------------------------------------------------------------------------
@st.cache_resource
def init_connection_pool():
    try:
        db_url = st.secrets["DATABASE_URL"]
        pool = ThreadedConnectionPool(1, 20, db_url)
        return pool
    except Exception as e:
        st.error(f"Eroare critică la inițializarea Connection Pool Supabase: {e}")
        st.stop()

db_pool = init_connection_pool()

@contextmanager
def db_cursor():
    conn = db_pool.getconn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        db_pool.putconn(conn)

# ------------------------------------------------------------------------------
# 2. Configurare Pagină & Stil UI
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="NexInd CMMS Enterprise Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------------------------------
# 3. Funcții Optimizate cu Cache Individual & Lazy Loading
# ------------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_setari():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM setari LIMIT 1")
        res = cur.fetchone()
    if res:
        return res
    return {
        "nume_firma_mea": "Nexus Industrial SRL", "cui_mea": "", "reg_com_mea": "", 
        "adresa_mea": "", "banca_mea": "", "iban_mea": "", "swep_mea": "", 
        "smtp_server": "smtp.gmail.com", "smtp_port": 587, "smtp_user": "", 
        "smtp_pass": "", "google_sheet_url": "", "email_tehnician": ""
    }

@st.cache_data(ttl=300)
def get_firme():
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon 
            FROM firme 
            ORDER BY nume_firma
        """)
        return cur.fetchall()

@st.cache_data(ttl=300)
def get_masini():
    with db_cursor() as cur:
        cur.execute("SELECT id, firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere, stare_utilaj, data_inceput_oprire, motiv_oprire FROM masini ORDER BY denumire")
        return cur.fetchall()

@st.cache_data(ttl=300)
def get_masini_firma(firma_id):
    with db_cursor() as c:
        c.execute("""
            SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina, m.stare_utilaj 
            FROM masini m
            JOIN firme f ON m.firma_id = f.id
            WHERE f.id = %s 
            ORDER BY m.denumire
        """, (firma_id,))
        return c.fetchall()

@st.cache_data(ttl=300)
def get_piese():
    with db_cursor() as cur:
        cur.execute("SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, subansamblu FROM piese ORDER BY denumire")
        return cur.fetchall()

@st.cache_data(ttl=300)
def get_piese_filtrate(select_masina_unica):
    with db_cursor() as cur:
        if select_masina_unica != "Toate mașinile / General":
            cur.execute("""
                SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, subansamblu FROM piese 
                WHERE LOWER(TRIM(masina_montaj)) LIKE LOWER(%s)
                   OR LOWER(masina_montaj) LIKE LOWER(%s)
                   OR LOWER(masina_montaj) LIKE LOWER(%s)
                   OR LOWER(TRIM(masina_montaj)) = 'general'
                   OR masina_montaj = ''
                   OR masina_montaj IS NULL
                ORDER BY denumire
            """, (
                f"%{select_masina_unica.strip()}%", 
                f"{select_masina_unica.strip()},%", 
                f"%, {select_masina_unica.strip()}%"
            ))
        else:
            cur.execute("SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, subansamblu FROM piese ORDER BY denumire")
        return cur.fetchall()

@st.cache_data(ttl=60)
def get_dashboard_kpi_data():
    with db_cursor() as c:
        c.execute("""
            SELECT
                COUNT(*) AS interventii,
                COALESCE(SUM(durata),0) AS minute,
                COUNT(DISTINCT firma) AS clienti,
                COUNT(DISTINCT masina) AS utilaje
            FROM reparatii
            WHERE DATE_TRUNC('month', data_creare) = DATE_TRUNC('month', CURRENT_DATE)
        """)
        res_rep = c.fetchone()
        
        c.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE stare_utilaj = 'Activă' OR stare_utilaj = 'Funcțională') AS active,
                COUNT(*) FILTER (WHERE stare_utilaj = 'În așteptare piese') AS asteptare_piese,
                COUNT(*) FILTER (WHERE stare_utilaj = 'Nefuncțională / Oprită' OR stare_utilaj = 'Oprită (Defect / Piese)') AS nefunctionale,
                COUNT(*) FILTER (WHERE stare_utilaj = 'Oprită pentru întreținere') AS oprite_intretinere,
                COUNT(*) AS total_utilaje
            FROM masini
        """)
        res_masini = c.fetchone()
        
    return res_rep, res_masini

@st.cache_data(ttl=300)
def get_dashboard_charts_data():
    with db_cursor() as c:
        c.execute("""
            SELECT defect, COUNT(*) AS aparitii
            FROM reparatii
            WHERE defect IS NOT NULL AND defect <> ''
            GROUP BY defect
            ORDER BY aparitii DESC
            LIMIT 10
        """)
        top_def = c.fetchall()

        c.execute("""
            SELECT firma, COUNT(*) AS interventii
            FROM reparatii
            GROUP BY firma
            ORDER BY interventii DESC
            LIMIT 10
        """)
        top_cli = c.fetchall()

        c.execute("""
            SELECT masina, COUNT(*) AS interventii
            FROM reparatii
            GROUP BY masina
            ORDER BY interventii DESC
            LIMIT 10
        """)
        top_ut = c.fetchall()

        c.execute("""
            SELECT masina, defect, COUNT(*) AS repetitii
            FROM reparatii
            WHERE defect IS NOT NULL AND defect <> '' AND data_creare > CURRENT_DATE - INTERVAL '180 day'
            GROUP BY masina, defect
            HAVING COUNT(*) >= 3
            ORDER BY repetitii DESC
            LIMIT 20
        """)
        def_rec = c.fetchall()

        c.execute("""
            SELECT denumire, data_intretinere
            FROM masini
            WHERE data_intretinere IS NOT NULL 
              AND CAST(data_intretinere AS DATE) <= CURRENT_DATE + INTERVAL '30 day'
            ORDER BY data_intretinere
        """)
        mas_scad = c.fetchall()

    return top_def, top_cli, top_ut, def_rec, mas_scad

# ------------------------------------------------------------------------------
# 4. Clasă Generare PDF Profesionist
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
    
    setari_pdf = get_setari()

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(0, 5, curata_text(f"{setari_pdf['nume_firma_mea']} | CUI: {setari_pdf['cui_mea']} | Reg. Com.: {setari_pdf['reg_com_mea']}"), 0, 1, 'L')
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(*SECONDARY)
    pdf.cell(0, 4, curata_text(f"Adresă: {setari_pdf['adresa_mea']} | Bancă: {setari_pdf['banca_mea']} | IBAN: {setari_pdf['iban_mea']} | SWIFT: {setari_pdf['swep_mea']}"), 0, 1, 'L')
    pdf.ln(6)

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(100, 7, curata_text(f"Nr. Inregistrare: #{data['id']}"), 0, 0)
    pdf.cell(90, 7, curata_text(f"Data: {str(data['data'])[:10]}"), 0, 1, 'R')
    pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
    pdf.ln(6)

    pdf.set_fill_color(*BG_LIGHT)
    pdf.rect(10, pdf.get_y(), 190, 32, 'F')
    pdf.set_xy(12, pdf.get_y() + 2)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(90, 6, curata_text("DETALII CLIENT"), 0, 0)
    pdf.cell(90, 6, curata_text("DETALII ECHIPAMENT"), 0, 1)
    
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_x(12)
    pdf.cell(90, 5, curata_text(f"Client: {data['client'] or 'Nespecificat'}"), 0, 0)
    pdf.cell(90, 5, curata_text(f"Echipament: {data['masina']} ({data.get('subansamblu','')})"), 0, 1)
    pdf.set_x(12)
    pdf.cell(90, 5, curata_text(f"Durata: {data['durata']} minute ({data.get('tip_interventie', 'N/A')})"), 0, 0)
    pdf.cell(90, 5, curata_text(f"Cod Eroare: {data.get('cod_eroare','N/A')}"), 0, 1)
    pdf.set_x(12)
    pdf.cell(90, 5, "", 0, 0)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(90, 5, curata_text(f"Stare Finala: {data['stare_finala']}"), 0, 1)
    pdf.ln(8)

    def adauga_sectiune(titlu, continut):
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*SECONDARY)
        pdf.cell(0, 6, curata_text(titlu.upper()), 0, 1)
        pdf.set_draw_color(*SECONDARY)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 5, curata_text(continut or "Nespecificat"))
        pdf.ln(4)

    adauga_sectiune("Titlu Lucrare", data['titlu'])
    adauga_sectiune("Simptom Initial / Defect", f"{data['simptom']} / {data['defect']}")
    adauga_sectiune("Solutie / Lucrari Executate", data['solutie'])

    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*SECONDARY)
    pdf.cell(0, 6, curata_text("TABEL PIESE (UTILIZATE / INLOCUITE / NECESARE / COMANDAT)"), 0, 1)
    pdf.set_draw_color(*SECONDARY)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(100, 6, curata_text("Denumire Piesa"), 1, 0, 'C', fill=True)
    pdf.cell(40, 6, curata_text("Cantitate"), 1, 0, 'C', fill=True)
    pdf.cell(50, 6, curata_text("Tip / Status"), 1, 1, 'C', fill=True)
    
    pdf.set_font('Helvetica', '', 9)
    piese_list = data.get('piese_json', [])
    if piese_list:
        for p in piese_list:
            if isinstance(p, dict):
                nume_p = p.get('piesa') or p.get('Piesa') or ''
                cant_p = p.get('cantitate') if p.get('cantitate') is not None else p.get('Cantitate', 1)
                tip_p = p.get('tip') or p.get('Tip') or ''
                
                pdf.cell(100, 6, curata_text(str(nume_p)), 1, 0, 'L')
                pdf.cell(40, 6, str(cant_p), 1, 0, 'C')
                pdf.cell(50, 6, curata_text(str(tip_p)), 1, 1, 'C')
            else:
                pdf.cell(100, 6, curata_text(str(p)), 1, 0, 'L')
                pdf.cell(40, 6, "1", 1, 0, 'C')
                pdf.cell(50, 6, curata_text("Utilizata"), 1, 1, 'C')
    else:
        pdf.cell(190, 6, curata_text("Nicio piesa inregistrata"), 1, 1, 'C')
    pdf.ln(4)

    if data['optimizari']:
        adauga_sectiune("Recomandari Tehnice & Siguranta", data['optimizari'])

    if pdf.get_y() > 235:
        pdf.add_page()

    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(95, 5, curata_text("EFECTUAT
