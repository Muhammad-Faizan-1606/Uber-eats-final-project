import os, joblib, pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression

CSV_PATH   = os.getenv("TRAIN_CSV", "data/ue_training_template.csv")
MODEL_PATH = os.getenv("MODEL_PATH", "models/refund_classifier.pkl")

def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "label" not in df.columns:
        raise ValueError("CSV must have 'label' with: deny|refund|escalate")
    df["order_status"] = df["order_status"].astype(str).str.lower().str.replace(" ","_").str.replace("-","_")
    df["refund_history_30d"] = pd.to_numeric(df["refund_history_30d"], errors="coerce").fillna(0).astype(int)
    df["handoff_photo"] = df["handoff_photo"].map(lambda x: str(x).lower() in ("1","true","yes","y","t"))
    df["courier_rating"] = pd.to_numeric(df["courier_rating"], errors="coerce").fillna(4.7)
    df["label"] = df["label"].astype(str).str.lower()
    return df

def train(df: pd.DataFrame):
    X = df[["order_status","refund_history_30d","handoff_photo","courier_rating"]]
    y = df["label"]
    cat = ["order_status","handoff_photo"]
    num = ["refund_history_30d","courier_rating"]
    ct = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
            ("num", StandardScaler(), num)
        ]
    )
    clf = LogisticRegression(max_iter=1000, multi_class="auto")
    pipe = Pipeline(steps=[("prep", ct), ("clf", clf)])
    pipe.fit(X, y)
    return pipe

def main():
    os.makedirs("models", exist_ok=True)
    df = load_data(CSV_PATH)
    pipe = train(df)
    joblib.dump(pipe, MODEL_PATH)
    print(f"Model trained → {MODEL_PATH}")

if __name__ == "__main__":
    main()
