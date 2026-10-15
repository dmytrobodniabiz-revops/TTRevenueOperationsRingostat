"""Data loading, cleaning and data-quality rules for the Ringostat RevOps test task."""
from pathlib import Path

import pandas as pd

DATA_PATH = str(Path(__file__).resolve().parent / "data" / "deals.xlsx")
CLOSED = ["Closed Won", "Closed Lost"]
STAGE_ORDER = ["Negotiations", "Trial", "Project set up", "Payment", "Closed Won", "Closed Lost"]
PPC_ORDER = ["0", "0-500", "500-1000", "1000-2000", "2000-5000", "5000-10000", "20000+"]
VALID_PERIODS = {"30", "90", "180", "360"}


def load(path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df["Number of sales reps"] = pd.to_numeric(df["Number of sales reps"], errors="coerce")
    df["aql_date"] = pd.to_datetime(df["AQL date"], format="%b %d, %Y", errors="coerce")
    df["close_date"] = pd.to_datetime(df["Closing Date"], format="%b %d, %Y", errors="coerce")
    df["excel_row"] = df.index + 2  # +1 header, +1 for 1-based rows -> row number in the source sheet
    df["country_code"] = df["Client country"].str.extract(r"^([A-Z]{2})")[0]
    df["is_closed"] = df["Stage"].isin(CLOSED)
    df["is_won"] = df["Stage"].eq("Closed Won")
    # Business normalisation: two labels with the same meaning. Flagged separately in data issues.
    df["crm"] = df["Client CRM"].replace({"Is not using": "No CRM"})
    return df


def win_rate(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Win rate = Won / (Won + Lost). Open deals are excluded: their outcome is unknown."""
    c = df[df["is_closed"]]
    g = c.groupby(by).agg(won=("is_won", "sum"), closed=("is_won", "size")).reset_index()
    g["win_rate"] = g["won"] / g["closed"]
    return g


def data_issues(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (rule summary, row-level issues). Rules run on the full dataset."""
    is_open = ~df["is_closed"]
    period = df["Subscription period"]
    rules = [
        ("High", "Closed Won/Lost, but Closing Date is empty", df["is_closed"] & df["close_date"].isna()),
        ("High", "Open stage, but Closing Date is filled", is_open & df["close_date"].notna()),
        ("High", "Closing Date earlier than AQL date", df["close_date"] < df["aql_date"]),
        ("High", "Closed Lost without Loss reason", df["Stage"].eq("Closed Lost") & df["Loss reason description"].isna()),
        ("High", "Loss reason on a deal that is not Closed Lost", ~df["Stage"].eq("Closed Lost") & df["Loss reason description"].notna()),
        ("High", "Closed Won without Subscription period", df["is_won"] & period.isna()),
        ("Medium", "Subscription period on a deal that is not Closed Won", ~df["is_won"] & period.notna()),
        ("Medium", "Subscription period not in 30/90/180/360", period.notna() & ~period.isin(VALID_PERIODS)),
        ("Medium", "Number of sales reps = 0", df["Number of sales reps"].eq(0)),
        ("Low", "Number of sales reps >= 100 (possible outlier or typo)", df["Number of sales reps"] >= 100),
        ("Medium", "Source = Facebook PPC, but PPC budget = 0", df["Source"].eq("Facebook PPC") & df["PPC budget USD"].eq("0")),
        ("Low", "Duplicate row (all columns identical)", df.duplicated(subset=[c for c in df.columns if c in
            ["AQL date", "Source", "Client CRM", "Client country", "Number of sales reps", "Subscription period",
             "PPC budget USD", "Stage", "Loss reason description", "Closing Date"]], keep="first")),
        ("Low", "Client CRM 'Is not using' (duplicates meaning of 'No CRM')", df["Client CRM"].eq("Is not using")),
    ]
    summary, rows = [], []
    show = ["excel_row", "AQL date", "Source", "Client CRM", "Client country", "Stage", "Closing Date",
            "Loss reason description", "Subscription period", "Number of sales reps"]
    for sev, name, mask in rules:
        mask = mask.fillna(False)
        summary.append({"Severity": sev, "Check": name, "Rows": int(mask.sum())})
        if mask.any():
            r = df.loc[mask, show].copy()
            r.insert(0, "Check", name)
            r.insert(0, "Severity", sev)
            rows.append(r)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return pd.DataFrame(summary), out
