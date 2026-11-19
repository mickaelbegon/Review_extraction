from __future__ import annotations

from dataclasses import dataclass


CHOICE_ASSESSMENT = [
    "isb_explicit_method_aligned",
    "isb_explicit_no_method",
    "isb_explicit_method_inconsistent",
    "isb_not_explicit_method_aligned",
    "isb_not_followed_alternative_described",
    "isb_not_followed_alternative_cited",
    "no_method_or_reference",
    "i_dont_know",
]

JOINT_ASSESSMENT = [*CHOICE_ASSESSMENT, "not_assessed"]
THORAX_ORIENTATION_DETAILS = ["z_up_convention", "other", "not_applicable"]
SEGMENT_CONSTRUCTION_DETAILS = [
    "body_or_segment_oriented",
    "articular_surface_oriented",
    "anatomical_landmarks",
    "geometrical_features",
    "other",
    "not_applicable",
]
HUMERUS_ISB_CONSTRUCTION_OPTION = ["isb_option_1", "isb_option_2", "other", "not_applicable"]
JOINT_ROTATION_DETAILS = ["other_euler_sequence", "helical_angle", "other", "not_applicable"]
JOINT_TRANSLATION_DETAILS = ["distal_coordinate_system", "joint_coordinate_system", "other", "not_applicable"]


# Reviewer coding rules: "ISB shoulder kinematics - Data extraction guide", "ISB data extraction examples for
# reviewers" and the review team's decisions. Shown to the extractor before the form.
CODING_RULES = """Coding rules (ISB shoulder kinematics data extraction guide; apply to every item):

General
- Check segment by segment and joint by joint whether the information is clear enough to understand and reproduce the method. Code the system used for the analysis, including any anatomical calibration.
- Figures count as methodological descriptions when they unambiguously define the same coordinate system as the reported analysis. Consider supplementary methods. A measurement device or laboratory frame alone does not establish an anatomical segment coordinate system.
- An obvious, uniquely interpretable typographical error is NOT a methodological departure (e.g. a self-referential cross product may be read as the intended axis only when the intended expression is clear). An unresolved contradiction is recorded as i_dont_know.
- A general statement such as "ISB recommendations were followed" is an applicable explicit ISB claim for all assessed segment and joint items. If the statement concerns only particular methods (e.g. "joint rotations followed ISB"), it applies only to those. Never infer missing details from the statement.

Response categories (numbering is only a reading aid)
1 isb_explicit_method_aligned = "ISB recommendations explicitly stated, and method described and aligned with them": an applicable explicit claim AND an adequate, compatible description of this item.
2 isb_explicit_method_inconsistent = "ISB recommendations explicitly stated, but the method described is inconsistent with them": an applicable claim, but the described item departs from ISB. An intentional modification also belongs here.
3 isb_explicit_no_method = "ISB recommendations explicitly stated, but no method described": an applicable claim, but this item cannot be checked from the description or a defining figure.
4 isb_not_explicit_method_aligned = "ISB recommendations not explicitly stated, but method described and aligned with them".
5 isb_not_followed_alternative_described = "ISB recommendations not followed / not explicitly stated, and alternative method described": an alternative directly described without an applicable ISB claim.
6 isb_not_followed_alternative_cited = "ISB recommendations not followed / not explicitly stated, and alternative method cited": a methodological citation replaces a direct description. It records how the method is reported and does not establish disagreement; do not check the cited article.
7 no_method_or_reference = "No method described nor cited allowing to check if ISB recommendations were followed or not": the item is relevant but no usable description, figure, methodological citation or applicable ISB claim is supplied.
8 i_dont_know = "I don't know": the information cannot be interpreted consistently (e.g. text and figure conflict for the same system). Never for plain absence of reporting; explain it in rationale_short.
Joint only: not_assessed = the rotation or translation component was not analysed (different from an analysed component whose method is missing -> 7).

Segment coordinate systems (thorax, clavicle, scapula, humerus): evaluate orientation, construction and origin separately.
- Axes orientation: which anatomical direction and sign are assigned to X, Y and Z. A clearly wrong axis is a departure.
- Axes construction: landmarks, planes, fitted features or cross products used to build the axes. Orientation agreement alone does not establish construction agreement.
- SCS origin: the anatomical point defining the origin. Origin agreement does not establish agreement for the axes.
- <segment>_used = yes only once an axis (coordinate) system is constructed for that segment; a marker or sensor alone is not enough (e.g. a single sternal sensor without axes -> no).
- Optional segment details are filled ONLY when an alternative is directly described (main item = 2 or 5); otherwise not_applicable. Orientation: z_up_convention when X is anteroposterior, Y mediolateral and Z superoinferior; otherwise other, with the axis assignment and signs explained in rationale_short. Construction: select every applicable descriptor (body_or_segment_oriented, articular_surface_oriented, anatomical_landmarks, geometrical_features, other); they describe different aspects and can overlap (a landmark-defined body plane is body_or_segment_oriented AND anatomical_landmarks; a fitted glenoid plane is articular_surface_oriented AND geometrical_features).
- humerus_axes_construction_isb_option (isb_option_1 / isb_option_2 / other) reproduces the form's live condition as it is: complete it only when ISB was not followed but an alternative was described for the humerus axes construction (humerus_axes_construction = isb_not_followed_alternative_described); otherwise not_applicable. Do not add another completion rule.

Joint coordinate systems and motions
- <joint>_reported = no when neither rotations nor translations are reported for that relation; then its rotations and translations are not_assessed and its details not_applicable.
- Rotations: interpret sequence labels together with the segment axes orientation. A sequence with different axis letters may be the same decomposition if axes were relabelled consistently: judge equivalence after accounting for axis directions, signs and rotation order. Code segment axes orientation and rotation computation separately.
- Translations: check both the tracked point and the reference axes (e.g. glenohumeral: point GH and the scapular axes). A proximal frame alone is insufficient when the tracked point or the frame definition is unclear.
- Optional rotation/translation details are filled ONLY for a directly described departure (main item = 2 or 5); otherwise not_applicable. Rotations: other_euler_sequence (e.g. X-Z-Y for glenohumeral), helical_angle (finite helical axis and angle), other. Translations: distal_coordinate_system (e.g. humeral axes for glenohumeral motion), joint_coordinate_system, other (explain the tracked point and frame in rationale_short).
- Method comparison: if the study compares methods and ISB is among the methods tested, code it as ISB (data can then be expressed according to ISB).
- If several methods are reported, state which one each answer concerns.

Study metadata
- number_shoulders: number of shoulders actually measured (1 per participant when only one side is measured); NR only when it cannot be determined."""


