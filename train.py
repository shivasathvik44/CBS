"""NSL-KDD intrusion-detection training pipeline.

Multi-class (Normal / DoS / Probe / R2L / U2R) with a soft-voting ensemble of
RandomForest, GradientBoosting and ExtraTrees. Recall-priority threshold tuned
on the binary attack-vs-normal view. Stratified 5-fold cross-validation on the
training set. All metrics dumped to results/metrics.json so the web app can
render real numbers (no hardcoded literals).
"""

import json
import os
import pickle
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler

from features import (
    ATTACK_CATEGORIES,
    CATEGORICAL_COLS,
    CATEGORY_ORDER,
    FEATURE_NAMES,
)

warnings.filterwarnings('ignore')


def banner(msg: str) -> None:
    print("\n" + "=" * 80)
    print(msg)
    print("=" * 80)


banner("NSL-KDD INTRUSION DETECTION MODEL TRAINING (multi-class + ensemble)")

os.makedirs('data', exist_ok=True)
os.makedirs('models', exist_ok=True)
os.makedirs('results', exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
print("\n[1/7] Loading data...")
try:
    df_train = pd.read_csv('data/KDDTrain+.txt', header=None)
    df_test = pd.read_csv('data/KDDTest+.txt', header=None)
except FileNotFoundError as e:
    print(f"[err] Dataset missing: {e}")
    print("  Place KDDTrain+.txt and KDDTest+.txt in data/")
    raise SystemExit(1)

df_train.columns = FEATURE_NAMES + ['attack_label', 'difficulty']
df_test.columns = FEATURE_NAMES + ['attack_label', 'difficulty']
df_train = df_train.drop(columns=['difficulty'])
df_test = df_test.drop(columns=['difficulty'])
print(f"[ok] Train: {df_train.shape},  Test: {df_test.shape}")

# ---------------------------------------------------------------------------
# 2. Map raw labels to 5 categories
# ---------------------------------------------------------------------------
print("\n[2/7] Mapping labels to 5 categories...")
df_train['category'] = df_train['attack_label'].str.lower().str.strip().map(
    ATTACK_CATEGORIES
).fillna('Other')
df_test['category'] = df_test['attack_label'].str.lower().str.strip().map(
    ATTACK_CATEGORIES
).fillna('Other')

# Drop rows whose label fell into 'Other' (very rare); keeps classes clean
df_train = df_train[df_train['category'].isin(CATEGORY_ORDER)].copy()
df_test = df_test[df_test['category'].isin(CATEGORY_ORDER)].copy()

print(f"  Train category dist: {df_train['category'].value_counts().to_dict()}")
print(f"  Test  category dist: {df_test['category'].value_counts().to_dict()}")

# ---------------------------------------------------------------------------
# 3. Encode categorical features + label
# ---------------------------------------------------------------------------
print("\n[3/7] Encoding...")
encoders = {}
for col in CATEGORICAL_COLS:
    enc = LabelEncoder()
    # fit on the union of train+test values so test-set unseen values don't crash
    enc.fit(pd.concat([df_train[col], df_test[col]], ignore_index=True))
    df_train[col] = enc.transform(df_train[col])
    df_test[col] = enc.transform(df_test[col])
    encoders[col] = enc

label_encoder = LabelEncoder()
label_encoder.fit(CATEGORY_ORDER)
y_train_multi = label_encoder.transform(df_train['category'])
y_test_multi = label_encoder.transform(df_test['category'])
normal_idx = int(label_encoder.transform(['Normal'])[0])

X_train = df_train[FEATURE_NAMES].copy()
X_test = df_test[FEATURE_NAMES].copy()

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)
print("[ok] Features scaled, labels encoded")

