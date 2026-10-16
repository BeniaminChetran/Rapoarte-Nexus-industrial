#-----------------------------------------------------------------------------------
# APLICATIE STREAMLIT OPTIMIZATĂ PENTRU SUPABASE (POSTGRESQL) - VERSIUNE PERFORMANTĂ
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
# 1. Configurare Pagină & Stil UI
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="NexInd",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------------------------------
# 2. Funcții Optimizate cu Cache pentru Reducerea Interogărilor Redundante
# ------------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_setari():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician FROM setari LIMIT 1")
    res = c.fetchone()
    conn.close()
    if res:
        return res
    return ("Nexus Industrial SRL", "", "", "", "", "", "", "smtp.gmail.com", 587, "", "", "", "")

@st.cache_data(ttl=300)
def get_firme():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id,
               nume_firma,
               nume_persoana,
               email
        FROM firme
        ORDER BY nume_firma
    """)
    data = c.fetchall()
    conn.close()
    return data

@st.cache_data(ttl=300)
def get_masini():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere
        FROM masini
    """)
    data = c.fetchall()
    conn.close()
    return data

@st.cache_data(ttl=300)
def get_piese():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, subansamblu
        FROM piese
        ORDER BY denumire
    """)
    data = c.fetchall()
    conn.close()
    return data

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
# 4. Funcție Trimitere Email prin SMTP (cu verificare adresă client)
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
    
    destinatari = []
    
    if destinatar_client and destinatar_client.strip():
        destinatari.append(destinatar_client.strip())
    
    if email_tehnician:
        destinatari.append(email_tehnician.strip())
    destinatari.append("contact@nexusindustrial.ro")
    
    destinatari_unice = [d for d in destinatari if d and d.strip()]
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
                
                if not (destinatar_client and destinatar_client.strip()):
                    return True, "clientul nu are o adresa de email iar emailul va fi trimis doar la personalul Nexus"
                else:
                    return True, f"E-mail trimis cu succes către: {', '.join(destinatari_unice)}"
            else:
                return False, "Setările SMTP (User sau Parolă) nu sunt completate."
    except Exception as e:
        return False, f"Eroare conexiune SMTP ({str(e)})"

# ------------------------------------------------------------------------------
# 5. Interfața Principală Streamlit & Sidebar
# ------------------------------------------------------------------------------
st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("Sistem integrat activ")

if st.sidebar.button("🛑 Închide aplicația", type="primary", key="inchide_server_btn"):
    st.sidebar.warning("Se închide serverul...")
    os._exit(0)

st.sidebar.markdown("---")
st.sidebar.info("Aplicație optimizată pentru mobil și desktop.")

st.title("🛠️ NexInd")

tab_activitati, tab_optimizare, tab_masini, tab_piese, tab_firme, tab_rapoarte, tab_setari = st.tabs([
    "📝 1. Activități", 
    "📊 2. Documentatii / Proceduri de reparatii", 
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
            email = st.text_input("Adresă E-mail Contact")
            telefon = st.text_input("Telefon")
            
        if st.form_submit_button("💾 Salvează Firmă Nouă"):
            if nume_firma and nume_persoana:
                c.execute("""
                    INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon))
                conn.commit()
                st.cache_data.clear()
                st.success(f"Firma **{nume_firma}** a fost salvată în Supabase!")
                st.rerun()
            else:
                st.error("Completați câmpurile obligatorii (*).")

    st.markdown("---")
    st.subheader("📋 Firme Înregistrate (Modificare & Ștergere)")
    firme_db = get_firme()
    
    for f in firme_db:
        fid, fnume, fpers, femail = f[0], f[1], f[2], f[3]
        c.execute("SELECT cui, reg_com, adresa, banca, cont, telefon FROM firme WHERE id = %s", (fid,))
        detalii_f = c.fetchone()
        fcui = detalii_f[0] if detalii_f else ""
        freg = detalii_f[1] if detalii_f else ""
        fadr = detalii_f[2] if detalii_f else ""
        fbanca = detalii_f[3] if detalii_f else ""
        fcont = detalii_f[4] if detalii_f else ""
        ftel = detalii_f[5] if detalii_f else ""

        with st.expander(f"🏢 {fnume} (CUI: {fcui or 'N/A'}) - Contact: {fpers}"):
            with st.form(f"mod_firma_{fid}"):
                mf_nume = st.text_input("Nume Firmă", value=fnume, key=f"mf_n_{fid}")
                mf_cui = st.text_input("CUI", value=fcui or "", key=f"mf_cui_{fid}")
                mf_reg = st.text_input("Reg. Com.", value=freg or "", key=f"mf_reg_{fid}")
                mf_adr = st.text_input("Adresă", value=fadr or "", key=f"mf_adr_{fid}")
                mf_banca = st.text_input("Bancă", value=fbanca or "", key=f"mf_b_{fid}")
                mf_cont = st.text_input("Cont", value=fcont or "", key=f"mf_cont_{fid}")
                mf_pers = st.text_input("Persoană Contact", value=fpers, key=f"mf_p_{fid}")
                mf_email = st.text_input("Email", value=femail or "", key=f"mf_e_{fid}")
                mf_tel = st.text_input("Telefon", value=ftel or "", key=f"mf_t_{fid}")
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    if st.form_submit_button("🔄 Modifică Tot"):
                        c.execute("""
                            UPDATE firme SET nume_firma=%s, cui=%s, reg_com=%s, adresa=%s, banca=%s, cont=%s, nume_persoana=%s, email=%s, telefon=%s
                            WHERE id=%s
                        """, (mf_nume, mf_cui, mf_reg, mf_adr, mf_banca, mf_cont, mf_pers, mf_email, mf_tel, fid))
                        conn.commit()
                        st.cache_data.clear()
                        st.success("Firma a fost actualizată în Supabase!")
                        st.rerun()
                with col_m2:
                    if st.form_submit_button("🗑️ Șterge Firma"):
                        try:
                            c.execute("DELETE FROM firme WHERE id=%s", (fid,))
                            conn.commit()
                            st.cache_data.clear()
                            st.success("Firma a fost ștearsă din Supabase!")
                            st.rerun()
                        except psycopg2.errors.ForeignKeyViolation:
                            conn.rollback()
                            st.error("Sterge masinile asociate acestei firme si apoi sterge firma.")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Eroare la ștergere: {str(e)}")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 3: Lista Mașini & Subansambluri