@dataclass(frozen=True)
class ExtractionItem:
    id: str
    theme: str
    question: str
    allowed_answers: list[str]
    guidance: str


SEGMENTS = ["thorax", "clavicle", "scapula", "humerus"]

JOINTS = {
    "thorax_global": "Thorax relative to the global coordinate system",
    "clavicle_thorax": "Clavicle relative to thorax",
    "scapula_clavicle": "Scapula relative to clavicle",
    "scapula_thorax": "Scapula relative to thorax",
    "humerus_scapula": "Humerus relative to scapula",
    "humerus_thorax": "Humerus relative to thorax",
}

EXPECTED_EULER = {
    "thorax_global": "Z-X-Y",
    "clavicle_thorax": "Y-X-Z",
    "scapula_clavicle": "Y-X-Z",
    "scapula_thorax": "Y-X-Z",
    "humerus_scapula": "Y-X-Y",
    "humerus_thorax": "Y-X-Y",
}


def build_extraction_items() -> list[ExtractionItem]:
    items: list[ExtractionItem] = [
        ExtractionItem(
            id="measurement_methods",
            theme="measurement_methods",
            question="Which measurement methods are used in the study?",
            allowed_answers=[
                "skin_markers_3d_optical",
                "skin_markers_2d_video",
                "skin_magnetic_tracking",
                "skin_imu",
                "bone_pins_3d_optical",
                "bone_pins_2d_video",
                "bone_pins_magnetic_tracking",
                "bone_pins_imu",
                "sensorless_multiple_cameras",
                "sensorless_single_camera",
                "single_plane_fluoroscopy_ct_mri",
                "biplane_fluoroscopy_ct_mri",
                "dynamic_ct_4dct",
                "dynamic_mri",
                "ultrasound_ct_mri",
                "other",
                "not_reported",
            ],
            guidance="Select all methods supported by explicit evidence.",
        )
    ]

    for segment in SEGMENTS:
        items.extend(
            [
                ExtractionItem(
                    id=f"{segment}_used",
                    theme=f"segment.{segment}",
                    question=f"Was the {segment} segment considered in the study?",
                    allowed_answers=["yes", "no", "unclear"],
                    guidance="Answer yes only once an axis (coordinate) system is constructed for the segment; a sensor or marker alone is not enough.",
                ),
                ExtractionItem(
                    id=f"{segment}_axes_orientation",
                    theme=f"segment.{segment}",
                    question=f"How does the study define {segment} axes orientation relative to ISB recommendations?",
                    allowed_answers=CHOICE_ASSESSMENT,
                    guidance="Which anatomical direction and sign are assigned to X, Y and Z for this segment. A clearly wrong axis is a departure. A general ISB statement is an applicable claim; check whether this item is described.",
                ),
                ExtractionItem(
                    id=f"{segment}_axes_construction",
                    theme=f"segment.{segment}",
                    question=f"How does the study construct the {segment} coordinate system axes relative to ISB recommendations?",
                    allowed_answers=CHOICE_ASSESSMENT,
                    guidance="Landmarks, planes, fitted features or cross products used to build the axes. Orientation agreement alone does not establish construction agreement. An obvious, uniquely interpretable typo is not a departure.",
                ),
                ExtractionItem(
                    id=f"{segment}_axes_construction_details",
                    theme=f"segment.{segment}",
                    question=f"If the {segment} axes construction differs from ISB recommendations, which construction approach is used?",
                    allowed_answers=SEGMENT_CONSTRUCTION_DETAILS,
                    guidance="Fill only when an alternative construction is directly described (axes construction = category 2 or 5): select all applicable descriptors (they can overlap). Otherwise not_applicable.",
                ),
                ExtractionItem(
                    id=f"{segment}_scs_origin",
                    theme=f"segment.{segment}",
                    question=f"How does the study define the {segment} SCS origin relative to ISB recommendations?",
                    allowed_answers=CHOICE_ASSESSMENT,
                    guidance="Look for the anatomical origin and whether it matches the ISB origin for this segment. Origin agreement does not establish agreement for the axes.",
                ),
            ]
        )

    items.extend(
        [
            ExtractionItem(
                id="thorax_axes_orientation_details",
                theme="segment.thorax",
                question="If thorax axes orientation differs from ISB recommendations, which orientation convention is used?",
                allowed_answers=THORAX_ORIENTATION_DETAILS,
                guidance="Fill only when an alternative orientation is directly described (thorax axes orientation = category 2 or 5): z_up_convention when X is anteroposterior, Y mediolateral and Z superoinferior; otherwise other (explain axes and signs). Otherwise not_applicable.",
            ),
            ExtractionItem(
                id="humerus_axes_construction_isb_option",
                theme="segment.humerus",
                question="Axes construction (optional): SCS Option 1 from the ISB recommendations, SCS Option 2 from the ISB recommendations, or Other?",
                allowed_answers=HUMERUS_ISB_CONSTRUCTION_OPTION,
                guidance="Live condition reproduced as in the form: complete only when ISB was not followed but an alternative was described (humerus_axes_construction = isb_not_followed_alternative_described). Otherwise not_applicable.",
            ),
        ]
    )

    for joint_id, label in JOINTS.items():
        items.extend(
            [
                ExtractionItem(
                    id=f"{joint_id}_reported",
                    theme=f"joint.{joint_id}",
                    question=f"Are joint kinematics reported for {label}?",
                    allowed_answers=["yes", "no", "unclear"],
                    guidance="No if neither rotations nor translations are reported for this relation (then rotations/translations = not_assessed, details = not_applicable).",
                ),
                ExtractionItem(
                    id=f"{joint_id}_rotations",
                    theme=f"joint.{joint_id}",
                    question=f"How are rotations computed for {label} relative to ISB recommendations?",
                    allowed_answers=JOINT_ASSESSMENT,
                    guidance=f"The ISB Euler sequence for this joint is {EXPECTED_EULER[joint_id]}. Interpret sequence letters with the segment axes: a relabelled but equivalent decomposition (axis directions, signs, order) agrees with ISB. Use not_assessed if rotations were not analysed. If methods are compared and ISB is one of them, code ISB.",
                ),
                ExtractionItem(
                    id=f"{joint_id}_rotation_details",
                    theme=f"joint.{joint_id}",
                    question=f"If rotations for {label} differ from ISB recommendations, which rotation approach is used?",
                    allowed_answers=JOINT_ROTATION_DETAILS,
                    guidance="Fill only for a directly described departure (rotations = category 2 or 5): select all that apply (other_euler_sequence e.g. X-Z-Y for glenohumeral; helical_angle for a finite helical axis and angle; other). Otherwise not_applicable.",
                ),
                ExtractionItem(
                    id=f"{joint_id}_translations",
                    theme=f"joint.{joint_id}",
                    question=f"How are translations computed for {label} relative to ISB recommendations?",
                    allowed_answers=JOINT_ASSESSMENT,
                    guidance="Check both the tracked point and the reference axes (glenohumeral example: point GH relative to the scapula, along the scapular axes). A proximal frame alone is insufficient when the point or frame definition is unclear. Use not_assessed if translations were not analysed.",
                ),
                ExtractionItem(
                    id=f"{joint_id}_translation_details",
                    theme=f"joint.{joint_id}",
                    question=f"If translations for {label} differ from ISB recommendations, which coordinate system is used?",
                    allowed_answers=JOINT_TRANSLATION_DETAILS,
                    guidance="Fill only for a directly described departure (translations = category 2 or 5): select all that apply (distal_coordinate_system e.g. humeral axes for glenohumeral; joint_coordinate_system; other, explaining point and frame). Otherwise not_applicable.",
                ),
            ]
        )

    return items


