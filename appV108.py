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
    
    # 3. Tabel Piese de Schimb (actualizat cu preț intrare, ieșire, ad. com., livrare)
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
    
    # 6. Tabel Setări Aplicație (inclusiv TVA și Pass mascat)
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
            tva REAL DEFAULT 19.0,
            pass TEXT DEFAULT 'nexus123'
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM setari")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO setari (nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician, tva, pass)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, ("Nexus Industrial SRL", "", "", "", "", "", "", "smtp.gmail.com", 587, "", "", "", "", 19.0, "nexus123"))
    
    conn.commit()
    conn.close()

init_db()

def get_setari():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician, tva, pass FROM setari LIMIT 1")
    res = c.fetchone()
    conn.close()
    if res:
        return res
    return ("Nexus Industrial SRL", "", "", "", "", "", "", "smtp.gmail.com", 587, "", "", "", 19.0, "nexus123")

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

    # Dacă este Deviz sau Ofertă de preț
    if titlu_doc in ["Deviz", "Oferta de pret"]:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*SECONDARY)
        pdf.cell(0, 6, curata_text("TABEL PIESE / SERVICII OFERTATE"), 0, 1)
        pdf.set_draw_color(*SECONDARY)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(80, 6, curata_text("Denumire Piesă / Serviciu"), 1, 0, 'C', fill=True)
        pdf.cell(25, 6, curata_text("Cantitate"), 1, 0, 'C', fill=True)
        pdf.cell(40, 6, curata_text("Preț Unitar (EUR)"), 1, 0, 'C', fill=True)
        pdf.cell(45, 6, curata_text("Valoare (EUR)"), 1, 1, 'C', fill=True)
        
        pdf.set_font('Helvetica', '', 9)
        piese_list = data.get('piese_json', [])
        subtotal_val = 0
        if piese_list:
            for p in piese_list:
                p_nume = p.get('piesa', '')
                p_cant = p.get('cantitate', 1)
                p_pret = p.get('pret_iesire', 0)
                p_val = p_cant * p_pret
                subtotal_val += p_val
                
                pdf.cell(80, 6, curata_text(p_nume), 1, 0, 'L')
                pdf.cell(25, 6, str(p_cant), 1, 0, 'C')
                pdf.cell(40, 6, f"{p_pret:.2f}", 1, 0, 'R')
                pdf.cell(45, 6, f"{p_val:.2f}", 1, 1, 'R')
        else:
            pdf.cell(190, 6, curata_text("Nici o piesă adăugată"), 1, 1, 'C')
        pdf.ln(2)
        
        tva_procent = data.get('tva_procent', 19.0)
        val_tva = subtotal_val * (tva_procent / 100.0)
        total_general = subtotal_val + val_tva
        
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(145, 6, curata_text("Subtotal (EUR):"), 1, 0, 'R')
        pdf.cell(45, 6, f"{subtotal_val:.2f}", 1, 1, 'R')
        pdf.cell(145, 6, curata_text(f"TVA ({tva_procent}%):"), 1, 0, 'R')
        pdf.cell(45, 6, f"{val_tva:.2f}", 1, 1, 'R')
        pdf.cell(145, 6, curata_text("TOTAL GENERAL CU TVA (EUR):"), 1, 0, 'R')
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
        # Raport clasic intervenție
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

st.title("🛠️ Sistem Integrat de Mentenanță - Nexus Industrial (Supabase)")

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
                mf_email = st.text_input("Email", value=femail, key=f"mf_e_{fid}")
                mf_tel = st.text_input("Telefon", value=ftel or "", key=f"mf_t_{fid}")
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    if st.form_submit_button("🔄 Modifică Tot"):
                        c.execute("""
                            UPDATE firme SET nume_firma=%s, cui=%s, reg_com=%s, adresa=%s, banca=%s, cont=%s, nume_persoana=%s, email=%s, telefon=%s
                            WHERE id=%s
                        """, (mf_nume, mf_cui, mf_reg, mf_adr, mf_banca, mf_cont, mf_pers, mf_email, mf_tel, fid))
                        conn.commit()
                        st.success("Firma a fost actualizată în Supabase!")
                        st.rerun()
                with col_m2:
                    if st.form_submit_button("🗑️ Șterge Firma"):
                        c.execute("DELETE FROM firme WHERE id=%s", (fid,))
                        conn.commit()
                        st.success("Firma a fost ștearsă din Supabase!")
                        st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 3: Lista Mașini & Subansambluri
