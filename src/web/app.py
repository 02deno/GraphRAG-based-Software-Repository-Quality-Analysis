from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from ..compatibility.repo_checker import RepoCompatibilityChecker
from ..main_pipeline import main as run_main_pipeline


app = Flask(__name__)
app.config['SECRET_KEY'] = 'graphrag-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'temp_uploads'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_repository():
    """Handle repository upload (ZIP file) or URL input."""
    repo_path = None
    cleanup_temp = False
    
    try:
        # Handle ZIP file upload
        if 'repository_file' in request.files:
            file = request.files['repository_file']
            if file.filename == '':
                flash('No file selected')
                return redirect(url_for('index'))
            
            if file and file.filename.endswith('.zip'):
                filename = secure_filename(file.filename)
                temp_dir = tempfile.mkdtemp(dir=app.config['UPLOAD_FOLDER'])
                zip_path = os.path.join(temp_dir, filename)
                file.save(zip_path)
                
                # Extract ZIP
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                repo_path = temp_dir
                cleanup_temp = True
            else:
                flash('Please upload a ZIP file')
                return redirect(url_for('index'))
        
        # Handle repository URL
        elif 'repository_url' in request.form:
            repo_url = request.form['repository_url'].strip()
            if not repo_url:
                flash('Please enter a repository URL')
                return redirect(url_for('index'))
            
            # For now, assume it's a local path (could be extended for git clone)
            repo_path = repo_url
            if not os.path.exists(repo_path):
                flash('Repository path does not exist')
                return redirect(url_for('index'))
        
        else:
            flash('Please provide either a file or URL')
            return redirect(url_for('index'))
        
        # Run compatibility check
        checker = RepoCompatibilityChecker()
        compatibility_result = checker.analyze_repository(repo_path)
        
        # Store results in session for analysis step
        session_data = {
            'repo_path': repo_path,
            'cleanup_temp': cleanup_temp,
            'compatibility': compatibility_result
        }
        
        # Store in session (using Flask's session)
        from flask import session
        session['analysis_data'] = session_data
        
        return render_template('compatibility.html', 
                             score=compatibility_result['score'],
                             details=compatibility_result['details'],
                             warnings=compatibility_result['warnings'])
    
    except Exception as e:
        # Cleanup on error
        if cleanup_temp and repo_path and os.path.exists(repo_path):
            import shutil
            shutil.rmtree(repo_path, ignore_errors=True)
        
        flash(f'Error processing repository: {str(e)}')
        return redirect(url_for('index'))


@app.route('/analyze', methods=['POST'])
def analyze_repository():
    """Run graph analysis on the repository."""
    from flask import session
    
    analysis_data = session.get('analysis_data')
    if not analysis_data:
        flash('Analysis data not found')
        return redirect(url_for('index'))
    
    repo_path = analysis_data['repo_path']
    cleanup_temp = analysis_data['cleanup_temp']
    
    try:
        # Run the main pipeline with minimal changes
        # We'll need to modify the main pipeline to accept repo_path and return results
        results = run_analysis_pipeline(repo_path)
        
        # Cleanup temporary files if needed
        if cleanup_temp and os.path.exists(repo_path):
            import shutil
            shutil.rmtree(repo_path, ignore_errors=True)
        
        return render_template('results_final.html', results=results)
    
    except Exception as e:
        # Cleanup on error
        if cleanup_temp and os.path.exists(repo_path):
            import shutil
            shutil.rmtree(repo_path, ignore_errors=True)
        
        flash(f'Error during analysis: {str(e)}')
        return redirect(url_for('index'))


def run_analysis_pipeline(repo_path: str) -> Dict:
    """Run the main graph analysis pipeline and return results."""
    # This will integrate with your existing main_pipeline.py
    # For now, we'll create a wrapper that captures the output
    
    import subprocess
    import json
    from datetime import datetime
    
    # Create results directory
    results_dir = Path("results") / f"web_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Run main pipeline
    graph_output = results_dir / "graph.json"
    analysis_output = results_dir / "analysis.txt"
    
    cmd = [
        "python", "src/main_pipeline.py",
        "--repo", repo_path,
        "--graph-output", str(graph_output),
        "--analysis-output", str(analysis_output),
        "--skip-visualization"  # Skip visualization for web version
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path.cwd())
    
    if result.returncode != 0:
        raise Exception(f"Pipeline failed: {result.stderr}")
    
    # Read results
    graph_data = json.loads(graph_output.read_text()) if graph_output.exists() else {}
    analysis_text = analysis_output.read_text() if analysis_output.exists() else "No analysis available"
    
    return {
        'graph_data': graph_data,
        'analysis_text': analysis_text,
        'pipeline_output': result.stdout,
        'results_dir': str(results_dir)
    }


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
