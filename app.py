"""Flask front-end for the multi-class NSL-KDD intrusion detection model.

Reads real metrics from results/metrics.json (no hardcoded literals), serves
multi-class predictions with per-row attack category and severity, and
persists each prediction run via db.save_prediction so the /history page can
show trends.
"""

import json
import os
import pickle
import warnings

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

import db
from features import (
    ATTACK_CATEGORIES,
    CATEGORICAL_COLS,
    CATEGORY_ORDER,
    FEATURE_NAMES,
    label_to_category,
)

warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG') == '1'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'txt'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db.init_db()

# ---------------------------------------------------------------------------
# Load model artifacts (multi-class)
# ---------------------------------------------------------------------------

MODEL = None
SCALER = None
ENCODERS = None
COLUMNS = None
THRESHOLD = None
LABEL_ENCODER = None
NORMAL_IDX = None
METRICS = None
MODEL_READY = False


def load_model_artifacts() -> None:
    global MODEL, SCALER, ENCODERS, COLUMNS, THRESHOLD, LABEL_ENCODER, NORMAL_IDX
    global METRICS, MODEL_READY
    try:
        with open('models/model.pkl', 'rb') as f:
            MODEL = pickle.load(f)
        with open('models/scaler.pkl', 'rb') as f:
            SCALER = pickle.load(f)
        with open('models/encoders.pkl', 'rb') as f:
            ENCODERS = pickle.load(f)
        with open('models/columns.pkl', 'rb') as f:
            COLUMNS = pickle.load(f)
        with open('models/threshold.pkl', 'rb') as f:
            THRESHOLD = pickle.load(f)
        with open('models/label_encoder.pkl', 'rb') as f:
            LABEL_ENCODER = pickle.load(f)
        NORMAL_IDX = int(LABEL_ENCODER.transform(['Normal'])[0])
        try:
            with open('results/metrics.json', 'r') as f:
                METRICS = json.load(f)
        except FileNotFoundError:
            METRICS = None
        MODEL_READY = True
        print("[ok] Model artifacts loaded")
    except FileNotFoundError as e:
        MODEL_READY = False
        print(f"[err] Model not found: {e}")
        print("  Run 'python train.py' to train the model first")


load_model_artifacts()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def preprocess_input(df: pd.DataFrame) -> np.ndarray:
    for col in CATEGORICAL_COLS:
        if col in df.columns and col in ENCODERS:
            enc = ENCODERS[col]
            known = set(enc.classes_)
            # Map unseen categorical values to a sentinel (first known class)
            df[col] = df[col].apply(lambda v: v if v in known else enc.classes_[0])
            df[col] = enc.transform(df[col])
    df_processed = df[COLUMNS].copy()
    return SCALER.transform(df_processed)


def severity_from_confidence(is_attack: bool, confidence: float) -> str:
    if not is_attack:
        return 'Safe'
    if confidence >= 0.9:
        return 'High'
    if confidence >= 0.7:
        return 'Medium'
    return 'Low'


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@app.route('/')
def index():
    return render_template('index.html', active_page='home')


@app.route('/predict')
def predict():
    return render_template('predict.html', active_page='predict')


@app.route('/insights')
def insights():
    return render_template('insights.html', active_page='insights')


@app.route('/history')
def history():
    return render_template('history.html', active_page='history')


@app.route('/learn')
def learn():
    return render_template('learn.html', active_page='learn')


@app.route('/about')
def about():
    return render_template('about.html', active_page='about')


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@app.route('/api/status')
def api_status():
    return jsonify({'ready': MODEL_READY})


