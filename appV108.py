# ------------------------------------------------------------------------------
    # TAB 4: Tabelul de Piese (Filtrare corectă pe masina_montaj)
    # ------------------------------------------------------------------------------
        with tab_piese:
        st.subheader("🔧 Gestiune Piese de Schimb")
        conn = get_db_connection()
        c = conn.cursor()
        masini_rows = get_masini()
        masini_existente = [row[2] for row in masini_rows]
        
        # Comboboxul principal de sus pentru filtrare
        filtru_piese_masina = st.selectbox(
            "Mașinile pe care se montează", 
            options=["Toate mașinile / General"] + masini_existente, 
            key="select_masina_principal_piese"
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
                p_masini_alese = st.multiselect("Mașinile pe care se montează", options=masini_existente)
                p_sub = st.text_input("Subansamblu")
                
            if st.form_submit_button("💾 Salvează Piesa"):
                if p_denumire:
                    masini_text_str = ", ".join(p_masini_alese) if p_masini_alese else "General"
                    c.execute("""
                        INSERT INTO piese (denumire, cod_producator, cod_comercial, masina_montaj, subansamblu)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (p_denumire, p_cod_prod, p_cod_com, masini_text_str, p_sub))
                    conn.commit()
                    st.cache_data.clear()
                    st.success(f"Piesa **{p_denumire}** a fost salvată în Supabase!")
                    st.rerun()
                else:
                    st.error("Completați denumirea piesei.")

        st.markdown("---")
        st.subheader("📋 Piese Înregistrate (Modificare & Ștergere)")
        
        # Interogare SQL optimizată pentru a căuta mașina în textul din masina_montaj
        if filtru_piese_masina != "Toate mașinile / General":
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
                f"%{filtru_piese_masina}%", 
                f"{filtru_piese_masina},%", 
                f"%, {filtru_piese_masina}%"
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
            st.info("Nu există piese înregistrate pentru mașina selectată.")
        conn.close()
