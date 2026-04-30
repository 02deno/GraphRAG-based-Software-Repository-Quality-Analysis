from __future__ import annotations

import os
import shutil
from typing import Tuple

from flask import request


def cleanup_temp_directory(repo_path: str, cleanup_needed: bool) -> None:
    """Clean up temporary directory if needed.
    
    Args:
        repo_path: Path to cleanup
        cleanup_needed: Whether cleanup is required
    """
    if cleanup_needed and repo_path and os.path.exists(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)


def handle_repository_upload(repo_handler) -> Tuple[str, bool]:
    """Handle repository upload from form data.
    
    Args:
        repo_handler: RepositoryHandler instance
        
    Returns:
        Tuple[str, bool]: (repository_path, cleanup_needed)
        
    Raises:
        ValueError: If no valid repository provided
    """
    # Handle ZIP file upload
    if 'repository_file' in request.files:
        file = request.files['repository_file']
        if file.filename:
            return repo_handler.handle_zip_upload(file)
    
    # Handle repository URL
    elif 'repository_url' in request.form:
        repo_url = request.form['repository_url'].strip()
        if repo_url:
            if repo_url.startswith('https://github.com/') or repo_url.startswith('git@github.com:'):
                return repo_handler.clone_github_repository(repo_url)
            else:
                return repo_handler.handle_local_repository(repo_url)
    
    raise ValueError('Please provide either a file or URL')
