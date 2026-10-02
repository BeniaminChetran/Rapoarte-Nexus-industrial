#-----------------------------------------------------------------------------------
#------------------Descriere--------------------------------------------------------
# Aceasta este varianta optimizată pentru Streamlit și SQLite
#-----------------------------------------------------------------------------------

import os
import json
import sqlite3
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
# CONFIGURARE CONEXIUNE (PostgreSQL / Supabase fallback)
# ------------------------------------------------------------------------------
def get_db_connection():
    db_url = st.secrets.get("DATABASE_URL", "postgresql://postgres:PAROLA_TA@db.PROIECT_ID.supabase.co:5432/postgres")
    conn = psycopg2.connect(db_url)
    return conn

# ------------------------------------------------------------------------------
# 1. Configurare Pagină & Stil UI (Optimizat și pentru Mobil)
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Nexus Industrial - Sistem Mentenanță",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "reparatii.db"

# ------------------------------------------------------------------------------
# 2. Inițializare Bază de Date SQLite (Tabele Multiple)
# ------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    
    # 1. Tabel Firme / Clienti & Date Fiscale & Persoana Contact
    c.execute('''
        CREATE TABLE IF NOT EXISTS firme (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            masina TEXT,
            defect TEXT,
            pas_numar INTEGER,
            descriere_pas TEXT
        )
    ''')
    
    # 5. Tabel Activități Zilnice / Rapoarte Intervenție
    c.execute('''
        CREATE TABLE IF NOT EXISTS reparatii (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    if c.execute("SELECT COUNT(*) FROM setari").fetchone()[0] == 0:
        default_sheet = "https://script.google.com/macros/s/AKfycbx5bRsK0NGZY2VmlyMS3BqUZzoAiIPwmFMsuLYo10_WQSThN6kgeL3MkugFNvxxTRxbBQ/exec"
        c.execute("""
            INSERT INTO setari (nume_firma_mea, cui_mea, adresa_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Nexus Industrial SRL", "", "", "smtp.gmail.com", 587, "nexusindustrialsrl@gmail.com", "unjz fjle jljm lrxn", default_sheet))
    
    conn.commit()
    conn.close()

init_db()

def get_setari():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    res = conn.execute("SELECT nume_firma_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url FROM setari LIMIT 1").fetchone()
    conn.close()
    if res:
        return res
    return ("Nexus Industrial SRL", "smtp.gmail.com", 587, "nexusindustrialsrl@gmail.com", "unjz fjle jljm lrxn", "https://script.google.com/macros/s/AKfycbx5bRsK0NGZY2VmlyMS3BqUZzoAiIPwmFMsuLYo10_WQSThN6kgeL3MkugFNvxxTRxbBQ/exec")

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
    pdf.cell(90, 7, curata_text(f"Data: {data['data'][:10]}"), 0, 1, 'R')
    pdf.line(10, 35, 200, 35)
    pdf.ln(3)

    pdf.set_fill_color(*BG_LIGHT)
    pdf.rect(10, 38, 190, 32, 'F')
    
    pdf.set_xy(12, 40)
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
    pdf.cell(90, 5, curata_text(f"Durata: {data['durata']} minute"), 0, 0)
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

    pdf.set_y(-45)
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

    output = pdf.output()
    return output if isinstance(output, bytes) else bytes(output, 'latin1')

# ------------------------------------------------------------------------------
# 4. Funcție Trimitere Email prin SMTP
# ------------------------------------------------------------------------------
def trimite_email_raport(destinatar, subiect, corp_mesaj, pdf_bytes, nume_fisier):
    _, smtp_srv, smtp_p, smtp_u, smtp_pwd, _ = get_setari()
    
    msg = EmailMessage()
    msg['Subject'] = subiect
    msg['From'] = "contact@nexusindustrial.ro"
    msg['To'] = destinatar
    msg.set_content(corp_mesaj)
    
    if pdf_bytes:
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=nume_fisier)
    
    try:
        with smtplib.SMTP(smtp_srv, int(smtp_p)) as server:
            server.starttls()
            if smtp_pwd:
                server.login(smtp_u, smtp_pwd)
                server.send_message(msg)
                return True, "E-mailul a fost trimis cu succes!"
            else:
                return False, "Parola SMTP nu este setată."
    except Exception as e:
        return False, f"Eroare conexiune SMTP ({str(e)})"

# ------------------------------------------------------------------------------
# 5. Interfața Principală Streamlit & Sidebar
# ------------------------------------------------------------------------------
st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("Drive: nexusindustrialsrl@gmail.com")

if st.sidebar.button("🛑 Închide Serverul Python", type="primary"):
    st.sidebar.warning("Se închide serverul...")
    os._exit(0)

st.sidebar.markdown("---")
st.sidebar.info("Aplicație optimizată pentru mobil și desktop.")

st.title("🛠️ Sistem Integrat de Mentenanță - Nexus Industrial")

tab_activitati, tab_optimizare, tab_masini, tab_piese, tab_firme, tab_rapoarte, tab_setari = st.tabs([
    "📝 1. Activități", 
    "📊 2. Optimizare", 
    "🏭 3. Mașini", 
    "🔧 4. Piese", 
    "📇 5. Firme",
    "📋 6. Istoric",
    "⚙️ 7. Setări"
])

# ------------------------------------------------------------------------------
# TAB 5: Nomenclator Firme
# ------------------------------------------------------------------------------
with tab_firme:
    st.subheader("📇 Gestiune Firme și Persoane de Contact")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    
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
                conn.execute("""
                    INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon))
                conn.commit()
                st.success(f"Firma **{nume_firma}** a fost salvată!")
                st.rerun()
            else:
                st.error("Completați câmpurile obligatorii (*).")

    st.markdown("---")
    st.subheader("📋 Firme Înregistrate (Modificare & Ștergere)")
    firme_db = conn.execute("SELECT id, nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon FROM firme").fetchall()
    
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
                mf_email = st.text_input("Email", value=femail, key=f"mf_e_{fid}")
                mf_tel = st.text_input("Telefon", value=ftel or "", key=f"mf_t_{fid}")
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    if st.form_submit_button("🔄 Modifică Tot"):
                        conn.execute("""
                            UPDATE firme SET nume_firma=?, cui=?, reg_com=?, adresa=?, banca=?, cont=?, nume_persoana=?, email=?, telefon=?
                            WHERE id=?
                        """, (mf_nume, mf_cui, mf_reg, mf_adr, mf_banca, mf_cont, mf_pers, mf_email, mf_tel, fid))
                        conn.commit()
                        st.success("Firma a fost actualizată!")
                        st.rerun()
                with col_m2:
                    if st.form_submit_button("🗑️ Șterge Firma"):
                        conn.execute("DELETE FROM firme WHERE id=?", (fid,))
                        conn.commit()
                        st.success("Firma a fost ștearsă!")
                        st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 3: Lista Mașini & Subansambluri
# ------------------------------------------------------------------------------
with tab_masini:
    st.subheader("🏭 Gestiune Mașini și Echipamente")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    firme_list = conn.execute("SELECT id, nume_firma FROM firme").fetchall()
    firme_dict = {f[1]: f[0] for f in firme_list}
    
    with st.form("form_masini", clear_on_submit=True):
        m_firma = st.selectbox("Selectează Firma Proprietară", options=list(firme_dict.keys()) if firme_dict else ["Nicio firmă"])
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
                if m_defecte and m_remediu:
                    conn.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (?, ?, ?, ?)",
                                 (m_denumire, m_defecte, 1, m_remediu))
                
                conn.execute("""
                    INSERT INTO masini (firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (firma_id, m_denumire, m_tip, m_serie, m_an, m_sub, m_erori, m_defecte, m_remediu, m_piese_nec, m_piese_inloc, m_fluide, str(m_data_ment), m_tip_ment))
                conn.commit()
                st.success(f"Mașina **{m_denumire}** a fost salvată!")
                st.rerun()
            else:
                st.error("Selectați o firmă și introduceți denumirea mașinii.")

    st.markdown("---")
    st.subheader("📋 Mașini Înregistrate (Modificare & Ștergere)")
    masini_db = conn.execute("""
        SELECT m.id, f.nume_firma, m.denumire, m.tip_masina, m.serie, m.an_fabricatie, m.subansambluri, m.erori, m.defecte, m.remediu, m.piese_necesare, m.piese_inlocuite, m.tipuri_fluide, m.tip_intretinere 
        FROM masini m JOIN firme f ON m.firma_id = f.id
    """).fetchall()
    
    for m in masini_db:
        mid, mfirma, mden, mtip, mser, man, msub, meri, mdef, mrem, mpnec, mpinl, mflu, mtipm = m
        with st.expander(f"⚙️ {mden} (Firma: {mfirma})"):
            with st.form(f"mod_masina_{mid}"):
                mm_den = st.text_input("Denumire", value=mden, key=f"mm_d_{mid}")
                mm_tip = st.text_input("Tip", value=mtip or "", key=f"mm_tip_{mid}")
                mm_ser = st.text_input("Serie", value=mser or "", key=f"mm_ser_{mid}")
                mm_an = st.number_input("An", value=int(man) if man else 2020, key=f"mm_an_{mid}")
                mm_sub = st.text_input("Subansambluri", value=msub or "", key=f"mm_sub_{mid}")
                mm_eri = st.text_input("Erori", value=meri or "", key=f"mm_eri_{mid}")
                mm_def = st.text_area("Defecte", value=mdef or "", key=f"mm_def_{mid}")
                mm_rem = st.text_area("Remediu", value=mrem or "", key=f"mm_rem_{mid}")
                mm_pnec = st.text_area("Piese Necesare", value=mpnec or "", key=f"mm_pnec_{mid}")
                mm_pinl = st.text_area("Piese Înlocuite", value=mpinl or "", key=f"mm_pinl_{mid}")
                mm_flu = st.text_area("Fluide", value=mflu or "", key=f"mm_flu_{mid}")
                mm_tipm = st.selectbox("Tip Întreținere", ["Lunară", "Semestrială", "Anuală"], index=0, key=f"mm_tipm_{mid}")
                
                col_mm1, col_mm2 = st.columns(2)
                with col_mm1:
                    if st.form_submit_button("🔄 Modifică Tot"):
                        conn.execute("""
                            UPDATE masini SET denumire=?, tip_masina=?, serie=?, an_fabricatie=?, subansambluri=?, erori=?, defecte=?, remediu=?, piese_necesare=?, piese_inlocuite=?, tipuri_fluide=?, tip_intretinere=?
                            WHERE id=?
                        """, (mm_den, mm_tip, mm_ser, mm_an, mm_sub, mm_eri, mm_def, mm_rem, mm_pnec, mm_pinl, mm_flu, mm_tipm, mid))
                        conn.commit()
                        st.success("Mașină actualizată!")
                        st.rerun()
                with col_mm2:
                    if st.form_submit_button("🗑️ Șterge Mașina"):
                        conn.execute("DELETE FROM masini WHERE id=?", (mid,))
                        conn.commit()
                        st.success("Mașina a fost ștearsă!")
                        st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 1: Activități Zilnice
# ------------------------------------------------------------------------------
with tab_activitati:
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    
    firme_db_all = conn.execute("SELECT id, nume_firma, nume_persoana, email FROM firme").fetchall()
    firme_activ = [f[1] for f in firme_db_all]
    
    if not firme_activ:
        st.warning("⚠️ Adăugați cel puțin o firmă în Tabul 5.")
    else:
        sel_firma = st.selectbox("1. Alege Firma la care lucrezi", options=firme_activ, key="act_firma")
        
        persoane_contact_firma = [f[2] for f in firme_db_all if f[1] == sel_firma]
        email_client_destinatar = [f[3] for f in firme_db_all if f[1] == sel_firma][0] if firme_db_all else "nexusindustrialsrl@gmail.com"
        
        masini_firma = [row[0] for row in conn.execute("SELECT m.denumire FROM masini m JOIN firme f ON m.firma_id = f.id WHERE f.nume_firma = ?", (sel_firma,)).fetchall()]
        sel_masina = st.selectbox("2. Alege Mașina / Echipamentul", options=masini_firma if masini_firma else ["Nicio mașină"], key="act_masina")
        
        subansamblu_list = []
        if masini_firma and sel_masina != "Nicio mașină":
            sub_db = conn.execute("SELECT subansambluri FROM masini WHERE denumire = ?", (sel_masina,)).fetchone()
            if sub_db and sub_db[0]:
                subansamblu_list = [s.strip() for s in sub_db[0].split(",")]
        
        sel_subansamblu = st.selectbox("3. Alege sau scrie Subansamblul", options=subansamblu_list if subansamblu_list else ["General"])
        
        c1, c2 = st.columns(2)
        with c1:
            titlu_lucrare = st.text_input("Titlu Lucrare", value="Intervenție tehnică")
            simptom = st.text_area("Simptom Inițial Reclamat")
            defect = st.text_area("Defect Constatat")
            
            erori_masina = []
            if masini_firma and sel_masina != "Nicio mașină":
                e_db = conn.execute("SELECT erori FROM masini WHERE denumire = ?", (sel_masina,)).fetchone()
                if e_db and e_db[0]:
                    erori_masina = [e.strip() for e in e_db[0].split(",")]
            cod_eroare = st.selectbox("Cod Eroare", options=["Niciunul"] + erori_masina)
            
        with c2:
            solutie = st.text_area("Soluție / Lucrări Executate")
            durata_min = st.number_input("Durată Intervenție (minute)", value=60, step=15)
            stare_fin = st.selectbox("Stare Finală Echipament", ["Funcțională", "În testare", "Oprită / Necesar piese"])
            
        st.markdown("##### Gestiune Piese")
        if "randuri_piese" not in st.session_state:
            st.session_state["randuri_piese"] = [{"piesa": "", "cantitate": 1, "tip": "Utilizata"}]
            
        piese_catalog = [row[0] for row in conn.execute("SELECT denumire FROM piese").fetchall()]
        
        for idx, rp in enumerate(st.session_state["randuri_piese"]):
            cols_p = st.columns([3, 1, 2, 1])
            with cols_p[0]:
                st.session_state["randuri_piese"][idx]["piesa"] = st.selectbox(f"Piesă #{idx+1}", options=["Selectează..."] + piese_catalog, key=f"p_sel_{idx}")
            with cols_p[1]:
                st.session_state["randuri_piese"][idx]["cantitate"] = st.number_input("Cant.", min_value=1, value=rp["cantitate"], key=f"p_cant_{idx}")
            with cols_p[2]:
                st.session_state["randuri_piese"][idx]["tip"] = st.selectbox("Tip", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], key=f"p_tip_{idx}")
            with cols_p[3]:
                if st.button("❌ Șterg", key=f"del_p_{idx}"):
                    st.session_state["randuri_piese"].pop(idx)
                    st.rerun()
                    
        if st.button("➕ Adaugă altă piesă"):
            st.session_state["randuri_piese"].append({"piesa": "", "cantitate": 1, "tip": "Utilizata"})
            st.rerun()
            
        c_tech1, c_tech2 = st.columns(2)
        tehnician_nume = c_tech1.text_input("Nume Tehnician", value="Tehnician Nexus")
        verificator_nume = c_tech2.selectbox("Verificat / Recepționat de", options=persoane_contact_firma if persoane_contact_firma else ["Niciun contact"])
        
        opt_recomandari = ""
        opt_match = conn.execute("SELECT descriere_pas FROM optimizari_interventie WHERE masina = ? AND defect = ?", (sel_masina, defect)).fetchone()
        if opt_match:
            opt_recomandari = opt_match[0]
            
        optimizari = st.text_area("Recomandări Tehnice", value=opt_recomandari)

        if "raport_salvat" not in st.session_state:
            st.session_state["raport_salvat"] = False
            st.session_state["ultimul_id_salvat"] = None

        col_b1, col_b2, col_b3 = st.columns(3)
        
        with col_b1:
            if st.button("💾 Salvează Activitatea în DB", type="primary"):
                piese_valide = [p for p in st.session_state["randuri_piese"] if p["piesa"] != "Selectează..."]
                conn.execute("""
                    INSERT INTO reparatii (firma, masina, subansamblu, defect, cod_eroare, piese_json, titlu, simptom, solutie, stare_finala, durata, optimizari, tehnician, verificator)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (sel_firma, sel_masina, sel_subansamblu, defect, cod_eroare, json.dumps(piese_valide, ensure_ascii=False), titlu_lucrare, simptom, solutie, stare_fin, durata_min, optimizari, tehnician_nume, verificator_nume))
                conn.commit()
                
                ultima_inreg = conn.execute("SELECT id FROM reparatii ORDER BY id DESC LIMIT 1").fetchone()
                if ultima_inreg:
                    st.session_state["ultimul_id_salvat"] = ultima_inreg[0]
                    
                st.session_state["raport_salvat"] = True
                st.success("Activitatea a fost salvată în baza de date!")
                st.rerun()
                
        if st.session_state["raport_salvat"] and st.session_state["ultimul_id_salvat"]:
            rid = st.session_state["ultimul_id_salvat"]
            
            full_rep_salvat = conn.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare FROM reparatii WHERE id=?", (rid,)).fetchone()
            
            if full_rep_salvat:
                rdata = full_rep_salvat[15]
                piese_data_salvate = json.loads(full_rep_salvat[7]) if full_rep_salvat[7] else []
                
                date_pdf = {
                    "id": full_rep_salvat[0], "client": full_rep_salvat[1], "masina": full_rep_salvat[2], "subansamblu": full_rep_salvat[3],
                    "durata": full_rep_salvat[4], "cod_eroare": full_rep_salvat[5], "stare_finala": full_rep_salvat[6], "piese_json": piese_data_salvate,
                    "titlu": full_rep_salvat[8], "simptom": full_rep_salvat[9], "defect": full_rep_salvat[10], "solutie": full_rep_salvat[11],
                    "optimizari": full_rep_salvat[12], "tehnician": full_rep_salvat[13], "verificator": full_rep_salvat[14], "data": rdata
                }
                pdf_bytes = genereaza_pdf(date_pdf)
                
                with col_b2:
                    st.download_button(
                        label=f"📥 Printează / Descarcă Raport #{rid}",
                        data=pdf_bytes,
                        file_name=f"Raport_Interventie_{rid}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                    
                with col_b3:
                    if st.button("📧 Trimite pe Email către Verificator"):
                        subiect = f"Raport de Interventie Tehnica #{rid} - {sel_firma}"
                        corp = f"Stimate beneficiar ({verificator_nume}),\n\nVă atașăm raportul de intervenție tehnică #{rid} pentru echipamentul {sel_masina}.\n\nEchipa Nexus Industrial"
                        
                        success, msg = trimite_email_raport(email_client_destinatar, subiect, corp, pdf_bytes, f"Raport_{rid}.pdf")
                        if success:
                            st.success(msg)
                            setari_info = get_setari()
                            sheet_url = setari_info[5]
                            if sheet_url:
                                try:
                                    ora_curenta = datetime.now().strftime("%H:%M:%S")
                                    piese_utilizate_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_data_salvate if p.get('tip') in ['Utilizata', 'Inlocuita']])
                                    piese_necesare_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_data_salvate if p.get('tip') in ['Necesara', 'De Comandat']])
                                    
                                    payload_sheet = {
                                        "id": str(rid), "data": str(rdata)[:10], "ora": str(ora_curenta),
                                        "firma": str(sel_firma), "masina": str(sel_masina),
                                        "subansamblu": str(sel_subansamblu or "General"), "solutie": str(solutie or ""),
                                        "verificator": str(verificator_nume or ""), "tehnician": str(tehnician_nume or ""),
                                        "piese utilizate": str(piese_utilizate_str), "necesar piese": str(piese_necesare_str)
                                    }
                                    req_data = json.dumps(payload_sheet).encode('utf-8')
                                    req = urllib.request.Request(sheet_url, data=req_data, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
                                    with urllib.request.urlopen(req) as response:
                                        response.read().decode('utf-8')
                                        st.success("Datele au fost trimise cu succes și în Google Sheet!")
                                except Exception as e:
                                    st.error(f"Eroare la Google Sheet: {str(e)}")
                        else:
                            st.error(msg)
    conn.close()

# ------------------------------------------------------------------------------
# TAB 2: Baza de Optimizare
# ------------------------------------------------------------------------------
with tab_optimizare:
    st.subheader("📊 Baza de Cunoștințe & Optimizare Intervenții")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    masini_existente = [row[0] for row in conn.execute("SELECT denumire FROM masini").fetchall()]
    
    if not masini_existente:
        st.warning("⚠️ Introduceți mai întâi mașini în Tabul 3.")
    else:
        sel_opt_masina = st.selectbox("Selectează Mașina", options=masini_existente, key="opt_m_sel")
        defecte_existente = [row[0] for row in conn.execute("SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = ?", (sel_opt_masina,)).fetchall() if row[0]]
        sel_opt_defect = st.selectbox("Selectează Defectul", options=defecte_existente + ["+ Defect nou"])
        
        def_final = st.text_area("Descriere Defect Nou") if sel_opt_defect == "+ Defect nou" else sel_opt_defect
            
        if sel_opt_defect != "+ Defect nou" and sel_opt_defect:
            st.markdown(f"##### 🔎 Pași existenți:")
            pasii_db = conn.execute("SELECT id, pas_numar, descriere_pas FROM optimizari_interventie WHERE masina = ? AND defect = ?", (sel_opt_masina, sel_opt_defect)).fetchall()
            for pe in pasii_db:
                st.info(f"Pasul {pe[1]}: {pe[2]}")
            st.markdown("---")
            
        st.markdown("##### Adăugare Pași Noi")
        if "pasi_lucrare_t" not in st.session_state:
            st.session_state["pasi_lucrare_t"] = []
            
        with st.form("form_add_pas", clear_on_submit=True):
            desc_p_nou = st.text_area("Descriere pas remediu nou")
            if st.form_submit_button("➕ Adaugă Pas în Listă"):
                if desc_p_nou:
                    st.session_state["pasi_lucrare_t"].append(desc_p_nou)
                    st.success("Pas adăugat!")
                    st.rerun()
                    
        if st.session_state["pasi_lucrare_t"]:
            pasi_modificati = [st.text_input(f"Pasul {idx+1}", value=pval, key=f"pas_ed_{idx}") for idx, pval in enumerate(st.session_state["pasi_lucrare_t"])]
                
            if st.button("💾 Salvează Toți Pașii în Baza de Date", type="primary"):
                if def_final:
                    for idx, pval in enumerate(pasi_modificati):
                        conn.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (?, ?, ?, ?)",
                                     (sel_opt_masina, def_final, idx+1, pval))
                    conn.commit()
                    st.session_state["pasi_lucrare_t"] = []
                    st.success("Pașii au fost salvați!")
                    st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 4: Tabelul de Piese
# ------------------------------------------------------------------------------
with tab_piese:
    st.subheader("🔧 Gestiune Piese de Schimb")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    masini_existente = [row[0] for row in conn.execute("SELECT denumire FROM masini").fetchall()]
    
    with st.form("form_piese", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            p_denumire = st.text_input("Denumire Piesă *")
            p_cod_prod = st.text_input("Cod Producător")
            p_cod_com = st.text_input("Cod Comercial")
        with c2:
            p_masini_alese = st.multiselect("Mașinile pe care se montează", options=masini_existente)
            p_sub = st.text_input("Subansamblu")
            p_pret = st.number_input("Preț Achiziție (RON)", min_value=0.0, value=0.0)
            
        if st.form_submit_button("💾 Salvează Piesa"):
            if p_denumire:
                masini_text_str = ", ".join(p_masini_alese) if p_masini_alese else "General"
                conn.execute("""
                    INSERT INTO piese (denumire, cod_producator, cod_comercial, masina_montaj, subansamblu, pret_achizitie)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (p_denumire, p_cod_prod, p_cod_com, masini_text_str, p_sub, p_pret))
                conn.commit()
                st.success(f"Piesa **{p_denumire}** a fost salvată!")
                st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 6: Istoric & Google Sheet
# ------------------------------------------------------------------------------
with tab_rapoarte:
    st.subheader("📋 Istoric Intervenții")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    reparatii_db = conn.execute("SELECT id, firma, masina, titlu, data_creare, simptom, solutie, verificator, tehnician FROM reparatii ORDER BY id DESC").fetchall()
    
    if reparatii_db:
        for rep in reparatii_db:
            rid, rfirma, rmas, rtit, rdat, rsimp, rsol, rverif, rtech = rep
            with st.expander(f"📄 Raport Inregistrare #{rid} - Firmă: {rfirma} | Echipament: {rmas}"):
                st.write(f"**Titlu:** {rtit}")
                st.write(f"**Soluție:** {rsol}")
                
                full_rep = conn.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare FROM reparatii WHERE id=?", (rid,)).fetchone()
                if full_rep:
                    piese_data = json.loads(full_rep[7]) if full_rep[7] else []
                    date_pdf = {
                        "id": full_rep[0], "client": full_rep[1], "masina": full_rep[2], "subansamblu": full_rep[3],
                        "durata": full_rep[4], "cod_eroare": full_rep[5], "stare_finala": full_rep[6], "piese_json": piese_data,
                        "titlu": full_rep[8], "simptom": full_rep[9], "defect": full_rep[10], "solutie": full_rep[11],
                        "optimizari": full_rep[12], "tehnician": full_rep[13], "verificator": full_rep[14], "data": full_rep[15]
                    }
                    pdf_bytes = genereaza_pdf(date_pdf)
                    
                    st.download_button(label=f"📥 Descarcă PDF Raport #{rid}", data=pdf_bytes, file_name=f"Raport_{rid}.pdf", mime="application/pdf", key=f"dl_{rid}")
    else:
        st.info("Nu există rapoarte înregistrate.")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 7: Setări
# ------------------------------------------------------------------------------
with tab_setari:
    st.subheader("⚙️ Setări Aplicație & Conectare")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    current_setari = conn.execute("SELECT nume_firma_mea, cui_mea, adresa_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url FROM setari LIMIT 1").fetchone()
    
    with st.form("form_setari"):
        s_nume = st.text_input("Nume Firma Ta", value=current_setari[0] if current_setari else "Nexus Industrial SRL")
        s_cui = st.text_input("CUI", value=current_setari[1] if current_setari else "")
        s_adresa = st.text_input("Adresă", value=current_setari[2] if current_setari else "")
        s_srv = st.text_input("SMTP Server", value=current_setari[3] if current_setari else "smtp.gmail.com")
        s_prt = st.number_input("SMTP Port", value=int(current_setari[4]) if current_setari and current_setari[4] else 587)
        s_usr = st.text_input("User Gmail", value=current_setari[5] if current_setari else "nexusindustrialsrl@gmail.com")
        s_pwd = st.text_input("App Password", type="password", value=current_setari[6] if current_setari else "")
        s_sheet = st.text_input("Google Sheet URL", value=current_setari[7] if current_setari else "")
        
        if st.form_submit_button("💾 Salvează Setările"):
            conn.execute("DELETE FROM setari")
            conn.execute("""
                INSERT INTO setari (nume_firma_mea, cui_mea, adresa_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (s_nume, s_cui, s_adresa, s_srv, s_prt, s_usr, s_pwd, s_sheet))
            conn.commit()
            st.success("Setările au fost salvate cu succes!")
            st.rerun()
    conn.close()
import os
import json
import sqlite3
import smtplib
import urllib.request
from datetime import datetime
from email.message import EmailMessage
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF
import psycopg2
import psycopg2.extras


# Încărcare variabile de mediu[cite: 4]
load_dotenv()

# ------------------------------------------------------------------------------
# CONFIGURARE CONEXIUNE SUPABASE (PostgreSQL)
# ------------------------------------------------------------------------------
def get_db_connection():
    db_url = st.secrets.get("DATABASE_URL", "postgresql://postgres:PAROLA_TA@db.PROIECT_ID.supabase.co:5432/postgres")[cite: 4]
    conn = psycopg2.connect(db_url)
    return conn

def execute_query(query, params=None):
    conn = get_db_connection()
    postgres_query = query.replace("%s", "%s")
    
    cur = conn.cursor()
    try:
        if params:
            cur.execute(postgres_query, params)
        else:
            cur.execute(postgres_query)
            
        if postgres_query.strip().upper().startswith("SELECT"):
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

# ------------------------------------------------------------------------------
# 1. Configurare Pagină & Stil UI (Optimizat și pentru Mobil)
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Nexus Industrial - Sistem Mentenanță",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "reparatii.db"

# ------------------------------------------------------------------------------
# 2. Inițializare Bază de Date SQLite (Tabele Multiple)
# ------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    
    # 1. Tabel Firme / Clienti & Date Fiscale & Persoana Contact
    c.execute('''
        CREATE TABLE IF NOT EXISTS firme (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            masina TEXT,
            defect TEXT,
            pas_numar INTEGER,
            descriere_pas TEXT
        )
    ''')
    
    # 5. Tabel Activități Zilnice / Rapoarte Intervenție
    c.execute('''
        CREATE TABLE IF NOT EXISTS reparatii (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    if c.execute("SELECT COUNT(*) FROM setari").fetchone()[0] == 0:
        default_sheet = "https://script.google.com/macros/s/AKfycbx5bRsK0NGZY2VmlyMS3BqUZzoAiIPwmFMsuLYo10_WQSThN6kgeL3MkugFNvxxTRxbBQ/exec"
        c.execute("""
            INSERT INTO setari (nume_firma_mea, cui_mea, adresa_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Nexus Industrial SRL", "", "", "smtp.gmail.com", 587, "nexusindustrialsrl@gmail.com", "unjz fjle jljm lrxn", default_sheet))
    
    conn.commit()
    conn.close()

init_db()

def get_setari():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    res = conn.execute("SELECT nume_firma_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url FROM setari LIMIT 1").fetchone()
    conn.close()
    if res:
        return res
    return ("Nexus Industrial SRL", "smtp.gmail.com", 587, "nexusindustrialsrl@gmail.com", "unjz fjle jljm lrxn", "https://script.google.com/macros/s/AKfycbx5bRsK0NGZY2VmlyMS3BqUZzoAiIPwmFMsuLYo10_WQSThN6kgeL3MkugFNvxxTRxbBQ/exec")

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
    pdf.cell(90, 7, curata_text(f"Data: {data['data'][:10]}"), 0, 1, 'R')
    pdf.line(10, 35, 200, 35)
    pdf.ln(3)

    pdf.set_fill_color(*BG_LIGHT)
    pdf.rect(10, 38, 190, 32, 'F')
    
    pdf.set_xy(12, 40)
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
    pdf.cell(90, 5, curata_text(f"Durata: {data['durata']} minute"), 0, 0)
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

    pdf.set_y(-45)
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

    return bytes(pdf.output())

# ------------------------------------------------------------------------------
# 4. Funcție Trimitere Email prin SMTP
# ------------------------------------------------------------------------------
def trimite_email_raport(destinatar, subiect, corp_mesaj, pdf_bytes, nume_fisier):
    _, smtp_srv, smtp_p, smtp_u, smtp_pwd, _ = get_setari()
    
    msg = EmailMessage()
    msg['Subject'] = subiect
    msg['From'] = "contact@nexusindustrial.ro"
    msg['To'] = destinatar
    msg.set_content(corp_mesaj)
    
    if pdf_bytes:
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=nume_fisier)
    
    try:
        with smtplib.SMTP(smtp_srv, int(smtp_p)) as server:
            server.starttls()
            if smtp_pwd:
                server.login(smtp_u, smtp_pwd)
                server.send_message(msg)
                return True, "E-mailul a fost trimis cu succes!"
            else:
                return False, "Parola SMTP nu este setată."
    except Exception as e:
        return False, f"Eroare conexiune SMTP ({str(e)})"

# ------------------------------------------------------------------------------
# 5. Interfața Principală Streamlit & Sidebar
# ------------------------------------------------------------------------------
st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("Drive: nexusindustrialsrl@gmail.com")

if st.sidebar.button("🛑 Închide Serverul Python", type="primary", key="inchide_server_btn"):
    st.sidebar.warning("Se închide serverul...")
    os._exit(0)

st.sidebar.markdown("---")
st.sidebar.info("Aplicație optimizată pentru mobil și desktop.")

st.title("🛠️ Sistem Integrat de Mentenanță - Nexus Industrial")

tab_activitati, tab_optimizare, tab_masini, tab_piese, tab_firme, tab_rapoarte, tab_setari = st.tabs([
    "📝 1. Activități", 
    "📊 2. Optimizare", 
    "🏭 3. Mașini", 
    "🔧 4. Piese", 
    "📇 5. Firme",
    "📋 6. Istoric",
    "⚙️ 7. Setări"
])

# ------------------------------------------------------------------------------
# TAB 5: Nomenclator Firme
# ------------------------------------------------------------------------------
with tab_firme:
    st.subheader("📇 Gestiune Firme și Persoane de Contact")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    
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
                conn.execute("""
                    INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon))
                conn.commit()
                st.success(f"Firma **{nume_firma}** a fost salvată!")
                st.rerun()
            else:
                st.error("Completați câmpurile obligatorii (*).")

    st.markdown("---")
    st.subheader("📋 Firme Înregistrate (Modificare & Ștergere)")
    firme_db = conn.execute("SELECT id, nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon FROM firme").fetchall()
    
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
                mf_email = st.text_input("Email", value=femail, key=f"mf_e_{fid}")
                mf_tel = st.text_input("Telefon", value=ftel or "", key=f"mf_t_{fid}")
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    if st.form_submit_button("🔄 Modifică Tot"):
                        conn.execute("""
                            UPDATE firme SET nume_firma=?, cui=?, reg_com=?, adresa=?, banca=?, cont=?, nume_persoana=?, email=?, telefon=?
                            WHERE id=?
                        """, (mf_nume, mf_cui, mf_reg, mf_adr, mf_banca, mf_cont, mf_pers, mf_email, mf_tel, fid))
                        conn.commit()
                        st.success("Firma a fost actualizată!")
                        st.rerun()
                with col_m2:
                    if st.form_submit_button("🗑️ Șterge Firma"):
                        conn.execute("DELETE FROM firme WHERE id=?", (fid,))
                        conn.commit()
                        st.success("Firma a fost ștearsă!")
                        st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 3: Lista Mașini & Subansambluri
# ------------------------------------------------------------------------------
with tab_masini:
    st.subheader("🏭 Gestiune Mașini și Echipamente")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    firme_list = conn.execute("SELECT id, nume_firma FROM firme").fetchall()
    firme_dict = {f[1]: f[0] for f in firme_list}
    
    with st.form("form_masini", clear_on_submit=True):
        m_firma = st.selectbox("Selectează Firma Proprietară", options=list(firme_dict.keys()) if firme_dict else ["Nicio firmă"])
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
                if m_defecte and m_remediu:
                    conn.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (?, ?, ?, ?)",
                                 (m_denumire, m_defecte, 1, m_remediu))
                
                conn.execute("""
                    INSERT INTO masini (firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (firma_id, m_denumire, m_tip, m_serie, m_an, m_sub, m_erori, m_defecte, m_remediu, m_piese_nec, m_piese_inloc, m_fluide, str(m_data_ment), m_tip_ment))
                conn.commit()
                st.success(f"Mașina **{m_denumire}** a fost salvată!")
                st.rerun()
            else:
                st.error("Selectați o firmă și introduceți denumirea mașinii.")

    st.markdown("---")
    st.subheader("📋 Mașini Înregistrate (Modificare & Ștergere)")
    masini_db = conn.execute("""
        SELECT m.id, f.nume_firma, m.denumire, m.tip_masina, m.serie, m.an_fabricatie, m.subansambluri, m.erori, m.defecte, m.remediu, m.piese_necesare, m.piese_inlocuite, m.tipuri_fluide, m.tip_intretinere 
        FROM masini m JOIN firme f ON m.firma_id = f.id
    """).fetchall()
    
    for m in masini_db:
        mid, mfirma, mden, mtip, mser, man, msub, meri, mdef, mrem, mpnec, mpinl, mflu, mtipm = m
        with st.expander(f"⚙️ {mden} (Firma: {mfirma})"):
            with st.form(f"mod_masina_{mid}"):
                mm_den = st.text_input("Denumire", value=mden, key=f"mm_d_{mid}")
                mm_tip = st.text_input("Tip", value=mtip or "", key=f"mm_tip_{mid}")
                mm_ser = st.text_input("Serie", value=mser or "", key=f"mm_ser_{mid}")
                mm_an = st.number_input("An", value=int(man) if man else 2020, key=f"mm_an_{mid}")
                mm_sub = st.text_input("Subansambluri", value=msub or "", key=f"mm_sub_{mid}")
                mm_eri = st.text_input("Erori", value=meri or "", key=f"mm_eri_{mid}")
                mm_def = st.text_area("Defecte", value=mdef or "", key=f"mm_def_{mid}")
                mm_rem = st.text_area("Remediu", value=mrem or "", key=f"mm_rem_{mid}")
                mm_pnec = st.text_area("Piese Necesare", value=mpnec or "", key=f"mm_pnec_{mid}")
                mm_pinl = st.text_area("Piese Înlocuite", value=mpinl or "", key=f"mm_pinl_{mid}")
                mm_flu = st.text_area("Fluide", value=mflu or "", key=f"mm_flu_{mid}")
                mm_tipm = st.selectbox("Tip Întreținere", ["Lunară", "Semestrială", "Anuală"], index=0, key=f"mm_tipm_{mid}")
                
                col_mm1, col_mm2 = st.columns(2)
                with col_mm1:
                    if st.form_submit_button("🔄 Modifică Tot"):
                        conn.execute("""
                            UPDATE masini SET denumire=?, tip_masina=?, serie=?, an_fabricatie=?, subansambluri=?, erori=?, defecte=?, remediu=?, piese_necesare=?, piese_inlocuite=?, tipuri_fluide=?, tip_intretinere=?
                            WHERE id=?
                        """, (mm_den, mm_tip, mm_ser, mm_an, mm_sub, mm_eri, mm_def, mm_rem, mm_pnec, mm_pinl, mm_flu, mm_tipm, mid))
                        conn.commit()
                        st.success("Mașină actualizată!")
                        st.rerun()
                with col_mm2:
                    if st.form_submit_button("🗑️ Șterge Mașina"):
                        conn.execute("DELETE FROM masini WHERE id=?", (mid,))
                        conn.commit()
                        st.success("Mașina a fost ștearsă!")
                        st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 1: Activități Zilnice
# ------------------------------------------------------------------------------
with tab_activitati:
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    
    firme_db_all = conn.execute("SELECT id, nume_firma, nume_persoana, email FROM firme").fetchall()
    firme_activ = [f[1] for f in firme_db_all]
    
    if not firme_activ:
        st.warning("⚠️ Adăugați cel puțin o firmă în Tabul 5.")
    else:
        sel_firma = st.selectbox("1. Alege Firma la care lucrezi", options=firme_activ, key="act_firma")
        
        persoane_contact_firma = [f[2] for f in firme_db_all if f[1] == sel_firma]
        email_client_destinatar = [f[3] for f in firme_db_all if f[1] == sel_firma][0] if firme_db_all else "nexusindustrialsrl@gmail.com"
        
        masini_firma = [row[0] for row in conn.execute("SELECT m.denumire FROM masini m JOIN firme f ON m.firma_id = f.id WHERE f.nume_firma = ?", (sel_firma,)).fetchall()]
        sel_masina = st.selectbox("2. Alege Mașina / Echipamentul", options=masini_firma if masini_firma else ["Nicio mașină"], key="act_masina")
        
        subansamblu_list = []
        if masini_firma and sel_masina != "Nicio mașină":
            sub_db = conn.execute("SELECT subansambluri FROM masini WHERE denumire = ?", (sel_masina,)).fetchone()
            if sub_db and sub_db[0]:
                subansamblu_list = [s.strip() for s in sub_db[0].split(",")]
        
        sel_subansamblu = st.selectbox("3. Alege sau scrie Subansamblul", options=subansamblu_list if subansamblu_list else ["General"])
        
        c1, c2 = st.columns(2)
        with c1:
            titlu_lucrare = st.text_input("Titlu Lucrare", value="Intervenție tehnică")
            simptom = st.text_area("Simptom Inițial Reclamat")
            defect = st.text_area("Defect Constatat")
            
            erori_masina = []
            if masini_firma and sel_masina != "Nicio mașină":
                e_db = conn.execute("SELECT erori FROM masini WHERE denumire = ?", (sel_masina,)).fetchone()
                if e_db and e_db[0]:
                    erori_masina = [e.strip() for e in e_db[0].split(",")]
            cod_eroare = st.selectbox("Cod Eroare", options=["Niciunul"] + erori_masina)
            
        with c2:
            solutie = st.text_area("Soluție / Lucrări Executate")
            durata_min = st.number_input("Durată Intervenție (minute)", value=60, step=15)
            stare_fin = st.selectbox("Stare Finală Echipament", ["Funcțională", "În testare", "Oprită / Necesar piese"])
            
        st.markdown("##### Gestiune Piese")
        if "randuri_piese" not in st.session_state:
            st.session_state["randuri_piese"] = [{"piesa": "", "cantitate": 1, "tip": "Utilizata"}]
            
        piese_catalog = [row[0] for row in conn.execute("SELECT denumire FROM piese").fetchall()]
        
        for idx, rp in enumerate(st.session_state["randuri_piese"]):
            cols_p = st.columns([3, 1, 2, 1])
            with cols_p[0]:
                st.session_state["randuri_piese"][idx]["piesa"] = st.selectbox(f"Piesă #{idx+1}", options=["Selectează..."] + piese_catalog, key=f"p_sel_{idx}")
            with cols_p[1]:
                st.session_state["randuri_piese"][idx]["cantitate"] = st.number_input("Cant.", min_value=1, value=rp["cantitate"], key=f"p_cant_{idx}")
            with cols_p[2]:
                st.session_state["randuri_piese"][idx]["tip"] = st.selectbox("Tip", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], key=f"p_tip_{idx}")
            with cols_p[3]:
                if st.button("❌ Șterg", key=f"del_p_{idx}"):
                    st.session_state["randuri_piese"].pop(idx)
                    st.rerun()
                    
        if st.button("➕ Adaugă altă piesă"):
            st.session_state["randuri_piese"].append({"piesa": "", "cantitate": 1, "tip": "Utilizata"})
            st.rerun()
            
        c_tech1, c_tech2 = st.columns(2)
        tehnician_nume = c_tech1.text_input("Nume Tehnician", value="Tehnician Nexus")
        verificator_nume = c_tech2.selectbox("Verificat / Recepționat de", options=persoane_contact_firma if persoane_contact_firma else ["Niciun contact"])
        
        opt_recomandari = ""
        opt_match = conn.execute("SELECT descriere_pas FROM optimizari_interventie WHERE masina = ? AND defect = ?", (sel_masina, defect)).fetchone()
        if opt_match:
            opt_recomandari = opt_match[0]
            
        optimizari = st.text_area("Recomandări Tehnice", value=opt_recomandari)

        if "raport_salvat" not in st.session_state:
            st.session_state["raport_salvat"] = False
            st.session_state["ultimul_id_salvat"] = None

        col_b1, col_b2, col_b3 = st.columns(3)
        
        with col_b1:
            if st.button("💾 Salvează Activitatea în DB", type="primary"):
                piese_valide = [p for p in st.session_state["randuri_piese"] if p["piesa"] != "Selectează..."]
                conn.execute("""
                    INSERT INTO reparatii (firma, masina, subansamblu, defect, cod_eroare, piese_json, titlu, simptom, solutie, stare_finala, durata, optimizari, tehnician, verificator)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (sel_firma, sel_masina, sel_subansamblu, defect, cod_eroare, json.dumps(piese_valide, ensure_ascii=False), titlu_lucrare, simptom, solutie, stare_fin, durata_min, optimizari, tehnician_nume, verificator_nume))
                conn.commit()
                
                ultima_inreg = conn.execute("SELECT id FROM reparatii ORDER BY id DESC LIMIT 1").fetchone()
                if ultima_inreg:
                    st.session_state["ultimul_id_salvat"] = ultima_inreg[0]
                    
                st.session_state["raport_salvat"] = True
                st.success("Activitatea a fost salvată în baza de date!")
                st.rerun()
                
        if st.session_state["raport_salvat"] and st.session_state["ultimul_id_salvat"]:
            rid = st.session_state["ultimul_id_salvat"]
            
            full_rep_salvat = conn.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare FROM reparatii WHERE id=?", (rid,)).fetchone()
            
            if full_rep_salvat:
                rdata = full_rep_salvat[15]
                piese_data_salvate = json.loads(full_rep_salvat[7]) if full_rep_salvat[7] else []
                
                date_pdf = {
                    "id": full_rep_salvat[0], "client": full_rep_salvat[1], "masina": full_rep_salvat[2], "subansamblu": full_rep_salvat[3],
                    "durata": full_rep_salvat[4], "cod_eroare": full_rep_salvat[5], "stare_finala": full_rep_salvat[6], "piese_json": piese_data_salvate,
                    "titlu": full_rep_salvat[8], "simptom": full_rep_salvat[9], "defect": full_rep_salvat[10], "solutie": full_rep_salvat[11],
                    "optimizari": full_rep_salvat[12], "tehnician": full_rep_salvat[13], "verificator": full_rep_salvat[14], "data": rdata
                }
                pdf_bytes = genereaza_pdf(date_pdf)
                
                with col_b2:
                    st.download_button(
                        label=f"📥 Printează / Descarcă Raport #{rid}",
                        data=pdf_bytes,
                        file_name=f"Raport_Interventie_{rid}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                    
                with col_b3:
                    if st.button("📧 Trimite pe Email către Verificator"):
                        subiect = f"Raport de Interventie Tehnica #{rid} - {sel_firma}"
                        corp = f"Stimate beneficiar ({verificator_nume}),\n\nVă atașăm raportul de intervenție tehnică #{rid} pentru echipamentul {sel_masina}.\n\nEchipa Nexus Industrial"
                        
                        success, msg = trimite_email_raport(email_client_destinatar, subiect, corp, pdf_bytes, f"Raport_{rid}.pdf")
                        if success:
                            st.success(msg)
                            setari_info = get_setari()
                            sheet_url = setari_info[5]
                            if sheet_url:
                                try:
                                    ora_curenta = datetime.now().strftime("%H:%M:%S")
                                    piese_utilizate_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_data_salvate if p.get('tip') in ['Utilizata', 'Inlocuita']])
                                    piese_necesare_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_data_salvate if p.get('tip') in ['Necesara', 'De Comandat']])
                                    
                                    payload_sheet = {
                                        "id": str(rid), "data": str(rdata)[:10], "ora": str(ora_curenta),
                                        "firma": str(sel_firma), "masina": str(sel_masina),
                                        "subansamblu": str(sel_subansamblu or "General"), "solutie": str(solutie or ""),
                                        "verificator": str(verificator_nume or ""), "tehnician": str(tehnician_nume or ""),
                                        "piese utilizate": str(piese_utilizate_str), "necesar piese": str(piese_necesare_str)
                                    }
                                    req_data = json.dumps(payload_sheet).encode('utf-8')
                                    req = urllib.request.Request(sheet_url, data=req_data, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
                                    with urllib.request.urlopen(req) as response:
                                        response.read().decode('utf-8')
                                        st.success("Datele au fost trimise cu succes și în Google Sheet!")
                                except Exception as e:
                                    st.error(f"Eroare la Google Sheet: {str(e)}")
                        else:
                            st.error(msg)
    conn.close()

# ------------------------------------------------------------------------------
# TAB 2: Baza de Optimizare
# ------------------------------------------------------------------------------
with tab_optimizare:
    st.subheader("📊 Baza de Cunoștințe & Optimizare Intervenții")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    masini_existente = [row[0] for row in conn.execute("SELECT denumire FROM masini").fetchall()]
    
    if not masini_existente:
        st.warning("⚠️ Introduceți mai întâi mașini în Tabul 3.")
    else:
        sel_opt_masina = st.selectbox("Selectează Mașina", options=masini_existente, key="opt_m_sel")
        defecte_existente = [row[0] for row in conn.execute("SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = ?", (sel_opt_masina,)).fetchall() if row[0]]
        sel_opt_defect = st.selectbox("Selectează Defectul", options=defecte_existente + ["+ Defect nou"])
        
        def_final = st.text_area("Descriere Defect Nou") if sel_opt_defect == "+ Defect nou" else sel_opt_defect
            
        if sel_opt_defect != "+ Defect nou" and sel_opt_defect:
            st.markdown(f"##### 🔎 Pași existenți:")
            pasii_db = conn.execute("SELECT id, pas_numar, descriere_pas FROM optimizari_interventie WHERE masina = ? AND defect = ?", (sel_opt_masina, sel_opt_defect)).fetchall()
            for pe in pasii_db:
                st.info(f"Pasul {pe[1]}: {pe[2]}")
            st.markdown("---")
            
        st.markdown("##### Adăugare Pași Noi")
        if "pasi_lucrare_t" not in st.session_state:
            st.session_state["pasi_lucrare_t"] = []
            
        with st.form("form_add_pas", clear_on_submit=True):
            desc_p_nou = st.text_area("Descriere pas remediu nou")
            if st.form_submit_button("➕ Adaugă Pas în Listă"):
                if desc_p_nou:
                    st.session_state["pasi_lucrare_t"].append(desc_p_nou)
                    st.success("Pas adăugat!")
                    st.rerun()
                    
        if st.session_state["pasi_lucrare_t"]:
            pasi_modificati = [st.text_input(f"Pasul {idx+1}", value=pval, key=f"pas_ed_{idx}") for idx, pval in enumerate(st.session_state["pasi_lucrare_t"])]
                
            if st.button("💾 Salvează Toți Pașii în Baza de Date", type="primary"):
                if def_final:
                    for idx, pval in enumerate(pasi_modificati):
                        conn.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (?, ?, ?, ?)",
                                     (sel_opt_masina, def_final, idx+1, pval))
                    conn.commit()
                    st.session_state["pasi_lucrare_t"] = []
                    st.success("Pașii au fost salvați!")
                    st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 4: Tabelul de Piese
