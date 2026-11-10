import requests
import ssl
from requests.adapters import HTTPAdapter

# Adaptor personalizat pentru a permite comunicarea cu serverul ANAF (evită Connection reset)
class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

def obtine_date_anaf(cui_input):
    cui_curat = ''.join(filter(str.isdigit, str(cui_input)))
    if not cui_curat:
        return None, "Introduceți un CUI valid!"
    
    url = "https://webservicesp.anaf.ro/PlatitorTvaRest/api/v6/ws/tva"
    payload = [{"cui": int(cui_curat), "data": date.today().strftime("%Y-%m-%d")}]
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # Folosim o sesiune cu adaptorul SSL personalizat
        session = requests.Session()
        session.mount("https://", LegacySSLAdapter())
        
        response = session.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            found = res_data.get("found", [])
            if found:
                date_f = found[0]
                date_gen = date_f.get("date_generale", {})
                adresa_sediu = date_f.get("adresa_sediu_social", {})
                
                strada = adresa_sediu.get("sden_strada", "")
                nr = adresa_sediu.get("sden_numar", "")
                loc = adresa_sediu.get("sden_localitate", "")
                jud = adresa_sediu.get("sden_judet", "")
                adresa_text = f"{loc}, Jud. {jud}, Str. {strada} Nr. {nr}".strip(", ")
                
                return {
                    "nume_firma": date_gen.get("denumire", ""),
                    "cui": str(date_gen.get("cui", "")),
                    "reg_com": date_gen.get("nrRegCom", ""),
                    "adresa": adresa_text or date_gen.get("adresa", "")
                }, None
            else:
                return None, "CUI-ul nu a fost găsit în baza de date ANAF."
        else:
            return None, f"Eroare HTTP de la ANAF: {response.status_code}"
    except Exception as e:
        return None, f"Eroare la conectarea cu API-ul ANAF: {e}"
