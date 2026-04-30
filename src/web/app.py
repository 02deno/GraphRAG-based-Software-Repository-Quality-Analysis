from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

from .handlers.repository_handler import RepositoryHandler
from .services.analysis_service import AnalysisService
from .utils.helpers import cleanup_temp_directory, handle_repository_upload


# Get the project root directory (parent of src/web)
project_root = Path(__file__).parent.parent.parent

app = Flask(__name__, template_folder=str(project_root / 'templates'))
app.config['SECRET_KEY'] = 'graphrag-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'temp_uploads'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize services
repo_handler = RepositoryHandler(app.config['UPLOAD_FOLDER'])
analysis_service = AnalysisService()


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_repository():
    """Handle repository upload (ZIP file) or URL input.
    
    Returns:
        Rendered template with compatibility results or redirect on error
    """
    repo_path = None
    cleanup_temp = False
    
    try:
        repo_path, cleanup_temp = handle_repository_upload(repo_handler)
        
        # Run compatibility check
        compatibility_result = analysis_service.run_compatibility_check(repo_path)
        
        # Store results in session for analysis step
        session_data = {
            'repo_path': repo_path,
            'cleanup_temp': cleanup_temp,
            'compatibility': compatibility_result
        }
        session['analysis_data'] = session_data
        
        return render_template('compatibility.html', 
                             score=compatibility_result['score'],
                             details=compatibility_result['details'],
                             warnings=compatibility_result['warnings'])
    
    except ValueError as e:
        flash(str(e))
        cleanup_temp_directory(repo_path, cleanup_temp)
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error processing repository: {str(e)}')
        cleanup_temp_directory(repo_path, cleanup_temp)
        return redirect(url_for('index'))


@app.route('/analyze', methods=['POST'])
def analyze_repository():
    """Run graph analysis on the repository.
    
    Returns:
        Rendered template with analysis results or redirect on error
    """
    analysis_data = session.get('analysis_data')
    if not analysis_data:
        flash('Analysis data not found')
        return redirect(url_for('index'))
    
    repo_path = analysis_data['repo_path']
    cleanup_temp = analysis_data['cleanup_temp']
    
    try:
        results = analysis_service.run_analysis_pipeline(repo_path)
        cleanup_temp_directory(repo_path, cleanup_temp)
        
        return render_template('results_final.html', results=results)
    
    except Exception as e:
        flash(f'Error during analysis: {str(e)}')
        cleanup_temp_directory(repo_path, cleanup_temp)
        return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
