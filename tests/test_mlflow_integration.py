"""
test_mlflow_integration.py — Tests pour MLflow Tracker
====================================================
Tests unitaires et d'intégration pour le tracking MLflow.

Usage:
  pytest tests/test_mlflow_integration.py -v
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.mlflow_tracker import MLflowTracker, MLflowRun
from config.settings import Settings


class TestMLflowTracker:
    """Tests du tracker MLflow."""

    @pytest.fixture
    def tracker(self):
        """Créer un tracker pour les tests."""
        return MLflowTracker(
            tracking_uri="http://localhost:5000", experiment_name="test_experiment"
        )

    def test_initialization(self, tracker):
        """Test l'initialisation du tracker."""
        assert tracker.tracking_uri == "http://localhost:5000"
        assert tracker.experiment_name == "test_experiment"
        assert tracker.client is not None

    @patch("mlflow.start_run")
    def test_start_run(self, mock_start, tracker):
        """Test le démarrage d'une run."""
        mock_run = Mock()
        mock_run.info.run_id = "test_run_123"
        mock_start.return_value = mock_run

        run_id = tracker.start_run("test_run", tags={"key": "value"})

        assert run_id == "test_run_123"
        mock_start.assert_called_once()

    @patch("mlflow.log_params")
    def test_log_params(self, mock_log, tracker):
        """Test le logging des paramètres."""
        params = {"chunk_size": 512, "top_k": 5, "temperature": 0.7}

        tracker.log_params(params)

        mock_log.assert_called_once()
        call_args = mock_log.call_args[0][0]

        # Vérifier que les paramètres sont convertis en strings
        assert all(isinstance(v, str) for v in call_args.values())

    @patch("mlflow.log_metrics")
    def test_log_metrics(self, mock_log, tracker):
        """Test le logging des métriques."""
        metrics = {
            "faithfulness": 0.85,
            "answer_relevancy": 0.78,
            "context_precision": 0.82,
        }

        tracker.log_metrics(metrics, step=0)

        mock_log.assert_called_once()
        call_args = mock_log.call_args[0][0]
        call_kwargs = mock_log.call_args[1]

        assert call_args == metrics
        assert call_kwargs["step"] == 0

    @patch("mlflow.log_artifact")
    def test_log_artifact(self, mock_log, tracker):
        """Test le logging d'artefacts."""
        # Créer un fichier temporaire
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump({"test": "data"}, f)
            temp_file = f.name

        try:
            tracker.log_artifact(temp_file, artifact_path="test_artifacts")

            mock_log.assert_called_once()
            call_args = mock_log.call_args[0]

            assert temp_file in call_args[0]
        finally:
            Path(temp_file).unlink()

    def test_log_eval_results(self, tracker):
        """Test le logging des résultats d'évaluation."""
        with patch("mlflow.log_metrics") as mock_metrics:
            with patch.object(tracker, "log_artifact"):
                eval_scores = {
                    "faithfulness": 0.87,
                    "answer_relevancy": 0.81,
                }

                tracker.log_eval_results(eval_scores, eval_name="RAGAS")

                # Vérifier que log_metrics a été appelé
                mock_metrics.assert_called_once()

    @patch("mlflow.search_runs")
    def test_compare_experiments(self, mock_search, tracker):
        """Test la comparaison des expériences."""
        # Créer des données simulées
        mock_search.return_value = MagicMock()
        mock_search.return_value.empty = False
        mock_search.return_value.iloc = MagicMock()
        mock_search.return_value.head.return_value.iloc = []

        _ = tracker.compare_experiments("faithfulness", top_n=5)

        # Vérifier que search_runs a été appelé
        mock_search.assert_called_once()

    @patch("mlflow.end_run")
    def test_end_run(self, mock_end, tracker):
        """Test la fermeture d'une run."""
        tracker.end_run(status="FINISHED")

        mock_end.assert_called_once()


class TestMLflowRun:
    """Tests du context manager MLflowRun."""

    @pytest.fixture
    def tracker(self):
        """Créer un tracker pour les tests."""
        return MLflowTracker(
            tracking_uri="http://localhost:5000", experiment_name="test_context_manager"
        )

    @patch.object(MLflowTracker, "start_run")
    @patch.object(MLflowTracker, "end_run")
    def test_context_manager_success(self, mock_end, mock_start, tracker):
        """Test le context manager en cas de succès."""
        mock_start.return_value = "run_123"

        with MLflowRun(tracker, "test_run", tags={"key": "value"}):
            pass

        mock_start.assert_called_once()
        mock_end.assert_called_once_with(status="FINISHED")

    @patch.object(MLflowTracker, "start_run")
    @patch.object(MLflowTracker, "end_run")
    def test_context_manager_exception(self, mock_end, mock_start, tracker):
        """Test le context manager en cas d'exception."""
        mock_start.return_value = "run_123"

        try:
            with MLflowRun(tracker, "test_run"):
                raise ValueError("Test exception")
        except ValueError:
            pass

        mock_start.assert_called_once()
        mock_end.assert_called_once_with(status="FAILED")


class TestMLflowIntegration:
    """Tests d'intégration avec la configuration."""

    def test_settings_mlflow_config(self):
        """Test que les settings MLflow sont corrects."""
        settings = Settings()

        assert settings.mlflow_tracking_uri == "http://localhost:5000"
        assert settings.mlflow_experiment == "rag-livraison"

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.set_experiment")
    def test_tracker_with_settings(self, mock_exp, mock_uri):
        """Test la création d'un tracker avec Settings."""
        settings = Settings()

        tracker = MLflowTracker(
            tracking_uri=settings.mlflow_tracking_uri,
            experiment_name=settings.mlflow_experiment,
        )

        assert tracker.tracking_uri == settings.mlflow_tracking_uri
        assert tracker.experiment_name == settings.mlflow_experiment


class TestMLflowMetrics:
    """Tests des métriques spécifiques à RAG."""

    @patch("mlflow.log_metrics")
    def test_rag_metrics_logging(self, mock_log):
        """Test le logging des métriques RAG."""
        tracker = MLflowTracker("http://localhost:5000", "test")

        rag_metrics = {
            "faithfulness": 0.85,
            "answer_relevancy": 0.78,
            "context_precision": 0.82,
            "context_recall": 0.75,
            "retrieval_time_ms": 150,
            "inference_time_ms": 800,
        }

        tracker.log_metrics(rag_metrics)

        mock_log.assert_called_once()
        call_args = mock_log.call_args[0][0]

        # Vérifier que toutes les métriques sont présentes
        for metric_name in rag_metrics:
            assert metric_name in call_args

    def test_metric_value_validation(self):
        """Test la validation des valeurs de métriques."""
        tracker = MLflowTracker("http://localhost:5000", "test")

        # Les métriques doivent être des floats
        metrics = {
            "score": 0.95,  # Valide
            "count": 100,  # Sera converti en float
        }

        # Ne doit pas lever d'exception
        with patch("mlflow.log_metrics"):
            tracker.log_metrics(metrics)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