EXTRACTION_ITEMS = build_extraction_items()


def extraction_form_prompt(item_ids: set[str] | list[str] | None = None) -> str:
    selected_item_ids = set(item_ids) if item_ids is not None else None
    lines = [
        CODING_RULES,
        "",
        "Use this systematic-review extraction form.",
        "Return one answer per item. Use only allowed answer identifiers.",
        "If evidence is missing or ambiguous, prefer 'unclear', 'no_method_or_reference', or 'not_assessed' over guessing.",
        "",
    ]
    for item in EXTRACTION_ITEMS:
        if selected_item_ids is not None and item.id not in selected_item_ids:
            continue
        lines.append(f"- {item.id}: {item.question}")
        lines.append(f"  Allowed answers: {', '.join(item.allowed_answers)}")
        lines.append(f"  Guidance: {item.guidance}")
    return "\n".join(lines)


def extraction_plan_prompt() -> str:
    lines = [
        "Decide which extraction blocks are relevant for this paper before detailed extraction.",
        "Return one decision for every theme listed below.",
        "Use status 'present' when the theme is clearly reported, 'absent' when it is clearly not reported, and 'unclear' when evidence is ambiguous or incomplete.",
        "When uncertain, prefer 'unclear' so the detailed extractor will inspect that block.",
        "",
        "Themes:",
        "- measurement_methods: any measurement/capture method used by the study",
    ]
    for segment in SEGMENTS:
        lines.append(f"- segment.{segment}: whether the {segment} segment coordinate system or kinematics are considered")
    for joint_id, label in JOINTS.items():
        lines.append(f"- joint.{joint_id}: whether joint kinematics are reported for {label}")
    return "\n".join(lines)


