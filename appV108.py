#-----------------------------------------------------------------------------------
# APLICATIE NexInd CMMS Enterprise Dashboard & Predictive v10.4.6
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
        cur.execute("SELECT id, firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere, stare_utilaj, data_inceput_oprire, motiv_oprire FROM masini")
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
        
        # Luăm stările direct din tabelul masini
        c.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE stare_utilaj = 'Activă') AS active,
                COUNT(*) FILTER (WHERE stare_utilaj = 'Oprită (Defect / Piese)') AS oprite_defect,
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
st.sidebar.text("CMMS Enterprise Dashboard v10.4.6")
st.sidebar.markdown("---")
st.sidebar.info("Conexiune optimizată prin ThreadedConnectionPool & Cache.")

st.title("🛠️ NexInd CMMS Dashboard & Predictive")

# REORGANIZARE TABURI: Istoricul este acum în Tabul 2, iar Procedurile/Optimizările în Tabul 3
tab_dashboard, tab_activitati, tab_istoric, tab_predictii, tab_masini, tab_piese, tab_firme, tab_setari = st.tabs([
    "📈 0. Dashboard",
    "📝 1. Activități", 
    "📋 2. Istoric", 
    "🔮 3. Predicții",
    "🏭 4. Mașini & Stări", 
    "🔧 5. Piese", 
    "📇 6. Firme",
    "⚙️ 7. Setări"
])

