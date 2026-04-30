from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict

from ...compatibility.repo_checker import RepoCompatibilityChecker


class AnalysisService:
    """Handles repository analysis operations."""
    
    def __init__(self):
        self.compatibility_checker = RepoCompatibilityChecker()
    
    def run_compatibility_check(self, repo_path: str) -> Dict:
        """Run compatibility analysis on repository.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dict: Compatibility analysis results
        """
        return self.compatibility_checker.analyze_repository(repo_path)
    
    def run_analysis_pipeline(self, repo_path: str) -> Dict:
        """Run the main graph analysis pipeline.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dict: Analysis results
            
        Raises:
            Exception: If pipeline execution fails
        """
        results_dir = Path("results") / f"web_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        graph_output = results_dir / "graph.json"
        analysis_output = results_dir / "analysis.txt"
        
        cmd = [
            "python", "src/main_pipeline.py",
            "--repo", repo_path,
            "--graph-output", str(graph_output),
            "--analysis-output", str(analysis_output),
            "--skip-visualization"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path.cwd())
        
        if result.returncode != 0:
            raise Exception(f"Pipeline failed: {result.stderr}")
        
        graph_data = {}
        analysis_text = "No analysis available"
        
        if graph_output.exists():
            try:
                graph_data = graph_output.read_text()
                graph_data = json.loads(graph_data)
            except (json.JSONDecodeError, IOError):
                graph_data = {}
        
        if analysis_output.exists():
            try:
                analysis_text = analysis_output.read_text()
            except IOError:
                analysis_text = "No analysis available"
        
        return {
            'graph_data': graph_data,
            'analysis_text': analysis_text,
            'pipeline_output': result.stdout,
            'results_dir': str(results_dir)
        }
