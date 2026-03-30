"""ML strategy — XGBoost with walk-forward training for signal generation."""
import pickle
from pathlib import Path

import numpy as np
import polars as pl
from loguru import logger
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from trading.config import TradingConfig
from trading.features.engineering import FeatureEngine
from trading.strategies.base import BaseStrategy, Signal


class MLStrategy(BaseStrategy):
    name = "ml"

    def __init__(self, config: TradingConfig | None = None):
        self.config = config or TradingConfig()
        self.feature_engine = FeatureEngine(self.config)
        self.feature_cols = self.feature_engine.get_feature_columns()
        self.model: XGBRegressor | None = None
        self.scaler: StandardScaler | None = None

    def _build_model(self) -> XGBRegressor:
        return XGBRegressor(
            max_depth=self.config.ml_max_depth,
            n_estimators=self.config.ml_n_estimators,
            learning_rate=self.config.ml_learning_rate,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,  # L1
            reg_lambda=1.0,  # L2
            random_state=42,
            n_jobs=-1,
        )

    def _valid_feature_exprs(self, columns: list[str]) -> list[pl.Expr]:
        return [
            pl.col(col).is_not_null() & pl.col(col).is_finite()
            for col in columns
        ]

    def _drop_invalid_rows(self, df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
        return df.filter(pl.all_horizontal(self._valid_feature_exprs(columns)))

    def train(self, df: pl.DataFrame, symbol: str = "model") -> None:
        """Train model on full dataset (for pre-training before paper trading)."""
        df_feat = self.feature_engine.add_target(df)
        df_clean = self._drop_invalid_rows(df_feat, self.feature_cols + ["target"])

        X = df_clean.select(self.feature_cols).to_numpy()
        y = df_clean["target"].to_numpy()

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = self._build_model()
        self.model.fit(X_scaled, y)

        # Save model
        model_dir = self.config.model_dir
        model_dir.mkdir(parents=True, exist_ok=True)
        with open(model_dir / f"{symbol}_xgb.pkl", "wb") as f:
            pickle.dump({"model": self.model, "scaler": self.scaler}, f)
        logger.info(f"ML model trained on {len(X)} samples, saved to {model_dir}/{symbol}_xgb.pkl")

    def load(self, symbol: str = "model") -> None:
        path = self.config.model_dir / f"{symbol}_xgb.pkl"
        if not path.exists():
            raise FileNotFoundError(f"No trained model at {path}. Run 'train' first.")
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.model = data["model"]
        self.scaler = data["scaler"]
        logger.info(f"Loaded ML model from {path}")

    def generate_signals(self, df: pl.DataFrame) -> pl.DataFrame:
        """Walk-forward signal generation with rolling retrain."""
        cfg = self.config
        train_window = cfg.ml_train_window
        retrain_interval = cfg.ml_retrain_interval
        threshold = cfg.ml_signal_threshold_bps / 10_000  # convert bps to decimal

        feature_cols = self.feature_cols
        n = len(df)
        signals = [Signal.HOLD] * n

        # Need at least train_window + some prediction rows
        if n < train_window + retrain_interval:
            logger.warning(f"Not enough data for walk-forward ({n} rows, need {train_window + retrain_interval})")
            return df.with_columns(pl.Series("signal", signals))

        # Drop rows where features are NaN (warmup period)
        valid_mask = self._drop_invalid_rows(df, feature_cols).height
        warmup = n - valid_mask

        i = max(warmup, train_window)
        last_train = 0

        while i < n:
            # Retrain if needed
            if i - last_train >= retrain_interval or last_train == 0:
                train_start = max(warmup, i - train_window)
                train_slice = df.slice(train_start, i - train_start)
                train_slice = self.feature_engine.add_target(train_slice)
                train_clean = self._drop_invalid_rows(train_slice, feature_cols + ["target"])

                if len(train_clean) < 50:
                    i += 1
                    continue

                X_train = train_clean.select(feature_cols).to_numpy()
                y_train = train_clean["target"].to_numpy()

                self.scaler = StandardScaler()
                X_train_scaled = self.scaler.fit_transform(X_train)

                self.model = self._build_model()
                self.model.fit(X_train_scaled, y_train)
                last_train = i

            # Predict for current row
            row = df.row(i, named=True)
            feat_vals = [row.get(c) for c in feature_cols]

            if any(v is None for v in feat_vals) or not np.isfinite(np.asarray(feat_vals, dtype=float)).all():
                i += 1
                continue

            X_pred = np.array(feat_vals).reshape(1, -1)
            X_pred_scaled = self.scaler.transform(X_pred)
            pred_return = self.model.predict(X_pred_scaled)[0]

            # Map prediction to signal
            if pred_return > 2 * threshold:
                signals[i] = Signal.STRONG_BUY
            elif pred_return > threshold:
                signals[i] = Signal.BUY
            elif pred_return < -2 * threshold:
                signals[i] = Signal.STRONG_SELL
            elif pred_return < -threshold:
                signals[i] = Signal.SELL
            else:
                signals[i] = Signal.HOLD

            i += 1

        return df.with_columns(pl.Series("signal", signals))

    def get_feature_importance(self) -> dict[str, float] | None:
        if self.model is None:
            return None
        importances = self.model.feature_importances_
        return dict(zip(self.feature_cols, importances))
