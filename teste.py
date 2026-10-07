import psycopg2
conn = psycopg2.connect("postgresql://postgres.bsuhnbtdysxgdcgfnbzp:Rapoarte%2E100%21%21@aws-1-eu-west-1.pooler.supabase.com:6543/postgres")
print("Conexiune reușită!")
conn.close()