# ------------------------------------------------------------------------------
with tab_masini:
    st.subheader("🏭 Gestiune Mașini și Echipamente")
    conn = get_db_connection()
    c = conn.cursor()
    firme_list = get_firme()
    firme_dict = {f[1]: f[0] for f in firme_list}
    
    lista_firme_select = ["Nicio firmă"] + list(firme_dict.keys())
    m_firma = st.selectbox("Selectează Firma Proprietară", options=lista_firme_select, key="select_firma_principal_masini")
    
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
                if m_defecte and m_remediu:
                    c.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (%s, %s, %s, %s)",
                              (m_denumire, m_defecte, 1, m_remediu))
                
                c.execute("""
                    INSERT INTO masini (firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (firma_id, m_denumire, m_tip, m_serie, m_an, m_sub, m_erori, m_defecte, m_remediu, m_piese_nec, m_piese_inloc, m_fluide, str(m_data_ment), m_tip_ment))
                conn.commit()
                st.cache_data.clear()
                st.success(f"Mașina **{m_denumire}** a fost salvată în Supabase!")
                st.rerun()
            else:
                st.error("Selectați o firmă validă (alta decât 'Nicio firmă') din meniul de sus și introduceți denumirea mașinii.")

    st.markdown("---")
    st.subheader("📋 Mașini Înregistrate")
    
    if m_firma != "Nicio firmă":
        firma_id_selectat = firme_dict[m_firma]
        c.execute("""
            SELECT m.id, f.nume_firma, m.denumire, m.tip_masina, m.serie, m.an_fabricatie, m.subansambluri, m.erori, m.defecte, m.remediu, m.piese_necesare, m.piese_inlocuite, m.tipuri_fluide, m.tip_intretinere 
            FROM masini m JOIN firme f ON m.firma_id = f.id WHERE m.firma_id = %s
        """, (firma_id_selectat,))
    else:
        c.execute("""
            SELECT m.id, f.nume_firma, m.denumire, m.tip_masina, m.serie, m.an_fabricatie, m.subansambluri, m.erori, m.defecte, m.remediu, m.piese_necesare, m.piese_inlocuite, m.tipuri_fluide, m.tip_intretinere 
            FROM masini m JOIN firme f ON m.firma_id = f.id
        """)
        
    masini_db = c.fetchall()
    
    if masini_db:
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
                            st.cache_data.clear()
                            st.success("Mașină actualizată în Supabase!")
                            st.rerun()
                    with col_mm2:
                        if st.form_submit_button("🗑️ Șterge Mașina"):
                            c.execute("DELETE FROM masini WHERE id=%s", (mid,))
                            conn.commit()
                            st.cache_data.clear()
                            st.success("Mașina a fost ștearsă din Supabase!")
                            st.rerun()
    else:
        st.info("Nu există mașini înregistrate pentru firma selectată.")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 1: Activități Zilnice
# ------------------------------------------------------------------------------
with tab_activitati:
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")
    conn = get_db_connection()
    c = conn.cursor()
    
    firme_db_all = get_firme()
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
            
        piese_catalog_rows = get_piese()
        piese_catalog = [row[1] for row in piese_catalog_rows]
        
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
                    rid_nou = ultima_inreg[0]
                    st.session_state["ultimul_id_salvat"] = rid_nou
                    
                    setari_info = get_setari()
                    sheet_url = setari_info[11]
                    if sheet_url:
                        try:
                            ora_curenta = datetime.now().strftime("%H:%M:%S")
                            data_curenta = datetime.now().strftime("%Y-%m-%d")
                            piese_utilizate_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_valide if p.get('tip') in ['Utilizata', 'Inlocuita']])
                            piese_necesare_str = ", ".join([f"{p.get('piesa')} ({p.get('cantitate')})" for p in piese_valide if p.get('tip') in ['Necesara', 'De Comandat']])
                            
                            payload_sheet = {
                                "status": "nefacturat",
                                "id": str(rid_nou),
                                "data": str(data_curenta),
                                "ora": str(ora_curenta),
                                "firma": str(sel_firma),
                                "masina": str(sel_masina),
                                "subansamblu": str(sel_subansamblu or "General"),
                                "solutie": str(solutie or ""),
                                "verificator": str(verificator_nume or ""),
                                "tehnician": str(tehnician_nume or ""),
                                "piese utilizate": str(piese_utilizate_str),
                                "necesar piese": str(piese_necesare_str)
                            }
                            req_data = json.dumps(payload_sheet).encode('utf-8')
                            req = urllib.request.Request(sheet_url, data=req_data, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(req) as response:
                                response.read().decode('utf-8')
                        except Exception as e:
                            st.warning(f"Nu s-a putut trimite în Google Sheet: {str(e)}")

                st.session_state["raport_salvat"] = True
                st.success("Activitatea a fost salvată în Supabase și trimisă în Google Sheet!")
                st.rerun()
                
        if st.session_state["raport_salvat"] and st.session_state["ultimul_id_salvat"]:
            rid = st.session_state["ultimul_id_salvat"]
            
            c.execute("SELECT id, firma, masina, subansamblu, durata, cod_eroare, stare_finala, piese_json, titlu, simptom, defect, solutie, optimizari, tehnician, verificator, data_creare FROM reparatii WHERE id=%s", (rid,))
            full_rep_salvat = c.fetchone()
            
            if full_rep_salvat:
                rdata = full_rep_salvat[15]
                piese_data_salvate = json.loads(full_rep_salvat[7]) if full_rep_salvat[7] else []
                
                date_pdf = {
                    "id": full_rep_salvat[0], "client": full_rep_salvat[1], "masina": full_rep_salvat[2], "subansamblu": full_rep_salvat[3],
                    "durata": full_rep_salvat[4], "cod_eroare": full_rep_salvat[5], "stare_finala": full_rep_salvat[6], "piese_json": piese_data_salvate,
                    "titlu": full_rep_salvat[8], "simptom": full_rep_salvat[9], "defect": full_rep_salvat[10], "solutie": full_rep_salvat[11],
                    "optimizari": full_rep_salvat[12], "tehnician": full_rep_salvat[13], "verificator": full_rep_salvat[14], "data": rdata
                }
                
                with col_b2:
                    if st.button("Generează PDF"):
                        st.session_state["pdf_bytes_curent"] = genereaza_pdf(date_pdf)
                        
                    if "pdf_bytes_curent" in st.session_state and st.session_state["pdf_bytes_curent"]:
                        st.download_button(
                            label=f"📥 Printează / Descarcă Raport #{rid}",
                            data=st.session_state["pdf_bytes_curent"],
                            file_name=f"Raport_Interventie_{rid}.pdf",
                            mime="application/pdf",
                            type="primary"
                        )
                    
                with col_b3:
                    if st.button("📧 Trimite pe Email către Verificator"):
                        pdf_bytes_email = st.session_state.get("pdf_bytes_curent") or genereaza_pdf(date_pdf)
                        subiect = f"Raport de Interventie Tehnica #{rid} - {sel_firma}"
                        corp = f"Stimate beneficiar ({verificator_nume}),\n\nVă atașăm raportul de intervenție tehnică #{rid} pentru echipamentul {sel_masina}.\n\nEchipa NexInd"
                        
                        success, msg = trimite_email_raport(email_client_destinatar, subiect, corp, pdf_bytes_email, f"Raport_{rid}.pdf")
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
    conn.close()

# ------------------------------------------------------------------------------
# TAB 2: Documentatii / Proceduri de reparații
# ------------------------------------------------------------------------------
with tab_optimizare:
    st.subheader("📊 Documentatii / Proceduri de reparații")
    conn = get_db_connection()
    c = conn.cursor()
    masini_rows = get_masini()
    masini_existente = [row[2] for row in masini_rows]
    
    if not masini_existente:
        st.warning("⚠️ Introduceți mai întâi mașini în Tabul 3.")
    else:
        sel_opt_masina = st.selectbox("Selectează Mașina", options=masini_existente, key="opt_m_sel")
        c.execute("SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = %s", (sel_opt_masina,))
        defecte_existente = [row[0] for row in c.fetchall() if row[0]]
        sel_opt_defect = st.selectbox("Selectează Defectul / Procedura", options=defecte_existente + ["+ Defect nou"])
        
        def_final = st.text_area("Descriere Defect Nou") if sel_opt_defect == "+ Defect nou" else sel_opt_defect
            
        if sel_opt_defect != "+ Defect nou" and sel_opt_defect:
            st.markdown(f"##### 🔎 Editare Pași de Reparație Existenti:")
            c.execute("SELECT id, pas_numar, descriere_pas FROM optimizari_interventie WHERE masina = %s AND defect = %s ORDER BY pas_numar", (sel_opt_masina, sel_opt_defect))
            pasii_db = c.fetchall()
            
            with st.form(f"form_edita_pasi_{sel_opt_masina}_{sel_opt_defect}"):
                pasi_editati_dict = {}
                for pe in pasii_db:
                    pid_pas, pnum, pdesc = pe[0], pe[1], pe[2]
                    pasi_editati_dict[pid_pas] = st.text_input(f"Pasul {pnum}", value=pdesc, key=f"edit_pas_db_{pid_pas}")
                
                col_ep1, col_ep2 = st.columns(2)
                with col_ep1:
                    if st.form_submit_button("🔄 Actualizează Pașii Modificați"):
                        for pid_pas, val_noua in pasi_editati_dict.items():
                            c.execute("UPDATE optimizari_interventie SET descriere_pas = %s WHERE id = %s", (val_noua, pid_pas))
                        conn.commit()
                        st.success("Procedura / pașii de reparație au fost actualizați cu succes!")
                        st.rerun()
                with col_ep2:
                    if st.form_submit_button("🗑️ Șterge Toată Procedura"):
                        c.execute("DELETE FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_opt_masina, sel_opt_defect))
                        conn.commit()
                        st.success("Procedura a fost ștearsă!")
                        st.rerun()
            st.markdown("---")
            
        st.markdown("##### Adăugare Pași Noi")
        if "pasi_lucrare_t" not in st.session_state:
            st.session_state["pasi_lucrare_t"] = []
            
        with st.form("form_add_pas", clear_on_submit=True):
            desc_p_nou = st.text_area("Descriere pas remediu nou")
            if st.form_submit_button("➕ Adaugă Pas în Listă"):
                if desc_p_nou:
                    st.session_state["pasi_lucrare_t"].append(desc_p_nou)
                    st.success("Pas adăugat în memorie!")
                    st.rerun()
                    
        if st.session_state["pasi_lucrare_t"]:
            pasi_modificati = [st.text_input(f"Pas nou {idx+1}", value=pval, key=f"pas_ed_{idx}") for idx, pval in enumerate(st.session_state["pasi_lucrare_t"])]
                
            if st.button("💾 Salvează Toți Pașii Noi în Baza de Date", type="primary"):
                if def_final:
                    c.execute("SELECT MAX(pas_numar) FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_opt_masina, def_final))
                    max_p = c.fetchone()
                    start_nr = (max_p[0] if max_p and max_p[0] else 0) + 1
                    
                    for idx, pval in enumerate(pasi_modificati):
                        c.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (%s, %s, %s, %s)",
                                  (sel_opt_masina, def_final, start_nr + idx, pval))
                    conn.commit()
                    st.session_state["pasi_lucrare_t"] = []
                    st.success("Pașii noi au fost salvați în Supabase!")
                    st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 4: Tabelul de Piese (Un singur control unificat pentru filtrare și adăugare)
# ------------------------------------------------------------------------------
with tab_piese:
    st.subheader("🔧 Gestiune Piese de Schimb")
    conn = get_db_connection()
    c = conn.cursor()
    masini_rows = get_masini()
    masini_existente = [row[2] for row in masini_rows]
    
    # UN SINGUR ELEMENT DE SELECȚIE PRINCIPAL (Afișat sus, în afara form-urilor)
    select_masina_unica = st.selectbox(
        "Selectează Mașina (Filtrare listă & Asociere piesă nouă)", 
        options=["Toate mașinile / General"] + masini_existente, 
        key="select_masina_unica_piese"
    )
    
    st.markdown("---")
    st.subheader("➕ Adaugă Piesă Nouă")
    
    with st.form("form_piese", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            p_denumire = st.text_input("Denumire Piesă *")
            p_cod_prod = st.text_input("Cod Producător")
            p_cod_com = st.text_input("Cod Comercial")
        with c2:
            p_sub = st.text_input("Subansamblu")
            # Informare clară legată de mașina preluată automat din controlul unic de sus
            st.info(f"📍 Piesa se va înregistra pentru: **{select_masina_unica}**")
            
        if st.form_submit_button("💾 Salvează Piesa"):
            if p_denumire:
                masini_text_str = select_masina_unica if select_masina_unica != "Toate mașinile / General" else "General"
                c.execute("""
                    INSERT INTO piese (denumire, cod_producator, cod_comercial, masina_montaj, subansamblu)
                    VALUES (%s, %s, %s, %s, %s)
                """, (p_denumire, p_cod_prod, p_cod_com, masini_text_str, p_sub))
                conn.commit()
                st.cache_data.clear()
                st.success(f"Piesa **{p_denumire}** a fost salvată pentru **{masini_text_str}**!")
                st.rerun()
            else:
                st.error("Completați denumirea piesei.")

    st.markdown("---")
    st.subheader("📋 Piese Înregistrate (Modificare & Ștergere)")
    
    # FILTRAREA INSTANTANEE A LISTEI FOLOSIND ACELAȘI CONTROL UNIC DE SUS
    if select_masina_unica != "Toate mașinile / General":
        c.execute("""
            SELECT * FROM piese 
            WHERE TRIM(masina_montaj) ILIKE %s 
               OR TRIM(masina_montaj) ILIKE %s 
               OR TRIM(masina_montaj) ILIKE %s 
               OR masina_montaj ILIKE 'General'
               OR masina_montaj = ''
               OR masina_montaj IS NULL
            ORDER BY denumire
        """, (
            f"%{select_masina_unica}%", 
            f"{select_masina_unica},%", 
            f"%, {select_masina_unica}%"
        ))
    else:
        c.execute("""
            SELECT * FROM piese
            ORDER BY denumire
        """)
        
    piese_db_all = c.fetchall()
    
    if piese_db_all:
        for p in piese_db_all:
            pid, pden, pcod_p, pcod_c, pmas, psub = p[0], p[1], p[2], p[3], p[4], p[5]
            with st.expander(f"🔩 {pden} (Mașini: {pmas})"):
                with st.form(f"mod_piesa_{pid}"):
                    mp_den = st.text_input("Denumire Piesă", value=pden, key=f"mp_den_{pid}")
                    mp_prod = st.text_input("Cod Producător", value=pcod_p or "", key=f"mp_prod_{pid}")
                    mp_com = st.text_input("Cod Comercial", value=pcod_c or "", key=f"mp_com_{pid}")
                    mp_mas = st.text_input("Mașini Montaj", value=pmas or "", key=f"mp_mas_{pid}")
                    mp_sub = st.text_input("Subansamblu", value=psub or "", key=f"mp_sub_{pid}")
                    
                    col_mp1, col_mp2 = st.columns(2)
                    with col_mp1:
                        if st.form_submit_button("🔄 Actualizează Piesa"):
                            c.execute("""
                                UPDATE piese SET denumire=%s, cod_producator=%s, cod_comercial=%s, masina_montaj=%s, subansamblu=%s
                                WHERE id=%s
                            """, (mp_den, mp_prod, mp_com, mp_mas, mp_sub, pid))
                            conn.commit()
                            st.cache_data.clear()
                            st.success("Piesa a fost actualizată în baza de date!")
                            st.rerun()
                    with col_mp2:
                        if st.form_submit_button("🗑️ Șterge Piesa"):
                            c.execute("DELETE FROM piese WHERE id=%s", (pid,))
                            conn.commit()
                            st.cache_data.clear()
                            st.success("Piesa a fost ștearsă din baza de date!")
                            st.rerun()
    else:
        st.info(f"Nu există piese înregistrate pentru selecția curentă ({select_masina_unica}).")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 6: Istoric & Google Sheet
# ------------------------------------------------------------------------------
with tab_rapoarte:
    st.subheader("📋 Istoric Intervenții")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT *
        FROM reparatii
        ORDER BY id DESC
        LIMIT 100
    """)
    reparatii_db = c.fetchall()
    
    if reparatii_db:
        for full_rep in reparatii_db:
            rid = full_rep[0]
            rfirma = full_rep[1]
            rmas = full_rep[2]
            rsub = full_rep[3]
            rdef = full_rep[4]
            rcod_err = full_rep[5]
            rpiese_json = full_rep[6]
            rtit = full_rep[7]
            rsimp = full_rep[8]
            rsol = full_rep[9]
            rstare = full_rep[10]
            rdurata = full_rep[11]
            ropt = full_rep[12]
            rtech = full_rep[13]
            rverif = full_rep[14]
            rdata = full_rep[15]
            
            with st.expander(f"📄 Raport Inregistrare #{rid} - Firmă: {rfirma} | Echipament: {rmas}"):
                st.write(f"**Titlu:** {rtit}")
                st.write(f"**Soluție:** {rsol}")
                
                piese_data = json.loads(rpiese_json) if rpiese_json else []
                date_pdf = {
                    "id": rid, "client": rfirma, "masina": rmas, "subansamblu": rsub,
                    "durata": rdurata, "cod_eroare": rcod_err, "stare_finala": rstare, "piese_json": piese_data,
                    "titlu": rtit, "simptom": rsimp, "defect": rdef, "solutie": rsol,
                    "optimizari": ropt, "tehnician": rtech, "verificator": rverif, "data": rdata
                }
                
                if st.button(f"Generează PDF Raport #{rid}", key=f"btn_pdf_{rid}"):
                    st.session_state[f"pdf_bytes_{rid}"] = genereaza_pdf(date_pdf)
                    
                if f"pdf_bytes_{rid}" in st.session_state:
                    st.download_button(label=f"📥 Descarcă PDF Raport #{rid}", data=st.session_state[f"pdf_bytes_{rid}"], file_name=f"Raport_{rid}.pdf", mime="application/pdf", key=f"dl_{rid}")
    else:
        st.info("Nu există rapoarte înregistrate.")
    conn.close()

# ------------------------------------------------------------------------------
# TAB 7: Setări
# ------------------------------------------------------------------------------
with tab_setari:
    st.subheader("⚙️ Setări Aplicație & Conectare")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician FROM setari LIMIT 1")
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
        
        if st.form_submit_button("💾 Salvează Setările"):
            c.execute("DELETE FROM setari")
            c.execute("""
                INSERT INTO setari (nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (s_nume, s_cui, s_reg, s_adresa, s_banca, s_iban, s_swep, s_srv, s_prt, s_usr, s_pwd, s_sheet, s_email_teh))
            conn.commit()
            st.cache_data.clear()
            st.success("Setările au fost salvate cu succes în Supabase!")
            st.rerun()
    conn.close()