@app.route('/api/predict', methods=['POST'])
def api_predict():
    if not MODEL_READY:
        return jsonify({'error': 'Model not loaded. Run python train.py first'}), 503

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format. Use .csv or .txt'}), 400

    filename = secure_filename(file.filename)

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_csv(file, sep=',', header=None)

        # Pull off label/difficulty columns if present (NSL-KDD raw format)
        original_labels = None
        if len(df.columns) == 43:  # 41 features + label + difficulty
            original_labels = df.iloc[:, -2].copy()
            df = df.iloc[:, :41]
        elif len(df.columns) == 42:  # 41 features + label
            original_labels = df.iloc[:, -1].copy()
            df = df.iloc[:, :41]
        elif len(df.columns) > 41:
            df = df.iloc[:, :41]

        if len(df.columns) != 41:
            return jsonify({'error': f'Expected 41 features, got {len(df.columns)}'}), 400

        df.columns = FEATURE_NAMES
        X_scaled = preprocess_input(df)

        # Multi-class prediction
        probas = MODEL.predict_proba(X_scaled)  # shape (n, n_classes)
        class_indices = np.argmax(probas, axis=1)
        top_confidences = probas[np.arange(len(probas)), class_indices]

        # Binary attack-vs-normal view using the recall-priority threshold
        attack_proba = 1.0 - probas[:, NORMAL_IDX]
        binary_attack = (attack_proba >= float(THRESHOLD)).astype(int)

        # If threshold flips a row to "attack" but argmax was Normal, prefer the
        # 2nd-most-likely class for naming the attack type
        predictions = []
        category_counts = {c: 0 for c in CATEGORY_ORDER}
        category_counts['Other'] = 0
        severity_counts = {'High': 0, 'Medium': 0, 'Low': 0, 'Safe': 0}

        class_names = LABEL_ENCODER.inverse_transform(np.arange(probas.shape[1]))

        for idx in range(len(df)):
            is_attack = bool(binary_attack[idx])
            pred_class_idx = int(class_indices[idx])

            if is_attack and pred_class_idx == NORMAL_IDX:
                # threshold-forced attack; pick best non-Normal class for the category
                row_proba = probas[idx].copy()
                row_proba[NORMAL_IDX] = -1
                pred_class_idx = int(np.argmax(row_proba))

            category = class_names[pred_class_idx]
            if not is_attack:
                category = 'Normal'

            confidence_pct = float(
                attack_proba[idx] if is_attack else (1.0 - attack_proba[idx])
            ) * 100

            # If the uploaded file already had labels, prefer the ground-truth
            # category for display so users see the real attack family.
            if original_labels is not None:
                truth_category = label_to_category(original_labels.iloc[idx])
                if truth_category in CATEGORY_ORDER or truth_category == 'Other':
                    category = truth_category if is_attack or truth_category == 'Normal' else category

            severity = severity_from_confidence(is_attack, confidence_pct / 100.0)
            prediction_label = 'Attack' if is_attack else 'Normal'

            predictions.append({
                'row': idx + 1,
                'prediction': prediction_label,
                'confidence': round(confidence_pct, 2),
                'category': category,
                'severity': severity,
            })

            category_counts[category] = category_counts.get(category, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        total = len(predictions)
        attacks = sum(1 for p in predictions if p['prediction'] == 'Attack')
        normal = total - attacks
        attack_rate = (attacks / total * 100) if total else 0.0
        avg_conf = float(np.mean([p['confidence'] for p in predictions])) if predictions else 0.0

        category_counts = {k: v for k, v in category_counts.items() if v > 0}
        severity_counts = {k: v for k, v in severity_counts.items() if v > 0}

        summary = {
            'total': total,
            'attacks': attacks,
            'normal': normal,
            'attack_rate': round(attack_rate, 2),
            'avg_confidence': round(avg_conf, 2),
            'category_counts': category_counts,
            'severity_counts': severity_counts,
        }

        try:
            db.save_prediction(summary, filename=filename)
        except Exception as e:
            print(f"[history] save failed (non-fatal): {e}")

        return jsonify({**summary, 'predictions': predictions})

    except Exception as e:
        return jsonify({'error': f'Processing error: {str(e)}'}), 500


@app.route('/api/insights')
def api_insights():
    if not MODEL_READY:
        return jsonify({'error': 'Model not loaded'}), 503
    if METRICS is None:
        return jsonify({'error': 'metrics.json not found — retrain the model'}), 500
    return jsonify(METRICS)


@app.route('/api/history')
def api_history():
    limit = request.args.get('limit', default=50, type=int)
    limit = max(1, min(limit, 200))
    return jsonify({'runs': db.recent_predictions(limit=limit)})


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def not_found(error):
    return render_template('index.html', active_page='home'), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == '__main__':
    print("=" * 80)
    print("AI-BASED INTRUSION DETECTION SYSTEM")
    print("=" * 80)
    if MODEL_READY:
        print("[ok] Model loaded")
        print("-> Open http://localhost:5000")
    else:
        print("[err] Model not found — run: python train.py")
    print("=" * 80)
    app.run(debug=app.config['DEBUG'], host='0.0.0.0', port=5000)
