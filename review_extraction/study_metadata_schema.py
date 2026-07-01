from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudyMetadataItem:
    id: str
    label: str
    coding: str
    guidance: str


STUDY_METADATA_ITEMS = [
    StudyMetadataItem("study_id", "Study ID", "FirstAuthorYear, e.g. Ludewig2009", "Build from first author surname and publication year."),
    StudyMetadataItem("first_author", "First author", "Text", "Surname of the first author."),
    StudyMetadataItem("year", "Year", "YYYY", "Publication year."),
    StudyMetadataItem("title", "Title", "Text", "Article title."),
    StudyMetadataItem("journal", "Journal", "Text", "Journal or source title."),
    StudyMetadataItem("doi", "DOI", "DOI / NR", "Use NR if no DOI is reported."),
    StudyMetadataItem(
        "study_design_purpose",
        "Study design / study purpose",
        "Methodological / validation / experimental / clinical / normative / modelling / other",
        "Choose the closest category and include a short descriptor if needed.",
    ),
    StudyMetadataItem("country_data_collection", "Country of data collection", "Country / multicountry / NR", "Prefer Methods or Participants evidence over affiliation."),
    StudyMetadataItem(
        "country_source",
        "Source used to identify country",
        "Methods / participants / institution / affiliation only / unclear",
        "Record where the country inference came from.",
    ),
    StudyMetadataItem("population_type", "Population type", "Healthy / pathological / cadaveric / model / mixed", "Use mixed when multiple population types are studied."),
    StudyMetadataItem("condition_studied", "Condition studied", "Healthy / rotator cuff tear / instability / stroke / OA / other / NR", "Use NR if not reported."),
    StudyMetadataItem("number_participants", "Number of participants", "n / NR", "Extract the participant count as reported."),
    StudyMetadataItem("number_shoulders", "Number of shoulders", "n shoulders / NR", "Extract shoulder count when reported separately."),
    StudyMetadataItem("age", "Age", "Mean +/- SD / range / age group / NR", "Preserve the reported age format."),
    StudyMetadataItem("sex_distribution", "Sex distribution", "n female, n male / % / NR", "Preserve counts or percentages as reported."),
    StudyMetadataItem("side_studied", "Side studied", "Right / left / both / dominant / non-dominant / NR", "Use NR if side is not reported."),
    StudyMetadataItem(
        "movement_task",
        "Movement or task studied",
        "Elevation / abduction / flexion / functional task / other",
        "Summarize the main movement or task.",
    ),
    StudyMetadataItem("active_passive", "Active or passive movement", "Active / passive / assisted / imposed / NR", "Choose the movement control category."),
    StudyMetadataItem("main_plane", "Main plane of movement", "Sagittal / frontal / scapular / multiple / free / NR", "Use multiple/free when more appropriate than a single plane."),
    StudyMetadataItem("isb_recommendation_cited", "ISB recommendation cited", "Yes / No / unclear", "Whether ISB recommendations are cited or explicitly mentioned."),
    StudyMetadataItem("data_availability", "Data availability", "None / supplementary material / repository / on request / NR", "Extract any data sharing statement."),
]


def study_metadata_prompt() -> str:
    lines = [
        "Extract study-level metadata for a systematic review.",
        "Return exactly one field for every requested field_id. Use NR when information is not reported.",
        "Use short values that can fit in a spreadsheet. Include evidence quotes when available.",
        "",
        "Fields:",
    ]
    for item in STUDY_METADATA_ITEMS:
        lines.append(f"- {item.id}: {item.label}")
        lines.append(f"  Recommended coding: {item.coding}")
        lines.append(f"  Guidance: {item.guidance}")
    return "\n".join(lines)


def metadata_labels() -> dict[str, str]:
    return {item.id: item.label for item in STUDY_METADATA_ITEMS}
