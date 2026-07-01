import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

from review_extraction.models import (
    ArticleResult,
    Evidence,
    ExtractedAnswer,
    ExtractionResult,
    ExtractionPlanResult,
    ExtractionThemeDecision,
    ScreeningCriterionAnswer,
    ScreeningResult,
    ScreeningValidationDecision,
    ScreeningValidationResult,
    StudyMetadataField,
    StudyMetadataResult,
    TokenUsage,
    ValidationDecision,
    ValidationResult,
)
from review_extraction.pipeline import process_many, process_pdf


class ExplodingAgents:
    def screen(self, *args, **kwargs):
        raise AssertionError("AI screening should not be called when cached JSON exists.")

    def validate_screening(self, *args, **kwargs):
        raise AssertionError("AI screening validation should not be called when cached JSON exists.")

    def extract(self, *args, **kwargs):
        raise AssertionError("AI extraction should not be called when cached JSON exists.")

    def validate(self, *args, **kwargs):
        raise AssertionError("AI validation should not be called when cached JSON exists.")


class RecordingAgents:
    def __init__(self) -> None:
        self.screen_contexts: list[str] = []
        self.screen_validation_contexts: list[str] = []
        self.extraction_contexts: list[str] = []
        self.validation_contexts: list[str] = []
        self.usage_events: list[TokenUsage] = []

    def extract_study_metadata(self, article_id: str, paper_context: str) -> StudyMetadataResult:
        self.usage_events.append(
            TokenUsage(step="study_metadata", model="model", input_tokens=90, output_tokens=9, total_tokens=99)
        )
        return StudyMetadataResult(
            article_id=article_id,
            fields=[
                StudyMetadataField(
                    field_id="study_id",
                    value=f"{article_id}2024",
                    confidence=0.8,
                    evidence=[Evidence(page=1, quote="Example study title.", relevance="title page")],
                    rationale_short="Study ID inferred from title metadata.",
                )
            ],
        )

    def plan_extraction(self, article_id: str, paper_context: str) -> ExtractionPlanResult:
        self.usage_events.append(
            TokenUsage(step="extraction_planning", model="model", input_tokens=80, output_tokens=8, total_tokens=88)
        )
        return ExtractionPlanResult(
            article_id=article_id,
            themes=[
                ExtractionThemeDecision(
                    theme_id="measurement_methods",
                    status="present",
                    confidence=0.9,
                    evidence=[Evidence(page=2, quote="Motion capture was used.", relevance="measurement")],
                    rationale_short="Measurement method is reported.",
                ),
                ExtractionThemeDecision(
                    theme_id="segment.thorax",
                    status="present",
                    confidence=0.9,
                    evidence=[Evidence(page=2, quote="Thorax coordinate system.", relevance="thorax")],
                    rationale_short="Thorax is reported.",
                ),
                ExtractionThemeDecision(
                    theme_id="segment.clavicle",
                    status="absent",
                    confidence=0.85,
                    evidence=[],
                    rationale_short="Clavicle is not reported.",
                ),
                ExtractionThemeDecision(
                    theme_id="segment.scapula",
                    status="absent",
                    confidence=0.85,
                    evidence=[],
                    rationale_short="Scapula is not reported.",
                ),
                ExtractionThemeDecision(
                    theme_id="segment.humerus",
                    status="absent",
                    confidence=0.85,
                    evidence=[],
                    rationale_short="Humerus is not reported.",
                ),
            ],
        )

    def screen(self, article_id: str, paper_context: str) -> ScreeningResult:
        self.screen_contexts.append(paper_context)
        self.usage_events.append(
            TokenUsage(step="screening", model="model", input_tokens=100, output_tokens=10, total_tokens=110)
        )
        return ScreeningResult(
            article_id=article_id,
            overall_decision="include",
            criteria=[
                ScreeningCriterionAnswer(
                    criterion_id="population",
                    decision="include",
                    confidence=0.9,
                    evidence=[
                        Evidence(
                            page=1,
                            quote="Healthy human participants",
                            relevance="Supports human population inclusion.",
                        )
                    ],
                    rationale_short="Human participants.",
                )
            ],
        )

    def validate_screening(
        self,
        article_id: str,
        paper_context: str,
        screening: ScreeningResult,
    ) -> ScreeningValidationResult:
        self.screen_validation_contexts.append(paper_context)
        self.usage_events.append(
            TokenUsage(step="screening_validation", model="validator", input_tokens=120, output_tokens=12, total_tokens=132)
        )
        return ScreeningValidationResult(
            article_id=article_id,
            overall_status="agree",
            corrected_overall_decision=None,
            decisions=[
                ScreeningValidationDecision(
                    criterion_id="population",
                    status="agree",
                    corrected_decision=None,
                    confidence=0.9,
                    evidence=[],
                    critique="Supported.",
                )
            ],
        )

    def extract(self, article_id: str, paper_context: str, *, item_ids=None) -> ExtractionResult:
        self.extraction_contexts.append(paper_context)
        if item_ids is not None:
            self.extract_item_ids = list(item_ids)
        self.usage_events.append(
            TokenUsage(step="extraction", model="model", input_tokens=200, output_tokens=20, total_tokens=220)
        )
        return ExtractionResult(
            article_id=article_id,
            answers=[
                ExtractedAnswer(
                    item_id="thorax_used",
                    answer="yes",
                    confidence=0.8,
                    evidence=[
                        Evidence(
                            page=2,
                            quote="Thorax and humerus coordinate systems",
                            relevance="Shows thorax segment use.",
                        )
                    ],
                    rationale_short="Thorax coordinate system reported.",
                    needs_human_review=False,
                )
            ],
        )

    def validate(self, article_id: str, paper_context: str, extraction: ExtractionResult, *, item_ids=None) -> ValidationResult:
        self.validation_contexts.append(paper_context)
        self.usage_events.append(
            TokenUsage(step="extraction_validation", model="validator", input_tokens=240, output_tokens=24, total_tokens=264)
        )
        return ValidationResult(
            article_id=article_id,
            decisions=[
                ValidationDecision(
                    item_id="thorax_used",
                    status="agree",
                    corrected_answer=None,
                    confidence=0.9,
                    evidence=[],
                    critique="Supported.",
                )
            ],
        )