# ------------------------------------------------------------------------------
# TAB 0: Dashboard KPI & Stare Echipamente
# ------------------------------------------------------------------------------
with tab_dashboard:
    st.title("📈 Dashboard CMMS & Stare Echipamente")

    kpi_res_rep, kpi_res_masini = get_dashboard_kpi_data()
    interventii_luna = kpi_res_rep["interventii"] if kpi_res_rep else 0
    ore_lucrate = round(kpi_res_rep["minute"] / 60, 1) if kpi_res_rep else 0
    clienti_activi = kpi_res_rep["clienti"] if kpi_res_rep else 0
    
    utilaje_active = kpi_res_masini["active"] if kpi_res_masini else 0
    oprite_defect = kpi_res_masini["oprite_defect"] if kpi_res_masini else 0
    oprite_intretinere = kpi_res_masini["oprite_intretinere"] if kpi_res_masini else 0
    total_utilaje = kpi_res_masini["total_utilaje"] if kpi_res_masini else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🔧 Intervenții lună", interventii_luna)
    c2.metric("⏱ Ore lucrate", ore_lucrate)
    c3.metric("🏢 Clienți", clienti_activi)
    c4.metric("🟢 Active", utilaje_active)
    c5.metric("🔴 Oprite (Defect/Piese)", oprite_defect)
    c6.metric("🟡 Oprite (Mentenanță)", oprite_intretinere)

    st.markdown("---")

    # Secțiune dedicată pentru vizualizarea clară a stării echipamentelor
    st.subheader("📊 Situație Detaliată Echipamente (Active / Oprite / Întreținere)")
    with db_cursor() as cur_stare:
        cur_stare.execute("""
            SELECT m.denumire, f.nume_firma, m.stare_utilaj, m.data_inceput_oprire, m.motiv_oprire 
            FROM masini m 
            JOIN firme f ON m.firma_id = f.id 
            ORDER BY m.stare_utilaj DESC, m.denumire
        """)
        toate_masinile_stare = cur_stare.fetchall()

    if toate_masinile_stare:
        df_stari = pd.DataFrame(toate_masinile_stare)
        df_stari.columns = ["Mașină", "Firmă / Client", "Stare Curentă", "Data Început Oprire", "Motiv / Detalii Oprire"]
        st.dataframe(df_stari, use_container_width=True)
    else:
        st.info("Nu există mașini înregistrate.")

    st.markdown("---")

    top_defecte, top_clienti, top_utilaje, defecte_recurente, masini_scadente = get_dashboard_charts_data()

    if top_defecte:
        df_defecte = pd.DataFrame(top_defecte)
        fig_defecte = px.bar(df_defecte, x="aparitii", y="defect", orientation="h", title="Top 10 Defecte")
        st.plotly_chart(fig_defecte, use_container_width=True, key="grafic_top_defecte_dashboard")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏢 Top Clienți")
        if top_clienti:
            df_clienti = pd.DataFrame(top_clienti)
            fig_clienti = px.bar(df_clienti, x="interventii", y="firma", orientation="h", title="Top Clienți după număr intervenții")
            st.plotly_chart(fig_clienti, use_container_width=True, key="grafic_top_clienti_dashboard")

    with col2:
        st.subheader("⚙️ Top Utilaje")
        if top_utilaje:
            df_utilaje = pd.DataFrame(top_utilaje)
            fig_utilaje = px.bar(df_utilaje, x="masina", y="interventii", title="Top Utilaje după număr intervenții")
            st.plotly_chart(fig_utilaje, use_container_width=True, key="grafic_top_utilaje_dashboard")

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
        sel_firma = st.selectbox("1. Alege Firma la care lucrezi", options=firme_activ, key="act_firma_principal_tab1")
        firma_obj = firme_dict_obj[sel_firma]
        persoane_contact_firma = [firma_obj['nume_persoana']] if firma_obj['nume_persoana'] else []
        email_client_destinatar = firma_obj['email'] or ""
        
        masini_firma_db = get_masini_firma(firma_obj['id'])
        masini_firma_nume = [m['denumire'] for m in masini_firma_db]
        
        sel_masina = st.selectbox("2. Alege Mașina / Echipamentul", options=masini_firma_nume if masini_firma_nume else ["Nicio mașină"], key="act_masina_tab1")
        
        subansamblu_list = []
        erori_masina = []
        if masini_firma_db and sel_masina != "Nicio mașină":
            match_m = next((m for m in masini_firma_db if m['denumire'] == sel_masina), None)
            if match_m:
                if match_m['subansambluri']:
                    subansamblu_list = [s.strip() for s in match_m['subansambluri'].split(",")]
                if match_m['erori']:
                    erori_masina = [e.strip() for e in match_m['erori'].split(",")]
        
        sel_subansamblu = st.selectbox("3. Alege sau scrie Subansamblul", options=subansamblu_list if subansamblu_list else ["General"], key="act_subansamblu_tab1")
        
        c1, c2 = st.columns(2)
        with c1:
            titlu_lucrare = st.text_input("Titlu Lucrare", value="Intervenție tehnică", key="act_titlu_tab1")
            simptom = st.text_area("Simptom Inițial Reclamat", key="act_simptom_tab1")
            defect = st.text_area("Defect Constatat", key="act_defect_tab1")
            cod_eroare = st.selectbox("Cod Eroare", options=["Niciunul"] + erori_masina, key="act_cod_eroare_tab1")
        with c2:
            solutie = st.text_area("Soluție / Lucrări Executate", key="act_solutie_tab1")
            durata_min = st.number_input("Durată Intervenție (minute)", value=60, step=15, key="act_durata_tab1")
            tip_interventie = st.selectbox("Tip Intervenție", ["reparatie", "diagnostic", "consultanta"], key="act_tip_interv_tab1")
            stare_fin = st.selectbox("Stare Finală Echipament", ["Funcțională", "În testare", "Oprită / Necesar piese"], key="act_stare_fin_tab1")
            
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
            key="editor_piese_activitati_tab1"
        )
            
        c_tech1, c_tech2 = st.columns(2)
        tehnician_nume = c_tech1.text_input("Nume Tehnician", value="Tehnician Nexus", key="act_tehnician_tab1")
        verificator_nume = c_tech2.selectbox("Verificat / Recepționat de", options=persoane_contact_firma if persoane_contact_firma else ["Niciun contact"], key="act_verificator_tab1")
        
        optimizari = st.text_area("Recomandări Tehnice", key="act_recomandari_tab1")

        if "raport_salvat" not in st.session_state:
            st.session_state["raport_salvat"] = False
            st.session_state["ultimul_id_salvat"] = None

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("💾 Salvează Activitatea în DB", type="primary", key="btn_salveaza_activitate_tab1"):
                piese_valide = edited_df.dropna(subset=["Piesa"]).to_dict(orient="records")
                
                with db_cursor() as c:
                    c.execute("""
                        INSERT INTO reparatii (firma, masina, subansamblu, defect, cod_eroare, piese_json, titlu, simptom, solutie, stare_finala, durata, optimizari, tehnician, verificator, tip_interventie) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (sel_firma, sel_masina, sel_subansamblu, defect, cod_eroare, json.dumps(piese_valide, ensure_ascii=False), titlu_lucrare, simptom, solutie, stare_fin, durata_min, optimizari, tehnician_nume, verificator_nume, tip_interventie))
                    res_ins = c.fetchone()
                    rid_nou = res_ins['id'] if res_ins else None

                    # Dacă starea finală e oprită, actualizăm automat și starea mașinii în tabelul masini
                    if stare_fin == "Oprită / Necesar piese":
                        c.execute("""
                            UPDATE masini SET stare_utilaj = 'Oprită (Defect / Piese)', data_inceput_oprire = CURRENT_DATE, motiv_oprire = %s 
                            WHERE denumire = %s
                        """, (defect, sel_masina))
                    elif stare_fin == "Funcțională":
                        c.execute("""
                            UPDATE masini SET stare_utilaj = 'Activă', data_inceput_oprire = NULL, motiv_oprire = NULL 
                            WHERE denumire = %s
                        """, (sel_masina,))

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

                    payload_sheet = {
                        "status": "nefacturat", "id": str(rid_nou), "data": datetime.now().strftime("%Y-%m-%d"),
                        "tip_interventie": tip_interventie, "ora": format_durata_text, "firma": str(sel_firma), "masina": str(sel_masina),
                        "subansamblu": str(sel_subansamblu or "General"),
                        "piese utilizate": ", ".join([f"{p.get('Piesa')} ({p.get('Cantitate')})" for p in piese_valide if p.get('Tip') in ['Utilizata', 'Inlocuita']]),
                        "necesar piese": ", ".join([f"{p.get('Piesa')} ({p.get('Cantitate')})" for p in piese_valide if p.get('Tip') in ['Necesara', 'De Comandat']]),
                        "verificator": str(verificator_nume or ""), "tehnician": str(tehnician_nume or "")
                    }

                    threading.Thread(
                        target=background_sync_task,
                        args=(payload_sheet, email_client_destinatar, f"Raport #{rid_nou} - {sel_firma}", f"Vă atașăm raportul #{rid_nou}.", pdf_bytes_gen, f"Raport_{rid_nou}.pdf"),
                        daemon=True
                    ).start()

                st.session_state["raport_salvat"] = True
                st.success("Activitatea a fost salvată și starea mașinii a fost actualizată!")
                st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: Istoric Intervenții (Mutat aici conform cerinței)
# ------------------------------------------------------------------------------
with tab_istoric:
    st.subheader("📋 Istoric Intervenții & Căutare Avansată")
    
    with st.expander("🔍 Căutare și Filtrare Rapoarte", expanded=True):
        firme_list_istoric = get_firme()
        nume_firme_opt = ["Toate firmele"] + [f['nume_firma'] for f in firme_list_istoric]
        
        masini_list_istoric = get_masini()
        nume_masini_opt = ["Toate mașinile"] + [m['denumire'] for m in masini_list_istoric]
        
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            filtru_firma = st.selectbox("Filtrează după Firmă", options=nume_firme_opt, key="filtru_ist_firma_tab2")
        with fc2:
            filtru_masina = st.selectbox("Filtrează după Mașină", options=nume_masini_opt, key="filtru_ist_masina_tab2")
        with fc3:
            foloseste_data = st.checkbox("Filtrează după o dată specifică", value=False, key="filtru_ist_check_data_tab2")
            filtru_data = st.date_input("Data intervenție", value=date.today(), key="filtru_ist_data_tab2") if foloseste_data else None

    query_str = "SELECT id, firma, masina, data_creare FROM reparatii WHERE 1=1"
    query_params = []

    if filtru_firma != "Toate firmele":
        query_str += " AND firma = %s"
        query_params.append(filtru_firma)
        
    if filtru_masina != "Toate mașinile":
        query_str += " AND masina = %s"
        query_params.append(filtru_masina)
        
    if foloseste_data and filtru_data:
        query_str += " AND DATE(data_creare) = %s"
        query_params.append(filtru_data)

    query_str += " ORDER BY id DESC LIMIT 100"

    with db_cursor() as cur_hist:
        cur_hist.execute(query_str, tuple(query_params))
        lista_reparatii_sumar = cur_hist.fetchall()
    
    st.markdown(f"**Rezultate găsite:** {len(lista_reparatii_sumar)} rapoarte")
    
    if lista_reparatii_sumar:
        opțiuni_select_raport = {f"Raport #{r['id']} | {r['firma']} - {r['masina']} ({str(r['data_creare'])[:10]})": r['id'] for r in lista_reparatii_sumar}
        
        raport_ales_str = st.selectbox("Selectează Raportul dorit pentru Vizualizare / Modificare", options=list(opțiuni_select_raport.keys()), key="select_raport_istoric_tab2")
        selected_rid = opțiuni_select_raport[raport_ales_str]
        
        with db_cursor() as cur_full:
            cur_full.execute("SELECT * FROM reparatii WHERE id = %s", (selected_rid,))
            full_rep = cur_full.fetchone()
            
        if full_rep:
            rid = full_rep['id']
            rfirma = full_rep['firma']
            rmas = full_rep['masina']
            rsub = full_rep['subansamblu']
            rdef = full_rep['defect']
            rcod_err = full_rep['cod_eroare']
            rpiese_json = full_rep['piese_json']
            rtit = full_rep['titlu']
            rsimp = full_rep['simptom']
            rsol = full_rep['solutie']
            rstare = full_rep['stare_finala']
            rdurata = full_rep['durata']
            ropt = full_rep['optimizari']
            rtech = full_rep['tehnician']
            rverif = full_rep['verificator']
            rdata = full_rep['data_creare']
            rtip_int = full_rep.get('tip_interventie') or "reparatie"
            
            with st.form(f"form_mod_istoric_{rid}"):
                st.markdown(f"##### ✏️ Modificare Raport #{rid}")
                em_titlu = st.text_input("Titlu Lucrare", value=rtit or "", key=f"em_tit_{rid}")
                em_simptom = st.text_area("Simptom Inițial", value=rsimp or "", key=f"em_simp_{rid}")
                em_defect = st.text_area("Defect Constatat", value=rdef or "", key=f"em_def_{rid}")
                em_solutie = st.text_area("Soluție / Lucrări Executate", value=rsol or "", key=f"em_sol_{rid}")
                
                c_e1, c_e2 = st.columns(2)
                with c_e1:
                    em_durata = st.number_input("Durată (minute)", value=int(rdurata) if rdurata else 60, key=f"em_dur_{rid}")
                    em_stare = st.selectbox("Stare Finală", ["Funcțională", "În testare", "Oprită / Necesar piese"], index=0 if rstare=="Funcțională" else 1, key=f"em_sta_{rid}")
                with c_e2:
                    em_tech = st.text_input("Tehnician", value=rtech or "", key=f"em_tec_{rid}")
                    em_verif = st.text_input("Verificator / Client", value=rverif or "", key=f"em_ver_{rid}")

                if st.form_submit_button("💾 Salvează Modificările Raportului"):
                    with db_cursor() as c:
                        c.execute("""
                            UPDATE reparatii 
                            SET titlu = %s, simptom = %s, defect = %s, solutie = %s, durata = %s, stare_finala = %s, tehnician = %s, verificator = %s
                            WHERE id = %s
                        """, (em_titlu, em_simptom, em_defect, em_solutie, em_durata, em_stare, em_tech, em_verif, rid))
                    st.success(f"Raportul #{rid} a fost actualizat!")
                    st.rerun()

            piese_data = json.loads(rpiese_json) if rpiese_json else []
            date_pdf = {
                "id": rid, "client": rfirma, "masina": rmas, "subansamblu": rsub, "durata": rdurata,
                "cod_eroare": rcod_err, "stare_finala": rstare, "piese_json": piese_data,
                "titlu": rtit, "simptom": rsimp, "defect": rdef, "solutie": rsol, "optimizari": ropt,
                "tehnician": rtech, "verificator": rverif, "data": rdata, "tip_interventie": rtip_int
            }
            if st.button(f"Generează PDF pentru Raport #{rid}", key=f"btn_pdf_{rid}"):
                pdf_b = genereaza_pdf(date_pdf)
                st.download_button(label=f"📥 Descarcă PDF Raport #{rid}", data=pdf_b, file_name=f"Raport_{rid}.pdf", mime="application/pdf", key=f"dl_{rid}")
    else:
        st.info("Nu există rapoarte înregistrate.")

# ------------------------------------------------------------------------------
# TAB 3: Predicții & Mentenanță
# ------------------------------------------------------------------------------
with tab_predictii:
    st.subheader("🔮 Tab Predicții & Analiză Mentenanță Preventivă")
    firme_list_pred = get_firme()
    nume_firme_pred = [f['nume_firma'] for f in firme_list_pred]

    if not nume_firme_pred:
        st.warning("⚠️ Nu există firme înregistrate.")
    else:
        p1, p2 = st.columns(2)
        sel_firma_pred = p1.selectbox("Selectează Firma", options=nume_firme_pred, key="pred_firma_tab3")
        firma_obj_pred = next((f for f in firme_list_pred if f['nume_firma'] == sel_firma_pred), None)
        masini_firma_pred = get_masini_firma(firma_obj_pred['id']) if firma_obj_pred else []
        nume_masini_pred = [m['denumire'] for m in masini_firma_pred]
        sel_masina_pred = p2.selectbox("Selectează Mașina", options=nume_masini_pred if nume_masini_pred else ["Nicio mașină"], key="pred_masina_tab3")

        if sel_masina_pred and sel_masina_pred != "Nicio mașină":
            st.success(f"Echipament selectat pentru analiză: **{sel_masina_pred}**")

# ------------------------------------------------------------------------------
# TAB 4: Mașini & Control Stări (Active / Oprite / Întreținere)
# ------------------------------------------------------------------------------
with tab_masini:
    st.subheader("🏭 Gestiune Mașini, Echipamente & Stări Operative")
    firme_list = get_firme()
    firme_dict = {f['nume_firma']: f['id'] for f in firme_list}
    
    m_firma = st.selectbox("Filtrează / Alege Firma Proprietară", options=["Toate firmele"] + list(firme_dict.keys()), key="select_firma_masini_tab4")
    
    st.markdown("---")
    st.subheader("➕ Adaugă Mașină Nouă")
    with st.form("form_masini", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            m_denumire = st.text_input("Denumire Mașină *")
            m_tip = st.text_input("Tip Mașină")
            m_serie = st.text_input("Număr Serie")
            m_an = st.number_input("An Fabricație", min_value=1950, max_value=2050, value=2020)
            m_stare_noua = st.selectbox("Stare Inițială Echipament", ["Activă", "Oprită (Defect / Piese)", "Oprită pentru întreținere"])
        with c2:
            m_sub = st.text_input("Subansambluri (separate prin virgulă)")
            m_erori = st.text_input("Erori (separate prin virgulă)")
            m_data_ment = st.date_input("Data Întreținere Planificată")
            m_motiv_oprire_nou = st.text_input("Motiv / DetALII Oprire (dacă e oprită)")
            m_data_oprire = st.date_input("Data Început Oprire (dacă e cazul)")
            
        if st.form_submit_button("💾 Salvează Mașina"):
            if m_firma != "Toate firmele" and m_denumire:
                firma_id = firme_dict[m_firma]
                with db_cursor() as c:
                    c.execute("""
                        INSERT INTO masini (firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, data_intretinere, stare_utilaj, data_inceput_oprire, motiv_oprire) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (firma_id, m_denumire, m_tip, m_serie, m_an, m_sub, m_erori, str(m_data_ment), m_stare_noua, str(m_data_oprire) if m_stare_noua != "Activă" else None, m_motiv_oprire_nou if m_stare_noua != "Activă" else None))
                get_masini.clear()
                st.success(f"Mașina **{m_denumire}** a fost salvată!")
                st.rerun()
            else:
                st.error("Selectați o firmă din lista specifică și introduceți denumirea mașinii.")

    st.markdown("---")
    st.subheader("📋 Modificare Stare & Setări Mașini Existente")
    
    with db_cursor() as cur:
        if m_firma != "Toate firmele":
            cur.execute("SELECT m.*, f.nume_firma FROM masini m JOIN firme f ON m.firma_id = f.id WHERE m.firma_id = %s", (firme_dict[m_firma],))
        else:
            cur.execute("SELECT m.*, f.nume_firma FROM masini m JOIN firme f ON m.firma_id = f.id")
        masini_db = cur.fetchall()

    for m in masini_db:
        stare_curenta = m['stare_utilaj'] if m.get('stare_utilaj') else "Activă"
        culoare_icon = "🟢" if stare_curenta == "Activă" else ("🔴" if "Defect" in stare_curenta else "🟡")
        
        with st.expander(f"{culoare_icon} {m['denumire']} | Stare: {stare_curenta} (Firma: {m['nume_firma']})"):
            with st.form(f"mod_masina_{m['id']}"):
                mm_den = st.text_input("Denumire", value=m['denumire'], key=f"mm_d_{m['id']}")
                
                stari_disponibile = ["Activă", "Oprită (Defect / Piese)", "Oprită pentru întreținere"]
                idx_stare = stari_disponibile.index(stare_curenta) if stare_curenta in stari_disponibile else 0
                mm_stare = st.selectbox("Schimbă Starea Echipamentului", options=stari_disponibile, index=idx_stare, key=f"mm_stare_{m['id']}")
                
                mm_data_oprire = st.date_input("Data Început Oprire / Mentenanță", value=datetime.strptime(str(m['data_inceput_oprire']), "%Y-%m-%d").date() if m.get('data_inceput_oprire') else date.today(), key=f"mm_d_op_{m['id']}")
                mm_motiv = st.text_input("Motiv Oprire / Detalii", value=m['motiv_oprire'] or "", key=f"mm_mot_{m['id']}")
                
                mm_sub = st.text_input("Subansambluri", value=m['subansambluri'] or "", key=f"mm_sub_{m['id']}")
                
                col_mm1, col_mm2 = st.columns(2)
                with col_mm1:
                    if st.form_submit_button("🔄 Actualizează Stare & Detalii"):
                        with db_cursor() as c:
                            c.execute("""
                                UPDATE masini 
                                SET denumire=%s, stare_utilaj=%s, data_inceput_oprire=%s, motiv_oprire=%s, subansambluri=%s
                                WHERE id=%s
                            """, (mm_den, mm_stare, str(mm_data_oprire) if mm_stare != "Activă" else None, mm_motiv if mm_stare != "Activă" else None, mm_sub, m['id']))
                        get_masini.clear()
                        st.success("Starea mașinii a fost actualizată!")
                        st.rerun()
                with col_mm2:
                    if st.form_submit_button("🗑️ Șterge Mașina"):
                        with db_cursor() as c:
                            c.execute("DELETE FROM masini WHERE id=%s", (m['id'],))
                        get_masini.clear()
                        st.success("Mașina a fost ștearsă!")
                        st.rerun()

# ------------------------------------------------------------------------------
# TAB 5: Piese
# ------------------------------------------------------------------------------
with tab_piese:
    st.subheader("🔧 Gestiune Piese de Schimb")
    masini_existente = [m['denumire'] for m in get_masini()]
    select_masina_unica = st.selectbox("Selectează Mașina", options=["Toate mașinile / General"] + masini_existente, key="sel_piese_t5")
    st.info("Folosește acest tab pentru catalogul de piese.")

# ------------------------------------------------------------------------------
# TAB 6: Firme
# ------------------------------------------------------------------------------
with tab_firme:
    st.subheader("📇 Gestiune Firme și Persoane de Contact")
    firme_db = get_firme()
    for f in firme_db:
        st.write(f"- **{f['nume_firma']}** (Contact: {f['nume_persoana']} | Tel: {f['telefon']})")

# ------------------------------------------------------------------------------
# TAB 7: Setări
# ------------------------------------------------------------------------------
with tab_setari:
    st.subheader("⚙️ Setări Aplicație & Conectare")
    current_setari = get_setari()
    st.text(f"Firma Curentă Setată: {current_setari['nume_firma_mea']}")
