from __future__ import annotations

import os
import shutil
from typing import Tuple

from flask import request

from src.web.handlers.repository_handler import RepositoryHandler
from src.web.utils.github_urls import is_github_clone_url


def cleanup_temp_directory(repo_path: str, cleanup_needed: bool) -> None:
    """Clean up temporary directory if needed.
    
    Args:
        repo_path: Path to cleanup
        cleanup_needed: Whether cleanup is required
    """
    if cleanup_needed and repo_path and os.path.exists(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)


def handle_repository_upload(repo_handler: RepositoryHandler) -> Tuple[str, bool]:
    """Handle repository upload from form data.
    
    Args:
        repo_handler: RepositoryHandler instance
        
    Returns:
        Tuple[str, bool]: (repository_path, cleanup_needed)
        
    Raises:
        ValueError: If no valid repository provided
    """
    # Handle ZIP file upload (Flask always includes the file key on multipart
    # posts even when no file was chosen, so URL handling must not be `elif`.)
    if 'repository_file' in request.files:
        file = request.files['repository_file']
        if file.filename:
            return repo_handler.handle_zip_upload(file)

    # Handle repository URL
    if 'repository_url' in request.form:
        repo_url = request.form['repository_url'].strip()
        if repo_url:
            if is_github_clone_url(repo_url):
                return repo_handler.clone_github_repository(repo_url)
            else:
                return repo_handler.handle_local_repository(repo_url)
    
    raise ValueError('Please provide either a file or URL')
