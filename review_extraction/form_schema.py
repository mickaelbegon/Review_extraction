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
]

JOINT_ASSESSMENT = [*CHOICE_ASSESSMENT, "not_assessed"]
THORAX_ORIENTATION_DETAILS = ["z_up_convention", "other", "not_applicable", "not_reported"]
SEGMENT_CONSTRUCTION_DETAILS = [
    "body_or_segment_oriented",
    "articular_surface_oriented",
    "anatomical_landmarks",
    "geometrical_features",
    "other",
    "not_applicable",
    "not_reported",
]
HUMERUS_ISB_CONSTRUCTION_OPTION = ["isb_option_1", "isb_option_2", "not_defined", "not_applicable", "not_reported"]
JOINT_ROTATION_DETAILS = ["other_euler_sequence", "helical_angle", "other", "not_applicable", "not_reported"]
JOINT_TRANSLATION_DETAILS = ["distal_coordinate_system", "joint_coordinate_system", "other", "not_applicable", "not_reported"]


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
                    guidance="Answer yes only if the segment coordinate system or segment kinematics are clearly used.",
                ),
                ExtractionItem(
                    id=f"{segment}_axes_orientation",
                    theme=f"segment.{segment}",
                    question=f"How does the study define {segment} axes orientation relative to ISB recommendations?",
                    allowed_answers=CHOICE_ASSESSMENT,
                    guidance="Distinguish a global claim that ISB was followed from a reproducible segment-specific method.",
                ),
                ExtractionItem(
                    id=f"{segment}_axes_construction",
                    theme=f"segment.{segment}",
                    question=f"How does the study construct the {segment} coordinate system axes relative to ISB recommendations?",
                    allowed_answers=CHOICE_ASSESSMENT,
                    guidance="Check landmarks, cross-products, and anatomical/geometrical definitions. Ignore obvious typos if intent is clear.",
                ),
                ExtractionItem(
                    id=f"{segment}_axes_construction_details",
                    theme=f"segment.{segment}",
                    question=f"If the {segment} axes construction differs from ISB recommendations, which construction approach is used?",
                    allowed_answers=SEGMENT_CONSTRUCTION_DETAILS,
                    guidance="Select not_applicable when ISB recommendations were followed or the segment was not used. Select all supported alternatives when the method differs.",
                ),
                ExtractionItem(
                    id=f"{segment}_scs_origin",
                    theme=f"segment.{segment}",
                    question=f"How does the study define the {segment} SCS origin relative to ISB recommendations?",
                    allowed_answers=CHOICE_ASSESSMENT,
                    guidance="Look for the anatomical origin and whether it matches the ISB origin for this segment.",
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
                guidance="Use z_up_convention for the thorax Z-up convention described in the form. Use not_applicable when ISB recommendations were followed or thorax was not used.",
            ),
            ExtractionItem(
                id="humerus_axes_construction_isb_option",
                theme="segment.humerus",
                question="If humerus axes construction follows ISB recommendations, which humerus SCS option is used?",
                allowed_answers=HUMERUS_ISB_CONSTRUCTION_OPTION,
                guidance="Select option 1 or 2 only when clearly supported. Use not_defined when the paper follows ISB but does not specify the option.",
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
                    guidance="Answer yes only if this joint relationship is considered or reported.",
                ),
                ExtractionItem(
                    id=f"{joint_id}_rotations",
                    theme=f"joint.{joint_id}",
                    question=f"How are rotations computed for {label} relative to ISB recommendations?",
                    allowed_answers=JOINT_ASSESSMENT,
                    guidance=f"The ISB Euler sequence for this joint is {EXPECTED_EULER[joint_id]}. Verify the reported sequence or alternative method.",
                ),
                ExtractionItem(
                    id=f"{joint_id}_rotation_details",
                    theme=f"joint.{joint_id}",
                    question=f"If rotations for {label} differ from ISB recommendations, which rotation approach is used?",
                    allowed_answers=JOINT_ROTATION_DETAILS,
                    guidance="Use not_applicable when ISB recommendations were followed or rotations were not assessed. Select all supported alternatives when a different approach is described.",
                ),
                ExtractionItem(
                    id=f"{joint_id}_translations",
                    theme=f"joint.{joint_id}",
                    question=f"How are translations computed for {label} relative to ISB recommendations?",
                    allowed_answers=JOINT_ASSESSMENT,
                    guidance="Check whether translations are reported, in which coordinate system, or not assessed.",
                ),
                ExtractionItem(
                    id=f"{joint_id}_translation_details",
                    theme=f"joint.{joint_id}",
                    question=f"If translations for {label} differ from ISB recommendations, which coordinate system is used?",
                    allowed_answers=JOINT_TRANSLATION_DETAILS,
                    guidance="Use not_applicable when ISB recommendations were followed, translations are not defined by ISB, or translations were not assessed.",
                ),
            ]
        )

    return items


EXTRACTION_ITEMS = build_extraction_items()


def extraction_form_prompt(item_ids: set[str] | list[str] | None = None) -> str:
    selected_item_ids = set(item_ids) if item_ids is not None else None
    lines = [
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