# ------------------------------------------------------------------------------
with tab_piese:
    st.subheader("🔧 Gestiune Piese de Schimb")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    masini_existente = [row[0] for row in conn.execute("SELECT denumire FROM masini").fetchall()]
    
    with st.form("form_piese", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            p_denumire = st.text_input("Denumire Piesă *")
            p_cod_prod = st.text_input("Cod Producător")
            p_cod_com = st.text_input("Cod Comercial")
        with c2:
            p_masini_alese = st.multiselect("Mașinile pe care se montează", options=masini_existente)
            p_sub = st.text_input("Subansamblu")
            p_pret = st.number_input("Preț Achiziție (RON)", min_value=0.0, value=0.0)
            
        if st.form_submit_button("💾 Salvează Piesa"):
            if p_denumire:
                masini_text_str = ", ".join(p_masini_alese) if p_masini_alese else "General"
                conn.execute("""
                    INSERT INTO piese (denumire, cod_producator, cod_comercial, masina_montaj, subansamblu, pret_achizitie)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (p_denumire, p_cod_prod, p_cod_com, masini_text_str, p_sub, p_pret))
                conn.commit()
                st.success(f"Piesa **{p_denumire}** a fost salvată!")
                st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 6: Istoric & Google Sheet
# ------------------------------------------------------------------------------
with tab_rapoarte:
    st.subheader("📋 Istoric Intervenții")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    reparatii_db = conn.execute("SELECT id, firma, masina, titlu, data_creare, simptom, solutie, verificator, tehnician FROM reparatii ORDER BY id DESC").fetchall()
    
    if reparatii_db:
        for rep in reparatii_db:
            rid, rfirma, rmas, rtit, rdat, rsimp, rsol, rverif, rtech = rep
            with st.expander(f"📄 Raport Inregistrare #{rid} - Firmă: {rfirma} | Echipament: {rmas}"):
                st.write(f"**Titlu:** {rtit}")
                st.write(f"**Soluție:** {rsol}")
                
                full_rep = conn.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare FROM reparatii WHERE id=?", (rid,)).fetchone()
                if full_rep:
                    piese_data = json.loads(full_rep[7]) if full_rep[7] else []
                    date_pdf = {
                        "id": full_rep[0], "client": full_rep[1], "masina": full_rep[2], "subansamblu": full_rep[3],
                        "durata": full_rep[4], "cod_eroare": full_rep[5], "stare_finala": full_rep[6], "piese_json": piese_data,
                        "titlu": full_rep[8], "simptom": full_rep[9], "defect": full_rep[10], "solutie": full_rep[11],
                        "optimizari": full_rep[12], "tehnician": full_rep[13], "verificator": full_rep[14], "data": full_rep[15]
                    }
                    pdf_bytes = genereaza_pdf(date_pdf)
                    
                    st.download_button(label=f"📥 Descarcă PDF Raport #{rid}", data=pdf_bytes, file_name=f"Raport_{rid}.pdf", mime="application/pdf", key=f"dl_{rid}")
    else:
        st.info("Nu există rapoarte înregistrate.")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 7: Setări
# ------------------------------------------------------------------------------
with tab_setari:
    st.subheader("⚙️ Setări Aplicație & Conectare")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    current_setari = conn.execute("SELECT nume_firma_mea, cui_mea, adresa_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url FROM setari LIMIT 1").fetchone()
    
    with st.form("form_setari"):
        s_nume = st.text_input("Nume Firma Ta", value=current_setari[0] if current_setari else "Nexus Industrial SRL")
        s_cui = st.text_input("CUI", value=current_setari[1] if current_setari else "")
        s_adresa = st.text_input("Adresă", value=current_setari[2] if current_setari else "")
        s_srv = st.text_input("SMTP Server", value=current_setari[3] if current_setari else "smtp.gmail.com")
        s_prt = st.number_input("SMTP Port", value=int(current_setari[4]) if current_setari and current_setari[4] else 587)
        s_usr = st.text_input("User Gmail", value=current_setari[5] if current_setari else "nexusindustrialsrl@gmail.com")
        s_pwd = st.text_input("App Password", type="password", value=current_setari[6] if current_setari else "")
        s_sheet = st.text_input("Google Sheet URL", value=current_setari[7] if current_setari else "")
        
        if st.form_submit_button("💾 Salvează Setările"):
            conn.execute("DELETE FROM setari")
            conn.execute("""
                INSERT INTO setari (nume_firma_mea, cui_mea, adresa_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (s_nume, s_cui, s_adresa, s_srv, s_prt, s_usr, s_pwd, s_sheet))
            conn.commit()
            st.success("Setările au fost salvate cu succes!")
            st.rerun()
    conn.close()
