"""
Keras LSTM for Temporal Mental Health Risk Scoring
Architecture: LSTM(64) → Dropout → LSTM(32) → Dense(1, sigmoid)
Input: sequence of 20 risk scores over time
Output: predicted risk score ∈ [0, 1]
"""

import os
import numpy as np
import logging

logger = logging.getLogger("mindgram.lstm")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "lstm_risk_model.keras")
SEQ_LEN = 20


def build_lstm_model():
    """Build and return a compiled Keras LSTM model."""
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    model = keras.Sequential([
        layers.Input(shape=(SEQ_LEN, 1)),
        layers.LSTM(64, return_sequences=True),
        layers.Dropout(0.2),
        layers.LSTM(32, return_sequences=False),
        layers.Dropout(0.2),
        layers.Dense(16, activation="relu"),
        layers.Dense(1, activation="sigmoid"),
    ])

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=["mae"],
    )
    logger.info(f"LSTM model built: {model.count_params()} params")
    return model


def generate_synthetic_training_data(n_samples: int = 5000):
    """
    Generate synthetic temporal risk sequences.
    Patterns:
      - Gradually worsening (high risk)
      - Stable positive (low risk)
      - Fluctuating (medium risk)
      - Sudden spike (high risk end)
    """
    X, y = [], []

    for _ in range(n_samples):
        pattern = np.random.choice(["worsen", "stable", "fluctuate", "spike"])

        if pattern == "worsen":
            seq = np.linspace(0.1, 0.9, SEQ_LEN) + np.random.normal(0, 0.05, SEQ_LEN)
            label = 0.85

        elif pattern == "stable":
            base = np.random.uniform(0.05, 0.25)
            seq = np.full(SEQ_LEN, base) + np.random.normal(0, 0.03, SEQ_LEN)
            label = base

        elif pattern == "fluctuate":
            seq = 0.4 + 0.3 * np.sin(np.linspace(0, 4 * np.pi, SEQ_LEN))
            seq += np.random.normal(0, 0.05, SEQ_LEN)
            label = float(np.mean(seq[-5:]))

        else:  # spike
            seq = np.random.uniform(0.1, 0.3, SEQ_LEN)
            seq[-3:] = np.random.uniform(0.7, 0.95, 3)
            label = 0.8

        seq = np.clip(seq, 0.0, 1.0)
        X.append(seq.reshape(SEQ_LEN, 1))
        y.append(float(np.clip(label, 0.0, 1.0)))

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def train_and_save_lstm():
    """Train LSTM on synthetic data and save to disk."""
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint

    logger.info("Training LSTM on synthetic data...")
    X, y = generate_synthetic_training_data(n_samples=8000)

    split = int(0.8 * len(X))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    model = build_lstm_model()
    callbacks = [
        EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True),
        ModelCheckpoint(MODEL_PATH, save_best_only=True),
    ]

    model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=30,
        batch_size=64,
        callbacks=callbacks,
        verbose=1,
    )

    model.save(MODEL_PATH)
    logger.info(f"LSTM saved to {MODEL_PATH}")
    return model


def build_or_load_lstm():
    """Load from disk if exists, else train from scratch."""
    if os.path.exists(MODEL_PATH):
        from tensorflow import keras
        logger.info(f"Loading LSTM from {MODEL_PATH}")
        return keras.models.load_model(MODEL_PATH)
    else:
        logger.info("No saved LSTM found — training from synthetic data...")
        return train_and_save_lstm()
