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
    page_title="Nexus Industrial Software",
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
        self.cell(0, 10, 'Pagina ' + str(self.page_no()) + ' | Generat automat - Nexus Industrial Software', 0, 0, 'C')

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
    pdf.cell(90, 7, curata_text(f"Data: {str(data.get('data', datetime.now()))[:10]}"), 0, 1, 'R')
    
    pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
    pdf.ln(6)

    pdf.set_fill_color(*BG_LIGHT)
    pdf.rect(10, pdf.get_y(), 190, 24, 'F')
    
    pdf.set_xy(12, pdf.get_y() + 2)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(90, 6, curata_text("BENEFICIAR / CLIENT"), 0, 0)
    pdf.cell(90, 6, curata_text("ECHIPAMENT / DETALII"), 0, 1)
    
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)
    
    pdf.set_x(12)
    pdf.cell(90, 5, curata_text(f"Client: {data.get('client', 'Nespecificat')}"), 0, 0)
    pdf.cell(90, 5, curata_text(f"Echipament: {data.get('masina', 'General')}"), 0, 1)
    
    pdf.ln(8)

    if titlu_doc in ["Deviz", "Oferta de pret"]:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*SECONDARY)
        pdf.cell(0, 6, curata_text("TABEL PIESE / SERVICII OFERTATE (LEI)"), 0, 1)
        pdf.set_draw_color(*SECONDARY)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(80, 6, curata_text("Denumire Piesă / Serviciu"), 1, 0, 'C', fill=True)
        pdf.cell(25, 6, curata_text("Cantitate"), 1, 0, 'C', fill=True)
        pdf.cell(40, 6, curata_text("Preț Unitar (LEI)"), 1, 0, 'C', fill=True)
        pdf.cell(45, 6, curata_text("Valoare (LEI)"), 1, 1, 'C', fill=True)
        
        pdf.set_font('Helvetica', '', 9)
        piese_list = data.get('piese_json', [])
        subtotal_val = 0
        if piese_list:
            for p in piese_list:
                p_nume = p.get('piesa', '')
                p_cant = p.get('cantitate', 1)
                p_pret_ron = p.get('pret_iesire', 0) * curs_bnr_val
                p_val = p_cant * p_pret_ron
                subtotal_val += p_val
                
                pdf.cell(80, 6, curata_text(p_nume), 1, 0, 'L')
                pdf.cell(25, 6, str(p_cant), 1, 0, 'C')
                pdf.cell(40, 6, f"{p_pret_ron:.2f}", 1, 0, 'R')
                pdf.cell(45, 6, f"{p_val:.2f}", 1, 1, 'R')
        else:
            pdf.cell(190, 6, curata_text("Nici o piesă adăugată"), 1, 1, 'C')
        pdf.ln(2)
        
        tva_procent = data.get('tva_procent', 21.0)
        val_tva = subtotal_val * (tva_procent / 100.0)
        total_general = subtotal_val + val_tva
        
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(145, 6, curata_text("Subtotal (LEI):"), 1, 0, 'R')
        pdf.cell(45, 6, f"{subtotal_val:.2f}", 1, 1, 'R')
        pdf.cell(145, 6, curata_text(f"TVA ({tva_procent}%):"), 1, 0, 'R')
        pdf.cell(45, 6, f"{val_tva:.2f}", 1, 1, 'R')
        pdf.cell(145, 6, curata_text("TOTAL GENERAL CU TVA (LEI):"), 1, 0, 'R')
        pdf.cell(45, 6, f"{total_general:.2f}", 1, 1, 'R')
        pdf.ln(6)
        
        if data.get('memo'):
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*SECONDARY)
            pdf.cell(0, 5, curata_text("TERMENI ȘI CONDIȚII / MENȚIUNI"), 0, 1)
            pdf.set_font('Helvetica', '', 8)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 4, curata_text(data.get('memo')))
    else:
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

        adauga_sectiune("Titlu Lucrare", data.get('titlu', ''))
        adauga_sectiune("Simptom / Soluție", f"Simptom: {data.get('simptom','')} | Soluție: {data.get('solutie','')}")
        
    try:
        output = pdf.output()
    except TypeError:
        output = pdf.output(dest='S')

    if isinstance(output, bytes):
        return output
    elif isinstance(output, bytearray):
        return bytes(output)
    elif isinstance(output, str):
        return output.encode('latin1')
    else:
        return str(output).encode('latin1', errors='ignore')