class EscalationAgents(RecordingAgents):
    def __init__(self) -> None:
        super().__init__()
        self.screen_models: list[str | None] = []
        self.validation_models: list[str | None] = []
        self.extract_models: list[str | None] = []
        self.config = SimpleNamespace(
            fallback_model="gpt-5.5",
            fallback_validator_model="gpt-5.5",
        )

    def plan_extraction(self, article_id: str, paper_context: str) -> ExtractionPlanResult:
        self.usage_events.append(TokenUsage(step="extraction_planning", model="gpt-5.4", total_tokens=1))
        return ExtractionPlanResult(
            article_id=article_id,
            themes=[
                ExtractionThemeDecision(
                    theme_id="measurement_methods",
                    status="present",
                    confidence=0.9,
                    evidence=[],
                    rationale_short="Measurement method is present.",
                ),
                ExtractionThemeDecision(
                    theme_id="segment.thorax",
                    status="present",
                    confidence=0.9,
                    evidence=[],
                    rationale_short="Thorax is present.",
                ),
            ],
        )

    def screen(self, article_id: str, paper_context: str, *, model: str | None = None) -> ScreeningResult:
        self.screen_models.append(model)
        self.screen_contexts.append(paper_context)
        self.usage_events.append(TokenUsage(step="screening", model=model or "gpt-5.4", total_tokens=1))
        decision = "unclear" if model is None else "include"
        overall = "uncertain" if model is None else "include"
        confidence = 0.6 if model is None else 0.95
        return ScreeningResult(
            article_id=article_id,
            overall_decision=overall,
            criteria=[
                ScreeningCriterionAnswer(
                    criterion_id="population",
                    decision=decision,
                    confidence=confidence,
                    evidence=[Evidence(page=1, quote="Healthy human participants", relevance="population")],
                    rationale_short="Population evidence.",
                )
            ],
        )

    def validate_screening(
        self,
        article_id: str,
        paper_context: str,
        screening: ScreeningResult,
        *,
        model: str | None = None,
    ) -> ScreeningValidationResult:
        self.screen_validation_contexts.append(paper_context)
        self.validation_models.append(model)
        self.usage_events.append(TokenUsage(step="screening_validation", model=model or "gpt-5.4", total_tokens=1))
        status = "insufficient_evidence" if model is None else "agree"
        confidence = 0.6 if model is None else 0.95
        return ScreeningValidationResult(
            article_id=article_id,
            overall_status=status,
            corrected_overall_decision=None,
            decisions=[
                ScreeningValidationDecision(
                    criterion_id="population",
                    status=status,
                    corrected_decision=None,
                    confidence=confidence,
                    evidence=[],
                    critique="Audit.",
                )
            ],
        )

    def extract(self, article_id: str, paper_context: str, *, model: str | None = None, item_ids=None) -> ExtractionResult:
        self.extract_models.append(model)
        self.extraction_contexts.append(paper_context)
        self.usage_events.append(TokenUsage(step="extraction", model=model or "gpt-5.4", total_tokens=1))
        review = model is None
        return ExtractionResult(
            article_id=article_id,
            answers=[
                ExtractedAnswer(
                    item_id="thorax_used",
                    answer="yes",
                    confidence=0.8,
                    evidence=[Evidence(page=2, quote="Thorax coordinate system", relevance="segment")],
                    rationale_short="Thorax was used.",
                    needs_human_review=review,
                )
            ],
        )

    def validate(
        self,
        article_id: str,
        paper_context: str,
        extraction: ExtractionResult,
        *,
        model: str | None = None,
        item_ids=None,
    ) -> ValidationResult:
        self.validation_contexts.append(paper_context)
        self.validation_models.append(model)
        self.usage_events.append(TokenUsage(step="extraction_validation", model=model or "gpt-5.4", total_tokens=1))
        status = "disagree" if model is None else "agree"
        return ValidationResult(
            article_id=article_id,
            decisions=[
                ValidationDecision(
                    item_id="thorax_used",
                    status=status,
                    corrected_answer="no" if model is None else None,
                    confidence=0.85,
                    evidence=[],
                    critique="Audit.",
                )
            ],
        )