# ------------------------------------------------------------------------------
with tab_masini:
    st.subheader("🏭 Gestiune Mașini și Echipamente")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, nume_firma FROM firme")
    firme_list = c.fetchall()
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
                    c.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (%s, %s, %s, %s)",
                              (m_denumire, m_defecte, 1, m_remediu))
                
                c.execute("""
                    INSERT INTO masini (firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (firma_id, m_denumire, m_tip, m_serie, m_an, m_sub, m_erori, m_defecte, m_remediu, m_piese_nec, m_piese_inloc, m_fluide, str(m_data_ment), m_tip_ment))
                conn.commit()
                st.success(f"Mașina **{m_denumire}** a fost salvată în Supabase!")
                st.rerun()
            else:
                st.error("Selectați o firmă și introduceți denumirea mașinii.")

    st.markdown("---")
    st.subheader("📋 Mașini Înregistrate (Modificare & Ștergere)")
    c.execute("""
        SELECT m.id, f.nume_firma, m.denumire, m.tip_masina, m.serie, m.an_fabricatie, m.subansambluri, m.erori, m.defecte, m.remediu, m.piese_necesare, m.piese_inlocuite, m.tipuri_fluide, m.tip_intretinere 
        FROM masini m JOIN firme f ON m.firma_id = f.id
    """)
    masini_db = c.fetchall()
    
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
                        c.execute("""
                            UPDATE masini SET denumire=%s, tip_masina=%s, serie=%s, an_fabricatie=%s, subansambluri=%s, erori=%s, defecte=%s, remediu=%s, piese_necesare=%s, piese_inlocuite=%s, tipuri_fluide=%s, tip_intretinere=%s
                            WHERE id=%s
                        """, (mm_den, mm_tip, mm_ser, mm_an, mm_sub, mm_eri, mm_def, mm_rem, mm_pnec, mm_pinl, mm_flu, mm_tipm, mid))
                        conn.commit()
                        st.success("Mașină actualizată în Supabase!")
                        st.rerun()
                with col_mm2:
                    if st.form_submit_button("🗑️ Șterge Mașina"):
                        c.execute("DELETE FROM masini WHERE id=%s", (mid,))
                        conn.commit()
                        st.success("Mașina a fost ștearsă din Supabase!")
                        st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 4: Tabelul de Piese (cu parolă pentru prețuri și rubrici noi)
# ------------------------------------------------------------------------------
with tab_piese:
    st.subheader("🔧 Gestiune Piese de Schimb")
    
    # Verificare parolă pentru vizibilitate rubrici financiare
    if "acces_piese_fin" not in st.session_state:
        st.session_state["acces_piese_fin"] = False
        
    if not st.session_state["acces_piese_fin"]:
        pass_input = st.text_input("Introduceți parola pentru a vizualiza prețurile și detaliile avansate:", type="password")
        setari_curente = get_setari()
        parola_corecta = setari_curente[13] if len(setari_curente) > 13 else "nexus123"
        if st.button("Deblocare Secțiune Finanțiară"):
            if pass_input == parola_corecta:
                st.session_state["acces_piese_fin"] = True
                st.success("Acces acordat!")
                st.rerun()
            else:
                st.error("Parolă incorectă!")
    else:
        st.success("🔒 Secțiunea financiară este deblocată.")
        if st.button("Blocare Acces"):
            st.session_state["acces_piese_fin"] = False
            st.rerun()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT denumire FROM masini")
    masini_existente = [row[0] for row in c.fetchall()]
    
    with st.form("form_piese", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            p_denumire = st.text_input("Denumire Piesă *")
            p_cod_prod = st.text_input("Cod Producător")
            p_cod_com = st.text_input("Cod Comercial")
            p_sub = st.text_input("Subansamblu")
        with c2:
            p_masini_alese = st.multiselect("Mașinile pe care se montează", options=masini_existente)
            p_pret = st.number_input("Preț Achiziție (RON)", min_value=0.0, value=0.0)
            p_intrare = st.number_input("Preț Intrare", min_value=0.0, value=0.0) if st.session_state["acces_piese_fin"] else 0.0
            p_iesire = st.number_input("Preț Ieșire", min_value=0.0, value=0.0) if st.session_state["acces_piese_fin"] else 0.0
            p_adcom = st.number_input("Ad. Com. (Adaos Comercial %)", min_value=0.0, value=0.0) if st.session_state["acces_piese_fin"] else 0.0
            p_livrare = st.number_input("Livrare (zile)", min_value=0, value=1) if st.session_state["acces_piese_fin"] else 1
            
        if st.form_submit_button("💾 Salvează Piesa"):
            if p_denumire:
                masini_text_str = ", ".join(p_masini_alese) if p_masini_alese else "General"
                c.execute("""
                    INSERT INTO piese (denumire, cod_producator, cod_comercial, masina_montaj, subansamblu, pret_achizitie, pret_intrare, pret_iesire, ad_com, livrare)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (p_denumire, p_cod_prod, p_cod_com, masini_text_str, p_sub, p_pret, p_intrare, p_iesire, p_adcom, p_livrare))
                conn.commit()
                st.success(f"Piesa **{p_denumire}** a fost salvată în Supabase!")
                st.rerun()
    
    st.markdown("---")
    st.subheader("📋 Catalog Piese Înregistrate")
    if st.session_state["acces_piese_fin"]:
        c.execute("SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, pret_intrare, pret_iesire, ad_com, livrare FROM piese")
        piese_db = c.fetchall()
        for p in piese_db:
            st.write(f"🔧 **{p[1]}** | Cod: {p[2]} | Intrare: {p[5]} | Ieșire: {p[6]} | Adaos: {p[7]}% | Livrare: {p[8]} zile")
    else:
        c.execute("SELECT denumire, cod_producator, masina_montaj FROM piese")
        piese_db = c.fetchall()
        for p in piese_db:
            st.write(f"🔧 **{p[0]}** | Cod: {p[1]} | Mașină: {p[2]}")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 6: Deviz & Ofertă de Preț
