from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreeningCriterion:
    id: str
    theme: str
    include: str
    exclude: str
    guidance: str


SCREENING_CRITERIA = [
    ScreeningCriterion(
        id="population",
        theme="Population",
        include="Healthy and non-healthy human populations.",
        exclude="Animal studies.",
        guidance="Include human participant or patient studies. Exclude non-human animal studies.",
    ),
    ScreeningCriterion(
        id="outcome",
        theme="Outcome",
        include="Shoulder kinematics or shoulder posture.",
        exclude="Upper limb kinematics without shoulder outcomes, such as carpal, wrist, or elbow only.",
        guidance="Look for shoulder-specific kinematics, posture, movement, or coordinate systems.",
    ),
    ScreeningCriterion(
        id="study_design",
        theme="Study design",
        include="Prospective primary research.",
        exclude="Reviews, retrospective/secondary analysis, and conference proceedings.",
        guidance="Exclude review articles, conference proceedings, and secondary or retrospective analyses.",
    ),
    ScreeningCriterion(
        id="language",
        theme="Other",
        include="English only.",
        exclude="N/A.",
        guidance="Include English full papers. Mark unclear when language cannot be inferred from the full paper text.",
    ),
]


def screening_prompt() -> str:
    lines = [
        "Screen the full paper before detailed extraction.",
        "Evaluate each inclusion/exclusion criterion independently using only the full paper text.",
        "Return 'exclude' for a criterion when an exclusion rule is clearly met.",
        "Return 'include' for a criterion when the inclusion rule is clearly met and no exclusion rule is met.",
        "Return 'unclear' when the full paper text does not provide enough evidence.",
        "Overall decision rules:",
        "- overall_decision='exclude' if any criterion is clearly excluded.",
        "- overall_decision='include' only if all criteria are included.",
        "- overall_decision='uncertain' otherwise.",
        "",
    ]
    for criterion in SCREENING_CRITERIA:
        lines.append(f"- {criterion.id} ({criterion.theme})")
        lines.append(f"  Include: {criterion.include}")
        lines.append(f"  Exclude: {criterion.exclude}")
        lines.append(f"  Guidance: {criterion.guidance}")
    return "\n".join(lines)