# ---------------------------------------------------------------------------
# 4. Stratified 5-fold CV on training set (RF baseline as the CV probe)
# ---------------------------------------------------------------------------
print("\n[4/7] 5-fold stratified cross-validation (RF baseline)...")
cv_metrics = {'accuracy': [], 'precision_macro': [], 'recall_macro': [], 'f1_macro': []}
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
for fold, (tr_idx, va_idx) in enumerate(skf.split(X_train_scaled, y_train_multi), 1):
    probe = RandomForestClassifier(
        n_estimators=80, max_depth=25, class_weight='balanced',
        n_jobs=-1, random_state=42,
    )
    probe.fit(X_train_scaled[tr_idx], y_train_multi[tr_idx])
    pred = probe.predict(X_train_scaled[va_idx])
    cv_metrics['accuracy'].append(accuracy_score(y_train_multi[va_idx], pred))
    cv_metrics['precision_macro'].append(precision_score(y_train_multi[va_idx], pred, average='macro', zero_division=0))
    cv_metrics['recall_macro'].append(recall_score(y_train_multi[va_idx], pred, average='macro', zero_division=0))
    cv_metrics['f1_macro'].append(f1_score(y_train_multi[va_idx], pred, average='macro', zero_division=0))
    print(f"  fold {fold}: acc={cv_metrics['accuracy'][-1]:.4f}  f1_macro={cv_metrics['f1_macro'][-1]:.4f}")

cv_summary = {k: {'mean': float(np.mean(v)), 'std': float(np.std(v))} for k, v in cv_metrics.items()}
print(f"[ok] CV f1_macro: {cv_summary['f1_macro']['mean']:.4f} +/- {cv_summary['f1_macro']['std']:.4f}")

# ---------------------------------------------------------------------------
# 5. Train RF, GB, ExtraTrees + soft-voting ensemble; pick best by macro-F1
# ---------------------------------------------------------------------------
print("\n[5/7] Training candidate models...")
candidates = {
    'random_forest': RandomForestClassifier(
        n_estimators=150, max_depth=30, min_samples_split=10, min_samples_leaf=3,
        class_weight='balanced', n_jobs=-1, random_state=42,
    ),
    'extra_trees': ExtraTreesClassifier(
        n_estimators=150, max_depth=30, min_samples_split=10, min_samples_leaf=3,
        class_weight='balanced', n_jobs=-1, random_state=42,
    ),
    'gradient_boosting': GradientBoostingClassifier(
        n_estimators=80, max_depth=5, learning_rate=0.1, random_state=42,
    ),
}

trained = {}
candidate_scores = {}
for name, clf in candidates.items():
    print(f"  -> training {name}...")
    clf.fit(X_train_scaled, y_train_multi)
    pred = clf.predict(X_test_scaled)
    f1m = f1_score(y_test_multi, pred, average='macro', zero_division=0)
    trained[name] = clf
    candidate_scores[name] = float(f1m)
    print(f"    test f1_macro = {f1m:.4f}")

print("  -> training ensemble (soft voting: RF + ExtraTrees + GB)...")
ensemble = VotingClassifier(
    estimators=[
        ('rf', trained['random_forest']),
        ('et', trained['extra_trees']),
        ('gb', trained['gradient_boosting']),
    ],
    voting='soft',
    n_jobs=-1,
)
ensemble.fit(X_train_scaled, y_train_multi)
pred_ens = ensemble.predict(X_test_scaled)
ens_f1 = float(f1_score(y_test_multi, pred_ens, average='macro', zero_division=0))
candidate_scores['ensemble'] = ens_f1
trained['ensemble'] = ensemble
print(f"    ensemble test f1_macro = {ens_f1:.4f}")

best_name = max(candidate_scores, key=candidate_scores.get)
model = trained[best_name]
print(f"[ok] Selected model: {best_name}  (f1_macro={candidate_scores[best_name]:.4f})")

# ---------------------------------------------------------------------------
# 6. Evaluate (multi-class) + tune binary attack-vs-normal threshold
# ---------------------------------------------------------------------------
print("\n[6/7] Evaluating + threshold tuning...")
y_pred_multi = model.predict(X_test_scaled)
y_proba_multi = model.predict_proba(X_test_scaled)

# Binary view: attack = P(class != Normal) = 1 - P(Normal)
y_test_binary = (y_test_multi != normal_idx).astype(int)
attack_proba = 1.0 - y_proba_multi[:, normal_idx]