# ------------------------------------------------------------------------------
with tab_deviz:
    st.subheader("🧮 Generare Deviz de Calcul & Ofertă de Preț")
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id, nume_firma, email FROM firme")
    firme_deviz = c.fetchall()
    firme_nume_list = [f[1] for f in firme_deviz]
    
    if not firme_nume_list:
        st.warning("⚠️ Adăugați cel puțin o firmă în Tabul 5.")
    else:
        sel_firma_deviz = st.selectbox("Selectează Firma / Client", options=firme_nume_list, key="deviz_firma")
        email_client_deviz = [f[2] for f in firme_deviz if f[1] == sel_firma_deviz][0] if firme_deviz else ""
        
        c.execute("SELECT m.denumire FROM masini m JOIN firme f ON m.firma_id = f.id WHERE f.nume_firma = %s", (sel_firma_deviz,))
        masini_deviz = [row[0] for row in c.fetchall()]
        sel_masina_deviz = st.selectbox("Selectează Mașina / Echipamentul (Opțional)", options=["General"] + masini_deviz, key="deviz_masina")
        
        # Preluare TVA din setări
        setari_val = get_setari()
        try:
            tva_setat = float(setari_val[14]) if len(setari_val) > 14 and setari_val[14] is not None else 21.0
        except (ValueError, TypeError):
            tva_setat = 21.0
        
        st.markdown("##### 🛒 Selectare Piese / Servicii pentru Deviz")
        if "randuri_deviz" not in st.session_state:
            st.session_state["randuri_deviz"] = [{"piesa": "", "cantitate": 1, "pret_iesire": 0.0}]
            
        c.execute("SELECT denumire, pret_iesire FROM piese")
        catalog_piese_raw = c.fetchall()
        catalog_piese_dict = {row[0]: row[1] for row in catalog_piese_raw}
        catalog_nume_piese = list(catalog_piese_dict.keys())
        
        for idx, rd in enumerate(st.session_state["randuri_deviz"]):
            cols_d = st.columns([3, 1, 2, 2, 1])
            with cols_d[0]:
                st.session_state["randuri_deviz"][idx]["piesa"] = st.selectbox(f"Piesă/Serviciu #{idx+1}", options=["Selectează..."] + catalog_nume_piese, key=f"d_sel_{idx}")
            with cols_d[1]:
                st.session_state["randuri_deviz"][idx]["cantitate"] = st.number_input("Cant.", min_value=1, value=rd["cantitate"], key=f"d_cant_{idx}")
            with cols_d[2]:
                p_curenta = st.session_state["randuri_deviz"][idx]["piesa"]
                pret_def = catalog_piese_dict.get(p_curenta, 0.0) if p_curenta != "Selectează..." else 0.0
                st.session_state["randuri_deviz"][idx]["pret_iesire"] = st.number_input("Preț Unitar (EUR)", value=float(pret_def), key=f"d_pret_{idx}")
            with cols_d[3]:
                val_total_linie = st.session_state["randuri_deviz"][idx]["cantitate"] * st.session_state["randuri_deviz"][idx]["pret_iesire"]
                st.metric("Total Linie", f"{val_total_linie:.2f} EUR")
            with cols_d[4]:
                if st.button("❌ Șterg", key=f"del_d_{idx}"):
                    st.session_state["randuri_deviz"].pop(idx)
                    st.rerun()
                    
        if st.button("➕ Adaugă altă linie"):
            st.session_state["randuri_deviz"].append({"piesa": "", "cantitate": 1, "pret_iesire": 0.0})
            st.rerun()
            
        # Calcul subtotal, tva și total
        piese_valide_deviz = [p for p in st.session_state["randuri_deviz"] if p["piesa"] != "Selectează..."]
        subtotal_deviz = sum([p["cantitate"] * p["pret_iesire"] for p in piese_valide_deviz])
        tva_deviz = subtotal_deviz * (tva_setat / 100.0)
        total_cu_tva_deviz = subtotal_deviz + tva_deviz
        
        st.markdown(f"### 💶 Sumar Financiar: Subtotal: **{subtotal_deviz:.2f} EUR** | TVA ({tva_setat}%): **{tva_deviz:.2f} EUR** | Total cu TVA: **{total_cu_tva_deviz:.2f} EUR**")
        
        default_memo = (
            "Oferta de preț este exprimată în EURO, totalul conține TVA și este valabilă 15 zile.\n"
            "Termenul de livrare este exprimat în zile lucrătoare și nu s-au luat în calcul zilele nelucrătoare oficiale.\n"
            "În funcție de complexitatea lucrărilor, durata intervenției poate suferi modificări. Acestea vă vor fi comunicate la fața locului.\n"
            "După demontarea grinzii de măsurare mașina de debitat nu mai poate fi utilizată până la finalizarea lucrării.\n"
            "Ghidajele liniare, patinele, rigla magnetică, capul de citire magnetic și consola electronică sunt furnizate de către client și nu fac obiectul...\n"
            "Pentru elementele care nu funcționează corect din cauza uzurilor sau defectelor ascunse se va face altă ofertă de preț iar timpul de predare...\n"
            "Eșalonare tranșe de plată:\n"
            "Tranșe 1    30% - la acceptarea ofertei de preț\n"
            "Tranșe 2    30% - la livrarea produselor\n"
            "Tranșe 3    40% - la finalizarea lucrării/punerea în funcțiune"
        )
        memo_text = st.text_area("Termeni și Condiții / Mențiuni (Memo)", value=default_memo, height=180)
        
        col_db1, col_db2, col_db3 = st.columns(3)
        
        data_deviz_struct = {
            "id": "DVZ-01", "client": sel_firma_deviz, "masina": sel_masina_deviz, 
            "piese_json": piese_valide_deviz, "tva_procent": tva_setat, "memo": memo_text
        }
        
        with col_db1:
            if st.button("📥 Generează PDF Deviz", type="primary"):
                pdf_deviz_bytes = genereaza_pdf(data_deviz_struct, titlu_doc="Deviz")
                st.download_button("💾 Descarcă Deviz PDF", data=pdf_deviz_bytes, file_name="Deviz_Calcul.pdf", mime="application/pdf")
                
        with col_db2:
            if st.button("📥 Generează PDF Ofertă de Preț"):
                pdf_oferta_bytes = genereaza_pdf(data_deviz_struct, titlu_doc="Oferta de pret")
                st.download_button("💾 Descarcă Ofertă PDF", data=pdf_oferta_bytes, file_name="Oferta_Pret.pdf", mime="application/pdf")
                
        with col_db3:
            if st.button("💾 Salvează & Trimite Deviz pe Email"):
                c.execute("""
                    INSERT INTO devize (tip, firma, masina, piese_json, total_valoare, tva_valoare, total_cu_tva, memo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, ("Deviz / Ofertă", sel_firma_deviz, sel_masina_deviz, json.dumps(piese_valide_deviz, ensure_ascii=False), subtotal_deviz, tva_deviz, total_cu_tva_deviz, memo_text))
                conn.commit()
                
                pdf_deviz_bytes = genereaza_pdf(data_deviz_struct, titlu_doc="Deviz")
                subiect_mail = f"Deviz de Calcul / Ofertă - {sel_firma_deviz}"
                corp_mail = f"Stimate beneficiar,\n\nVă atașăm devizul de calcul pentru echipamentul {sel_masina_deviz}.\n\nEchipa Nexus Industrial"
                
                success, msg = trimite_email_raport(email_client_deviz, subiect_mail, corp_mail, pdf_deviz_bytes, "Deviz.pdf")
                if success:
                    st.success(f"Devizul a fost salvat și e-mailul trimis cu succes! ({msg})")
                else:
                    st.error(msg)
    conn.close()

# ------------------------------------------------------------------------------
# TAB 1: Activități Zilnice
# ------------------------------------------------------------------------------
with tab_activitati:
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id, nume_firma, nume_persoana, email FROM firme")
    firme_db_all = c.fetchall()
    firme_activ = [f[1] for f in firme_db_all]
    
    if not firme_activ:
        st.warning("⚠️ Adăugați cel puțin o firmă în Tabul 5.")
    else:
        sel_firma = st.selectbox("1. Alege Firma la care lucrezi", options=firme_activ, key="act_firma")
        
        persoane_contact_firma = [f[2] for f in firme_db_all if f[1] == sel_firma]
        email_client_destinatar = [f[3] for f in firme_db_all if f[1] == sel_firma][0] if firme_db_all else ""
        
        c.execute("SELECT m.denumire FROM masini m JOIN firme f ON m.firma_id = f.id WHERE f.nume_firma = %s", (sel_firma,))
        masini_firma = [row[0] for row in c.fetchall()]
        sel_masina = st.selectbox("2. Alege Mașina / Echipamentul", options=masini_firma if masini_firma else ["Nicio mașină"], key="act_masina")
        
        subansamblu_list = []
        if masini_firma and sel_masina != "Nicio mașină":
            c.execute("SELECT subansambluri FROM masini WHERE denumire = %s", (sel_masina,))
            sub_db = c.fetchone()
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
                c.execute("SELECT erori FROM masini WHERE denumire = %s", (sel_masina,))
                e_db = c.fetchone()
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
            
        c.execute("SELECT denumire FROM piese")
        piese_catalog = [row[0] for row in c.fetchall()]
        
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
        c.execute("SELECT descriere_pas FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_masina, defect))
        opt_match = c.fetchone()
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
                c.execute("""
                    INSERT INTO reparatii (firma, masina, subansamblu, defect, cod_eroare, piese_json, titlu, simptom, solutie, stare_finala, durata, optimizari, tehnician, verificator)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (sel_firma, sel_masina, sel_subansamblu, defect, cod_eroare, json.dumps(piese_valide, ensure_ascii=False), titlu_lucrare, simptom, solutie, stare_fin, durata_min, optimizari, tehnician_nume, verificator_nume))
                conn.commit()
                
                c.execute("SELECT id FROM reparatii ORDER BY id DESC LIMIT 1")
                ultima_inreg = c.fetchone()
                if ultima_inreg:
                    st.session_state["ultimul_id_salvat"] = ultima_inreg[0]
                    
                st.session_state["raport_salvat"] = True
                st.success("Activitatea a fost salvată în Supabase!")
                st.rerun()
                
        if st.session_state["raport_salvat"] and st.session_state["ultimul_id_salvat"]:
            rid = st.session_state["ultimul_id_salvat"]
            
            c.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare FROM reparatii WHERE id=%s", (rid,))
            full_rep_salvat = c.fetchone()
            
            if full_rep_salvat:
                rdata = full_rep_salvat[15]
                piese_data_salvate = json.loads(full_rep_salvat[7]) if full_rep_salvat[7] else []
                
                # Filtrăm piesele ca să excludem manopera și transportul (case insensitive)
                piese_filtrate_raport = [
                    p for p in piese_data_salvate 
                    if 'manopera' not in p.get('piesa', '').lower() and 'transport' not in p.get('piesa', '').lower()
                ]
                
                date_pdf = {
                    "id": full_rep_salvat[0], "client": full_rep_salvat[1], "masina": full_rep_salvat[2], "subansamblu": full_rep_salvat[3],
                    "durata": full_rep_salvat[4], "cod_eroare": full_rep_salvat[5], "stare_finala": full_rep_salvat[6], "piese_json": piese_filtrate_raport,
                    "titlu": full_rep_salvat[8], "simptom": full_rep_salvat[9], "defect": full_rep_salvat[10], "solutie": full_rep_salvat[11],
                    "optimizari": full_rep_salvat[12], "tehnician": full_rep_salvat[13], "verificator": full_rep_salvat[14], "data": rdata
                }
                pdf_bytes = genereaza_pdf(date_pdf, titlu_doc="RAPORT DE INTERVENTIE TEHNICA")
                
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
                            sheet_url = setari_info[11]  # google_sheet_url
                            if sheet_url:
                                try:
                                    ora_curenta = datetime.now().strftime("%H:%M:%S")
                                    piese_utilizate_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_filtrate_raport if p.get('tip') in ['Utilizata', 'Inlocuita']])
                                    piese_necesare_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_filtrate_raport if p.get('tip') in ['Necesara', 'De Comandat']])
                                    
                                    payload_sheet = {
                                        "sheet_name": "Act zilnica",
                                        "id": str(rid), "data": str(rdata)[:10], "ora": str(ora_curenta),
                                        "firma": str(sel_firma), "masina": str(sel_masina),
                                        "subansamblu": str(sel_subansamblu or "General"), "solutie": str(solutie or ""),
                                        "verificator": str(verificator_nume or ""), "tehnician": str(tehnician_nume or ""),
                                        "piese utilizate": str(piese_utilizate_str), "necesar piese": str(piese_necesare_str),
                                        "stare facturare": "Nefacturat"
                                    }
                                    req_data = json.dumps(payload_sheet).encode('utf-8')
                                    req = urllib.request.Request(sheet_url, data=req_data, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
                                    with urllib.request.urlopen(req) as response:
                                        response.read().decode('utf-8')
                                        st.success("Datele au fost trimise cu succes în Google Sheet ('Act zilnica')!")
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
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT denumire FROM masini")
    masini_existente = [row[0] for row in c.fetchall()]
    
    if not masini_existente:
        st.warning("⚠️ Introduceți mai întâi mașini în Tabul 3.")
    else:
        sel_opt_masina = st.selectbox("Selectează Mașina", options=masini_existente, key="opt_m_sel")
        c.execute("SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = %s", (sel_opt_masina,))
        defecte_existente = [row[0] for row in c.fetchall() if row[0]]
        sel_opt_defect = st.selectbox("Selectează Defectul", options=defecte_existente + ["+ Defect nou"])
        
        def_final = st.text_area("Descriere Defect Nou") if sel_opt_defect == "+ Defect nou" else sel_opt_defect
            
        if sel_opt_defect != "+ Defect nou" and sel_opt_defect:
            st.markdown(f"##### 🔎 Pași existenți:")
            c.execute("SELECT id, pas_numar, descriere_pas FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_opt_masina, sel_opt_defect))
            pasii_db = c.fetchall()
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
                        c.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (%s, %s, %s, %s)",
                                  (sel_opt_masina, def_final, idx+1, pval))
                    conn.commit()
                    st.session_state["pasi_lucrare_t"] = []
                    st.success("Pașii au fost salvați în Supabase!")
                    st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 7: Istoric & Google Sheet
# ------------------------------------------------------------------------------
with tab_rapoarte:
    st.subheader("📋 Istoric Intervenții")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, firma, masina, titlu, data_creare, simptom, solutie, verificator, tehnician FROM reparatii ORDER BY id DESC")
    reparatii_db = c.fetchall()
    
    if reparatii_db:
        for rep in reparatii_db:
            rid, rfirma, rmas, rtit, rdat, rsimp, rsol, rverif, rtech = rep
            with st.expander(f"📄 Raport Inregistrare #{rid} - Firmă: {rfirma} | Echipament: {rmas}"):
                st.write(f"**Titlu:** {rtit}")
                st.write(f"**Soluție:** {rsol}")
                
                c.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare FROM reparatii WHERE id=%s", (rid,))
                full_rep = c.fetchone()
                if full_rep:
                    piese_data = json.loads(full_rep[7]) if full_rep[7] else []
                    piese_filtrate_raport = [
                        p for p in piese_data 
                        if 'manopera' not in p.get('piesa', '').lower() and 'transport' not in p.get('piesa', '').lower()
                    ]
                    date_pdf = {
                        "id": full_rep[0], "client": full_rep[1], "masina": full_rep[2], "subansamblu": full_rep[3],
                        "durata": full_rep[4], "cod_eroare": full_rep[5], "stare_finala": full_rep[6], "piese_json": piese_filtrate_raport,
                        "titlu": full_rep[8], "simptom": full_rep[9], "defect": full_rep[10], "solutie": full_rep[11],
                        "optimizari": full_rep[12], "tehnician": full_rep[13], "verificator": full_rep[14], "data": full_rep[15]
                    }
                    pdf_bytes = genereaza_pdf(date_pdf, titlu_doc="RAPORT DE INTERVENTIE TEHNICA")
                    
                    st.download_button(label=f"📥 Descarcă PDF Raport #{rid}", data=pdf_bytes, file_name=f"Raport_{rid}.pdf", mime="application/pdf", key=f"dl_{rid}")
    else:
        st.info("Nu există rapoarte înregistrate.")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 8: Setări (inclusiv TVA și Pass ascuns)
# ------------------------------------------------------------------------------
with tab_setari:
    st.subheader("⚙️ Setări Aplicație & Conectare")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician, tva, pass FROM setari LIMIT 1")
    current_setari = c.fetchone()
    
    with st.form("form_setari"):
        s_nume = st.text_input("Nume Firma Ta", value=current_setari[0] if current_setari else "Nexus Industrial SRL")
        s_cui = st.text_input("CUI", value=current_setari[1] if current_setari else "")
        s_reg = st.text_input("Nr. Reg. Com.", value=current_setari[2] if current_setari else "")
        s_adresa = st.text_input("Adresă", value=current_setari[3] if current_setari else "")
        s_banca = st.text_input("Bancă", value=current_setari[4] if current_setari else "")
        s_iban = st.text_input("IBAN (Cont)", value=current_setari[5] if current_setari else "")
        s_swep = st.text_input("SWEP (SWIFT)", value=current_setari[6] if current_setari else "")
        s_srv = st.text_input("SMTP Server", value=current_setari[7] if current_setari else "smtp.gmail.com")
        s_prt = st.number_input("SMTP Port", value=int(current_setari[8]) if current_setari and current_setari[8] else 587)
        s_usr = st.text_input("User Gmail", value=current_setari[9] if current_setari else "")
        s_pwd = st.text_input("App Password", type="password", value=current_setari[10] if current_setari else "")
        s_sheet = st.text_input("Google Sheet URL", value=current_setari[11] if current_setari else "")
        s_email_teh = st.text_input("E-mail Tehnician", value=current_setari[12] if current_setari and len(current_setari) > 12 and current_setari[12] else "")
        s_tva = st.number_input("TVA (%)", min_value=0.0, value=float(current_setari[14]) if current_setari and len(current_setari) > 14 and current_setari[14] is not None else 21.0)
        s_pass = st.text_input("Parolă Acces Piese & Devize (Pass)", type="password", value=current_setari[15] if current_setari and len(current_setari) > 15 and current_setari[15] else "nexus123")
        
        if st.form_submit_button("💾 Salvează Setările"):
            c.execute("DELETE FROM setari")
            c.execute("""
                INSERT INTO setari (nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician, tva, pass)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (s_nume, s_cui, s_reg, s_adresa, s_banca, s_iban, s_swep, s_srv, s_prt, s_usr, s_pwd, s_sheet, s_email_teh, s_tva, s_pass))
            conn.commit()
            st.success("Setările au fost salvate cu succes în Supabase!")
            st.rerun()
    conn.close()
