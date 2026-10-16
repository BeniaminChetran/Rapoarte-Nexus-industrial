#-----------------------------------------------------------------------------------
# APLICATIE NexInd CMMS Enterprise Dashboard & Predictive v10.4.5
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
# 3. Funcții Optimizate cu Cache Individual, Lazy Loading & KPI Consolidate
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
        cur.execute("SELECT id, firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere FROM masini")
        return cur.fetchall()

@st.cache_data(ttl=300)
def get_masini_firma(firma_id):
    with db_cursor() as c:
        c.execute("""
            SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina 
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
                COUNT(DISTINCT masina) AS utilaje,
                COUNT(*) FILTER (WHERE stare_finala='Oprită / Necesar piese') AS utilaje_oprite
            FROM reparatii
            WHERE DATE_TRUNC('month', data_creare) = DATE_TRUNC('month', CURRENT_DATE)
        """)
        return c.fetchone()

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

@st.cache_data(ttl=300)
def get_predictive_piese_data(firma, masina):
    with db_cursor() as cur_piese:
        cur_piese.execute("""
            SELECT piese_json FROM reparatii
            WHERE firma = %s AND masina = %s AND piese_json IS NOT NULL
        """, (firma, masina))
        return cur_piese.fetchall()

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
            pdf.cell(100, 6, curata_text(p.get('piesa', '')), 1, 0, 'L')
            pdf.cell(40, 6, str(p.get('cantitate', 1)), 1, 0, 'C')
            pdf.cell(50, 6, curata_text(p.get('tip', '')), 1, 1, 'C')
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
    pdf.cell(95, 5, curata_text("EFECTUAT DE (TEHNICIAN)"), 0, 0, 'C')
    pdf.cell(95, 5, curata_text("VERIFICAT / RECEPTIONAT DE"), 0, 1, 'C')
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(95, 5, curata_text(f"Nume: {data['tehnician'] or 'Tehnician Nexus'}"), 0, 0, 'C')
    pdf.cell(95, 5, curata_text(f"Nume: {data['verificator'] or 'Client'}"), 0, 1, 'C')
    pdf.ln(8)
    pdf.cell(95, 5, curata_text("Semnatura: ___________________"), 0, 0, 'C')
    pdf.cell(95, 5, curata_text("Semnatura: ___________________"), 0, 1, 'C')

    output = pdf.output(dest='S') if hasattr(pdf, 'output') else pdf.output()
    return output if isinstance(output, bytes) else output.encode('latin1', errors='ignore')

# ------------------------------------------------------------------------------
# 5. Background Services Non-Blocking
# ------------------------------------------------------------------------------
def trimite_email_raport(destinatar_client, subiect, corp_mesaj, pdf_bytes, nume_fisier):
    setari = get_setari()
    smtp_srv = setari["smtp_server"]
    smtp_p = setari["smtp_port"]
    smtp_u = setari["smtp_user"]
    smtp_pwd = st.secrets.get("SMTP_PASSWORD", setari["smtp_pass"])
    email_tehnician = setari["email_tehnician"]
    
    msg = EmailMessage()
    msg['Subject'] = subiect
    msg['From'] = smtp_u if smtp_u else "contact@nexusindustrial.ro"
    
    destinatari = []
    if destinatar_client and destinatar_client.strip():
        destinatari.append(destinatar_client.strip())
    if email_tehnician and email_tehnician.strip():
        destinatari.append(email_tehnician.strip())
    destinatari.append("contact@nexusindustrial.ro")
    
    destinatari_unice = list(set([d for d in destinatari if d and d.strip()]))
    msg['To'] = ", ".join(destinatari_unice)
    msg.set_content(corp_mesaj)
    if pdf_bytes:
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=nume_fisier)
    
    try:
        with smtplib.SMTP(smtp_srv, int(smtp_p), timeout=10) as server:
            server.starttls()
            if smtp_pwd and smtp_u:
                server.login(smtp_u, smtp_pwd)
                server.send_message(msg)
    except Exception:
        pass

