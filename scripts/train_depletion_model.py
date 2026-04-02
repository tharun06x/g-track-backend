from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.depletion_prediction import (
    build_training_dataset,
    generate_synthetic_lifecycle_records,
    train_linear_regression_model,
)
from services.feature_pipeline import build_features


def main() -> None:
    synthetic_records = generate_synthetic_lifecycle_records(lifecycle_count=80, seed=11)
    feature_rows = build_features(synthetic_records)
    training_df = build_training_dataset(feature_rows)

    if training_df.empty:
        print("No training rows generated. Adjust synthetic generator settings.")
        return

    result = train_linear_regression_model(training_df)
    print(f"Model saved to: {result.model_path}")
    print(f"Rows used: {result.rows_used}")
    print(f"Validation MAE (days): {result.mae_days:.3f}")
    if result.mae_days <= 1.5:
        print("Quality: useful (<= 1.5 days MAE)")
    else:
        print("Quality: needs improvement (> 1.5 days MAE)")


if __name__ == "__main__":
    main()
