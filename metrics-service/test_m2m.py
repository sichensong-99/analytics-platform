import os
from databricks import sql
from databricks.sdk.core import Config, oauth_service_principal

HOST      = "dbc-620cc0fc-b4ee.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/39f94dd6ed9a78a4"
CLIENT_ID = os.environ["DATABRICKS_CLIENT_ID"]
SECRET    = os.environ["DATABRICKS_CLIENT_SECRET"]

def credential_provider():
    cfg = Config(host=f"https://{HOST}", client_id=CLIENT_ID, client_secret=SECRET)
    return oauth_service_principal(cfg)

print("1) 建连接(测 M2M 鉴权 + warehouse Can-use)...")
conn = sql.connect(server_hostname=HOST, http_path=HTTP_PATH,
                   credentials_provider=credential_provider)
print("   ✅ 连上了 = 鉴权 OK + warehouse 能用")

with conn.cursor() as c:
    print("2) SELECT 1(测最基础查询)...")
    c.execute("SELECT 1")
    print("   ✅", c.fetchone())

    print("3) 读真表(测 Unity Catalog 的 SELECT 权限)...")
    c.execute("SELECT COUNT(*) FROM mvdevdatabricks.analytics_platform_32degrees.fact_orders_line")
    print("   ✅ fact_orders_line 行数 =", c.fetchone()[0])

conn.close()
print("\n🎉 全过 —— SP 凭据 + warehouse + 数据权限都 OK,可以放心翻 ACA")