# ------------------------------------------------------------------------------
# 4. Funcție Trimitere Email prin SMTP
# ------------------------------------------------------------------------------
def trimite_email_raport(destinatar_client, subiect, corp_mesaj, pdf_bytes, nume_fisier):
    setari = get_setari()
    smtp_srv = setari[7]
    smtp_p = setari[8]
    smtp_u = setari[9]
    smtp_pwd = setari[10]
    email_tehnician = setari[12] if len(setari) > 12 else ""
    
    msg = EmailMessage()
    msg['Subject'] = subiect
    msg['From'] = smtp_u if smtp_u else "contact@nexusindustrial.ro"
    
    destinatari = [destinatar_client]
    if email_tehnician:
        destinatari.append(email_tehnician)
    destinatari.append("contact@nexusindustrial.ro")
    
    destinatari_unice = [d.strip() for d in destinatari if d and d.strip()]
    msg['To'] = ", ".join(destinatari_unice)
    msg.set_content(corp_mesaj)
    
    if pdf_bytes:
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=nume_fisier)
    
    try:
        with smtplib.SMTP(smtp_srv, int(smtp_p)) as server:
            server.starttls()
            if smtp_pwd and smtp_u:
                server.login(smtp_u, smtp_pwd)
                server.send_message(msg)
                return True, f"E-mailul a fost trimis cu succes către: {', '.join(destinatari_unice)}"
            else:
                return False, "Setările SMTP (User sau Parolă) nu sunt completate."
    except Exception as e:
        return False, f"Eroare conexiune SMTP ({str(e)})"

# ------------------------------------------------------------------------------
# 5. Interfața Principală Streamlit & Sidebar
# ------------------------------------------------------------------------------
st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("Sistem integrat activ")

if st.sidebar.button("🛑 Închide Serverul Python", type="primary", key="inchide_server_btn"):
    st.sidebar.warning("Se închide serverul...")
    os._exit(0)

st.sidebar.markdown("---")
st.sidebar.info("Aplicație optimizată pentru mobil și desktop.")

st.title("Nexus Industrial Software")

tab_activitati, tab_optimizare, tab_masini, tab_piese, tab_firme, tab_deviz, tab_rapoarte, tab_setari = st.tabs([
    "📝 1. Activități", 
    "📊 2. Optimizare", 
    "🏭 3. Mașini", 
    "🔧 4. Piese", 
    "📇 5. Firme",
    "🧮 6. Deviz & Ofertă",
    "📋 7. Istoric",
    "⚙️ 8. Setări"
])

# ------------------------------------------------------------------------------
# TAB 5: Nomenclator Firme
# ------------------------------------------------------------------------------
with tab_firme:
    st.subheader("📇 Gestiune Firme și Persoane de Contact")
    conn = get_db_connection()
    c = conn.cursor()
    
    with st.form("form_firme", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nume_firma = st.text_input("Nume Firmă / Client *")
            cui = st.text_input("CUI")
            reg_com = st.text_input("Nr. Reg. Com.")
            adresa = st.text_input("Adresă Sediu")
        with c2:
            banca = st.text_input("Bancă")
            cont = st.text_input("Cont (IBAN)")
            nume_persoana = st.text_input("Persoană de Contact *")
            email = st.text_input("Adresă E-mail Contact *")
            telefon = st.text_input("Telefon")
            
        if st.form_submit_button("💾 Salvează Firmă Nouă"):
            if nume_firma and nume_persoana and email:
                c.execute("""
                    INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon))
                conn.commit()
                st.success(f"Firma **{nume_firma}** a fost salvată în Supabase!")
                st.rerun()
            else:
                st.error("Completați câmpurile obligatorii (*).")

    st.markdown("---")
    st.subheader("📋 Firme Înregistrate (Modificare & Ștergere)")
    c.execute("SELECT id, nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon FROM firme")
    firme_db = c.fetchall()
    
    for f in firme_db:
        fid, fnume, fcui, freg, fadr, fbanca, fcont, fpers, femail, ftel = f
        with st.expander(f"🏢 {fnume} (CUI: {fcui or 'N/A'}) - Contact: {fpers}"):
            with st.form(f"mod_firma_{fid}"):
                mf_nume = st.text_input("Nume Firmă", value=fnume, key=f"mf_n_{fid}")
                mf_cui = st.text_input("CUI", value=fcui or "", key=f"mf_cui_{fid}")
                mf_reg = st.text_input("Reg. Com.", value=freg or "", key=f"mf_reg_{fid}")
                mf_adr = st.text_input("Adresă", value=fadr or "", key=f"mf_adr_{fid}")
                mf_banca = st.text_input("Bancă", value=fbanca or "", key=f"mf_b_{fid}")
                mf_cont = st.text_input("Cont", value=fcont or "", key=f"mf_cont_{fid}")
                mf_pers = st.text_input("Persoană Contact", value=fpers, key=f"mf_p_{fid}")
                