def update_google_sheet(payload_sheet):
    setari_info = get_setari()
    sheet_url = setari_info['google_sheet_url']
    if sheet_url:
        try:
            req = urllib.request.Request(sheet_url, data=json.dumps(payload_sheet).encode('utf-8'), headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read().decode('utf-8')
        except Exception:
            pass

def background_sync_task(payload_sheet, email_client, subiect, corp_mesaj, pdf_bytes, nume_fisier):
    update_google_sheet(payload_sheet)
    if email_client:
        trimite_email_raport(email_client, subiect, corp_mesaj, pdf_bytes, nume_fisier)

# ------------------------------------------------------------------------------
# 6. Interfața Principală Streamlit & Sidebar
# ------------------------------------------------------------------------------
st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("CMMS Enterprise Dashboard v10.4.5")
st.sidebar.markdown("---")
st.sidebar.info("Conexiune optimizată prin ThreadedConnectionPool & Cache.")

st.title("🛠️ NexInd CMMS Dashboard & Predictive")

tab_dashboard, tab_activitati, tab_optimizare, tab_predictii, tab_masini, tab_piese, tab_firme, tab_rapoarte, tab_setari = st.tabs([
    "📈 0. Dashboard",
    "📝 1. Activități", 
    "📊 2. Documentații / Proceduri", 
    "🔮 3. Predicții",
    "🏭 4. Mașini", 
    "🔧 5. Piese", 
    "📇 6. Firme",
    "📋 7. Istoric",
    "⚙️ 8. Setări"
])

# ------------------------------------------------------------------------------
# TAB 0: Dashboard KPI
# ------------------------------------------------------------------------------
with tab_dashboard:
    st.title("📈 Dashboard CMMS")

    kpi_res = get_dashboard_kpi_data()
    interventii_luna = kpi_res["interventii"] if kpi_res else 0
    ore_lucrate = round(kpi_res["minute"] / 60, 1) if kpi_res else 0
    clienti_activi = kpi_res["clienti"] if kpi_res else 0
    utilaje_active = kpi_res["utilaje"] if kpi_res else 0
    utilaje_oprite = kpi_res["utilaje_oprite"]Iată codul complet și corectat pentru aplicația ta Streamlit (v10.4.5), în care am remediat conflictul de chei duplicate (inclusiv pentru `act_firma` și celelalte elemente din tabul de activități) și am menținut toate funcționalitățile cerute de tine până acum (inclusiv ordinea coloanelor și închiderea panoului de editare din Istoric):

```python
#-----------------------------------------------------------------------------------
# APLICATIE NexInd CMMS Enterprise Dashboard & Predictive v10.4.5
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
# 3. Funcții Optimizate cu Cache Individual, Lazy Loading & KPI Consolidate
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
        cur.execute("SELECT id, firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere FROM masini")
        return cur.fetchall()

@st.cache_data(ttl=300)
def get_masini_firma(firma_id):
    with db_cursor() as c:
        c.execute("""
            SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina 
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
                COUNT(DISTINCT masina) AS utilaje,
                COUNT(*) FILTER (WHERE stare_finala='Oprită / Necesar piese') AS utilaje_oprite
            FROM reparatii
            WHERE DATE_TRUNC('month', data_creare) = DATE_TRUNC('month', CURRENT_DATE)
        """)
        return c.fetchone()

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

@st.cache_data(ttl=300)
def get_predictive_piese_data(firma, masina):
    with db_cursor() as cur_piese:
        cur_piese.execute("""
            SELECT piese_json FROM reparatii
            WHERE firma = %s AND masina = %s AND piese_json IS NOT NULL
        """, (firma, masina))
        return cur_piese.fetchall()

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
            pdf.cell(100, 6, curata_text(p.get('piesa', '')), 1, 0, 'L')
            pdf.cell(40, 6, str(p.get('cantitate', 1)), 1, 0, 'C')
            pdf.cell(50, 6, curata_text(p.get('tip', '')), 1, 1, 'C')
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
    pdf.cell(95, 5, curata_text("EFECTUAT DE (TEHNICIAN)"), 0, 0, 'C')
    pdf.cell(95, 5, curata_text("VERIFICAT / RECEPTIONAT DE"), 0, 1, 'C')
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(95, 5, curata_text(f"Nume: {data['tehnician'] or 'Tehnician Nexus'}"), 0, 0, 'C')
    pdf.cell(95, 5, curata_text(f"Nume: {data['verificator'] or 'Client'}"), 0, 1, 'C')
    pdf.ln(8)
    pdf.cell(95, 5, curata_text("Semnatura: ___________________"), 0, 0, 'C')
    pdf.cell(95, 5, curata_text("Semnatura: ___________________"), 0, 1, 'C')

    output = pdf.output(dest='S') if hasattr(pdf, 'output') else pdf.output()
    return output if isinstance(output, bytes) else output.encode('latin1', errors='ignore')

# ------------------------------------------------------------------------------
# 5. Background Services Non-Blocking
# ------------------------------------------------------------------------------
def trimite_email_raport(destinatar_client, subiect, corp_mesaj, pdf_bytes, nume_fisier):
    setari = get_setari()
    smtp_srv = setari["smtp_server"]
    smtp_p = setari["smtp_port"]
    smtp_u = setari["smtp_user"]
    smtp_pwd = st.secrets.get("SMTP_PASSWORD", setari["smtp_pass"])
    email_tehnician = setari["email_tehnician"]
    
    msg = EmailMessage()
    msg['Subject'] = subiect
    msg['From'] = smtp_u if smtp_u else "contact@nexusindustrial.ro"
    
    destinatari = []
    if destinatar_client and destinatar_client.strip():
        destinatari.append(destinatar_client.strip())
    if email_tehnician and email_tehnician.strip():
        destinatari.append(email_tehnician.strip())
    destinatari.append("contact@nexusindustrial.ro")
    
    destinatari_unice = list(set([d for d in destinatari if d and d.strip()]))
    msg['To'] = ", ".join(destinatari_unice)
    msg.set_content(corp_mesaj)
    if pdf_bytes:
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=nume_fisier)
    
    try:
        with smtplib.SMTP(smtp_srv, int(smtp_p), timeout=10) as server:
            server.starttls()
            if smtp_pwd and smtp_u:
                server.login(smtp_u, smtp_pwd)
                server.send_message(msg)
    except Exception:
        pass

def update_google_sheet(payload_sheet):
    setari_info = get_setari()
    sheet_url = setari_info['google_sheet_url']
    if sheet_url:
        try:
            req = urllib.request.Request(sheet_url, data=json.dumps(payload_sheet).encode('utf-8'), headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read().decode('utf-8')
        except Exception:
            pass

def background_sync_task(payload_sheet, email_client, subiect, corp_mesaj, pdf_bytes, nume_fisier):
    update_google_sheet(payload_sheet)
    if email_client:
        trimite_email_raport(email_client, subiect, corp_mesaj, pdf_bytes, nume_fisier)

# ------------------------------------------------------------------------------
# 6. Interfața Principală Streamlit & Sidebar
# ------------------------------------------------------------------------------
st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("CMMS Enterprise Dashboard v10.4.5")
st.sidebar.markdown("---")
st.sidebar.info("Conexiune optimizată prin ThreadedConnectionPool & Cache.")

st.title("🛠️ NexInd CMMS Dashboard & Predictive")

tab_dashboard, tab_activitati, tab_optimizare, tab_predictii, tab_masini, tab_piese, tab_firme, tab_rapoarte, tab_setari = st.tabs([
    "📈 0. Dashboard",
    "📝 1. Activități", 
    "📊 2. Documentații / Proceduri", 
    "🔮 3. Predicții",
    "🏭 4. Mașini", 
    "🔧 5. Piese", 
    "📇 6. Firme",
    "📋 7. Istoric",
    "⚙️ 8. Setări"
])

# ------------------------------------------------------------------------------
# TAB 0: Dashboard KPI
# ------------------------------------------------------------------------------
with tab_dashboard:
    st.title("📈 Dashboard CMMS")

    kpi_res = get_dashboard_kpi_data()
    interventii_luna = kpi_res["interventii"] if kpi_res else 0
    ore_lucrate = round(kpi_res["minute"] / 60, 1) if kpi_res else 0
    clienti_activi = kpi_res["clienti"] if kpi_res else 0
    utilaje_active = kpi_res["utilaje"] if kpi_res else 0
    utilaje_oprite = kpi_res["utilaje_oprite"] if kpi_res else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🔧 Intervenții luna curentă", interventii_luna)
    c2.metric("⏱ Ore lucrate", ore_lucrate)
    c3.metric("🏢 Clienți activi", clienti_activi)
    c4.metric("⚙️ Utilaje active", utilaje_active)
    c5.metric("🚨 Utilaje Oprite", utilaje_oprite)

    st.markdown("---")

    top_defecte, top_clienti, top_utilaje, defecte_recurente, masini_scadente = get_dashboard_charts_data()

    if top_defecte:
        df_defecte = pd.DataFrame(top_defecte)
        fig_defecte = px.bar(
            df_defecte,
            x="aparitii",
            y="defect",
            orientation="h",
            title="Top 10 Defecte"
        )
        st.plotly_chart(fig_defecte, use_container_width=True, key="grafic_top_defecte_dashboard")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏢 Top Clienți")
        if top_clienti:
            df_clienti = pd.DataFrame(top_clienti)
            fig_clienti = px.bar(
                df_clienti,
                x="interventii",
                y="firma",
                orientation="h",
                title="Top Clienți după număr intervenții"
            )
            st.plotly_chart(fig_clienti, use_container_width=True, key="grafic_top_clienti_dashboard")

    with col2:
        st.subheader("⚙️ Top Utilaje")
        if top_utilaje:
            df_utilaje = pd.DataFrame(top_utilaje)
            fig_utilaje = px.bar(
                df_utilaje,
                x="masina",
                y="interventii",
                title="Top Utilaje după număr intervenții"
            )
            st.plotly_chart(fig_utilaje, use_container_width=True, key="grafic_top_utilaje_dashboard")

    st.markdown("---")

    st.subheader("⚠️ Defecte Recurente (Ultimele 180 zile)")
    if defecte_recurente:
        for d in defecte_recurente:
            st.warning(
                f"""
⚠️ **{d['masina']}**
Defect: {d['defect']}
Număr apariții: {d['repetitii']}
"""
            )
    else:
        st.success("Nu există defecte recurente identificate în ultimele 180 de zile.")

    st.markdown("---")

    st.subheader("📅 Întrețineri Scadente")
    if masini_scadente:
        df_scadente = pd.DataFrame(masini_scadente)
        st.dataframe(df_scadente, use_container_width=True)
    else:
        st.success("Nu există întrețineri programate în următoarele 30 de zile.")

# ------------------------------------------------------------------------------
# TAB 1: Activități Zilnice
# ------------------------------------------------------------------------------
with tab_activitati:
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")
    firme_db_all = get_firme()
    firme_dict_obj = {f['nume_firma']: f for f in firme_db_all}
    firme_activ = list(firme_dict_obj.keys())
    
    if not firme_activ:
        st.warning("⚠️ Adăugați cel puțin o firmă în Tabul de Firme.")
    else:
        sel_firma = st.selectbox("1. Alege Firma la care lucrezi", options=firme_activ, key="act_firma_principal")
        firma_obj = firme_dict_obj[sel_firma]
        persoane_contact_firma = [firma_obj['nume_persoana']] if firma_obj['nume_persoana'] else []
        email_client_destinatar = firma_obj['email'] or ""
        
        masini_firma_db = get_masini_firma(firma_obj['id'])
        masini_firma_nume = [m['denumire'] for m in masini_firma_db]
        
        sel_masina = st.selectbox("2. Alege Mașina / Echipamentul", options=masini_firma_nume if masini_firma_nume else ["Nicio mașină"], key="act_masina_principal")
        
        subansamblu_list = []
        erori_masina = []
        if masini_firma_db and sel_masina != "Nicio mașină":
            match_m = next((m for m in masini_firma_db if m['denumire'] == sel_masina), None)
            if match_m:
                if match_m['subansambluri']:
                    subansamblu_list = [s.strip() for s in match_m['subansambluri'].split(",")]
                if match_m['erori']:
                    erori_masina = [e.strip() for e in match_m['erori'].split(",")]
        
        sel_subansamblu = st.selectbox("3. Alege sau scrie Subansamblul", options=subansamblu_list if subansamblu_list else ["General"], key="act_subansamblu")
        
        c1, c2 = st.columns(2)
        with c1:
            titlu_lucrare = st.text_input("Titlu Lucrare", value="Intervenție tehnică", key="act_titlu")
            simptom = st.text_area("Simptom Inițial Reclamat", key="act_simptom")
            defect = st.text_area("Defect Constatat", key="act_defect")
            cod_eroare = st.selectbox("Cod Eroare", options=["Niciunul"] + erori_masina, key="act_cod_eroare")
        with c2:
            solutie = st.text_area("Soluție / Lucrări Executate", key="act_solutie")
            durata_min = st.number_input("Durată Intervenție (minute)", value=60, step=15, key="act_durata")
            tip_interventie = st.selectbox("Tip Intervenție", ["reparatie", "diagnostic", "consultanta"], key="act_tip_interventie")
            stare_fin = st.selectbox("Stare Finală Echipament", ["Funcțională", "În testare", "Oprită / Necesar piese"], key="act_stare_finala")
            
        st.markdown("##### 🔧 Gestiune Piese (Utilizate / Înlocuite / Necesare)")
        
        if "df_piese_editor" not in st.session_state:
            st.session_state["df_piese_editor"] = pd.DataFrame(columns=["Piesa", "Cantitate", "Tip"])

        piese_catalog_rows = get_piese()
        piese_catalog = [p['denumire'] for p in piese_catalog_rows]

        edited_df = st.data_editor(
            st.session_state["df_piese_editor"],
            num_rows="dynamic",
            column_config={
                "Piesa": st.column_config.SelectboxColumn("Piesă", options=piese_catalog, required=True),
                "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=1, default=1),
                "Tip": st.column_config.SelectboxColumn("Tip / Status", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], required=True)
            },
            key="editor_piese_activitati"
        )
            
        c_tech1, c_tech2 = st.columns(2)
        tehnician_nume = c_tech1.text_input("Nume Tehnician", value="Tehnician Nexus", key="act_tehnician")
        verificator_nume = c_tech2.selectbox("Verificat / Recepționat de", options=persoane_contact_firma if persoane_contact_firma else ["Niciun contact"], key="act_verificator")
        
        opt_recomandari = ""
        with db_cursor() as cur_opt:
            cur_opt.execute("SELECT descriere_pas FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_masina, defect))
            opt_match = cur_opt.fetchone()
            if opt_match:
                opt_recomandari = opt_match['descriere_pas']
            
        optimizari = st.text_area("Recomandări Tehnice", value=opt_recomandari, key="act_optimizari")

        if "raport_salvat" not in st.session_state:
            st.session_state["raport_salvat"] = False
            st.session_state["ultimul_id_salvat"] = None

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("💾 Salvează Activitatea în DB", type="primary", key="btn_salveaza_activitate"):
                piese_valide = edited_df.dropna(subset=["Piesa"]).to_dict(orient="records")
                
                with db_cursor() as c:
                    c.execute("""
                        INSERT INTO reparatii (firma, masina, subansamblu, defect, cod_eroare, piese_json, titlu, simptom, solutie, stare_finala, durata, optimizari, tehnician, verificator, tip_interventie) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (sel_firma, sel_masina, sel_subansamblu, defect, cod_eroare, json.dumps(piese_valide, ensure_ascii=False), titlu_lucrare, simptom, solutie, stare_fin, durata_min, optimizari, tehnician_nume, verificator_nume, tip_interventie))
                    res_ins = c.fetchone()
                    rid_nou = res_ins['id'] if res_ins else None

                if rid_nou:
                    st.session_state["ultimul_id_salvat"] = rid_nou
                    
                    date_pdf_pre = {
                        "id": rid_nou, "client": sel_firma, "masina": sel_masina, "subansamblu": sel_subansamblu,
                        "durata": durata_min, "cod_eroare": cod_eroare, "stare_finala": stare_fin,
                        "piese_json": [{"piesa": p.get("Piesa"), "cantitate": p.get("Cantitate"), "tip": p.get("Tip")} for p in piese_valide],
                        "titlu": titlu_lucrare, "simptom": simptom, "defect": defect, "solutie": solutie,
                        "optimizari": optimizari, "tehnician": tehnician_nume, "verificator": verificator_nume, "data": datetime.now(),
                        "tip_interventie": tip_interventie
                    }
                    pdf_bytes_gen = genereaza_pdf(date_pdf_pre)

                    ore_calc = int(durata_min // 60)
                    minute_calc = int(durata_min % 60)
                    format_durata_text = f"{ore_calc} ore {minute_calc} minute" if ore_calc > 0 else f"{minute_calc} minute"

                    # Mapare corectă conform ordinii cerute în Google Sheets:
                    # A: Stare facturare, B: ID Raport, C: Data, D: Tip Int., E: Durata, F: Firma, G: Masina, H: Subansamblul, I: Piese Utilizate, J: Necesar Piese, K: Verificator, L: Tehnician
                    payload_sheet = {
                        "status": "nefacturat", 
                        "id": str(rid_nou), 
                        "data": datetime.now().strftime("%Y-%m-%d"),
                        "tip_interventie": tip_interventie, 
                        "ora": format_durata_text, 
                        "firma": str(sel_firma), 
                        "masina": str(sel_masina),
                        "subansamblu": str(sel_subansamblu or "General"),
                        "piese utilizate": ", ".join([f"{p.get('Piesa')} ({p.get('Cantitate')})" for p in piese_valide if p.get('Tip') in ['Utilizata', 'Inlocuita']]),
                        "necesar piese": ", ".join([f"{p.get('Piesa')} ({p.get('Cantitate')})" for p in piese_valide if p.get('Tip') in ['Necesara', 'De Comandat']]),
                        "verificator": str(verificator_nume or ""), 
                        "tehnician": str(tehnician_nume or "")
                    }

                    threading.Thread(
                        target=background_sync_task,
                        args=(payload_sheet, email_client_destinatar, f"Raport #{rid_nou} - {sel_firma}", f"Vă atașăm raportul #{rid_nou}.", pdf_bytes_gen, f"Raport_{rid_nou}.pdf"),
                        daemon=True
                    ).start()

                st.session_state["raport_salvat"] = True
                st.success("Activitatea a fost salvată!")
                st.rerun()
                
        if st.session_state["raport_salvat"] and st.session_state["ultimul_id_salvat"]:
            rid = st.session_state["ultimul_id_salvat"]
            with db_cursor() as cur_rep:
                cur_rep.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare, tip_interventie FROM reparatii WHERE id=%s", (rid,))
                full_rep_salvat = cur_rep.fetchone()

            if full_rep_salvat:
                date_pdf = {
                    "id": full_rep_salvat['id'], "client": full_rep_salvat['firma'], "masina": full_rep_salvat['masina'], "subansamblu": full_rep_salvat['subansamblu'],
                    "durata": full_rep_salvat['durata'], "cod_eroare": full_rep_salvat['cod_eroare'], "stare_finala": full_rep_salvat['stare_finala'], "piese_json": json.loads(full_rep_salvat['piese_json']) if full_rep_salvat['piese_json'] else [],
                    "titlu": full_rep_salvat['titlu'], "simptom": full_rep_salvat['simptom'], "defect": full_rep_salvat['defect'], "solutie": full_rep_salvat['solutie'],
                    "optimizari": full_rep_salvat['optimizari'], "tehnician": full_rep_salvat['tehnician'], "verificator": full_rep_salvat['verificator'], "data": full_rep_salvat['data_creare'],
                    "tip_interventie": full_rep_salvat.get('tip_interventie') or "reparatie"
                }
                with col_b2:
                    if st.button("Generează PDF", key="btn_genereaza_pdf_activitati"):
                        st.session_state["pdf_bytes_curent"] = genereaza_pdf(date_pdf)
                    if "pdf_bytes_curent" in st.session_state and st.session_state["pdf_bytes_curent"]:
                        st.download_button(label=f"📥 Descarcă Raport #{rid}", data=st.session_state["pdf_bytes_curent"], file_name=f"Raport_{rid}.pdf", mime="application/pdf", type="primary", key="dl_pdf_activitati")
                with col_b3:
                    st.info("E-mailul și Google Sheet s-au sincronizat în fundal.")

# ------------------------------------------------------------------------------
# TAB 2: Documentații / Proceduri de reparații
# ------------------------------------------------------------------------------
with tab_optimizare:
    st.subheader("📊 Documentații / Proceduri de reparații")
    masini_existente = [m['denumire'] for m in get_masini()]
    
    if not masini_existente:
        st.warning("⚠️ Adăugați mașini în Tabul aferent.")
    else:
        sel_opt_masina = st.selectbox("Selectează Mașina", options=masini_existente, key="opt_m_sel")
        
        with db_cursor() as cur_d:
            cur_d.execute("SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = %s", (sel_opt_masina,))
            defecte_existente = [row['defect'] for row in cur_d.fetchall() if row['defect']]
        
        opțiuni_defecte = ["+ Defect nou (scrie mai jos)"] + defecte_existente
        sel_opt_defect_complet = st.selectbox("Selectează sau creează Defectul / Procedura", options=opțiuni_defecte, key="select_defect_unificat")
        
        if sel_opt_defect_complet == "+ Defect nou (scrie mai jos)":
            def_final = st.text_input("Introduceți descrierea pentru defectul / procedura nouă *", key="input_defect_nou_text")
        else:
            def_final = sel_opt_defect_complet
            
        st.markdown("---")
        
        if sel_opt_defect_complet != "+ Defect nou (scrie mai jos)" and sel_opt_defect_complet:
            st.markdown(f"##### 🔎 Editare Pași de Reparație existenți pentru: **{sel_opt_defect_complet}**")
            with db_cursor() as cur_p:
                cur_p.execute("SELECT id, pas_numar, descriere_pas FROM optimizari_interventie WHERE masina = %s AND defect = %s ORDER BY pas_numar", (sel_opt_masina, sel_opt_defect_complet))
                pasii_db = cur_p.fetchall()
            
            with st.form(f"form_edita_pasi_{sel_opt_masina}_{sel_opt_defect_complet}"):
                pasi_editati_dict = {pe['id']: st.text_input(f"Pasul {pe['pas_numar']}", value=pe['descriere_pas'], key=f"edit_pas_db_{pe['id']}") for pe in pasii_db}
                col_ep1, col_ep2 = st.columns(2)
                with col_ep1:
                    if st.form_submit_button("🔄 Actualizează Pașii"):
                        with db_cursor() as c:
                            for pid_pas, val_noua in pasi_editati_dict.items():
                                c.execute("UPDATE optimizari_interventie SET descriere_pas = %s WHERE id = %s", (val_noua, pid_pas))
                        st.success("Pașii au fost actualizați cu succes!")
                        st.rerun()
                with col_ep2:
                    if st.form_submit_button("🗑️ Șterge Toată Procedura"):
                        with db_cursor() as c:
                            c.execute("DELETE FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_opt_masina, sel_opt_defect_complet))
                        st.success("Procedura a fost ștearsă!")
                        st.rerun()
            st.markdown("---")
            
        st.markdown(f"##### ➕ Adaugă Pași Noi pentru: **{def_final if def_final else 'Nefinit'}**")
        if "pasi_lucrare_t" not in st.session_state:
            st.session_state["pasi_lucrare_t"] = []
            
        with st.form("form_add_pas", clear_on_submit=True):
            desc_p_nou = st.text_area("Descriere pas remediu nou", key="desc_pas_nou_input")
            if st.form_submit_button("➕ Adaugă Pas în Memorie"):
                if desc_p_nou:
                    st.session_state["pasi_lucrare_t"].append(desc_p_nou)
                    st.success("Pas adăugat în listă!")
                    st.rerun()
                    
        if st.session_state["pasi_lucrare_t"]:
            st.write("Pași adăugați pregătiți pentru salvare:")
            pasi_modificati = [st.text_input(f"Pas nou {idx+1}", value=pval, key=f"pas_ed_{idx}") for idx, pval in enumerate(st.session_state["pasi_lucrare_t"])]
            if st.button("💾 Salvează Toți Pașii Noi în Baza de Date", type="primary", key="btn_salveaza_toti_pasii_noi"):
                if def_final and def_final.strip() != "":
                    with db_cursor() as cur_mx:
                        cur_mx.execute("SELECT MAX(pas_numar) as max_p FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_opt_masina, def_final))
                        max_p = cur_mx.fetchone()
                    
                    start_nr = (max_p['max_p'] if max_p and max_p['max_p'] else 0) + 1
                    with db_cursor() as c:
                        for idx, pval in enumerate(pasi_modificati):
                            c.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (%s, %s, %s, %s)", (sel_opt_masina, def_final, start_nr + idx, pval))
                    st.session_state["pasi_lucrare_t"] = []
                    st.success("Pașii noi au fost salvați în Supabase!")
                    st.rerun()
                else:
                    st.error("Introduceți sau selectați un defect valid înainte de salvare.")

# ------------------------------------------------------------------------------
# TAB 3: Predicții & Mentenanță Predictivă
# ------------------------------------------------------------------------------
with tab_predictii:
    st.subheader("🔮 Tab Predicții & Analiză Mentenanță Preventivă (Health Score)")
    st.markdown("Selectează firma și mașina dorită pentru a calcula indicele de sănătate (Health Score) și a analiza defectele recurente.")

    firme_list_pred = get_firme()
    nume_firme_pred = [f['nume_firma'] for f in firme_list_pred]

    if not nume_firme_pred:
        st.warning("⚠️ Nu există firme înregistrate în baza de date.")
    else:
        p1, p2 = st.columns(2)
        with p1:
            sel_firma_pred = st.selectbox("Selectează Firma", options=nume_firme_pred, key="pred_firma")
        
        firma_obj_pred = next((f for f in firme_list_pred if f['nume_firma'] == sel_firma_pred), None)
        masini_firma_pred = get_masini_firma(firma_obj_pred['id']) if firma_obj_pred else []
        nume_masini_pred = [m['denumire'] for m in masini_firma_pred]

        with p2:
            sel_masina_pred = st.selectbox("Selectează Mașina", options=nume_masini_pred if nume_masini_pred else ["Nicio mașină disponibilă"], key="pred_masina")

        st.markdown("---")

        if sel_masina_pred and sel_masina_pred != "Nicio mașină disponibilă":
            with db_cursor() as cur_pred:
                cur_pred.execute("""
                    SELECT defect, COUNT(*) as frecventa, MAX(data_creare) as ultima_aparitie, 
                           ARRAY_AGG(DISTINCT subansamblu) as subansambluri_afectate
                    FROM reparatii
                    WHERE firma = %s AND masina = %s AND defect IS NOT NULL AND defect != ''
                    GROUP BY defect
                    ORDER BY frecventa DESC
                """, (sel_firma_pred, sel_masina_pred))
                defecte_recurente = cur_pred.fetchall()

                cur_pred.execute("""
                    SELECT COUNT(*) as oprite
                    FROM reparatii
                    WHERE firma = %s AND masina = %s AND stare_finala = 'Oprită / Necesar piese'
                """, (sel_firma_pred, sel_masina_pred))
                res_oprite = cur_pred.fetchone()
                utilaj_oprit_count = res_oprite['oprite'] if res_oprite else 0

            score = 100
            for d in defecte_recurente:
                frecv = d['frecventa']
                score -= (frecv * 5)
                if frecv >= 3:
                    score -= 10
            
            if utilaj_oprit_count > 0:
                score -= (utilaj_oprit_count * 15)
            
            score = max(0, min(100, score))

            st.markdown(f"### 🛡️ Index de Sănătate Echipament (Health Score): **{sel_masina_pred}**")
            col_sc1, col_sc2 = st.columns([2, 1])
            with col_sc1:
                st.progress(score / 100)
            with col_sc2:
                if score >= 90:
                    st.success(f"🟢 Health Score: {score}% (Excelent)")
                elif score >= 70:
                    st.info(f"🟡 Health Score: {score}% (Bun)")
                elif score >= 50:
                    st.warning(f"🟠 Health Score: {score}% (Atenție)")
                else:
                    st.error(f"🔴 Health Score: {score}% (Risc Ridicat)")

            st.markdown("---")
            st.markdown(f"### 📈 Analiză Defecte Recurente pentru: **{sel_masina_pred}** ({sel_firma_pred})")

            if defecte_recurente:
                for index, d in enumerate(defecte_recurente):
                    frecventa = d['frecventa']
                    ultima = str(d['ultima_aparitie'])[:10]
                    subansambluri = ", ".join([str(s) for s in d['subansambluri_afectate'] if s])

                    if frecventa >= 3:
                        st.error(
                            f"🚨 **Alertă Critică (Defect Recurent Frecvent):** \"{d['defect']}\"\n\n"
                            f"- **Număr apariții:** {frecventa} intervenții\n"
                            f"- **Ultima semnalare:** {ultima}\n"
                            f"- **Subansamblu vizat:** {subansambluri or 'General'}\n\n"
                            f"💡 *Recomandare de mentenanță predictivă:* Acest defect s-a repetat de {frecventa} ori. Se recomandă revizia capitală a subansamblului sau înlocuirea completă a piesei uzate pentru a preveni o oprire neplanificată!"
                        )
                    elif frecventa == 2:
                        st.warning(
                            f"⚠️ **Atenționare (Defect Repetat):** \"{d['defect']}\"\n\n"
                            f"- **Număr apariții:** {frecventa} intervenții\n"
                            f"- **Ultima semnalare:** {ultima}\n"
                            f"- **Subansamblu vizat:** {subansambluri or 'General'}\n\n"
                            f"💡 *Recomandare:* Monitorizați îndeaproape acest component la următoarea inspecție periodică."
                        )
                    else:
                        st.info(
                            f"ℹ️ **Defect izolat:** \"{d['defect']}\" (Apărut o singură dată la data de {ultima})."
                        )
            else:
                st.success("✅ Nu există defecte recurente înregistrate pentru această mașină. Echipamentul are un istoric stabil.")

            st.markdown("---")
            st.markdown(f"### 🔩 Istoric Consum Piese / Necesare pentru: **{sel_masina_pred}**")
            
            reparatii_piese = get_predictive_piese_data(sel_firma_pred, sel_masina_pred)

            total_piese_consum = {}
            for rep in reparatii_piese:
                try:
                    p_list = json.loads(rep['piese_json']) if isinstance(rep['piese_json'], str) else rep['piese_json']
                    if isinstance(p_list, list):
                        for p in p_list:
                            nume_p = p.get('piesa') or p.get('Piesa')
                            cant = int(p.get('cantitate') or p.get('Cantitate') or 1)
                            tip_p = p.get('tip') or p.get('Tip') or 'Utilizata'
                            if nume_p and nume_p != "Selectează...":
                                if nume_p not in total_piese_consum:
                                    total_piese_consum[nume_p] = {"cantitate": 0, "tip": tip_p}
                                total_piese_consum[nume_p]["cantitate"] += cant
                except Exception:
                    pass

            if total_piese_consum:
                df_predictii_piese = pd.DataFrame([
                    {"Denumire Piesă": k, "Cantitate Totală Consumată/Solicitată": v["cantitate"], "Ultimul Status": v["tip"]}
                    for k, v in total_piese_consum.items()
                ])
                st.dataframe(df_predictii_piese, use_container_width=True)
            else:
                st.info("Nu există piese înregistrate în istoricul intervențiilor pentru acest echipament.")
        else:
            st.info("Vă rugăm să selectați o mașină validă pentru a vizualiza predicțiile.")

# ------------------------------------------------------------------------------
# TAB 4: Mașini
# ------------------------------------------------------------------------------
with tab_masini:
    st.subheader("🏭 Gestiune Mașini și Echipamente")
    firme_list = get_firme()
    firme_dict = {f['nume_firma']: f['id'] for f in firme_list}
    
    m_firma = st.selectbox("Selectează Firma Proprietară", options=["Nicio firmă"] + list(firme_dict.keys()), key="select_firma_principal_masini")
    
    st.markdown("---")
    st.subheader("➕ Adaugă Mașină Nouă")
    with st.form("form_masini", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            m_denumire = st.text_input("Denumire Mașină *")
            m_tip = st.text_input("Tip Mașină")
            m_serie = st.text_input("Număr Serie")
            m_an = st.number_input("An Fabricație", min_value=1950, max_value=2050, value=2020)
        with c2:
            m_sub = st.text_input("Subansambluri (separate prin virgulă)")
            m_erori = st.text_input("Erori (separate prin virgulă)")
            m_data_ment = st.date_input("Data Întreținere Planificată")
            m_tip_ment = st.selectbox("Tip Întreținere", ["Lunară", "Semestrială", "Anuală"])
            
        m_defecte = st.text_area("Defecte (Memo)")
        m_remediu = st.text_area("Remediu aferent (Memo)")
        m_piese_nec = st.text_area("Piese Necesare")
        m_piese_inloc = st.text_area("Piese Înlocuite")
        m_fluide = st.text_area("Tipuri de Fluide")
        
        if st.form_submit_button("💾 Salvează Mașina"):
            if m_firma != "Nicio firmă" and m_denumire:
                firma_id = firme_dict[m_firma]
                with db_cursor() as c:
                    if m_defecte and m
