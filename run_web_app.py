#!/usr/bin/env python3
"""
Web Application Runner for GraphRAG Repository Analysis

This script starts the Flask web application for the full-stack
GraphRAG repository analysis tool.

Usage:
    python run_web_app.py

Then open http://localhost:5000 in your browser.
"""

import os
import sys
from pathlib import Path

# Project root must be on path so ``import src.…`` resolves (``src`` is the package).
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    from src.web.app import app
    
    print("🚀 Starting GraphRAG Repository Analysis Web App...")
    print("📱 Open your browser and go to: http://localhost:5000")
    print("📁 Upload a repository ZIP file or provide a local path")
    print("🔍 The system will check compatibility before analysis")
    print("⚠️  Repositories with <50% compatibility will require confirmation")
    print("✅ Compatible repositories will be analyzed automatically")
    print()
    
    # Create necessary directories
    os.makedirs("temp_uploads", exist_ok=True)
    os.makedirs("results", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    # Run the Flask app
    app.run(debug=True, host="0.0.0.0", port=5000)