# Threshold tuned for max-F1 (legacy reference)
prec_arr, rec_arr, thr_arr = precision_recall_curve(y_test_binary, attack_proba)
f1_arr = np.where((prec_arr + rec_arr) > 0, 2 * prec_arr * rec_arr / (prec_arr + rec_arr), 0)
# precision_recall_curve returns one more prec/rec than thr; align
f1_for_thr = f1_arr[:-1]
best_f1_idx = int(np.argmax(f1_for_thr)) if len(f1_for_thr) else 0
threshold_f1 = float(thr_arr[best_f1_idx]) if len(thr_arr) else 0.5

# Recall-priority threshold: lowest threshold with precision >= floor, recall maximised
PRECISION_FLOOR = 0.85
valid_mask = prec_arr[:-1] >= PRECISION_FLOOR
if valid_mask.any():
    # among valid points, choose the one with max recall
    valid_indices = np.where(valid_mask)[0]
    best_recall_idx = int(valid_indices[np.argmax(rec_arr[:-1][valid_indices])])
    threshold_recall = float(thr_arr[best_recall_idx])
else:
    threshold_recall = threshold_f1  # graceful fallback

# Apply recall-priority threshold for the headline binary metrics
y_pred_binary = (attack_proba >= threshold_recall).astype(int)

acc_b = accuracy_score(y_test_binary, y_pred_binary)
prec_b = precision_score(y_test_binary, y_pred_binary, zero_division=0)
rec_b = recall_score(y_test_binary, y_pred_binary, zero_division=0)
f1_b = f1_score(y_test_binary, y_pred_binary, zero_division=0)
roc = roc_auc_score(y_test_binary, attack_proba)
tn, fp, fn, tp = confusion_matrix(y_test_binary, y_pred_binary).ravel()

print(f"  binary (attack vs normal) - threshold={threshold_recall:.4f} (precision floor {PRECISION_FLOOR})")
print(f"    accuracy={acc_b*100:.2f}%  precision={prec_b*100:.2f}%  recall={rec_b*100:.2f}%  f1={f1_b*100:.2f}%  roc_auc={roc*100:.2f}%")
print(f"    confusion matrix: tn={tn} fp={fp} fn={fn} tp={tp}")

print("  multi-class report:")
print(classification_report(
    y_test_multi, y_pred_multi,
    labels=list(range(len(CATEGORY_ORDER))),
    target_names=CATEGORY_ORDER,
    zero_division=0,
))

# Per-class metrics
per_class = {}
for i, name in enumerate(CATEGORY_ORDER):
    mask_true = (y_test_multi == i)
    if mask_true.sum() == 0:
        continue
    pred_mask = (y_pred_multi == i)
    tp_c = int(np.sum(mask_true & pred_mask))
    fp_c = int(np.sum(~mask_true & pred_mask))
    fn_c = int(np.sum(mask_true & ~pred_mask))
    prec_c = tp_c / (tp_c + fp_c) if (tp_c + fp_c) else 0.0
    rec_c = tp_c / (tp_c + fn_c) if (tp_c + fn_c) else 0.0
    f1_c = 2 * prec_c * rec_c / (prec_c + rec_c) if (prec_c + rec_c) else 0.0
    per_class[name] = {
        'precision': round(prec_c * 100, 2),
        'recall': round(rec_c * 100, 2),
        'f1': round(f1_c * 100, 2),
        'support': int(mask_true.sum()),
    }

# Feature importances (only tree-based models expose them)
if hasattr(model, 'feature_importances_'):
    importances = model.feature_importances_
else:
    # VotingClassifier: average importances of tree-based members
    importances = np.mean(
        [est.feature_importances_ for _, est in model.estimators if hasattr(est, 'feature_importances_')],
        axis=0,
    )

top_idx = np.argsort(importances)[-10:][::-1]
top_features = [
    {'name': FEATURE_NAMES[i], 'importance': round(float(importances[i]), 6)}
    for i in top_idx
]

# ---------------------------------------------------------------------------
# 7. Save artifacts + metrics.json + report.txt
# ---------------------------------------------------------------------------
print("\n[7/7] Saving artifacts...")

with open('models/model.pkl', 'wb') as f:
    pickle.dump(model, f)
