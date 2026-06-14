"""Output paths must be anchored to the project directory, not the process cwd."""

from pathlib import Path

from src.stock_analysis.config.settings import PROJECT_ROOT, Settings


class TestProjectAnchoredPaths:
    def test_project_root_is_the_project_directory(self):
        assert (PROJECT_ROOT / "src" / "stock_analysis").is_dir()

    def test_default_output_dirs_are_absolute(self):
        s = Settings(_env_file=None)
        assert Path(s.report_output_dir).is_absolute()
        assert Path(s.data_output_dir).is_absolute()
        assert Path(s.crew_log_file).is_absolute()
        assert Path(s.report_output_dir) == PROJECT_ROOT / "reports"
