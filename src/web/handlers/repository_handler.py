from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Tuple

from werkzeug.utils import secure_filename

from src.utils.repo_slug import (
    filesystem_slug,
    slug_from_github_clone_url,
    slug_from_local_repo_path,
)
from src.web.utils.github_urls import is_github_clone_url


class RepositoryHandler:
    """Handles repository operations including ZIP extraction and Git cloning."""
    
    def __init__(self, upload_folder: str) -> None:
        """Store the directory used for uploads and extracted or cloned repositories.

        Args:
            upload_folder: Writable folder path for temporary content.
        """
        self.upload_folder = upload_folder
    
    def handle_zip_upload(self, file) -> Tuple[str, bool, str]:
        """Handle ZIP file upload and extraction.

        Args:
            file: Uploaded file object

        Returns:
            Tuple of ``(repository_path, cleanup_needed, results_folder_slug)``.
            
        Raises:
            ValueError: If file is invalid or extraction fails
        """
        if file.filename == '':
            raise ValueError('No file selected')
        
        if not file.filename.endswith('.zip'):
            raise ValueError('Please upload a ZIP file')
        
        try:
            filename = secure_filename(file.filename)
            stem = Path(filename).stem if filename else "upload"
            slug = filesystem_slug(stem)
            temp_dir = tempfile.mkdtemp(dir=self.upload_folder, prefix=f"{slug}_")
            zip_path = os.path.join(temp_dir, filename)
            file.save(zip_path)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            return temp_dir, True, slug

        except Exception as e:
            if "temp_dir" in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError(f"ZIP extraction failed: {str(e)}")
    
    def clone_github_repository(self, repo_url: str) -> Tuple[str, bool, str]:
        """Clone a GitHub repository to temporary directory.

        Args:
            repo_url: GitHub repository URL

        Returns:
            Tuple of ``(repository_path, cleanup_needed, results_folder_slug)``.
            
        Raises:
            ValueError: If cloning fails
        """
        if not is_github_clone_url(repo_url):
            raise ValueError('Invalid GitHub URL format')
        
        temp_dir = None
        slug = slug_from_github_clone_url(repo_url)
        try:
            temp_dir = tempfile.mkdtemp(dir=self.upload_folder, prefix=f"{slug}_")
            clone_cmd = ["git", "clone", repo_url, temp_dir]
            result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                raise ValueError(f"Failed to clone repository: {result.stderr}")

            return temp_dir, True, slug

        except subprocess.TimeoutExpired:
            raise ValueError("Repository clone timed out (60s limit)")
        except Exception as e:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError(f"Error cloning repository: {str(e)}")
    
    def handle_local_repository(self, repo_path: str) -> Tuple[str, bool, str]:
        """Handle local repository path.

        Args:
            repo_path: Local repository path

        Returns:
            Tuple of ``(repository_path, cleanup_needed, results_folder_slug)``.
            
        Raises:
            ValueError: If path doesn't exist
        """
        if not os.path.exists(repo_path):
            raise ValueError("Repository path does not exist")

        resolved = os.path.abspath(repo_path)
        return resolved, False, slug_from_local_repo_path(resolved)