class PipelineTests(unittest.TestCase):
    def test_process_many_creates_outputs_for_empty_pdf_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pdf_input"
            out_dir = root / "outputs"
            input_dir.mkdir()

            results = process_many(input_dir, out_dir, agents=object(), write_highlights=False)

            self.assertEqual(results, [])
            self.assertTrue((out_dir / "index.json").exists())
            self.assertTrue((out_dir / "summary.csv").exists())
            self.assertTrue((out_dir / "summary.xlsx").exists())
            self.assertEqual(json.loads((out_dir / "index.json").read_text(encoding="utf-8")), [])

    def test_process_pdf_reuses_existing_article_json_without_ai_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "paper.pdf"
            out_dir = root / "outputs"
            out_dir.mkdir()
            result = ArticleResult(article_id="paper", source_pdf=str(pdf_path), answers=[])
            (out_dir / "paper.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

            loaded = process_pdf(pdf_path, out_dir, agents=ExplodingAgents(), write_highlights=False)

            self.assertEqual(loaded.article_id, "paper")
            self.assertEqual(loaded.answers, [])

    def test_process_many_reports_progress_for_cached_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pdf_input"
            out_dir = root / "outputs"
            input_dir.mkdir()
            out_dir.mkdir()
            pdf_path = input_dir / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            result = ArticleResult(article_id="paper", source_pdf=str(pdf_path), answers=[])
            (out_dir / "paper.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
            messages: list[str] = []

            process_many(
                input_dir,
                out_dir,
                agents=ExplodingAgents(),
                write_highlights=False,
                progress=messages.append,
            )

            self.assertIn("Found 1 PDF(s) to process.", messages)
            self.assertTrue(any("[1/1] paper.pdf: reuse existing JSON: paper.json" in message for message in messages))
            self.assertIn("[1/1] paper.pdf: done", messages)
            self.assertIn("write index.json", messages)
            self.assertIn("write summary.csv", messages)

    def test_process_many_limit_uses_first_sorted_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pdf_input"
            out_dir = root / "outputs"
            input_dir.mkdir()
            out_dir.mkdir()
            for name in ["b_paper.pdf", "a_paper.pdf"]:
                (input_dir / name).write_bytes(b"%PDF-1.4\n")
                article_id = Path(name).stem
                result = ArticleResult(article_id=article_id, source_pdf=str(input_dir / name), answers=[])
                (out_dir / f"{article_id}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
            messages: list[str] = []

            results = process_many(
                input_dir,
                out_dir,
                agents=ExplodingAgents(),
                write_highlights=False,
                limit=1,
                progress=messages.append,
            )

            self.assertEqual([result.article_id for result in results], ["a_paper"])
            self.assertIn("Found 1 PDF(s) to process (limit=1).", messages)
            self.assertTrue(any("[1/1] a_paper.pdf: reuse existing JSON: a_paper.json" in message for message in messages))

    def test_force_ignores_cached_article_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "paper.pdf"
            out_dir = root / "outputs"
            out_dir.mkdir()
            result = ArticleResult(article_id="paper", source_pdf=str(pdf_path), answers=[])
            (out_dir / "paper.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
            fake_pdf_ingest = ModuleType("review_extraction.pdf_ingest")
            fake_pdf_ingest.extract_pdf_text = lambda path: []
            fake_pdf_ingest.pages_to_prompt_context = lambda pages: ""
            original_pdf_ingest = sys.modules.get("review_extraction.pdf_ingest")
            sys.modules["review_extraction.pdf_ingest"] = fake_pdf_ingest

            try:
                with self.assertRaises(AssertionError):
                    process_pdf(
                        pdf_path,
                        out_dir,
                        agents=ExplodingAgents(),
                        write_highlights=False,
                        reuse_existing=False,
                    )
            finally:
                if original_pdf_ingest is None:
                    sys.modules.pop("review_extraction.pdf_ingest", None)
                else:
                    sys.modules["review_extraction.pdf_ingest"] = original_pdf_ingest

    def test_process_pdf_uses_targeted_contexts_for_ai_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            out_dir = root / "outputs"
            pages = [
                SimpleNamespace(page=1, text="Abstract. Healthy human participants completed shoulder tasks."),
                SimpleNamespace(page=2, text="Methods. Thorax and humerus coordinate systems used marker clusters."),
                SimpleNamespace(page=3, text="Unrelated filler. " * 500),
            ]
            fake_pdf_ingest = ModuleType("review_extraction.pdf_ingest")
            fake_pdf_ingest.extract_pdf_text = lambda path: pages
            original_pdf_ingest = sys.modules.get("review_extraction.pdf_ingest")
            sys.modules["review_extraction.pdf_ingest"] = fake_pdf_ingest
            agents = RecordingAgents()

            try:
                result = process_pdf(pdf_path, out_dir, agents=agents, write_highlights=False)
            finally:
                if original_pdf_ingest is None:
                    sys.modules.pop("review_extraction.pdf_ingest", None)
                else:
                    sys.modules["review_extraction.pdf_ingest"] = original_pdf_ingest

            self.assertEqual(result.article_id, "paper")
            self.assertEqual(len(agents.screen_contexts), 1)
            self.assertEqual(len(agents.extraction_contexts), 1)
            self.assertIn("TARGETED FULL-PAPER SCREENING CONTEXT", agents.screen_contexts[0])
            self.assertIn("TARGETED METHODOLOGY EXTRACTION CONTEXT", agents.extraction_contexts[0])
            self.assertIn("TARGETED METHODOLOGY EXTRACTION CONTEXT", agents.validation_contexts[0])
            self.assertGreaterEqual(len(agents.screen_validation_contexts[0]), len(agents.screen_contexts[0]))
            self.assertGreaterEqual(len(agents.validation_contexts[0]), len(agents.extraction_contexts[0]))
            self.assertEqual(
                [usage.step for usage in result.usage],
                ["screening", "screening_validation", "study_metadata", "extraction_planning", "extraction", "extraction_validation"],
            )
            self.assertEqual(sum(usage.total_tokens for usage in result.usage), 913)
            self.assertEqual(result.study_metadata[0].field_id, "study_id")
            self.assertIn("thorax_used", agents.extract_item_ids)
            self.assertNotIn("clavicle_used", agents.extract_item_ids)
            self.assertTrue(any(answer.item_id == "clavicle_used" and answer.final_answer == "no" for answer in result.answers))
            self.assertIsNotNone(result.processing_seconds)
            self.assertTrue(all(usage.elapsed_seconds is not None for usage in result.usage))

    def test_uncertain_screening_escalates_to_fallback_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            out_dir = root / "outputs"
            pages = [
                SimpleNamespace(page=1, text="Abstract. Healthy human participants completed shoulder tasks."),
                SimpleNamespace(page=2, text="Methods. Thorax coordinate system was used."),
                SimpleNamespace(page=3, text="Background filler without screening keywords. " * 800),
            ]
            fake_pdf_ingest = ModuleType("review_extraction.pdf_ingest")
            fake_pdf_ingest.extract_pdf_text = lambda path: pages
            original_pdf_ingest = sys.modules.get("review_extraction.pdf_ingest")
            sys.modules["review_extraction.pdf_ingest"] = fake_pdf_ingest
            agents = EscalationAgents()

            try:
                process_pdf(pdf_path, out_dir, agents=agents, write_highlights=False)
            finally:
                if original_pdf_ingest is None:
                    sys.modules.pop("review_extraction.pdf_ingest", None)
                else:
                    sys.modules["review_extraction.pdf_ingest"] = original_pdf_ingest

            self.assertEqual(agents.screen_models, [None, "gpt-5.5"])
            self.assertIn("gpt-5.5", agents.validation_models)
            self.assertEqual(agents.extract_models, [None, "gpt-5.5"])

    def test_process_many_workers_use_separate_agent_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pdf_input"
            out_dir = root / "outputs"
            input_dir.mkdir()
            for name in ["a_paper.pdf", "b_paper.pdf"]:
                (input_dir / name).write_bytes(b"%PDF-1.4\n")
            fake_pdf_ingest = ModuleType("review_extraction.pdf_ingest")
            fake_pdf_ingest.extract_pdf_text = lambda path: [
                SimpleNamespace(page=1, text="Abstract. Healthy human participants completed shoulder tasks."),
                SimpleNamespace(page=2, text="Methods. Thorax coordinate system was used."),
            ]
            original_pdf_ingest = sys.modules.get("review_extraction.pdf_ingest")
            sys.modules["review_extraction.pdf_ingest"] = fake_pdf_ingest
            created_agents: list[RecordingAgents] = []

            def factory() -> RecordingAgents:
                agent = RecordingAgents()
                created_agents.append(agent)
                return agent

            try:
                results = process_many(
                    input_dir,
                    out_dir,
                    agents=RecordingAgents(),
                    write_highlights=False,
                    workers=2,
                    agent_factory=factory,
                )
            finally:
                if original_pdf_ingest is None:
                    sys.modules.pop("review_extraction.pdf_ingest", None)
                else:
                    sys.modules["review_extraction.pdf_ingest"] = original_pdf_ingest

            self.assertEqual([result.article_id for result in results], ["a_paper", "b_paper"])
            self.assertEqual(len(created_agents), 2)
            self.assertTrue(all(agent.usage_events for agent in created_agents))


if __name__ == "__main__":
    unittest.main()