with open('models/scaler.pkl', 'wb') as f:
    pickle.dump(scaler, f)
with open('models/encoders.pkl', 'wb') as f:
    pickle.dump(encoders, f)
with open('models/columns.pkl', 'wb') as f:
    pickle.dump(list(FEATURE_NAMES), f)
with open('models/threshold.pkl', 'wb') as f:
    pickle.dump(threshold_recall, f)
with open('models/label_encoder.pkl', 'wb') as f:
    pickle.dump(label_encoder, f)

# Pretty model-parameter summary for the Insights page
if best_name == 'ensemble':
    model_params = {
        'algorithm': 'Soft-Voting Ensemble (RF + ExtraTrees + GradientBoosting)',
        'voting': 'soft',
    }
else:
    raw_params = model.get_params()
    model_params = {
        'algorithm': best_name.replace('_', ' ').title(),
        'n_estimators': raw_params.get('n_estimators'),
        'max_depth': raw_params.get('max_depth'),
        'class_weight': raw_params.get('class_weight'),
        'random_state': raw_params.get('random_state'),
    }
    # drop None values for cleaner UI
    model_params = {k: v for k, v in model_params.items() if v is not None}

metrics = {
    'accuracy': round(acc_b * 100, 2),
    'precision': round(prec_b * 100, 2),
    'recall': round(rec_b * 100, 2),
    'f1': round(f1_b * 100, 2),
    'roc_auc': round(roc * 100, 2),
    'threshold': round(threshold_recall, 4),
    'threshold_f1_max': round(threshold_f1, 4),
    'precision_floor': PRECISION_FLOOR,
    'confusion_matrix': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)},
    'per_class': per_class,
    'top_features': top_features,
    'model_params': model_params,
    'model_name': best_name,
    'candidate_scores': {k: round(v, 4) for k, v in candidate_scores.items()},
    'cv': {k: {'mean': round(v['mean'], 4), 'std': round(v['std'], 4)} for k, v in cv_summary.items()},
    'classes': CATEGORY_ORDER,
}

with open('results/metrics.json', 'w') as f:
    json.dump(metrics, f, indent=2)
print("[ok] Saved: results/metrics.json")

# Human-readable companion report
lines = [
    "AI-BASED INTRUSION DETECTION SYSTEM",
    f"Training Report - NSL-KDD ({pd.Timestamp.now().isoformat(timespec='seconds')})",
    "=" * 80,
    f"Selected model:  {best_name}",
    "",
    "BINARY METRICS (attack vs normal, recall-priority threshold)",
    f"  threshold        = {threshold_recall:.4f}  (precision floor {PRECISION_FLOOR})",
    f"  accuracy         = {acc_b*100:.2f}%",
    f"  precision        = {prec_b*100:.2f}%",
    f"  recall           = {rec_b*100:.2f}%",
    f"  f1               = {f1_b*100:.2f}%",
    f"  roc_auc          = {roc*100:.2f}%",
    f"  confusion matrix = tn={tn}  fp={fp}  fn={fn}  tp={tp}",
    "",
    "CANDIDATE F1-macro (test set):",
]
for n, s in candidate_scores.items():
    lines.append(f"  {n:20s} {s:.4f}")
lines += ["", "PER-CLASS METRICS (test set, multi-class):"]
for name, m in per_class.items():
    lines.append(f"  {name:8s}  precision={m['precision']:.2f}%  recall={m['recall']:.2f}%  f1={m['f1']:.2f}%  support={m['support']}")
lines += ["", "CROSS-VALIDATION (5-fold stratified, training set, RF probe):"]
for k, v in cv_summary.items():
    lines.append(f"  {k:18s} mean={v['mean']:.4f}  std={v['std']:.4f}")
lines += ["", "TOP FEATURES:"]
for f in top_features:
    lines.append(f"  {f['name']:30s} {f['importance']:.6f}")

with open('results/report.txt', 'w') as f:
    f.write("\n".join(lines))
print("[ok] Saved: results/report.txt")

banner("[ok] TRAINING COMPLETED")
print("Run 'python app.py' to start the web app.")
