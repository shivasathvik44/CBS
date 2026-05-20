#!/usr/bin/env python3
"""
Setup Verification Script
Checks everything and provides detailed diagnostics
"""

import os
import sys
from pathlib import Path

def check_directories():
    """Check if all required directories exist"""
    dirs = {
        'data': 'NSL-KDD dataset folder',
        'models': 'Trained model artifacts folder',
        'templates': 'HTML templates folder',
        'static': 'CSS/JS/static files folder',
        'static/css': 'CSS stylesheets folder',
        'static/js': 'JavaScript files folder',
        'results': 'Training results folder',
    }
    
    print("\n" + "=" * 80)
    print("1. CHECKING DIRECTORIES")
    print("=" * 80)
    
    missing = []
    for dir_name, description in dirs.items():
        path = Path(dir_name)
        if path.exists():
            print(f"  ✓ {dir_name:20} — {description}")
        else:
            print(f"  ✗ {dir_name:20} — {description} [MISSING]")
            missing.append(dir_name)
    
    return missing

def check_files():
    """Check if all required files exist"""
    files = {
        'app.py': 'Flask application',
        'train.py': 'Model training script',
        'requirements.txt': 'Python dependencies',
        'templates/base.html': 'Base template',
        'templates/index.html': 'Home page',
        'templates/predict.html': 'Prediction page',
        'templates/insights.html': 'Insights page',
        'templates/learn.html': 'Learn page',
        'templates/about.html': 'About page',
        'static/css/style.css': 'CSS stylesheet',
        'static/js/predict.js': 'Predict page JS',
        'static/js/insights.js': 'Insights page JS',
    }
    
    print("\n" + "=" * 80)
    print("2. CHECKING FILES")
    print("=" * 80)
    
    missing = []
    for file_name, description in files.items():
        path = Path(file_name)
        if path.exists():
            size = path.stat().st_size
            if size > 1024*1024:
                size_str = f"{size/(1024*1024):.1f}MB"
            elif size > 1024:
                size_str = f"{size/1024:.1f}KB"
            else:
                size_str = f"{size}B"
            print(f"  ✓ {file_name:30} — {description:25} ({size_str})")
        else:
            print(f"  ✗ {file_name:30} — {description:25} [MISSING]")
            missing.append(file_name)
    
    return missing

def check_model_artifacts():
    """Check if model has been trained"""
    artifacts = ['model.pkl', 'scaler.pkl', 'encoders.pkl', 'columns.pkl', 'threshold.pkl']
    
    print("\n" + "=" * 80)
    print("3. CHECKING MODEL ARTIFACTS")
    print("=" * 80)
    
    missing = []
    for artifact in artifacts:
        path = Path('models') / artifact
        if path.exists():
            size = path.stat().st_size
            size_str = f"{size/(1024*1024):.1f}MB" if size > 1024*1024 else f"{size/1024:.1f}KB"
            print(f"  ✓ models/{artifact:20} ({size_str})")
        else:
            print(f"  ✗ models/{artifact:20} [MISSING]")
            missing.append(f"models/{artifact}")
    
    return len(missing) > 0

def check_dataset():
    """Check if NSL-KDD dataset exists"""
    files = ['KDDTrain+.txt', 'KDDTest+.txt']
    
    print("\n" + "=" * 80)
    print("4. CHECKING NSL-KDD DATASET")
    print("=" * 80)
    
    missing = []
    for file in files:
        path = Path('data') / file
        if path.exists():
            size = path.stat().st_size
            size_str = f"{size/(1024*1024):.1f}MB"
            print(f"  ✓ data/{file:20} ({size_str})")
        else:
            print(f"  ✗ data/{file:20} [MISSING]")
            missing.append(file)
    
    return missing

def check_dependencies():
    """Check if Python dependencies are installed"""
    print("\n" + "=" * 80)
    print("5. CHECKING PYTHON DEPENDENCIES")
    print("=" * 80)
    
    dependencies = {
        'flask': 'Flask',
        'pandas': 'Pandas',
        'numpy': 'NumPy',
        'sklearn': 'Scikit-learn',
    }
    
    missing = []
    for module, name in dependencies.items():
        try:
            __import__(module)
            print(f"  ✓ {name:15} installed")
        except ImportError:
            print(f"  ✗ {name:15} NOT installed")
            missing.append(module)
    
    return missing

def main():
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "AI-BASED INTRUSION DETECTION SYSTEM - SETUP VERIFICATION".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    
    missing_dirs = check_directories()
    missing_files = check_files()
    model_missing = check_model_artifacts()
    missing_data = check_dataset()
    missing_deps = check_dependencies()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)
    
    all_ok = (
        not missing_dirs and 
        not missing_files and 
        not model_missing and 
        not missing_data and 
        not missing_deps
    )
    
    issues = []
    
    if missing_deps:
        issues.append(f"\n⚠️  MISSING PYTHON PACKAGES: {', '.join(missing_deps)}")
        issues.append("   Run: pip install -r requirements.txt")
    
    if missing_data:
        issues.append(f"\n⚠️  NSL-KDD DATASET MISSING: {', '.join(missing_data)}")
        issues.append("   Download from: https://www.unb.ca/cic/datasets/nsl-kdd.html")
        issues.append("   Extract to: data/ folder")
    
    if model_missing:
        issues.append("\n⚠️  MODEL NOT TRAINED")
        issues.append("   Run: python train.py")
        issues.append("   (Only needed once, after downloading dataset)")
    
    if missing_files:
        issues.append(f"\n⚠️  MISSING FILES: {', '.join(missing_files[:3])}")
        if len(missing_files) > 3:
            issues.append(f"        ... and {len(missing_files)-3} more")
        issues.append("   Re-download the project")
    
    if missing_dirs:
        issues.append(f"\n⚠️  MISSING FOLDERS: {', '.join(missing_dirs[:3])}")
        if len(missing_dirs) > 3:
            issues.append(f"        ... and {len(missing_dirs)-3} more")
        issues.append("   Re-download the project")
    
    if issues:
        for issue in issues:
            print(issue)
    
    # Status
    print("\n" + "=" * 80)
    if all_ok:
        print("✓ ALL CHECKS PASSED!")
        print("\nYou're ready to run the application:")
        print("  → python app.py")
        print("  → Open http://localhost:5000")
    else:
        print("✗ SETUP INCOMPLETE")
        print("\nFix the issues above, then run this script again:")
        print("  → python verify_setup.py")
    
    print("=" * 80 + "\n")
    
    return 0 if all_ok else 1

if __name__ == '__main__':
    sys.exit(main())