# Main item -> optional details item. Details are filled only for a directly described departure/alternative.
DETAIL_PARENTS = {
    **{f"{s}_axes_construction_details": f"{s}_axes_construction" for s in SEGMENTS},
    "thorax_axes_orientation_details": "thorax_axes_orientation",
    **{f"{j}_rotation_details": f"{j}_rotations" for j in JOINTS},
    **{f"{j}_translation_details": f"{j}_translations" for j in JOINTS},
}
DEPARTURE_DESCRIBED = {"isb_explicit_method_inconsistent", "isb_not_followed_alternative_described"}


def consistency_errors(answers: dict[str, str | list[str]]) -> list[str]:
    """Conditional rules of the reviewer guide that can be checked mechanically."""

    def values(item_id: str) -> list[str]:
        value = answers.get(item_id, [])
        return value if isinstance(value, list) else [value]

    errors: list[str] = []
    for detail, parent in DETAIL_PARENTS.items():
        chosen = values(detail)
        departure = bool(set(values(parent)) & DEPARTURE_DESCRIBED)
        if "not_applicable" in chosen and len(chosen) > 1:
            errors.append(f"{detail}: not_applicable cannot be combined with other options")
        if departure and chosen == ["not_applicable"]:
            errors.append(f"{detail}: {parent} describes a departure (category 2 or 5), so tick the applicable details (or other)")
        if not departure and chosen != ["not_applicable"]:
            errors.append(f"{detail}: must be not_applicable because {parent} is not category 2 or 5")
    humerus_alternative = values("humerus_axes_construction") == ["isb_not_followed_alternative_described"]
    option = values("humerus_axes_construction_isb_option")
    if humerus_alternative and option == ["not_applicable"]:
        errors.append("humerus_axes_construction_isb_option: must be answered when humerus_axes_construction = isb_not_followed_alternative_described")
    if not humerus_alternative and option != ["not_applicable"]:
        errors.append("humerus_axes_construction_isb_option: must be not_applicable unless humerus_axes_construction = isb_not_followed_alternative_described")
    for joint in JOINTS:
        if values(f"{joint}_reported") == ["no"]:
            for part in ("rotations", "translations"):
                if values(f"{joint}_{part}") != ["not_assessed"]:
                    errors.append(f"{joint}_{part}: must be not_assessed because {joint}_reported = no")
        elif values(f"{joint}_reported") == ["yes"] and values(f"{joint}_rotations") == values(f"{joint}_translations") == ["not_assessed"]:
            errors.append(f"{joint}_reported = yes but both rotations and translations are not_assessed")
    return errors
