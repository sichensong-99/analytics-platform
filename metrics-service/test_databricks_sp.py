import os
from databricks.sdk import WorkspaceClient

host = os.environ["DATABRICKS_HOST"]
client_id = os.environ["DATABRICKS_CLIENT_ID"]
client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]
warehouse_id = os.environ["DATABRICKS_SQL_WAREHOUSE_ID"]

w = WorkspaceClient(
    host=host,
    client_id=client_id,
    client_secret=client_secret,
)

resp = w.statement_execution.execute_statement(
    warehouse_id=warehouse_id,
    statement="SELECT 1 AS ok",
    wait_timeout="30s",
)

print("Statement ID:", resp.statement_id)
print("Status:", resp.status.state)

if resp.status.error:
    print("Error:", resp.status.error)
